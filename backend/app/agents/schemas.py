from __future__ import annotations

from pydantic import BaseModel, Field


class Question(BaseModel):
    question: str
    recommendation: str = ""
    reason: str = ""
    options: list[str] = Field(default_factory=list)


class AlignmentQuestions(BaseModel):
    questions: list[Question] = Field(default_factory=list)


class PlanModule(BaseModel):
    name: str
    description: str
    files: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)


class PlanDraft(BaseModel):
    modules: list[PlanModule] = Field(default_factory=list)
    interfaces: str = ""
    acceptance_map: dict[str, str] = Field(default_factory=dict)


class FileDraft(BaseModel):
    path: str
    content: str


class CodeDraft(BaseModel):
    files: list[FileDraft] = Field(default_factory=list)
    notes: str = ""


class TestDraft(BaseModel):
    files: list[FileDraft] = Field(default_factory=list)


class ReviewVerdict(BaseModel):
    passed: bool
    score: int = Field(default=0, ge=0, le=4)
    issues: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DimensionScore(BaseModel):
    dimension: str
    score: int = Field(ge=0, le=4)
    evidence: list[str] = Field(default_factory=list)
    issue: str = ""


class EvaluationDraft(BaseModel):
    dimensions: list[DimensionScore] = Field(default_factory=list)
    summary: str = ""
