from __future__ import annotations

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from backend.app.db.models import Event, Message, Project, Run
from backend.app.db.repositories import ProjectRepository


def test_project_crud_and_cascade(db_session) -> None:
    repo = ProjectRepository(db_session)
    project = Project(name="记账小工具", workspace_path="/tmp/demo")
    repo.add(project)
    db_session.commit()

    loaded = repo.get(project.id)
    assert loaded is not None
    assert loaded.name == "记账小工具"

    run = Run(project_id=project.id, thread_id="thread-1")
    db_session.add(run)
    db_session.add(
        Message(
            project_id=project.id,
            run_id=run.id,
            role="user",
            content="你好，世界",
        )
    )
    db_session.commit()

    run_id = run.id
    db_session.execute(delete(Project).where(Project.id == project.id))
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(Run, run_id) is None


def test_chinese_roundtrip(db_session) -> None:
    project = Project(name="中文项目", workspace_path="/tmp/中文")
    db_session.add(project)
    db_session.flush()
    message = Message(project_id=project.id, role="user", content="记账、分类、导出")
    db_session.add(message)
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(Message, message.id)
    assert loaded is not None
    assert loaded.content == "记账、分类、导出"


def test_event_sequence_is_unique(db_session) -> None:
    project = Project(name="事件项目", workspace_path="/tmp/e")
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-2")
    db_session.add(run)
    db_session.flush()

    db_session.add(Event(run_id=run.id, seq=1, type="a", stage="s", payload_json={}))
    db_session.add(Event(run_id=run.id, seq=1, type="b", stage="s", payload_json={}))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
