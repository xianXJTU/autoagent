from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    run_id: str
    seq: int
    type: str
    stage: str = ""
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


def format_sse(event: EventOut) -> str:
    data = event.model_dump_json()
    return f"id: {event.seq}\ndata: {data}\n\n"
