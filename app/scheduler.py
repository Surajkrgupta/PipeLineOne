from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.pipelines.dsa_pipeline import run_dsa_pipeline_safe

scheduler = BackgroundScheduler()


def _scheduled_dsa_job():
    db = SessionLocal()
    try:
        run_dsa_pipeline_safe(db)
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        _scheduled_dsa_job,
        trigger=CronTrigger(hour=settings.daily_run_hour, minute=settings.daily_run_minute),
        id="daily_dsa_pipeline",
        replace_existing=True,
    )
    scheduler.start()
