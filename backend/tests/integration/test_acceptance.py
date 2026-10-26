from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from backend.app.agents.schemas import PlanDraft, ReviewVerdict
from backend.app.config import Settings
from backend.app.db.models import Project, Run, TestResult
from backend.app.events.service import EventService
from backend.app.services.acceptance import AcceptanceService
from backend.app.workspace.manager import WorkspaceManager


class StubReviewer:
    def __init__(self, passed: bool = True, issues: list[str] | None = None) -> None:
        self.passed = passed
        self.issues = issues or []

    async def review(self, readme, plan, code_summary, test_output):
        return ReviewVerdict(
            passed=self.passed,
            score=4 if self.passed else 1,
            issues=self.issues,
            evidence=["tests"],
        )


def _setup(db_session, tmp_path: Path):
    project = Project(name="验收项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-accept")
    db_session.add(run)
    db_session.commit()
    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create(project.id, "验收项目")
    return project, run, manager


async def test_acceptance_passes(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run, manager = _setup(db_session, tmp_path)
    repo = manager.repo_path(project.id)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_ok.py").write_text(
        "def test_ok(): assert True\n", encoding="utf-8"
    )
    events = EventService(memory_session_factory, test_settings.data_root)
    service = AcceptanceService(
        memory_session_factory, manager, events, StubReviewer(),
        test_python=Path(sys.executable),
    )
    outcome = await service.accept(project.id, run.id, "# 需求", PlanDraft(modules=[]))
    assert outcome.passed
    db_session.expire_all()
    assert db_session.get(Run, run.id).status == "验收中"
    rows = db_session.scalars(select(TestResult)).all()
    assert rows[0].result == "pass"


async def test_acceptance_rejects_twice_then_fails(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run, manager = _setup(db_session, tmp_path)
    repo = manager.repo_path(project.id)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_bad.py").write_text(
        "def test_bad(): assert False\n", encoding="utf-8"
    )
    events = EventService(memory_session_factory, test_settings.data_root)
    service = AcceptanceService(
        memory_session_factory, manager, events, StubReviewer(True, ["测试失败"]),
        test_python=Path(sys.executable),
    )
    first = await service.accept(project.id, run.id, "# 需求", PlanDraft(modules=[]))
    assert not first.passed
    assert not first.failed_to_user
    second = await service.accept(project.id, run.id, "# 需求", PlanDraft(modules=[]))
    assert not second.passed
    assert second.failed_to_user
    db_session.expire_all()
    assert db_session.get(Run, run.id).status == "失败"
