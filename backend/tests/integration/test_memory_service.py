from __future__ import annotations

from datetime import datetime, timedelta, timezone

import chromadb

from backend.app.db.models import Memory, Project
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.memory.service import MemoryService
from backend.app.memory.vector_store import ChromaVectorStore


def _service(memory_session_factory, name: str) -> MemoryService:
    provider = FakeLLMProvider()
    model_service = ModelService(provider, provider, memory_session_factory)
    store = ChromaVectorStore(client=chromadb.EphemeralClient(), name=name)
    return MemoryService(memory_session_factory, model_service, store)


async def test_layers_search_dedupe_and_invalidate(
    db_session, memory_session_factory
) -> None:
    project = Project(name="记忆项目", workspace_path="/tmp/mem")
    db_session.add(project)
    db_session.commit()

    service = _service(memory_session_factory, "memories_layers")
    first = await service.record_project_decision(
        "必须使用 MySQL", "README 第一版", project.id
    )
    session_memory = await service.record_session(
        "用户说过要记账", "message-1", project.id
    )
    assert session_memory.embedding_id is None
    assert first.layer == "project"

    hits = await service.search(
        "必须使用 MySQL", layer="project", project_id=project.id
    )
    assert hits
    assert hits[0].memory.id == first.id
    assert hits[0].score > 0.9

    merged = await service.record_project_decision(
        "必须使用 MySQL", "README 第二版", project.id
    )
    assert merged.id == first.id
    assert "README 第二版" in merged.meta["sources"]

    preference = await service.record_global_preference("界面用中文", "用户确认")
    assert preference.layer == "global"
    assert not await service.search(
        "界面用中文", layer="project", project_id=project.id
    )

    service.invalidate(first.id)
    assert (
        await service.search("必须使用 MySQL", layer="project", project_id=project.id)
        == []
    )


async def test_decay_moves_low_confidence_to_cold(
    db_session, memory_session_factory
) -> None:
    service = _service(memory_session_factory, "memories_decay")
    old = Memory(
        layer="global",
        content="旧偏好",
        source="旧",
        confidence=0.8,
        valid_from=datetime.now(timezone.utc) - timedelta(days=180),
        status="active",
        meta={},
    )
    db_session.add(old)
    db_session.commit()

    changed = service.apply_decay()
    assert changed >= 1
    db_session.expire_all()
    loaded = db_session.get(Memory, old.id)
    assert loaded is not None
    assert loaded.status == "cold"
    assert loaded.confidence < 0.3
