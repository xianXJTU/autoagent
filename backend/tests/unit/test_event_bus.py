from __future__ import annotations

from datetime import datetime, timezone

from backend.app.events.bus import EventBus
from backend.app.events.schema import EventOut, format_sse


def _event(seq: int) -> EventOut:
    return EventOut(
        run_id="run-1",
        seq=seq,
        type="test",
        stage="unit",
        agent_id="a",
        payload={"seq": seq},
        created_at=datetime.now(timezone.utc),
    )


async def test_bus_fans_out_to_all_subscribers() -> None:
    bus = EventBus()
    first = bus.subscribe("run-1")
    second = bus.subscribe("run-1")
    await bus.publish("run-1", _event(1))

    assert (await first.get()).seq == 1
    assert (await second.get()).seq == 1
    assert bus.subscriber_count("run-1") == 2


async def test_bus_unsubscribe() -> None:
    bus = EventBus()
    queue = bus.subscribe("run-1")
    bus.unsubscribe("run-1", queue)
    assert bus.subscriber_count("run-1") == 0


def test_sse_format_contains_id_and_data() -> None:
    frame = format_sse(_event(7))
    assert frame.startswith("id: 7\n")
    assert "data: " in frame
    assert frame.endswith("\n\n")
