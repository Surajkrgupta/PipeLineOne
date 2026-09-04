from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import PipelineRun, RunStatus
from app.pipelines.dsa_pipeline import approve_and_upload, create_test_approval_request, reject_run, run_dsa_pipeline_safe
from app.scheduler import start_scheduler
from app.schemas import PipelineRunOut, TriggerResponse
from app.services import notifier
from app.services.cleanup import cleanup_old_run_files
from app.startup import restore_youtube_secrets

Base.metadata.create_all(bind=engine)
restore_youtube_secrets()


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
    GET /runs/{run_id}) to publish it to YouTube. Manual HTTP fallback --
    normally you'll use the Telegram Approve button instead."""
    run = db.query(PipelineRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != RunStatus.awaiting_approval:
        raise HTTPException(status_code=400, detail=f"Run is in status '{run.status}', not awaiting approval")

    return approve_and_upload(db, run)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/test-telegram")
def test_telegram():
    """Sends a test message to verify TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    are configured correctly. Returns the REAL outcome -- check the 'sent'
    field, not just that this endpoint returned 200."""
    result = notifier.notify("✅ Telegram notifications are working correctly for the DSA pipeline.")
    return result


@app.get("/test-network")
def test_network():
    """Diagnostic: tests raw outbound HTTPS connectivity to Groq's API,
    completely bypassing the Groq SDK. This isolates whether a failure is a
    genuine network/DNS/TLS problem on this host, versus something specific
    to how the SDK builds its client."""
    import httpx
    results = {}
    for name, url in [
        ("groq_api", "https://api.groq.com"),
        ("general_internet", "https://www.google.com"),
    ]:
        try:
            resp = httpx.get(url, timeout=10.0, trust_env=False)
            results[name] = {"reachable": True, "status_code": resp.status_code}
        except Exception as e:
            cause = f" (cause: {type(e.__cause__).__name__}: {e.__cause__})" if e.__cause__ else ""
            results[name] = {"reachable": False, "error": f"{type(e).__name__}: {e}{cause}"}
    return results


@app.post("/test-approval-flow", response_model=PipelineRunOut)
def test_approval_flow(db: Session = Depends(get_db)):
    """Sends a fake Telegram approval request (dummy title/duration/theme)
    without running the real pipeline. Use this to verify the Approve/Reject
    buttons and webhook are wired correctly. Tapping Approve marks it
    'uploaded' with a fake video ID -- no real YouTube upload happens."""
    return create_test_approval_request(db)


@app.post("/cleanup")
def trigger_cleanup(hours: int = 24, db: Session = Depends(get_db)):
    """Manually triggers the file-cleanup pass instead of waiting for the
    hourly scheduled job. Useful for testing -- pass ?hours=0 to clean up
    everything eligible regardless of age."""
    count = cleanup_old_run_files(db, hours=hours)
    return {"cleaned_runs": count}


def _upload_after_approval_task(run_id: int, callback_query_id: str):
    """Background task: performs the actual YouTube upload after an Approve
    tap, then edits the Telegram message with the final result. Runs in the
    background because uploads can take longer than Telegram's webhook
    response timeout allows."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if not run:
            return
        try:
            approve_and_upload(db, run)
        except Exception as e:
            print(f"[telegram-webhook] Upload failed for run #{run_id}: {e}")
            if run.telegram_chat_id and run.telegram_message_id:
                notifier.edit_message(
                    run.telegram_chat_id, run.telegram_message_id,
                    f"⚠️ Upload failed\n\n{run.problem_title}\n\nError: {e}"
                )
    finally:
        db.close()


@app.post("/telegram-webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Receives Telegram updates -- specifically, taps on the Approve/Reject
    buttons sent by notifier.send_approval_request. Must respond quickly
    (Telegram expects a fast 200 OK), so the actual upload runs as a
    background task rather than blocking this request."""
    if settings.telegram_webhook_secret:
        incoming_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if incoming_secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    update = await request.json()
    callback_query = update.get("callback_query")
    if not callback_query:
        return {"ok": True}

    callback_id = callback_query["id"]
    data = callback_query.get("data", "")

    try:
        action, run_id_str = data.split(":")
        run_id = int(run_id_str)
    except (ValueError, IndexError):
        notifier.answer_callback_query(callback_id, "Invalid button data")
        return {"ok": True}

    run = db.query(PipelineRun).filter_by(id=run_id).first()
    if not run:
        notifier.answer_callback_query(callback_id, "Run not found")
        return {"ok": True}

    if run.status != RunStatus.awaiting_approval:
        notifier.answer_callback_query(callback_id, f"Already handled (status: {run.status})")
        return {"ok": True}

    if action == "approve":
        notifier.answer_callback_query(callback_id, "Uploading to YouTube...")
        if run.telegram_chat_id and run.telegram_message_id:
            notifier.edit_message(
                run.telegram_chat_id, run.telegram_message_id,
                f"⏳ Uploading...\n\n{run.problem_title}", remove_buttons=True
            )
        background_tasks.add_task(_upload_after_approval_task, run_id, callback_id)

    elif action == "reject":
        notifier.answer_callback_query(callback_id, "Rejected")
        reject_run(db, run)

    else:
        notifier.answer_callback_query(callback_id, "Unknown action")

    return {"ok": True}