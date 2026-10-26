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
    return Settings(
        _env_file=None,
        fake_llm=True,
        autoagent_db_password="test",
        workspace_root=tmp_path / "workspace",
        data_root=tmp_path / "data",
        checkpoint_path=tmp_path / "data" / "checkpoints.sqlite",
        chroma_path=tmp_path / "data" / "chroma",
    )
