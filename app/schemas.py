from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PipelineRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    problem_slug: str
    problem_title: str
    difficulty: str | None
    status: str
    error_message: str | None
    youtube_video_id: str | None
    created_at: datetime
    updated_at: datetime


class TriggerResponse(BaseModel):
    run_id: int
    status: str
    message: str
