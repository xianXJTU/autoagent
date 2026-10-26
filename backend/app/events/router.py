from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from .schema import format_sse
from .service import EventService

router = APIRouter(prefix="/api/runs/{run_id}/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    run_id: str,
    request: Request,
    after: int = 0,
    limit: int | None = Query(default=None, ge=1),
) -> StreamingResponse:
    settings = request.app.state.settings
    bus = request.app.state.event_bus
    service = EventService(request.app.state.session_factory, settings.data_root, bus)

    async def generator():
        sent = 0
        for event in service.list_after(run_id, after):
            yield format_sse(event)
            sent += 1
            if limit is not None and sent >= limit:
                return
        queue = bus.subscribe(run_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield format_sse(event)
                sent += 1
                if limit is not None and sent >= limit:
                    break
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
