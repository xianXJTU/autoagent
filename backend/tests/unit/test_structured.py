from __future__ import annotations

import pytest
from pydantic import BaseModel

from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.llm.structured import chat_structured, extract_json


class Demo(BaseModel):
    name: str
    count: int


def test_extract_json_handles_fences() -> None:
    assert extract_json('```json\n{"name":"a","count":1}\n```') == {
        "name": "a",
        "count": 1,
    }
    assert extract_json('前缀 {"name":"b","count":2} 后缀')["count"] == 2


def test_extract_json_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        extract_json("没有对象")


async def test_structured_repairs_bad_output(memory_session_factory) -> None:
    provider = FakeLLMProvider(
        [
            {"content": "不是 JSON"},
            {"content": '{"name":"demo","count":2}'},
        ]
    )
    service = ModelService(provider, provider, memory_session_factory)
    result, _ = await chat_structured(
        service, Demo, [{"role": "user", "content": "给个 JSON"}]
    )
    assert result.name == "demo"
    assert result.count == 2
    assert len(provider.calls) == 2
    assert any(
        "json" in message["content"].lower()
        for message in provider.calls[0]["messages"]
    )
