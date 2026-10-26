"""并行编码、模块测试与修复循环。"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..agents.base import AgentContext
from ..agents.coder import CoderAgent
from ..agents.tools import ToolRegistry
from ..db.models import Module, TestResult
from ..events.service import EventService
from ..llm.service import ModelService
from ..skills.loader import load_skill_file
from ..skills.recall import SkillRecallService
from ..workspace.manager import WorkspaceManager
from ..workspace.runner import CommandRunner


@dataclass
class ModuleResult:
    module_id: str
    name: str
    status: str
    rounds: int = 0
    commit: str | None = None
    error: str = ""


class CodingService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        workspace: WorkspaceManager,
        events: EventService,
        model_service: ModelService,
        skill_recall: SkillRecallService | None = None,
        max_fix_rounds: int = 5,
        test_timeout: float = 300.0,
    ) -> None:
        self.session_factory = session_factory
        self.workspace = workspace
        self.events = events
        self.model_service = model_service
        self.skill_recall = skill_recall
        self.max_fix_rounds = max_fix_rounds
        self.test_timeout = test_timeout

    async def code_modules(
        self,
        project_id: str,
        run_id: str,
        module_ids: list[str],
        test_python: Path | None = None,
    ) -> list[ModuleResult]:
        python = str(test_python or sys.executable)
        semaphore = asyncio.Semaphore(max(1, len(module_ids)))

        async def worker(module_id: str) -> ModuleResult:
            async with semaphore:
                return await self._code_one(project_id, run_id, module_id, python)

        return list(await asyncio.gather(*(worker(item) for item in module_ids)))

    async def _code_one(
        self, project_id: str, run_id: str, module_id: str, test_python: str
    ) -> ModuleResult:
        with self.session_factory() as session:
            module = session.get(Module, module_id)
            if module is None:
                return ModuleResult(module_id, "", "失败", error="模块不存在")
            if module.status == "已完成":
                return ModuleResult(module_id, module.name, "已完成")
            name = module.name
            spec = dict(module.spec_json or {})

        worktree = self.workspace.create_module(project_id, module_id)
        tests = list(spec.get("tests") or ["tests"])
        skills_text, skill_note = await self._skills(
            run_id, module_id, f"{name} {spec.get('description', '')}"
        )

        runner = CommandRunner(worktree)
        tools = ToolRegistry(
            worktree,
            runner=runner,
            venv_python=Path(test_python),
            allowed_paths=set(spec.get("files") or []),
        )
        coder = CoderAgent(
            AgentContext(
                project_id=project_id,
                run_id=run_id,
                model_service=self.model_service,
                tools=tools,
                module_id=module_id,
            )
        )

        test_text = self._read_tests(worktree, tests)
        await self.events.emit(
            run_id, "module.started", stage="编码中", agent_id="coder",
            payload={"module_id": module_id, "name": name, "skills": skill_note},
        )

        rounds = 0
        failure = ""
        try:
            draft = await coder.write_module(spec, spec.get("interfaces", ""), skills_text, test_text)
            await coder.apply(draft)
        except Exception as exc:
            await self._set_status(module_id, "失败")
            await self.events.emit(
                run_id, "module.failed", stage="编码中", agent_id="coder",
                payload={"module_id": module_id, "error": str(exc)},
            )
            return ModuleResult(module_id, name, "失败", error=str(exc))

        passed = False
        while rounds < self.max_fix_rounds:
            rounds += 1
            result = await asyncio.to_thread(
                runner.run,
                [test_python, "-m", "pytest", *tests, "-q"],
                worktree,
                self.test_timeout,
            )
            self._record_test(
                run_id, module_id, name,
                "pass" if result.exit_code == 0 else "fail",
                result.stdout + result.stderr, result.duration_ms,
            )
            if result.exit_code == 0:
                passed = True
                break
            failure = (result.stdout + result.stderr)[-4000:]
            await self.events.emit(
                run_id, "module.test_failed", stage="测试中", agent_id="coder",
                payload={"module_id": module_id, "round": rounds},
            )
            if rounds >= self.max_fix_rounds:
                break
            try:
                draft = await coder.fix_module(spec, failure, draft.notes)
                await coder.apply(draft)
            except Exception as exc:
                failure = str(exc)
                break

        if not passed:
            await self._set_status(module_id, "失败")
            await self.events.emit(
                run_id, "module.failed", stage="测试中", agent_id="coder",
                payload={
                    "module_id": module_id, "rounds": rounds, "error": failure[:1000]
                },
            )
            return ModuleResult(
                module_id, name, "失败", rounds=rounds, error=failure
            )

        commit = self.workspace.commit_module(
            project_id, module_id, f"模块 {name} 完成"
        )
        await self._set_status(module_id, "已完成")
        await self.events.emit(
            run_id, "module.completed", stage="测试中", agent_id="coder",
            payload={"module_id": module_id, "rounds": rounds, "commit": commit},
        )
        return ModuleResult(
            module_id, name, "已完成", rounds=rounds, commit=commit
        )

    async def _skills(
        self, run_id: str, module_id: str, query: str
    ) -> tuple[str, list[dict[str, Any]]]:
        if self.skill_recall is None:
            return "", []
        candidates = await self.skill_recall.recall(query, limit=8)
        selected = candidates[:3]
        conflicts = self.skill_recall.conflicts([item.skill for item in selected])
        if conflicts:
            winners = {item.winner.id for item in conflicts if item.winner}
            filtered = [item for item in selected if item.skill.id in winners]
            selected = filtered or selected[:1]
            await self.events.emit(
                run_id, "skills.conflict", stage="编码中", agent_id="planner",
                payload={
                    "module_id": module_id,
                    "conflicts": [
                        {
                            "decision_point": item.decision_point,
                            "winner": item.winner.name if item.winner else None,
                            "reason": item.reason,
                        }
                        for item in conflicts
                    ],
                },
            )
        bodies: list[str] = []
        note: list[dict[str, Any]] = []
        for candidate in selected:
            try:
                body = load_skill_file(Path(candidate.skill.path)).body
            except Exception:
                body = candidate.skill.description
            bodies.append(f"【{candidate.skill.name}】\n{body}")
            note.append(
                {"id": candidate.skill.id, "name": candidate.skill.name, "score": candidate.score}
            )
        self.skill_recall.record_usage(
            run_id, module_id, candidates, [item.skill for item in selected]
        )
        return "\n\n".join(bodies), note

    @staticmethod
    def _read_tests(worktree: Path, tests: list[str]) -> str:
        chunks: list[str] = []
        for item in tests:
            path = worktree / item
            if path.is_file():
                chunks.append(f"# {item}\n" + path.read_text(encoding="utf-8"))
            elif path.is_dir():
                for file in sorted(path.rglob("*.py")):
                    chunks.append(
                        f"# {file.relative_to(worktree).as_posix()}\n"
                        + file.read_text(encoding="utf-8")
                    )
        return "\n\n".join(chunks)

    def _record_test(
        self,
        run_id: str,
        module_id: str,
        name: str,
        result: str,
        output: str,
        duration_ms: int,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                TestResult(
                    run_id=run_id,
                    module_id=module_id,
                    kind="module",
                    case_name=name,
                    result=result,
                    error="" if result == "pass" else output[-4000:],
                    duration_ms=duration_ms,
                )
            )
            session.commit()

    async def _set_status(self, module_id: str, status: str) -> None:
        with self.session_factory() as session:
            module = session.get(Module, module_id)
            if module is not None:
                module.status = status
                session.commit()
