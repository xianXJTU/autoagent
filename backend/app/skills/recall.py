"""技能召回与使用记录。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Skill, SkillUsage
from ..llm.service import ModelService
from ..memory.vector_store import ChromaVectorStore
from .conflicts import SkillConflict, detect_conflicts


@dataclass
class SkillCandidate:
    skill: Skill
    score: float


class SkillRecallService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        embedding_service: ModelService,
        vector_store: ChromaVectorStore,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    async def recall(
        self, query: str, limit: int = 8, min_score: float = 0.2
    ) -> list[SkillCandidate]:
        if self.vector_store.count() == 0:
            return []
        vector = (await self.embedding_service.embed([query])).vectors[0]
        hits = self.vector_store.query(vector, n_results=limit)
        candidates: list[SkillCandidate] = []
        with self.session_factory() as session:
            for hit in hits:
                score = 1.0 - hit.distance
                if score < min_score:
                    continue
                skill = session.get(Skill, hit.id)
                if skill is None or skill.status != "active":
                    continue
                session.expunge(skill)
                candidates.append(SkillCandidate(skill=skill, score=score))
        return candidates

    def fallback(self) -> Skill | None:
        with self.session_factory() as session:
            skill = session.scalar(
                select(Skill)
                .where(Skill.category == "generic", Skill.status == "active")
                .limit(1)
            )
            if skill is not None:
                session.expunge(skill)
            return skill

    def select(
        self, candidates: list[SkillCandidate], selected_ids: list[str]
    ) -> list[Skill]:
        mapping = {candidate.skill.id: candidate.skill for candidate in candidates}
        chosen = [mapping[item] for item in selected_ids if item in mapping]
        if not chosen:
            chosen = [candidate.skill for candidate in candidates[:3]]
        return chosen

    def conflicts(self, skills: list[Skill]) -> list[SkillConflict]:
        return detect_conflicts(skills)

    def record_usage(
        self,
        run_id: str,
        module_id: str | None,
        candidates: list[SkillCandidate],
        selected: list[Skill],
        reasons: dict[str, str] | None = None,
    ) -> None:
        reason_map = reasons or {}
        selected_ids = {skill.id for skill in selected}
        with self.session_factory() as session:
            for rank, candidate in enumerate(candidates, start=1):
                if candidate.skill.id not in selected_ids:
                    continue
                session.add(
                    SkillUsage(
                        run_id=run_id,
                        module_id=module_id,
                        skill_id=candidate.skill.id,
                        rank=rank,
                        score=candidate.score,
                        reason=reason_map.get(candidate.skill.id, "策划者复核入选"),
                    )
                )
            session.commit()

    def usage_rows(self, run_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(SkillUsage).where(SkillUsage.run_id == run_id)
            ).all()
            return [
                {
                    "skill_id": row.skill_id,
                    "module_id": row.module_id,
                    "rank": row.rank,
                    "score": row.score,
                    "reason": row.reason,
                }
                for row in rows
            ]
