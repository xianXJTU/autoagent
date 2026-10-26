from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SKILL_CATEGORIES = ("user", "project", "domain", "generic")


class SkillValidationError(ValueError):
    pass


class SkillMeta(BaseModel):
    name: str = Field(min_length=1)
    version: str = "1.0.0"
    description: str = Field(min_length=1)
    language: str = "python"
    category: Literal["user", "project", "domain", "generic"] = "domain"
    tags: list[str] = Field(default_factory=list)
    decision_points: dict[str, str] = Field(default_factory=dict)
    applies_when: str = ""

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError("技能名称不能为空且不能包含路径分隔符")
        return cleaned


class SkillDocument(BaseModel):
    meta: SkillMeta
    body: str = ""
    path: Path

    def embedding_text(self) -> str:
        points = "；".join(f"{key}={value}" for key, value in self.meta.decision_points.items())
        return "\n".join(
            part
            for part in (
                self.meta.description,
                self.meta.applies_when,
                "标签：" + "、".join(self.meta.tags) if self.meta.tags else "",
                "决策点：" + points if points else "",
                self.body[:800],
            )
            if part
        )
