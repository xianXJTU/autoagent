"""编排器：检查点、恢复、暂停取消与异常兜底。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from .budget import BudgetExceeded, BudgetLimits
from .graph import build_graph
from .handlers import NodeHandlers
from .state import (
    STAGE_CANCELLED,
    STAGE_FAILED,
    STAGE_PAUSED,
    RunState,
    initial_state,
    validate_transition,
)


class Orchestrator:
    def __init__(
        self,
        handlers: NodeHandlers,
        checkpoint_path: Path,
        limits: BudgetLimits | None = None,
    ) -> None:
        self.handlers = handlers
        self.checkpoint_path = Path(checkpoint_path)
        self.limits = limits or BudgetLimits()
        self._context = None
        self._saver = None
        self.graph = None

    async def __aenter__(self) -> "Orchestrator":
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._context = AsyncSqliteSaver.from_conn_string(str(self.checkpoint_path))
        self._saver = await self._context.__aenter__()
        self.graph = build_graph(self.handlers, self.limits).compile(
            checkpointer=self._saver
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._context is not None:
            await self._context.__aexit__(exc_type, exc, tb)

    def _config(self, run_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": run_id}}

    async def start(
        self, project_id: str, run_id: str, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        state = initial_state(project_id, run_id)
        if extra:
            state.update(extra)
        return await self._invoke(state, run_id)

    async def advance(
        self, run_id: str, updates: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        snapshot = await self.graph.aget_state(self._config(run_id))
        if not snapshot.values:
            raise KeyError(f"运行不存在：{run_id}")
        merged_updates = dict(updates or {})
        if (
            merged_updates.get("approved")
            and snapshot.values.get("stage") == "待审阅"
        ):
            merged_updates["stage"] = "已批准"
        state = {**snapshot.values, **merged_updates}
        target = merged_updates.get("stage")
        if target and target != snapshot.values.get("stage"):
            validate_transition(snapshot.values.get("stage", ""), target)
        return await self._invoke(state, run_id)

    async def get_state(self, run_id: str) -> dict[str, Any]:
        snapshot = await self.graph.aget_state(self._config(run_id))
        return dict(snapshot.values)

    async def pause(self, run_id: str, reason: str = "") -> dict[str, Any]:
        current = await self.get_state(run_id)
        validate_transition(current.get("stage", ""), STAGE_PAUSED)
        await self.graph.aupdate_state(
            self._config(run_id),
            {
                "stage": STAGE_PAUSED,
                "paused_from": current.get("stage", ""),
                "last_error": reason,
            },
        )
        return await self.get_state(run_id)

    async def resume(self, run_id: str) -> dict[str, Any]:
        current = await self.get_state(run_id)
        if current.get("stage") != STAGE_PAUSED:
            raise ValueError("当前不是暂停状态")
        return await self.advance(run_id, {"stage": current.get("paused_from", "")})

    async def cancel(self, run_id: str, reason: str = "") -> dict[str, Any]:
        current = await self.get_state(run_id)
        validate_transition(current.get("stage", ""), STAGE_CANCELLED)
        await self.graph.aupdate_state(
            self._config(run_id),
            {"stage": STAGE_CANCELLED, "last_error": reason},
        )
        return await self.get_state(run_id)

    async def _invoke(self, state: RunState, run_id: str) -> dict[str, Any]:
        try:
            result = await self.graph.ainvoke(state, self._config(run_id))
        except BudgetExceeded as exc:
            await self.graph.aupdate_state(
                self._config(run_id),
                {"stage": STAGE_PAUSED, "last_error": str(exc)},
            )
            result = (await self.graph.aget_state(self._config(run_id))).values
        except Exception as exc:
            await self.graph.aupdate_state(
                self._config(run_id),
                {
                    "stage": STAGE_FAILED,
                    "last_error": f"{type(exc).__name__}: {exc}",
                },
            )
            result = (await self.graph.aget_state(self._config(run_id))).values
        return dict(result)
