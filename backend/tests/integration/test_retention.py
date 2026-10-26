from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.db.models import Event, Memory, Message, Project, Run
from backend.app.services.retention import RetentionService
from backend.app.workspace.manager import WorkspaceManager


def _setup(db_session, tmp_path: Path):
    project = Project(name="保留项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-retain")
    db_session.add(run)
    db_session.flush()
    db_session.add(
        Message(project_id=project.id, run_id=run.id, role="user", content="你好")
    )
    db_session.add(
        Event(
            run_id=run.id, seq=1, type="test", stage="对齐中",
            payload_json={"password": "123456", "ok": True},
        )
    )
    db_session.add(
        Memory(
            layer="project", project_id=project.id, content="决定了用 MySQL",
            source="doc:1", confidence=0.8, status="active", meta={},
        )
    )
    db_session.commit()
    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create(project.id, "保留项目")
    return project, run, manager


def _count(db_session, model) -> int:
    return int(db_session.scalar(select(func.count()).select_from(model)))


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, ids: list[str]) -> None:
        self.deleted.extend(ids)


def test_delete_keeps_anonymized_trace_and_exports(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run, manager = _setup(db_session, tmp_path)
    project_id = project.id
    run_id = run.id
    memory = db_session.scalars(select(Memory)).one()
    memory_id = memory.id
    db_session.commit()
    run_dir = test_settings.data_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "events.jsonl").write_text('{"type":"x"}\n', encoding="utf-8")
    stale_export = test_settings.data_root / "exports" / f"{project_id}.zip"
    stale_export.parent.mkdir(parents=True, exist_ok=True)
    stale_export.write_bytes(b"old")
    vectors = FakeVectorStore()
    service = RetentionService(
        memory_session_factory,
        tmp_path / "workspace",
        test_settings.data_root,
        vector_store=vectors,
    )
    result = service.delete_project(project_id, keep_traces=True, export=True)
    assert result.deleted
    assert result.export_path and result.export_path.exists()
    assert result.archive_path and result.archive_path.exists()
    text = result.archive_path.read_text(encoding="utf-8")
    assert "123456" not in text
    assert "***" in text

    db_session.expire_all()
    assert db_session.get(Project, project_id) is None
    assert db_session.get(Run, run_id) is None
    assert _count(db_session, Message) == 0
    assert _count(db_session, Event) == 0
    assert _count(db_session, Memory) == 0
    assert vectors.deleted == [memory_id]
    assert not run_dir.exists()
    assert not (tmp_path / "workspace" / project_id).exists()


def test_delete_without_traces(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, _, _ = _setup(db_session, tmp_path)
    project_id = project.id
    service = RetentionService(
        memory_session_factory, tmp_path / "workspace", test_settings.data_root
    )
    result = service.delete_project(project_id, keep_traces=False)
    assert result.archive_path is None
    assert not (test_settings.data_root / "archive" / f"{project_id}.jsonl").exists()
