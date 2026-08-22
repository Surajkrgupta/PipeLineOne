import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, Integer, String, Text

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
    video_duration_seconds = Column(Float, nullable=True)
    theme_name = Column(String, nullable=True)
    voice_name = Column(String, nullable=True)
    youtube_video_id = Column(String, nullable=True)

    # Telegram approval message tracking -- needed so the webhook handler can
    # edit the original message (e.g. remove buttons, show the final result)
    # after the person taps Approve/Reject.
    telegram_chat_id = Column(String, nullable=True)
    telegram_message_id = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)