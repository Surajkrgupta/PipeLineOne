"""Deletes local media files (video, thumbnail, and the whole per-run
working directory) roughly 24 hours after a run finishes, while keeping the
PipelineRun database row forever as the permanent historical record
(problem title, difficulty, YouTube link, duration, theme/voice used, date).

Runs still in progress (fetched/generated/rendered/awaiting_approval/
uploading) are never touched -- only terminal states (uploaded/rejected/
failed) are eligible, and only once they're older than the cutoff.
"""

import os
import shutil
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import PipelineRun, RunStatus

TERMINAL_STATUSES = [RunStatus.uploaded, RunStatus.rejected, RunStatus.failed]


def cleanup_old_run_files(db: Session, hours: int = 24) -> int:
    """Deletes the run directory for any terminal-state run older than
    `hours`, whose files haven't already been cleaned up. Returns the count
    of runs cleaned in this pass."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    candidates = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.status.in_(TERMINAL_STATUSES),
            PipelineRun.created_at < cutoff,
            PipelineRun.files_deleted_at.is_(None),
        )
        .all()
    )

    cleaned_count = 0
    for run in candidates:
        run_dir = os.path.join(settings.output_dir, f"run_{run.id}")
        try:
            if os.path.isdir(run_dir):
                shutil.rmtree(run_dir)
                print(f"[cleanup] Deleted files for run #{run.id} ({run_dir})")
            else:
                print(f"[cleanup] Run #{run.id} directory already gone -- marking cleaned anyway")

            run.video_path = None
            run.thumbnail_path = None
            run.files_deleted_at = datetime.utcnow()
            db.commit()
            cleaned_count += 1
        except Exception as e:
            print(f"[cleanup] Failed to clean run #{run.id}: {e}")
            db.rollback()

    return cleaned_count