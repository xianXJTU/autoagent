from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.db.models import Document, Message, Project, Run
from backend.app.events.service import EventService
from backend.app.services.intervention import InterventionService


class FakeOrchestrator:
    def __init__(self) -> None:
        self.paused: list[tuple[str, str]] = []

    async def pause(self, run_id: str, reason: str = "") -> None:
        self.paused.append((run_id, reason))


class FakeMemory:
    def __init__(self) -> None:
        self.calls = []

    async def record_project_decision(self, content: str, source: str, project_id: str):
        self.calls.append(content)


def _setup(db_session, tmp_path: Path):
    project = Project(name="干预项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-intervene")
    db_session.add(run)
    db_session.commit()
    return project, run


async def test_supplement_scope_change_and_overthrow(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run = _setup(db_session, tmp_path)
    events = EventService(memory_session_factory, test_settings.data_root)
    memory = FakeMemory()
    orchestrator = FakeOrchestrator()
    service = InterventionService(
        memory_session_factory, events, memory=memory, orchestrator=orchestrator
    )

    supplement = await service.handle(project.id, run.id, "导出记得带表头")
    assert supplement["type"] == "supplement"
    assert not supplement["paused"]
    assert memory.calls

    scope = await service.handle(project.id, run.id, "增加一个预算提醒")
    assert scope["type"] == "scope_change"
    assert scope["requires_confirmation"]
    assert orchestrator.paused
    db_session.expire_all()
    assert db_session.get(Run, run.id).status == "暂停"

    db_session.add(
        Document(
            project_id=project.id,
            run_id=run.id,
            kind="readme",
            version=1,
            content="旧需求",
            status="approved",
        )
    )
    db_session.commit()

    overthrow = await service.handle(project.id, run.id, "全部推翻，重新开始")
    assert overthrow["type"] == "overthrow"
    db_session.expire_all()
    assert db_session.get(Run, run.id).status == "对齐中"
    documents = db_session.scalars(select(Document)).all()
    assert all(document.status == "superseded" for document in documents)
    messages = db_session.scalars(select(Message)).all()
    assert len(messages) == 3
