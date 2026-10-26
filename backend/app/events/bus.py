"""运行事件的内存广播。"""

from __future__ import annotations

import asyncio

from .schema import EventOut


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[EventOut]]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue[EventOut]:
        queue: asyncio.Queue[EventOut] = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[EventOut]) -> None:
        subscribers = self._subscribers.get(run_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(run_id, None)

    async def publish(self, run_id: str, event: EventOut) -> None:
        for queue in list(self._subscribers.get(run_id, set())):
            queue.put_nowait(event)

    def subscriber_count(self, run_id: str) -> int:
        return len(self._subscribers.get(run_id, set()))
