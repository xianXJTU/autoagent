"""把对齐之后的各阶段接进 LangGraph 状态机。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..agents.base import AgentContext
from ..agents.evaluator import EvaluatorAgent
from ..agents.planner import PlannerAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.schemas import PlanDraft
from ..config import Settings
from ..db.models import Document, Project, Run
from ..evaluation.service import EvaluationService
from ..events.service import EventService
from ..llm.service import ModelService
from ..memory.service import MemoryService
from ..orchestration import (
    BudgetLimits,
    NodeHandlers,
    Orchestrator,
    RunState,
)
from ..skills.recall import SkillRecallService
from ..workspace.manager import WorkspaceManager
from .acceptance import AcceptanceService
from .coding import CodingService
from .delivery import package_project, write_start_script
from .merging import MergeService
from .planning import PlanningService


class PipelineService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        workspace: WorkspaceManager,
        events: EventService,
        model_service: ModelService,
        memory: MemoryService,
        skill_recall: SkillRecallService,
        test_python: Path | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.workspace = workspace
        self.events = events
        self.model_service = model_service
        self.memory = memory
        self.skill_recall = skill_recall
        self.test_python = test_python or Path(sys.executable)

    def _handlers(self) -> NodeHandlers:
        return NodeHandlers(
            plan=self._plan,
            test_design=self._test_design,
            dispatch=self._dispatch,
            code=self._code,
            merge=self._merge,
            accept=self._accept,
            deliver=self._deliver,
            evaluate=self._evaluate,
        )

    def _limits(self) -> BudgetLimits:
        return BudgetLimits(
            seconds=self.settings.run_timeout_seconds,
            total_tokens=self.settings.run_max_tokens,
            model_calls=self.settings.run_max_model_calls,
        )

    async def run_after_approval(
        self, project_id: str, run_id: str
    ) -> dict[str, Any]:
        readme = self._readme(project_id)
        async with Orchestrator(
            self._handlers(), self.settings.checkpoint_path, self._limits()
        ) as orchestrator:
            return await orchestrator.start(
                project_id,
                run_id,
                {"stage": "已批准", "approved": True, "readme": readme},
            )

    async def resume(self, project_id: str, run_id: str, stage: str) -> dict[str, Any]:
        async with Orchestrator(
            self._handlers(), self.settings.checkpoint_path, self._limits()
        ) as orchestrator:
            return await orchestrator.advance(run_id, {"stage": stage})

    def _planner(self, state: RunState) -> PlannerAgent:
        return PlannerAgent(
            AgentContext(
                project_id=state["project_id"],
                run_id=state["run_id"],
                model_service=self.model_service,
            )
        )

    def _reviewer(self, state: RunState) -> ReviewerAgent:
        return ReviewerAgent(
            AgentContext(
                project_id=state["project_id"],
                run_id=state["run_id"],
                model_service=self.model_service,
            )
        )

    async def _stopped(self, run_id: str) -> str | None:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is not None and run.status in {"暂停", "取消"}:
                return run.status
        return None

    async def _plan(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        self._set_status(state["project_id"], state["run_id"], "计划中")
        service = PlanningService(
            self.session_factory,
            self._planner(state),
            self._reviewer(state),
            self.workspace,
        )
        result = await service.generate(
            state["project_id"], state["run_id"], state.get("readme", "")
        )
        return {
            "stage": "计划中",
            "module_ids": result.module_ids,
            "plan_json": result.plan.model_dump_json(),
            "plan_document_id": result.plan_document_id,
            "test_files": result.test_files,
        }

    async def _test_design(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        self._set_status(state["project_id"], state["run_id"], "计划就绪")
        return {"stage": "计划就绪"}

    async def _dispatch(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        self._set_status(state["project_id"], state["run_id"], "编码中")
        return {"stage": "编码中"}

    async def _code(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        service = CodingService(
            self.session_factory,
            self.workspace,
            self.events,
            self.model_service,
            skill_recall=self.skill_recall,
            max_fix_rounds=self.settings.test_fix_rounds,
        )
        results = await service.code_modules(
            state["project_id"],
            state["run_id"],
            state.get("module_ids", []),
            test_python=self.test_python,
        )
        failed = [item for item in results if item.status != "已完成"]
        if failed:
            errors = "; ".join(f"{item.name}: {item.error[:300]}" for item in failed)
            self._set_status(state["project_id"], state["run_id"], "失败")
            return {"stage": "失败", "last_error": errors}
        self._set_status(state["project_id"], state["run_id"], "测试中")
        return {"stage": "测试中"}

    async def _merge(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        service = MergeService(
            self.session_factory,
            self.workspace,
            self.events,
            test_python=self.test_python,
        )
        outcome = await service.merge_all(
            state["project_id"], state["run_id"], state.get("module_ids", [])
        )
        if not outcome.success:
            self._set_status(state["project_id"], state["run_id"], "失败")
            return {"stage": "失败", "last_error": outcome.failed}
        self._set_status(state["project_id"], state["run_id"], "合并中")
        return {"stage": "合并中"}

    async def _accept(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        plan = PlanDraft.model_validate_json(state.get("plan_json") or "{}")
        service = AcceptanceService(
            self.session_factory,
            self.workspace,
            self.events,
            self._reviewer(state),
            test_python=self.test_python,
            max_rounds=self.settings.acceptance_rounds,
        )
        outcome = await service.accept(
            state["project_id"], state["run_id"], state.get("readme", ""), plan
        )
        if not outcome.passed and not outcome.failed_to_user:
            outcome = await service.accept(
                state["project_id"], state["run_id"], state.get("readme", ""), plan
            )
        if outcome.passed:
            self._set_status(state["project_id"], state["run_id"], "验收中")
            return {"stage": "验收中"}
        self._set_status(state["project_id"], state["run_id"], "失败")
        return {
            "stage": "失败",
            "last_error": "；".join(outcome.issues)[:2000],
        }

    async def _deliver(self, state: RunState) -> dict[str, Any]:
        stopped = await self._stopped(state["run_id"])
        if stopped:
            return {"stage": stopped}
        repo = self.workspace.repo_path(state["project_id"])
        write_start_script(repo)
        package = package_project(
            repo, self.settings.data_root / "exports" / f"{state['run_id']}.zip"
        )
        self._set_status(state["project_id"], state["run_id"], "已交付")
        await self.events.emit(
            state["run_id"], "delivery.completed", stage="已交付", agent_id="planner",
            payload={"package": str(package)},
        )
        return {"stage": "已交付", "package_path": str(package)}

    async def _evaluate(self, state: RunState) -> dict[str, Any]:
        evaluator = EvaluatorAgent(
            AgentContext(
                project_id=state["project_id"],
                run_id=state["run_id"],
                model_service=self.model_service,
            )
        )
        service = EvaluationService(
            self.session_factory, self.events, evaluator=evaluator, memory=self.memory
        )
        await service.evaluate(state["run_id"])
        return {"evaluated": True}

    def _readme(self, project_id: str) -> str:
        with self.session_factory() as session:
            document = session.scalar(
                select(Document)
                .where(Document.project_id == project_id, Document.kind == "readme")
                .order_by(Document.version.desc())
                .limit(1)
            )
            return document.content if document is not None else ""

    def _set_status(self, project_id: str, run_id: str, status: str) -> None:
        with self.session_factory() as session:
            project = session.get(Project, project_id)
            run = session.get(Run, run_id)
            if project is not None:
                project.status = status
            if run is not None:
                run.status = status
            session.commit()
