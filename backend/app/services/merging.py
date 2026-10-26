"""按依赖顺序合并模块并运行集成测试。"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Module, TestResult
from ..events.service import EventService
from ..workspace.manager import WorkspaceManager
from ..workspace.runner import CommandRunner


@dataclass
class MergeOutcome:
    success: bool
    merged: list[str] = field(default_factory=list)
    failed: str = ""
    conflict: bool = False
    output: str = ""


def topological_order(modules: list[Module]) -> list[Module]:
    by_name = {module.name: module for module in modules}
    ordered: list[Module] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(module: Module) -> None:
        if module.name in done:
            return
        if module.name in visiting:
            raise ValueError(f"模块依赖存在环：{module.name}")
        visiting.add(module.name)
        for dependency in module.depends_on or []:
            target = by_name.get(dependency)
            if target is not None:
                visit(target)
        visiting.discard(module.name)
        done.add(module.name)
        ordered.append(module)

    for module in modules:
        visit(module)
    return ordered


class MergeService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        workspace: WorkspaceManager,
        events: EventService,
        test_python: Path | None = None,
        test_timeout: float = 300.0,
    ) -> None:
        self.session_factory = session_factory
        self.workspace = workspace
        self.events = events
        self.test_python = str(test_python or sys.executable)
        self.test_timeout = test_timeout

    async def merge_all(
        self, project_id: str, run_id: str, module_ids: list[str]
    ) -> MergeOutcome:
        with self.session_factory() as session:
            modules = [
                session.get(Module, module_id) for module_id in module_ids
            ]
            modules = [module for module in modules if module is not None]
            for module in modules:
                session.expunge(module)
        try:
            ordered = topological_order(modules)
        except ValueError as exc:
            return MergeOutcome(success=False, failed=str(exc))

        repo = self.workspace.repo_path(project_id)
        runner = CommandRunner(repo)
        merged: list[str] = []
        merged_tests: list[str] = []

        for module in ordered:
            if module.status != "已完成":
                return MergeOutcome(
                    success=False,
                    merged=merged,
                    failed=f"模块 {module.name} 未通过测试，状态为 {module.status}",
                )
            result = self.workspace.merge_module(project_id, module.id)
            if not result.merged:
                self._set_status(module.id, "冲突")
                await self.events.emit(
                    run_id, "merge.conflict", stage="合并中", agent_id="planner",
                    payload={"module_id": module.id, "message": result.message[:1000]},
                )
                return MergeOutcome(
                    success=False,
                    merged=merged,
                    failed=f"模块 {module.name} 合并冲突",
                    conflict=result.conflict,
                    output=result.message,
                )

            merged.append(module.name)
            self._set_status(module.id, "已合并")
            merged_tests.extend((module.spec_json or {}).get("tests", []))
            await self.events.emit(
                run_id, "merge.completed", stage="合并中", agent_id="planner",
                payload={"module_id": module.id, "commit": result.commit},
            )

            if merged_tests:
                check = await asyncio.to_thread(
                    runner.run,
                    [self.test_python, "-m", "pytest", *sorted(set(merged_tests)), "-q"],
                    repo,
                    self.test_timeout,
                )
                self._record_test(
                    run_id, module.id, f"合并后测试：{module.name}",
                    "pass" if check.exit_code == 0 else "fail",
                    check.stdout + check.stderr, check.duration_ms,
                )
                if check.exit_code != 0:
                    self._set_status(module.id, "集成失败")
                    await self.events.emit(
                        run_id, "merge.failed", stage="合并中", agent_id="planner",
                        payload={"module_id": module.id, "output": (check.stdout + check.stderr)[-1000:]},
                    )
                    return MergeOutcome(
                        success=False,
                        merged=merged,
                        failed=f"合并 {module.name} 后测试失败",
                        output=(check.stdout + check.stderr)[-4000:],
                    )

        full = await asyncio.to_thread(
            runner.run, [self.test_python, "-m", "pytest", "-q"], repo, self.test_timeout
        )
        self._record_test(
            run_id, None, "全量集成测试",
            "pass" if full.exit_code == 0 else "fail",
            full.stdout + full.stderr, full.duration_ms,
        )
        if full.exit_code != 0:
            await self.events.emit(
                run_id, "merge.full_failed", stage="合并中", agent_id="planner",
                payload={"output": (full.stdout + full.stderr)[-1000:]},
            )
            return MergeOutcome(
                success=False,
                merged=merged,
                failed="全量集成测试失败",
                output=(full.stdout + full.stderr)[-4000:],
            )

        return MergeOutcome(success=True, merged=merged)

    def _set_status(self, module_id: str, status: str) -> None:
        with self.session_factory() as session:
            module = session.get(Module, module_id)
            if module is not None:
                module.status = status
                session.commit()

    def _record_test(
        self,
        run_id: str,
        module_id: str | None,
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
                    kind="integration",
                    case_name=name,
                    result=result,
                    error="" if result == "pass" else output[-4000:],
                    duration_ms=duration_ms,
                )
            )
            session.commit()
