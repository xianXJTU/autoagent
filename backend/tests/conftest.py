from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Settings  # noqa: E402


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    # 先读本地 .env（保留真实数据库凭据），再覆盖测试开关与临时目录。
    base = Settings()
    return base.model_copy(
        update={
            "fake_llm": True,
            "autoagent_db_name": base.autoagent_db_test_name,
            "workspace_root": tmp_path / "workspace",
            "data_root": tmp_path / "data",
            "checkpoint_path": tmp_path / "data" / "checkpoints.sqlite",
            "chroma_path": tmp_path / "data" / "chroma",
        }
    )


@pytest.fixture
def db_engine(test_settings: Settings):
    from backend.app.db.models import Base
    from backend.app.db.session import build_engine

    engine = build_engine(test_settings.test_database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    from backend.app.db.session import build_session_factory

    factory = build_session_factory(db_engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def memory_session_factory(db_engine):
    from backend.app.db.session import build_session_factory

    return build_session_factory(db_engine)


@pytest.fixture
def api_app(test_settings: Settings, db_engine):
    from backend.app.main import create_app

    return create_app(test_settings)
