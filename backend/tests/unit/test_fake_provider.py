from __future__ import annotations

import pytest

from backend.app.llm.base import ChatResult
from backend.app.llm.fake import FakeLLMProvider


async def test_scripted_chat_and_deterministic_embeddings() -> None:
    provider = FakeLLMProvider(
        [ChatResult(content="第一", prompt_tokens=3), {"content": "第二"}]
    )
    first = await provider.chat([{"role": "user", "content": "hi"}])
    second = await provider.chat([{"role": "user", "content": "hi"}])
    assert first.content == "第一"
    assert second.content == "第二"

    result = await provider.embed(["同样的文本", "同样的文本"])
    assert len(result.vectors) == 2
    assert len(result.vectors[0]) == 1024
    assert result.vectors[0] == result.vectors[1]


async def test_empty_script_raises() -> None:
    provider = FakeLLMProvider([])
    with pytest.raises(RuntimeError):
        await provider.chat([{"role": "user", "content": "hi"}])
