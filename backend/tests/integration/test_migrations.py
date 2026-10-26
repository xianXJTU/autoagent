from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend.app.config import Settings
from backend.app.db.models import Base

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_TABLES = {
    "projects",
    "runs",
    "messages",
    "documents",
    "modules",
    "events",
    "memories",
    "skills",
    "skill_usage",
    "tests",
    "evaluations",
    "model_calls",
    "tool_calls",
}


def _alembic_config(settings: Settings) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.test_database_url)
    return config


def test_upgrade_and_downgrade(test_settings: Settings) -> None:
    engine = create_engine(test_settings.test_database_url, future=True)
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))

    config = _alembic_config(test_settings)
    command.upgrade(config, "head")

    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables

    command.downgrade(config, "base")
    tables_after = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.isdisjoint(tables_after)

    command.upgrade(config, "head")
    tables_final = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= tables_final
    engine.dispose()
