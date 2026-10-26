"""统一的脱敏处理。

日志、事件、模型调用记录都必须经过这里，避免密钥与个人隐私落盘或进入评测报告。
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "access_token",
    "refresh_token",
    "private_key",
}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[A-Za-z0-9._\-]{6,}"), "sk-***"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password|passwd|pwd)\b(\s*[:=]\s*)([^\s,;\"'}\]]+)"
        ),
        r"\1\2***",
    ),
    (
        re.compile(r"(?i)(mysql(?:\+pymysql)?://[^:\s/]+:)([^@\s]+)(@)"),
        r"\1***\3",
    ),
]


def redact_text(text: str) -> str:
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_obj(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                result[key] = "***"
            else:
                result[key] = redact_obj(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact_obj(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
