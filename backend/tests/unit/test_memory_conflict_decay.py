from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.db.models import Memory
from backend.app.memory.conflict import resolve_conflict
from backend.app.memory.decay import decayed_confidence


def _memory(confidence: float, minutes_ago: int, content: str = "x") -> Memory:
    return Memory(
        layer="project",
        content=content,
        source="test",
        confidence=confidence,
        valid_from=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )


def test_newer_memory_wins() -> None:
    result = resolve_conflict(_memory(0.9, 10), _memory(0.9, 1))
    assert result.winner is not None
    assert result.reason == "时间更新的优先"


def test_confidence_wins_when_time_close() -> None:
    result = resolve_conflict(_memory(0.9, 1), _memory(0.5, 1))
    assert result.winner is not None
    assert result.winner.confidence == 0.9


def test_close_memories_need_arbitration() -> None:
    result = resolve_conflict(_memory(0.8, 1), _memory(0.8, 1))
    assert result.winner is None
    assert result.needs_arbitration


def test_decay_half_life() -> None:
    now = datetime.now(timezone.utc)
    assert decayed_confidence(0.8, now - timedelta(days=90), now) == 0.4
    assert decayed_confidence(0.8, now, now) == 0.8
