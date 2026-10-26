"""需求对齐、文档版本与审阅。"""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..agents.planner import PlannerAgent
from ..agents.schemas import AlignmentQuestions
from ..db.models import Document, Message, Project, Run
from ..events.service import EventService
from ..memory.service import MemoryService

STOP_PHRASES = {"够了", "可以了", "开始吧", "开始", "信息够了", "继续吧"}


def render_diff(old: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile="上一版",
            tofile="当前版",
            lineterm="",
        )
    )


def format_questions(questions: AlignmentQuestions, round_no: int) -> str:
    lines = [f"第 {round_no} 轮问题："]
    for index, question in enumerate(questions.questions, start=1):
        lines.append(f"{index}. {question.question}")
        if question.recommendation:
            lines.append(f"   建议：{question.recommendation}")
        if question.options:
            lines.append("   选项：" + " / ".join(question.options))
    return "\n".join(lines)


class AlignmentService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        planner: PlannerAgent,
        events: EventService,
        memory: MemoryService | None = None,
        workspace_root: Path | None = None,
        max_rounds: int = 5,
    ) -> None:
        self.session_factory = session_factory
        self.planner = planner
        self.events = events
        self.memory = memory
        self.workspace_root = workspace_root
        self.max_rounds = max_rounds

    async def start(self, project_id: str, run_id: str) -> AlignmentQuestions:
        history = self._history_text(project_id)
        questions = await self.planner.ask_questions(history, 1, self.max_rounds)
        content = format_questions(questions, 1)
        self._add_message(
            project_id, run_id, "planner", content, agent_id="planner",
            meta={"round": 1, "questions": questions.model_dump()},
        )
        self._set_round(run_id, 1)
        self._set_status(project_id, run_id, "对齐中")
        await self.events.emit(
            run_id, "alignment.questions", stage="对齐中", agent_id="planner",
            payload={"round": 1, "questions": questions.model_dump()},
        )
        return questions

    async def answer(self, project_id: str, run_id: str, text: str) -> dict[str, Any]:
        self._add_message(project_id, run_id, "user", text)
        round_no = self._round(run_id)
        history = self._history_text(project_id)
        if text.strip() in STOP_PHRASES or round_no >= self.max_rounds:
            readme = await self.planner.draft_readme(history)
            document = self._save_document(project_id, run_id, "readme", readme)
            self._set_status(project_id, run_id, "待审阅")
            await self.events.emit(
                run_id, "alignment.readme", stage="待审阅", agent_id="planner",
                payload={"document_id": document.id, "version": document.version},
            )
            return {
                "action": "review",
                "document_id": document.id,
                "version": document.version,
                "content": readme,
            }

        next_round = round_no + 1
        questions = await self.planner.ask_questions(
            history, next_round, self.max_rounds
        )
        content = format_questions(questions, next_round)
        self._add_message(
            project_id, run_id, "planner", content, agent_id="planner",
            meta={"round": next_round, "questions": questions.model_dump()},
        )
        self._set_round(run_id, next_round)
        await self.events.emit(
            run_id, "alignment.questions", stage="对齐中", agent_id="planner",
            payload={"round": next_round, "questions": questions.model_dump()},
        )
        return {
            "action": "questions",
            "round": next_round,
            "questions": questions.model_dump(),
        }

    async def approve(self, project_id: str, document_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None or document.project_id != project_id:
                raise ValueError("文档不存在")
            if document.status == "approved":
                return {"document_id": document.id, "version": document.version}
            if document.status != "draft":
                raise ValueError("只有草稿可以审批")
            document.status = "approved"
            document.approved_at = datetime.now(timezone.utc)
            session.commit()
            session.refresh(document)
            content = document.content
            version = document.version
            run_id = document.run_id

        if self.workspace_root is not None:
            readme_path = self.workspace_root / project_id / "repo" / "README.md"
            if readme_path.parent.exists():
                readme_path.write_text(content, encoding="utf-8")

        if run_id:
            self._set_status(project_id, run_id, "已批准")
        if self.memory is not None:
            await self.memory.record_project_decision(
                "需求文档通过：" + content[:500],
                f"document:{document_id}",
                project_id,
            )
        if run_id:
            await self.events.emit(
                run_id, "alignment.approved", stage="已批准", agent_id="planner",
                payload={"document_id": document_id, "version": version},
            )
        return {"document_id": document_id, "version": version}

    async def request_changes(
        self, project_id: str, document_id: str, feedback: str
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            document = session.get(Document, document_id)
            if document is None or document.project_id != project_id:
                raise ValueError("文档不存在")
            run_id = document.run_id
            if document.status == "draft":
                document.status = "superseded"
            session.commit()

        if run_id is None:
            raise ValueError("文档没有关联运行")
        self._add_message(
            project_id, run_id, "user", feedback,
            meta={"document_id": document_id, "intent": "request_changes"},
        )
        history = self._history_text(project_id)
        readme = await self.planner.draft_readme(
            history + "\n用户对上一版的修改意见：" + feedback
        )
        new_document = self._save_document(project_id, run_id, "readme", readme)
        self._set_status(project_id, run_id, "待审阅")
        await self.events.emit(
            run_id, "alignment.revised", stage="待审阅", agent_id="planner",
            payload={
                "document_id": new_document.id,
                "version": new_document.version,
                "feedback": feedback,
            },
        )
        return {
            "document_id": new_document.id,
            "version": new_document.version,
            "content": readme,
        }

    def latest_document(self, project_id: str, kind: str = "readme") -> Document | None:
        with self.session_factory() as session:
            document = session.scalar(
                select(Document)
                .where(Document.project_id == project_id, Document.kind == kind)
                .order_by(Document.version.desc())
                .limit(1)
            )
            if document is not None:
                session.expunge(document)
            return document

    def diff_latest(self, project_id: str, kind: str = "readme") -> str:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Document)
                .where(Document.project_id == project_id, Document.kind == kind)
                .order_by(Document.version.desc())
                .limit(2)
            ).all()
        if len(rows) < 2:
            return ""
        return render_diff(rows[1].content, rows[0].content)

    def _history_text(self, project_id: str) -> str:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Message)
                .where(Message.project_id == project_id)
                .order_by(Message.created_at.asc())
            ).all()
            return "\n".join(
                f"{'用户' if row.role == 'user' else '代理'}：{row.content}"
                for row in rows
            )

    def _add_message(
        self,
        project_id: str,
        run_id: str,
        role: str,
        content: str,
        agent_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Message:
        with self.session_factory() as session:
            message = Message(
                project_id=project_id,
                run_id=run_id,
                role=role,
                agent_id=agent_id,
                content=content,
                visible=True,
                meta=meta or {},
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            session.expunge(message)
            return message

    def _save_document(
        self, project_id: str, run_id: str, kind: str, content: str
    ) -> Document:
        with self.session_factory() as session:
            current = session.scalar(
                select(func.max(Document.version)).where(
                    Document.project_id == project_id, Document.kind == kind
                )
            )
            document = Document(
                project_id=project_id,
                run_id=run_id,
                kind=kind,
                version=int(current or 0) + 1,
                content=content,
                status="draft",
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            session.expunge(document)
            return document

    def _set_round(self, run_id: str, round_no: int) -> None:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is None:
                return
            run.usage_json = {**(run.usage_json or {}), "alignment_round": round_no}
            session.commit()

    def _round(self, run_id: str) -> int:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            return int(((run.usage_json or {}) if run else {}).get("alignment_round", 1))

    def _set_status(self, project_id: str, run_id: str, status: str) -> None:
        with self.session_factory() as session:
            project = session.get(Project, project_id)
            run = session.get(Run, run_id)
            if project is not None:
                project.status = status
            if run is not None:
                run.status = status
            session.commit()
