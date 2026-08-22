from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.pipelines.dsa_pipeline import run_dsa_pipeline_safe
from app.services.cleanup import cleanup_old_run_files

scheduler = BackgroundScheduler()


def _scheduled_dsa_job():
    db = SessionLocal()
    try:
        run_dsa_pipeline_safe(db)
    finally:
        db.close()


def _scheduled_cleanup_job():
    db = SessionLocal()
    try:
        count = cleanup_old_run_files(db, hours=24)
        if count:
            print(f"[scheduler] Cleanup pass removed files for {count} run(s)")
    except Exception as e:
        print(f"[scheduler] Cleanup job failed: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        _scheduled_dsa_job,
        trigger=CronTrigger(hour=settings.daily_run_hour, minute=settings.daily_run_minute),
        id="daily_dsa_pipeline",
        replace_existing=True,
    )
    scheduler.add_job(
        _scheduled_cleanup_job,
        trigger=IntervalTrigger(hours=1),
        id="hourly_file_cleanup",
        replace_existing=True,
    )
    scheduler.start()