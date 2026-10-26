from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    requirement: str = ""


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class ChangeRequest(BaseModel):
    feedback: str = Field(min_length=1, max_length=20000)
