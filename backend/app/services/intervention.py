"""运行中途的用户干预。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Document, Message, Project, Run
from ..events.service import EventService
from ..memory.service import MemoryService


class InterventionType(str, Enum):
    SUPPLEMENT = "supplement"
    SCOPE_CHANGE = "scope_change"
    OVERTHROW = "overthrow"


_OVERTHROW_WORDS = ["推翻", "重新开始", "全部重来", "不要了", "从头再来"]
_SCOPE_WORDS = ["改成", "改为", "增加", "删除", "去掉", "换成", "调整", "加一个", "减一个"]


def classify_intervention(text: str) -> InterventionType:
    if any(word in text for word in _OVERTHROW_WORDS):
        return InterventionType.OVERTHROW
    if any(word in text for word in _SCOPE_WORDS):
        return InterventionType.SCOPE_CHANGE
    return InterventionType.SUPPLEMENT


class InterventionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        events: EventService,
        memory: MemoryService | None = None,
        orchestrator: Any | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.events = events
        self.memory = memory
        self.orchestrator = orchestrator

    async def handle(
        self, project_id: str, run_id: str, text: str
    ) -> dict[str, Any]:
        kind = classify_intervention(text)
        self._add_message(project_id, run_id, text, kind.value)

        if kind is InterventionType.SUPPLEMENT:
            if self.memory is not None:
                await self.memory.record_project_decision(
                    "运行中的补充说明：" + text, f"message:{run_id}", project_id
                )
            await self.events.emit(
                run_id, "intervention.supplement", stage=self._stage(run_id),
                payload={"text": text},
            )
            return {"type": kind.value, "paused": False, "requires_confirmation": False}

        if kind is InterventionType.SCOPE_CHANGE:
            self._set_status(project_id, run_id, "暂停")
            if self.orchestrator is not None:
                await self.orchestrator.pause(run_id, "需求范围变更待确认")
            await self.events.emit(
                run_id, "intervention.scope_change", stage="暂停",
                payload={"text": text, "requires_confirmation": True},
            )
            return {"type": kind.value, "paused": True, "requires_confirmation": True}

        self._supersede_documents(project_id)
        self._set_status(project_id, run_id, "对齐中")
        self._reset_round(run_id)
        if self.orchestrator is not None:
            await self.orchestrator.pause(run_id, "用户要求推翻重来")
        await self.events.emit(
            run_id, "intervention.overthrow", stage="对齐中",
            payload={"text": text, "new_version_line": True},
        )
        return {"type": kind.value, "paused": True, "new_version_line": True}

    def _add_message(
        self, project_id: str, run_id: str, text: str, kind: str
    ) -> None:
        with self.session_factory() as session:
            session.add(
                Message(
                    project_id=project_id,
                    run_id=run_id,
                    role="user",
                    content=text,
                    visible=True,
                    meta={"intervention_type": kind},
                )
            )
            session.commit()

    def _supersede_documents(self, project_id: str) -> None:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Document).where(
                    Document.project_id == project_id,
                    Document.status.in_(["draft", "approved"]),
                )
            ).all()
            for document in rows:
                document.status = "superseded"
            session.commit()

    def _reset_round(self, run_id: str) -> None:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.usage_json = {**(run.usage_json or {}), "alignment_round": 0}
                session.commit()

    def _set_status(self, project_id: str, run_id: str, status: str) -> None:
        with self.session_factory() as session:
            project = session.get(Project, project_id)
            run = session.get(Run, run_id)
            if project is not None:
                project.status = status
            if run is not None:
                run.status = status
            session.commit()

    def _stage(self, run_id: str) -> str:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            return run.status if run is not None else ""
