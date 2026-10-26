"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings, get_settings
from .logging_config import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    current.validate_runtime()
    current.ensure_dirs()
    configure_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    app = FastAPI(
        title=current.app_name,
        version=current.app_version,
        lifespan=lifespan,
    )
    app.state.settings = current

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "app": current.app_name,
            "version": current.app_version,
        }

    return app


app = create_app()
