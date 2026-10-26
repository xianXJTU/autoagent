from __future__ import annotations

import pytest

from backend.app.orchestration.state import (
    InvalidTransition,
    STAGE_CODING,
    STAGE_DELIVERED,
    STAGE_PAUSED,
    validate_transition,
)


def test_valid_transition() -> None:
    validate_transition("待审阅", "已批准")
    validate_transition(STAGE_CODING, "测试中")


def test_pause_is_global() -> None:
    validate_transition("编码中", STAGE_PAUSED)


def test_invalid_transition() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition("对齐中", STAGE_DELIVERED)


def test_terminal_cannot_pause() -> None:
    with pytest.raises(InvalidTransition):
        validate_transition("取消", STAGE_PAUSED)
