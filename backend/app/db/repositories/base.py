"""通用仓储基类。"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from ..models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        return obj

    def get(self, identifier: str) -> ModelT | None:
        return self.session.get(self.model, identifier)

    def delete(self, obj: ModelT) -> None:
        self.session.delete(obj)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
