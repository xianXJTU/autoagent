from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.db.models import Module, Project, Run, TestResult
from backend.app.events.service import EventService
from backend.app.services.merging import MergeService
from backend.app.workspace.manager import WorkspaceManager


def _setup(db_session, tmp_path: Path):
    project = Project(name="合并项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-merge")
    db_session.add(run)
    db_session.flush()
    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create(project.id, "合并项目")
    return project, run, manager


def _module(db_session, project, run, name: str, files: list[str], tests: list[str]):
    module = Module(
        run_id=run.id,
        project_id=project.id,
        name=name,
        status="已完成",
        spec_json={"name": name, "files": files, "tests": tests},
        depends_on=[],
    )
    db_session.add(module)
    db_session.commit()
    return module


async def test_merge_success_and_full_tests(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run, manager = _setup(db_session, tmp_path)
    repo = manager.repo_path(project.id)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_a.py").write_text("def test_a(): assert True\n", encoding="utf-8")
    (repo / "tests" / "test_b.py").write_text("def test_b(): assert True\n", encoding="utf-8")
    manager.commit_main(project.id, "测试")

    first = _module(db_session, project, run, "A", ["a.py"], ["tests/test_a.py"])
    second = _module(db_session, project, run, "B", ["b.py"], ["tests/test_b.py"])

    for module, filename in ((first, "a.py"), (second, "b.py")):
        worktree = manager.create_module(project.id, module.id)
        (worktree / filename).write_text("VALUE = 1\n", encoding="utf-8")
        manager.commit_module(project.id, module.id, f"{module.name} 完成")

    events = EventService(memory_session_factory, test_settings.data_root)
    service = MergeService(
        memory_session_factory, manager, events, test_python=Path(sys.executable)
    )
    outcome = await service.merge_all(project.id, run.id, [first.id, second.id])
    assert outcome.success
    assert set(outcome.merged) == {"A", "B"}
    assert (repo / "a.py").exists() and (repo / "b.py").exists()

    db_session.expire_all()
    rows = db_session.scalars(select(TestResult)).all()
    assert rows and all(row.result == "pass" for row in rows)


async def test_merge_conflict(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run, manager = _setup(db_session, tmp_path)
    first = _module(db_session, project, run, "A", ["shared.py"], [])
    second = _module(db_session, project, run, "B", ["shared.py"], [])

    for module, content in ((first, "A"), (second, "B")):
        worktree = manager.create_module(project.id, module.id)
        (worktree / "shared.py").write_text(content, encoding="utf-8")
        manager.commit_module(project.id, module.id, f"{module.name} 完成")

    events = EventService(memory_session_factory, test_settings.data_root)
    service = MergeService(
        memory_session_factory, manager, events, test_python=Path(sys.executable)
    )
    outcome = await service.merge_all(project.id, run.id, [first.id, second.id])
    assert not outcome.success
    assert outcome.conflict
