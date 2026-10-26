from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_defaults_and_business_constraints() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_name == "autoagent"
    assert settings.autoagent_db_name == "autoagent"
    assert settings.deepseek_model == "deepseek-flash"
    assert settings.max_modules == 7
    assert settings.test_fix_rounds == 5
    assert settings.acceptance_rounds == 2


def test_database_url_encodes_password() -> None:
    settings = Settings(_env_file=None, autoagent_db_password="p@ss/w:rd")
    assert "p%40ss%2Fw%3Ard" in settings.database_url
    assert settings.database_url.startswith("mysql+pymysql://")
    assert "charset=utf8mb4" in settings.database_url
    assert settings.test_database_url.endswith(
        "/autoagent_test?charset=utf8mb4"
    )


def test_runtime_validation_requires_keys() -> None:
    settings = Settings(
        _env_file=None,
        deepseek_api_key="",
        embedding_api_key="",
        embedding_base_url="",
    )
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        settings.validate_runtime()


def test_fake_mode_allows_missing_keys() -> None:
    settings = Settings(_env_file=None, fake_llm=True, deepseek_api_key="")
    settings.validate_runtime()


def test_module_cap_is_enforced() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_modules=8)
