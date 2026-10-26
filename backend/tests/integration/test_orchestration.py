from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.orchestration.budget import BudgetLimits
from backend.app.orchestration.handlers import NodeHandlers
from backend.app.orchestration.orchestrator import Orchestrator
from backend.app.orchestration.state import InvalidTransition


def _handlers(log: list[str]) -> NodeHandlers:
    async def align(state):
        log.append("align")
        return {"stage": "待审阅"}

    async def plan(state):
        log.append("plan")
        return {"stage": "计划中"}

    async def test_design(state):
        log.append("test_design")
        return {"stage": "计划就绪"}

    async def dispatch(state):
        log.append("dispatch")
        return {"stage": "编码中"}

    async def code(state):
        log.append("code")
        return {"stage": "测试中"}

    async def merge(state):
        log.append("merge")
        return {"stage": "合并中"}

    async def accept(state):
        log.append("accept")
        return {"stage": "验收中"}

    async def deliver(state):
        log.append("deliver")
        return {"stage": "已交付"}

    async def evaluate(state):
        log.append("evaluate")
        return {"evaluated": True}

    return NodeHandlers(
        align=align,
        plan=plan,
        test_design=test_design,
        dispatch=dispatch,
        code=code,
        merge=merge,
        accept=accept,
        deliver=deliver,
        evaluate=evaluate,
    )


async def test_full_chain_and_no_repeat(tmp_path: Path) -> None:
    log: list[str] = []
    async with Orchestrator(_handlers(log), tmp_path / "cp.sqlite") as orchestrator:
        first = await orchestrator.start("p1", "r1")
        assert first["stage"] == "待审阅"
        assert log == ["align"]

        done = await orchestrator.advance("r1", {"approved": True})
        assert done["stage"] == "已交付"
        assert done["evaluated"] is True
        assert log == [
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

        again = await orchestrator.advance("r1", {})
        assert log == [
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
        assert again["stage"] == "已交付"


async def test_checkpoint_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "cp.sqlite"
    log: list[str] = []
    async with Orchestrator(_handlers(log), path) as first:
        await first.start("p1", "r1")

    async with Orchestrator(_handlers(log), path) as second:
        state = await second.get_state("r1")
        assert state["stage"] == "待审阅"
        done = await second.advance("r1", {"approved": True})
        assert done["stage"] == "已交付"
        assert "plan" in log


async def test_budget_pauses(tmp_path: Path) -> None:
    log: list[str] = []
    limits = BudgetLimits(seconds=0)
    async with Orchestrator(_handlers(log), tmp_path / "cp.sqlite", limits) as orchestrator:
        state = await orchestrator.start("p1", "r1")
        assert state["stage"] == "暂停"
        assert "预算" in state["last_error"]


async def test_invalid_stage_update_is_rejected(tmp_path: Path) -> None:
    async with Orchestrator(_handlers([]), tmp_path / "cp.sqlite") as orchestrator:
        await orchestrator.start("p1", "r1")
        with pytest.raises(InvalidTransition):
            await orchestrator.advance("r1", {"stage": "已交付"})


async def test_pause_and_resume(tmp_path: Path) -> None:
    log: list[str] = []
    async with Orchestrator(_handlers(log), tmp_path / "cp.sqlite") as orchestrator:
        await orchestrator.start("p1", "r1")
        paused = await orchestrator.pause("r1", "用户暂停")
        assert paused["stage"] == "暂停"
        resumed = await orchestrator.resume("r1")
        assert resumed["stage"] == "待审阅"
