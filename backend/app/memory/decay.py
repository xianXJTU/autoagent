"""记忆衰减。"""

from __future__ import annotations

from datetime import datetime, timezone


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def decayed_confidence(
    confidence: float,
    since: datetime,
    now: datetime | None = None,
    half_life_days: float = 90.0,
) -> float:
    current = now or datetime.now(timezone.utc)
    elapsed_days = max(0.0, (_timestamp(current) - _timestamp(since)) / 86400.0)
    factor = 0.5 ** (elapsed_days / half_life_days)
    return max(0.0, min(1.0, confidence * factor))
