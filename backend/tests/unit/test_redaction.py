from __future__ import annotations

from backend.app.redaction import redact_obj, redact_text


def test_masks_api_key() -> None:
    output = redact_text("请求头 Bearer sk-abc123DEF456ghi789")
    assert "abc123DEF456ghi789" not in output
    assert "***" in output


def test_masks_password_assignment() -> None:
    output = redact_text("password=123456 token=abc")
    assert "123456" not in output
    assert "token=***" in output or "token=abc" not in output


def test_masks_database_url_password() -> None:
    output = redact_text(
        "mysql+pymysql://autoagent_app:secretpass@127.0.0.1:3306/autoagent"
    )
    assert "secretpass" not in output


def test_masks_nested_sensitive_keys() -> None:
    output = redact_obj(
        {
            "password": "123456",
            "nested": {"api_key": "value", "content": "sk-abcdef123456"},
            "items": [{"token": "t"}],
        }
    )
    assert output["password"] == "***"
    assert output["nested"]["api_key"] == "***"
    assert "sk-abcdef123456" not in output["nested"]["content"]
    assert output["items"][0]["token"] == "***"
