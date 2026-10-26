"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings, get_settings
from .db.session import build_engine, build_session_factory
from .events.bus import EventBus
from .events.router import router as events_router
from .logging_config import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    current.validate_runtime()
    current.ensure_dirs()
    configure_logging()

    engine = build_engine(current.database_url)
    session_factory = build_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title=current.app_name,
        version=current.app_version,
        lifespan=lifespan,
    )
    app.state.settings = current
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.event_bus = EventBus()
    app.include_router(events_router)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "app": current.app_name,
            "version": current.app_version,
        }

    return app


app = create_app()
