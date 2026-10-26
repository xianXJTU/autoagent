"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes.projects import router as projects_router
from .api.routes.runs import router as runs_router
from .config import Settings, get_settings
from .events.router import router as events_router
from .logging_config import configure_logging
from .redaction import redact_text
from .services.container import ServiceContainer


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    current.validate_runtime()
    current.ensure_dirs()
    configure_logging()

    container = ServiceContainer(current)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        container.close()

    app = FastAPI(
        title=current.app_name,
        version=current.app_version,
        lifespan=lifespan,
    )
    app.state.settings = current
    app.state.services = container
    app.state.engine = container.engine
    app.state.session_factory = container.session_factory
    app.state.event_bus = container.events.bus

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(events_router)
    app.include_router(projects_router)
    app.include_router(runs_router)

    @app.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger("autoagent.api").exception("未处理异常")
        return JSONResponse(
            status_code=500,
            content={
                "detail": redact_text(f"{type(exc).__name__}: {exc}")[:2000]
            },
        )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "app": current.app_name,
            "version": current.app_version,
        }

    frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend.exists():
        app.mount("/", StaticFiles(directory=str(frontend), html=True), name="frontend")

    return app


app = create_app()
