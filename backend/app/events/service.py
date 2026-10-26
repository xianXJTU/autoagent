"""事件写入服务：数据库、JSONL、内存广播三者保持一致。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Event
from ..redaction import redact_obj
from .bus import EventBus
from .jsonl import append_event_line
from .schema import EventOut


class EventService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        data_root: Path,
        bus: EventBus | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.data_root = data_root
        self.bus = bus or EventBus()

    async def emit(
        self,
        run_id: str,
        type: str,
        stage: str = "",
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EventOut:
        safe_payload = redact_obj(payload or {})
        last_error: Exception | None = None
        for _ in range(5):
            with self.session_factory() as session:
                current = session.scalar(
                    select(func.coalesce(func.max(Event.seq), 0)).where(
                        Event.run_id == run_id
                    )
                )
                record = Event(
                    run_id=run_id,
                    seq=int(current or 0) + 1,
                    type=type,
                    stage=stage,
                    agent_id=agent_id,
                    payload_json=safe_payload,
                )
                session.add(record)
                try:
                    session.commit()
                except IntegrityError as exc:
                    session.rollback()
                    last_error = exc
                    await asyncio.sleep(0)
                    continue
                event = EventOut(
                    id=record.id,
                    run_id=record.run_id,
                    seq=record.seq,
                    type=record.type,
                    stage=record.stage,
                    agent_id=record.agent_id,
                    payload=safe_payload,
                    created_at=record.created_at,
                )
                break
        else:
            raise RuntimeError(f"事件序号分配失败：{last_error}")

        append_event_line(self.data_root, run_id, event.model_dump(mode="json"))
        await self.bus.publish(run_id, event)
        return event

    def list_after(self, run_id: str, after_seq: int = 0) -> list[EventOut]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Event)
                .where(Event.run_id == run_id, Event.seq > after_seq)
                .order_by(Event.seq.asc())
            ).all()
            return [
                EventOut(
                    id=row.id,
                    run_id=row.run_id,
                    seq=row.seq,
                    type=row.type,
                    stage=row.stage,
                    agent_id=row.agent_id,
                    payload=row.payload_json or {},
                    created_at=row.created_at,
                )
                for row in rows
            ]
