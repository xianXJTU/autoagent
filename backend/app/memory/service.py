"""四层记忆服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Memory
from ..llm.service import ModelService
from .decay import decayed_confidence
from .vector_store import ChromaVectorStore, VectorHit

LAYERS = {"session", "project", "global", "case"}


@dataclass
class MemoryHit:
    memory: Memory
    score: float


class MemoryService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedding_service: ModelService,
        vector_store: ChromaVectorStore,
        dedupe_threshold: float = 0.92,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.dedupe_threshold = dedupe_threshold

    async def add(
        self,
        layer: str,
        content: str,
        source: str,
        confidence: float,
        project_id: str | None = None,
        meta: dict[str, Any] | None = None,
        embed: bool = True,
        dedupe: bool = True,
    ) -> Memory:
        if layer not in LAYERS:
            raise ValueError(f"未知记忆层：{layer}")
        if not embed:
            return self._insert(
                layer, content, source, confidence, project_id, meta or {}
            )

        vector = (await self.embedding_service.embed([content])).vectors[0]
        if dedupe:
            duplicate = self._find_duplicate(vector, layer, project_id)
            if duplicate is not None:
                merged = self._merge(duplicate, source, confidence)
                return merged or duplicate

        memory = self._insert(layer, content, source, confidence, project_id, meta or {})
        self.vector_store.upsert(
            ids=[memory.id],
            embeddings=[vector],
            documents=[content],
            metadatas=[
                {
                    "layer": layer,
                    "project_id": project_id or "",
                    "status": "active",
                    "confidence": confidence,
                }
            ],
        )
        return memory

    def _insert(
        self,
        layer: str,
        content: str,
        source: str,
        confidence: float,
        project_id: str | None,
        meta: dict[str, Any],
    ) -> Memory:
        with self.session_factory() as session:
            memory = Memory(
                layer=layer,
                content=content,
                source=source,
                confidence=confidence,
                project_id=project_id,
                status="active",
                meta=meta,
            )
            session.add(memory)
            session.commit()
            session.refresh(memory)
            return memory

    def _where(self, layer: str | None, project_id: str | None) -> dict[str, Any] | None:
        conditions: list[dict[str, Any]] = [{"status": "active"}]
        if layer:
            conditions.append({"layer": layer})
        if project_id is not None:
            conditions.append({"project_id": project_id})
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _find_duplicate(
        self, vector: list[float], layer: str, project_id: str | None
    ) -> Memory | None:
        hits = self.vector_store.query(
            vector, n_results=1, where=self._where(layer, project_id)
        )
        if not hits:
            return None
        top = hits[0]
        similarity = 1.0 - top.distance
        if similarity < self.dedupe_threshold:
            return None
        with self.session_factory() as session:
            memory = session.get(Memory, top.id)
            if memory is not None and memory.status == "active":
                session.expunge(memory)
                return memory
        return None

    def _merge(self, memory: Memory, source: str, confidence: float) -> Memory | None:
        with self.session_factory() as session:
            current = session.get(Memory, memory.id)
            if current is None:
                return None
            meta = dict(current.meta or {})
            sources = list(meta.get("sources", []))
            if current.source:
                sources.append(current.source)
            sources.append(source)
            meta["sources"] = list(dict.fromkeys(sources))
            current.meta = meta
            current.source = source
            current.confidence = max(current.confidence, confidence)
            session.commit()
            session.refresh(current)
            session.expunge(current)
            return current

    async def search(
        self,
        query: str,
        layer: str | None = None,
        project_id: str | None = None,
        limit: int = 5,
        min_score: float = 0.25,
    ) -> list[MemoryHit]:
        if self.vector_store.count() == 0:
            return []
        vector = (await self.embedding_service.embed([query])).vectors[0]
        hits = self.vector_store.query(
            vector, n_results=limit, where=self._where(layer, project_id)
        )
        results: list[MemoryHit] = []
        with self.session_factory() as session:
            for hit in hits:
                score = 1.0 - hit.distance
                if score < min_score:
                    continue
                memory = session.get(Memory, hit.id)
                if memory is None or memory.status != "active":
                    continue
                memory.last_hit_at = datetime.now(timezone.utc)
                results.append(MemoryHit(memory=memory, score=score))
            session.commit()
        return results

    async def record_session(
        self, content: str, source: str, project_id: str | None = None
    ) -> Memory:
        return await self.add(
            "session", content, source, 0.4, project_id=project_id, embed=False
        )

    async def record_project_decision(
        self, content: str, source: str, project_id: str
    ) -> Memory:
        return await self.add("project", content, source, 0.8, project_id=project_id)

    async def record_global_preference(
        self, content: str, source: str
    ) -> Memory:
        return await self.add("global", content, source, 0.9)

    async def record_case(
        self,
        content: str,
        source: str,
        project_id: str | None,
        meta: dict[str, Any] | None = None,
    ) -> Memory:
        return await self.add(
            "case", content, source, 0.7, project_id=project_id, meta=meta or {}
        )

    def promote(self, memory_id: str, confidence: float = 0.95) -> Memory | None:
        with self.session_factory() as session:
            memory = session.get(Memory, memory_id)
            if memory is None:
                return None
            memory.confidence = min(0.95, max(memory.confidence, confidence))
            memory.status = "active"
            session.commit()
            session.refresh(memory)
            return memory

    def invalidate(self, memory_id: str) -> Memory | None:
        with self.session_factory() as session:
            memory = session.get(Memory, memory_id)
            if memory is None:
                return None
            memory.status = "invalid"
            memory.meta = {**(memory.meta or {}), "invalidated_at": datetime.now(timezone.utc).isoformat()}
            session.commit()
            session.refresh(memory)
            return memory

    def restore(self, memory_id: str, confidence: float = 0.5) -> Memory | None:
        with self.session_factory() as session:
            memory = session.get(Memory, memory_id)
            if memory is None:
                return None
            memory.status = "active"
            memory.confidence = max(memory.confidence, confidence)
            session.commit()
            session.refresh(memory)
            return memory

    def apply_decay(
        self, now: datetime | None = None, half_life_days: float = 90.0
    ) -> int:
        current = now or datetime.now(timezone.utc)
        changed = 0
        with self.session_factory() as session:
            rows = session.scalars(
                select(Memory).where(
                    Memory.status == "active",
                    Memory.layer.in_(["global", "case"]),
                )
            ).all()
            for memory in rows:
                meta = dict(memory.meta or {})
                since_raw = meta.get("last_decay_at")
                since = memory.valid_from
                if since_raw:
                    try:
                        since = datetime.fromisoformat(since_raw)
                    except ValueError:
                        since = memory.valid_from
                memory.confidence = decayed_confidence(
                    memory.confidence, since, current, half_life_days
                )
                meta["last_decay_at"] = current.isoformat()
                memory.meta = meta
                if memory.confidence < 0.3:
                    memory.status = "cold"
                changed += 1
            session.commit()
        return changed
