import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text

from app.database import Base


class RunStatus(str, enum.Enum):
    fetched = "fetched"
    generated = "generated"
    rendered = "rendered"
    awaiting_approval = "awaiting_approval"
    uploading = "uploading"
    uploaded = "uploaded"
    failed = "failed"


class PipelineRun(Base):
    """One row per daily POTD run. Tracks progress through each stage so a
    failed run can be inspected or retried without redoing completed steps."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    problem_slug = Column(String, unique=True, index=True)  # e.g. "two-sum" -- prevents duplicate posts
    problem_title = Column(String)
    difficulty = Column(String)

    status = Column(Enum(RunStatus), default=RunStatus.fetched)
    error_message = Column(Text, nullable=True)

    script_text = Column(Text, nullable=True)      # LLM-generated narration script
    solution_code = Column(Text, nullable=True)     # LLM-generated code
    video_path = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    youtube_video_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
