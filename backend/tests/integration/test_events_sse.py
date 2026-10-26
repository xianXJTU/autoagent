from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from backend.app.config import Settings
from backend.app.db.models import Project, Run
from backend.app.db.session import build_session_factory
from backend.app.events.service import EventService
from backend.app.main import create_app


async def test_sse_backlog_after_reconnect(
    db_engine, db_session, test_settings: Settings
) -> None:
    project = Project(name="SSE 项目", workspace_path="/tmp/sse")
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-sse")
    db_session.add(run)
    db_session.commit()

    factory = build_session_factory(db_engine)
    service = EventService(factory, test_settings.data_root)
    await service.emit(run.id, "ready", stage="对齐中", payload={"n": 1})

    app = create_app(test_settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "GET", f"/api/runs/{run.id}/events/stream?after=0&limit=1"
        ) as response:
            assert response.status_code == 200
            lines = response.aiter_lines()
            async for line in lines:
                if line.startswith("data: "):
                    assert '"n":1' in line.replace(" ", "")
                    break
