from __future__ import annotations

from dataclasses import dataclass

from .state import RunState


class BudgetExceeded(Exception):
    pass


@dataclass
class BudgetLimits:
    seconds: float = 7200.0
    total_tokens: int = 2_000_000
    model_calls: int = 200


def check_budget(state: RunState, limits: BudgetLimits) -> None:
    usage = state.get("usage") or {}
    if float(usage.get("elapsed_seconds", 0)) >= limits.seconds:
        raise BudgetExceeded("运行时长超出预算")
    if int(usage.get("total_tokens", 0)) >= limits.total_tokens:
        raise BudgetExceeded("token 用量超出预算")
    if int(usage.get("model_calls", 0)) >= limits.model_calls:
        raise BudgetExceeded("模型调用次数超出预算")
