"""LangGraph 图。"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from .budget import BudgetLimits, check_budget
from .handlers import NodeHandlers
from .state import (
    STAGE_ACCEPTING,
    STAGE_ALIGNING,
    STAGE_APPROVED,
    STAGE_CODING,
    STAGE_DELIVERED,
    STAGE_MERGING,
    STAGE_PLANNING,
    STAGE_PLAN_READY,
    STAGE_REVIEW,
    STAGE_TESTING,
    STOP_STAGES,
    RunState,
    validate_transition,
)

NODE_NAMES = [
    "align",
    "plan",
    "test_design",
    "dispatch",
    "code",
    "merge",
    "accept",
    "deliver",
    "evaluate",
]


def route_start(state: RunState) -> str:
    stage = state.get("stage", STAGE_ALIGNING)
    if stage == STAGE_ALIGNING:
        return "align"
    if stage == STAGE_REVIEW:
        return "plan" if state.get("approved") else "end"
    if stage == STAGE_APPROVED:
        return "plan"
    if stage == STAGE_PLANNING:
        return "test_design"
    if stage == STAGE_PLAN_READY:
        return "dispatch"
    if stage == STAGE_CODING:
        return "code"
    if stage == STAGE_TESTING:
        return "merge"
    if stage == STAGE_MERGING:
        return "accept"
    if stage == STAGE_ACCEPTING:
        return "deliver"
    if stage == STAGE_DELIVERED and not state.get("evaluated"):
        return "evaluate"
    return "end"


def _guarded(
    name: str, handler: Callable[[RunState], Any], limits: BudgetLimits
) -> Callable[[RunState], Any]:
    async def node(state: RunState) -> dict:
        check_budget(state, limits)
        updates = await handler(state)
        if not isinstance(updates, dict):
            raise TypeError(f"节点 {name} 必须返回字典")
        target = updates.get("stage")
        if target and target != state.get("stage"):
            validate_transition(state.get("stage", STAGE_ALIGNING), target)
        return updates

    node.__name__ = f"node_{name}"
    return node


def _chain_after(node: str, next_node: str) -> Callable[[RunState], str]:
    def route(state: RunState) -> str:
        if state.get("stage") in STOP_STAGES:
            return "end"
        return next_node

    route.__name__ = f"after_{node}"
    return route


def build_graph(handlers: NodeHandlers, limits: BudgetLimits | None = None):
    limits = limits or BudgetLimits()
    builder = StateGraph(RunState)
    for name in NODE_NAMES:
        builder.add_node(name, _guarded(name, getattr(handlers, name), limits))

    builder.add_conditional_edges(
        START,
        route_start,
        {
            "align": "align",
            "plan": "plan",
            "dispatch": "dispatch",
            "code": "code",
            "merge": "merge",
            "accept": "accept",
            "evaluate": "evaluate",
            "end": END,
        },
    )
    builder.add_edge("align", END)
    builder.add_conditional_edges(
        "plan", _chain_after("plan", "test_design"),
        {"test_design": "test_design", "end": END},
    )
    builder.add_conditional_edges(
        "test_design", _chain_after("test_design", "dispatch"),
        {"dispatch": "dispatch", "end": END},
    )
    builder.add_conditional_edges(
        "dispatch", _chain_after("dispatch", "code"),
        {"code": "code", "end": END},
    )
    builder.add_conditional_edges(
        "code", _chain_after("code", "merge"),
        {"merge": "merge", "end": END},
    )
    builder.add_conditional_edges(
        "merge", _chain_after("merge", "accept"),
        {"accept": "accept", "end": END},
    )
    builder.add_conditional_edges(
        "accept", _chain_after("accept", "deliver"),
        {"deliver": "deliver", "end": END},
    )
    builder.add_conditional_edges(
        "deliver", _chain_after("deliver", "evaluate"),
        {"evaluate": "evaluate", "end": END},
    )
    builder.add_edge("evaluate", END)
    return builder
