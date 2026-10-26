from __future__ import annotations

import pytest
from sqlalchemy import func, select

from backend.app.db.models import ModelCall, Project, Run
from backend.app.llm.base import ChatResult
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService


class _BrokenProvider(FakeLLMProvider):
    async def chat(self, *args, **kwargs):
        raise RuntimeError("模拟失败")


async def test_chat_and_embedding_are_recorded(
    db_session, memory_session_factory
) -> None:
    project = Project(name="模型项目", workspace_path="/tmp/m")
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-model")
    db_session.add(run)
    db_session.commit()

    provider = FakeLLMProvider([ChatResult(content="结果", prompt_tokens=7)])
    service = ModelService(provider, provider, memory_session_factory)
    result = await service.chat(
        [{"role": "user", "content": "hi"}],
        run_id=run.id,
        agent_id="planner",
        purpose="对齐",
    )
    embedding = await service.embed(["一段文本"], run_id=run.id, agent_id="planner")

    assert result.content == "结果"
    assert len(embedding.vectors[0]) == 1024

    with memory_session_factory() as session:
        rows = session.scalars(select(ModelCall)).all()
        assert len(rows) == 2
        assert {row.purpose for row in rows} == {"对齐", "embedding"}
        assert all(row.status == "ok" for row in rows)
        assert session.scalar(select(func.count()).select_from(ModelCall)) == 2


async def test_failed_call_is_recorded(
    db_session, memory_session_factory
) -> None:
    project = Project(name="失败项目", workspace_path="/tmp/f")
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-fail")
    db_session.add(run)
    db_session.commit()

    provider = _BrokenProvider()
    service = ModelService(provider, provider, memory_session_factory)
    with pytest.raises(RuntimeError):
        await service.chat(
            [{"role": "user", "content": "hi"}], run_id=run.id, purpose="失败"
        )

    with memory_session_factory() as session:
        row = session.scalars(select(ModelCall)).one()
        assert row.status == "error"
