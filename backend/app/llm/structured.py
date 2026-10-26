"""结构化输出解析与修复。"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .service import ModelService

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("输出中没有 JSON 对象")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("JSON 顶层必须是对象")
    return value


async def chat_structured(
    service: ModelService,
    schema: type[SchemaT],
    messages: list[dict[str, Any]],
    run_id: str | None = None,
    agent_id: str | None = None,
    purpose: str = "",
    max_repair: int = 2,
) -> tuple[SchemaT, Any]:
    conversation = list(messages)
    last_error: Exception | None = None
    for _ in range(max_repair + 1):
        result = await service.chat(
            conversation,
            run_id=run_id,
            agent_id=agent_id,
            purpose=purpose,
            response_format={"type": "json_object"},
        )
        try:
            return schema.model_validate(extract_json(result.content)), result
        except (ValueError, ValidationError) as exc:
            last_error = exc
            conversation = conversation + [
                {"role": "assistant", "content": result.content},
                {
                    "role": "user",
                    "content": f"上一次输出无法解析：{exc}。请只输出符合要求的 JSON 对象。",
                },
            ]
    raise ValueError(f"结构化输出修复失败：{last_error}")
