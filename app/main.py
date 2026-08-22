from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.models import PipelineRun, RunStatus
from app.pipelines.dsa_pipeline import approve_and_upload, run_dsa_pipeline_safe
from app.scheduler import start_scheduler
from app.schemas import PipelineRunOut, TriggerResponse

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()  # kicks off the daily cron job in the background
    yield


app = FastAPI(title="DSA POTD → YouTube Pipeline", lifespan=lifespan)


def _run_pipeline_task():
    db = SessionLocal()
    try:
        run_dsa_pipeline_safe(db)
    finally:
        db.close()


@app.post("/run/dsa-pipeline", response_model=TriggerResponse)
def trigger_pipeline(background_tasks: BackgroundTasks):
    """Manually trigger today's pipeline run immediately instead of waiting
    for the scheduled time. Runs in the background so the request returns fast."""
    background_tasks.add_task(_run_pipeline_task)
    return TriggerResponse(run_id=0, status="started", message="Pipeline run triggered in background.")


@app.get("/runs", response_model=list[PipelineRunOut])
def list_runs(db: Session = Depends(get_db)):
    return db.query(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(30).all()


@app.get("/runs/{run_id}", response_model=PipelineRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/approve/{run_id}", response_model=PipelineRunOut)
def approve_run(run_id: int, db: Session = Depends(get_db)):
    """Call this after reviewing the rendered video (see video_path from
    GET /runs/{run_id}) to publish it to YouTube."""
    run = db.query(PipelineRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != RunStatus.awaiting_approval:
        raise HTTPException(status_code=400, detail=f"Run is in status '{run.status}', not awaiting approval")

    return approve_and_upload(db, run)


from app.services import notifier


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/test-telegram")
def test_telegram():
    """Sends a test message to verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    are configured correctly. Check your Telegram chat after calling this."""
    notifier.notify("✅ Telegram notifications are working correctly for the DSA pipeline.")
    return {"status": "sent", "note": "Check your Telegram chat. If nothing arrived, verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set."}
