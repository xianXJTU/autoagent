"""图节点处理函数。真正的代理逻辑在后续模块注入。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from .state import RunState

NodeResult = dict
NodeHandler = Callable[[RunState], Awaitable[NodeResult]]


async def _noop(state: RunState) -> NodeResult:
    return {}


@dataclass
class NodeHandlers:
    align: NodeHandler = _noop
    plan: NodeHandler = _noop
    test_design: NodeHandler = _noop
    dispatch: NodeHandler = _noop
    code: NodeHandler = _noop
    merge: NodeHandler = _noop
    accept: NodeHandler = _noop
    deliver: NodeHandler = _noop
    evaluate: NodeHandler = _noop
