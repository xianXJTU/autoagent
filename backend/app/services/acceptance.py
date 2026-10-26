"""整体验收：先跑测试，再请验收者逐条核对。"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from ..agents.reviewer import ReviewerAgent
from ..agents.schemas import PlanDraft, ReviewVerdict
from ..db.models import Project, Run, TestResult
from ..events.service import EventService
from ..workspace.manager import WorkspaceManager
from ..workspace.runner import CommandRunner


@dataclass
class AcceptanceOutcome:
    passed: bool
    verdict: ReviewVerdict | None = None
    issues: list[str] = field(default_factory=list)
    output: str = ""
    failed_to_user: bool = False
    rounds: int = 0


class AcceptanceService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        workspace: WorkspaceManager,
        events: EventService,
        reviewer: ReviewerAgent,
        test_python: Path | None = None,
        max_rounds: int = 2,
        test_timeout: float = 300.0,
    ) -> None:
        self.session_factory = session_factory
        self.workspace = workspace
        self.events = events
        self.reviewer = reviewer
        self.test_python = str(test_python or sys.executable)
        self.max_rounds = max_rounds
        self.test_timeout = test_timeout

    async def accept(
        self,
        project_id: str,
        run_id: str,
        readme: str,
        plan: PlanDraft,
    ) -> AcceptanceOutcome:
        repo = self.workspace.repo_path(project_id)
        rounds = self._round(run_id) + 1
        self._set_round(run_id, rounds)
        self._set_status(project_id, run_id, "验收中")

        runner = CommandRunner(repo)
        result = await asyncio.to_thread(
            runner.run, [self.test_python, "-m", "pytest", "-q"], repo, self.test_timeout
        )
        output = result.stdout + result.stderr
        self._record_test(
            run_id,
            "pass" if result.exit_code == 0 else "fail",
            output,
            result.duration_ms,
        )

        verdict = await self.reviewer.review(
            readme, plan, self._code_summary(repo), output
        )
        passed = result.exit_code == 0 and verdict.passed
        if passed:
            await self.events.emit(
                run_id, "acceptance.passed", stage="验收中", agent_id="reviewer",
                payload={"score": verdict.score, "evidence": verdict.evidence},
            )
            return AcceptanceOutcome(
                passed=True, verdict=verdict, output=output, rounds=rounds
            )

        issues = verdict.issues or [output[-1000:]]
        if rounds >= self.max_rounds:
            self._set_status(project_id, run_id, "失败")
            await self.events.emit(
                run_id, "acceptance.failed", stage="验收中", agent_id="reviewer",
                payload={"issues": issues, "rounds": rounds},
            )
            return AcceptanceOutcome(
                passed=False,
                verdict=verdict,
                issues=issues,
                output=output,
                failed_to_user=True,
                rounds=rounds,
            )

        self._set_status(project_id, run_id, "编码中")
        await self.events.emit(
            run_id, "acceptance.rejected", stage="验收中", agent_id="reviewer",
            payload={"issues": issues, "rounds": rounds},
        )
        return AcceptanceOutcome(
            passed=False,
            verdict=verdict,
            issues=issues,
            output=output,
            failed_to_user=False,
            rounds=rounds,
        )

    def _code_summary(self, repo: Path) -> str:
        lines: list[str] = []
        for path in sorted(repo.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo).as_posix()
            if any(
                part in relative
                for part in (".git/", ".venv/", "__pycache__/", ".pytest_cache/")
            ):
                continue
            lines.append(f"{relative} ({path.stat().st_size} bytes)")
        return "\n".join(lines)

    def _round(self, run_id: str) -> int:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            return int(((run.usage_json or {}) if run else {}).get("acceptance_round", 0))

    def _set_round(self, run_id: str, rounds: int) -> None:
        with self.session_factory() as session:
            run = session.get(Run, run_id)
            if run is not None:
                run.usage_json = {
                    **(run.usage_json or {}),
                    "acceptance_round": rounds,
                }
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

    def _record_test(
        self, run_id: str, result: str, output: str, duration_ms: int
    ) -> None:
        with self.session_factory() as session:
            session.add(
                TestResult(
                    run_id=run_id,
                    module_id=None,
                    kind="acceptance",
                    case_name="整体验收",
                    result=result,
                    error="" if result == "pass" else output[-4000:],
                    duration_ms=duration_ms,
                )
            )
            session.commit()
