import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, Integer, String, Text

from app.database import Base


class RunStatus(str, enum.Enum):
    fetched = "fetched"
    generated = "generated"
    rendered = "rendered"
    awaiting_approval = "awaiting_approval"
    uploading = "uploading"
    uploaded = "uploaded"
    rejected = "rejected"
    failed = "failed"


class PipelineRun(Base):
    """One row per daily POTD run. Tracks progress through each stage so a
    failed run can be inspected or retried without redoing completed steps.

    Local media files (video_path, thumbnail_path) are deleted ~24h after
    the run reaches a terminal state (uploaded/rejected/failed) by
    app/services/cleanup.py -- this row's metadata is kept permanently as
    the historical record, even after the files themselves are gone."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    problem_slug = Column(String, unique=True, index=True)  # e.g. "two-sum" -- prevents duplicate posts
    problem_title = Column(String)
    difficulty = Column(String)

    status = Column(Enum(RunStatus), default=RunStatus.fetched)
    error_message = Column(Text, nullable=True)

    script_text = Column(Text, nullable=True)      # LLM-generated narration script
    solution_code = Column(Text, nullable=True)     # LLM-generated code
    video_path = Column(String, nullable=True)      # cleared to NULL once files are cleaned up
    thumbnail_path = Column(String, nullable=True)  # cleared to NULL once files are cleaned up
    video_duration_seconds