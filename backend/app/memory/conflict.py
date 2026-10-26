"""记忆冲突裁决。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..db.models import Memory


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


@dataclass
class ConflictResolution:
    winner: Memory | None
    reason: str
    needs_arbitration: bool = False


def resolve_conflict(
    first: Memory, second: Memory, time_window_seconds: float = 60.0
) -> ConflictResolution:
    delta_time = abs(_timestamp(first.valid_from) - _timestamp(second.valid_from))
    if delta_time > time_window_seconds:
        winner = first if _timestamp(first.valid_from) > _timestamp(second.valid_from) else second
        return ConflictResolution(winner=winner, reason="时间更新的优先")

    delta_confidence = abs(first.confidence - second.confidence)
    if delta_confidence >= 0.05:
        winner = first if first.confidence > second.confidence else second
        return ConflictResolution(winner=winner, reason="置信值更高的优先")

    return ConflictResolution(
        winner=None, reason="时间与置信值接近，需要模型仲裁或询问用户", needs_arbitration=True
    )
