from __future__ import annotations

from pathlib import Path

import chromadb
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.db.models import Project, Run, Skill, SkillUsage
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.memory.vector_store import ChromaVectorStore
from backend.app.skills.indexer import SkillIndexer
from backend.app.skills.recall import SkillRecallService

ROOT = Path(__file__).resolve().parents[3]


def _services(memory_session_factory, name: str):
    provider = FakeLLMProvider()
    model_service = ModelService(provider, provider, memory_session_factory)
    store = ChromaVectorStore(client=chromadb.EphemeralClient(), name=name)
    indexer = SkillIndexer(memory_session_factory, model_service, store)
    recall = SkillRecallService(memory_session_factory, model_service, store)
    return indexer, recall


async def test_index_recall_fallback_and_usage(
    db_session, memory_session_factory, test_settings: Settings
) -> None:
    project = Project(name="技能项目", workspace_path="/tmp/skill")
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-skill")
    db_session.add(run)
    db_session.commit()

    indexer, recall = _services(memory_session_factory, "skills_recall")
    indexed = await indexer.index_all(ROOT / "skills")
    assert len(indexed) >= 5

    candidates = await recall.recall("Python 后端接口基础与请求校验", limit=5)
    names = [candidate.skill.name for candidate in candidates]
    assert "python-api-basic" in names
    assert candidates[0].score >= candidates[-1].score

    selected = recall.select(candidates, [candidates[0].skill.id])
    assert selected
    recall.record_usage(
        run.id, None, candidates, selected, {selected[0].id: "与模块接口开发最匹配"}
    )
    with memory_session_factory() as session:
        rows = session.scalars(select(SkillUsage)).all()
        assert len(rows) == 1
        assert rows[0].reason == "与模块接口开发最匹配"

    fallback = recall.fallback()
    assert fallback is not None
    assert fallback.category == "generic"

    # 重复入库不产生重复记录
    await indexer.index_all(ROOT / "skills")
    with memory_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Skill)) == len(indexed)
