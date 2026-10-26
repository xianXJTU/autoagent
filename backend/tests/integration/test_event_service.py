from __future__ import annotations

from pathlib import Path

from backend.app.config import Settings
from backend.app.db.models import Project, Run
from backend.app.db.session import build_session_factory
from backend.app.events.jsonl import read_event_lines
from backend.app.events.service import EventService


async def test_emit_assigns_sequence_redacts_and_mirrors(
    db_engine, db_session, test_settings: Settings, tmp_path: Path
) -> None:
    project = Project(name="事件项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-events")
    db_session.add(run)
    db_session.commit()

    factory = build_session_factory(db_engine)
    service = EventService(factory, test_settings.data_root)

    first = await service.emit(
        run.id,
        "message",
        stage="对齐中",
        agent_id="planner",
        payload={"content": "你好", "password": "123456"},
    )
    second = await service.emit(run.id, "state", stage="待审阅", payload={"ok": True})

    assert first.seq == 1
    assert second.seq == 2
    assert first.payload["password"] == "***"

    lines = read_event_lines(test_settings.data_root, run.id)
    assert [line["seq"] for line in lines] == [1, 2]
    assert lines[0]["payload"]["password"] == "***"

    persisted = service.list_after(run.id, after_seq=0)
    assert [event.seq for event in persisted] == [1, 2]
    assert service.list_after(run.id, after_seq=1)[0].seq == 2
