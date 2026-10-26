from __future__ import annotations

from sqlalchemy import select

from ..models import Project
from .base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    def list_recent(self, limit: int = 50) -> list[Project]:
        statement = (
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
