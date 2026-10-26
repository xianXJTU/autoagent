"""数据库实体。

第一版使用 MySQL 8；JSON 字段用于保存结构化事件与规格，避免过早拆表。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="对齐中", index=True
    )
    workspace_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    current_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="对齐中")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    budget_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str] = mapped_column(String(64), default=new_id, nullable=False)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_project_created", "project_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE")
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "kind", "version", name="uq_documents_project_kind_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE")
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Module(TimestampMixin, Base):
    __tablename__ = "modules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="待开始")
    worktree_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    branch: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    owner_agent: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_events_run_seq"),
        Index("ix_events_run_seq", "run_id", "seq"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE")
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Memory(TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_layer_status", "layer", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_hit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    embedding_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="python")
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    decision_points_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    applies_when: Mapped[str] = mapped_column(Text, nullable=False, default="")
    path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class SkillUsage(Base):
    __tablename__ = "skill_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id", ondelete="CASCADE")
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class TestResult(Base):
    __tablename__ = "tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    case_name: Mapped[str] = mapped_column(String(300), nullable=False)
    script_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    judge: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ModelCall(Base):
    __tablename__ = "model_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool: Mapped[str] = mapped_column(String(100), nullable=False)
    args_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    result_digest: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
