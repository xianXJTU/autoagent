from __future__ import annotations

from backend.app.agents.prompts import (
    CODER_SYSTEM,
    EVALUATOR_SYSTEM,
    PLANNER_SYSTEM,
    REVIEWER_SYSTEM,
)


def test_role_prompts_contain_boundaries() -> None:
    assert "唯一" in PLANNER_SYSTEM
    assert "不修改" in CODER_SYSTEM or "不得修改" in CODER_SYSTEM
    assert "tests/" in REVIEWER_SYSTEM
    assert "证据" in EVALUATOR_SYSTEM
    assert "不得修改业务代码" in REVIEWER_SYSTEM
