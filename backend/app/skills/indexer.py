from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Skill
from ..llm.service import ModelService
from ..memory.vector_store import ChromaVectorStore
from .loader import load_skills
from .schema import SkillDocument


class SkillIndexer:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedding_service: ModelService,
        vector_store: ChromaVectorStore,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    async def index_document(self, document: SkillDocument) -> Skill:
        meta = document.meta
        with self.session_factory() as session:
            skill = session.scalar(select(Skill).where(Skill.name == meta.name))
            if skill is None:
                skill = Skill(name=meta.name)
                session.add(skill)
            skill.version = meta.version
            skill.description = meta.description
            skill.language = meta.language
            skill.category = meta.category
            skill.tags_json = list(meta.tags)
            skill.decision_points_json = dict(meta.decision_points)
            skill.applies_when = meta.applies_when
            skill.path = str(document.path)
            skill.status = "active"
            session.commit()
            session.refresh(skill)
            session.expunge(skill)

        vector = (
            await self.embedding_service.embed([document.embedding_text()])
        ).vectors[0]
        self.vector_store.upsert(
            ids=[skill.id],
            embeddings=[vector],
            documents=[meta.description],
            metadatas=[
                {
                    "name": meta.name,
                    "language": meta.language,
                    "category": meta.category,
                    "version": meta.version,
                }
            ],
        )
        return skill

    async def index_all(self, root: Path) -> list[Skill]:
        return [await self.index_document(document) for document in load_skills(root)]
