from __future__ import annotations

from types import SimpleNamespace

from backend.app.llm.base import StreamDelta
from backend.app.llm.deepseek import DeepSeekProvider
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.structured import chat_structured_stream
from pydantic import BaseModel


class Demo(BaseModel):
    name: str
    count: int


class _AsyncChunks:
    def __init__(self, chunks):
        self.chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.chunks)
        except StopIteration:
            raise StopAsyncIteration


class _StreamingCompletions:
    def __init__(self, chunks):
        self.chunks = chunks
        self.last_kwargs = None

    async def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _AsyncChunks(self.chunks)


def _delta_chunk(content="", reasoning=""):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, reasoning_content=reasoning)
            )
        ],
        usage=None,
    )


def _usage_chunk(prompt=10, completion=5):
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


async def test_deepseek_stream_yields_reasoning_and_usage() -> None:
    completions = _StreamingCompletions(
        [_delta_chunk(reasoning="先想"), _delta_chunk(content="OK"), _usage_chunk()]
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = DeepSeekProvider("k", "http://x", "deepseek-flash", client=client)

    deltas = [delta async for delta in provider.chat_stream([{"role": "user", "content": "hi"}])]
    assert deltas[0].reasoning == "先想"
    assert deltas[1].content == "OK"
    assert deltas[-1].done
    assert deltas[-1].prompt_tokens == 10
    assert completions.last_kwargs["stream"] is True


async def test_deepseek_stream_json_hint() -> None:
    completions = _StreamingCompletions([_delta_chunk(content='{"a":1}'), _usage_chunk()])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = DeepSeekProvider("k", "http://x", "deepseek-flash", client=client)

    async for _ in provider.chat_stream(
        [{"role": "user", "content": "请给对象"}],
        response_format={"type": "json_object"},
    ):
        pass
    messages = completions.last_kwargs["messages"]
    assert any("json" in message["content"].lower() for message in messages)


async def test_fake_stream_and_structured_stream() -> None:
    provider = FakeLLMProvider(
        [{"reasoning": "先想一下", "content": '{"name":"demo","count":2}'}]
    )
    seen: list[tuple[str, str]] = []

    async def consume():
        parts = []
        async for delta in provider.chat_stream([{"role": "user", "content": "hi"}]):
            if delta.reasoning:
                seen.append(("reasoning", delta.reasoning))
            if delta.content:
                parts.append(delta.content)
                seen.append(("content", delta.content))
        return "".join(parts)

    text = await consume()
    assert "demo" in text
    assert seen[0][0] == "reasoning"

    provider2 = FakeLLMProvider(
        [{"reasoning": "想", "content": '{"name":"demo","count":2}'}]
    )
    collected: list[tuple[str, str]] = []
    result, _ = await chat_structured_stream(
        _StubService(provider2),
        Demo,
        [{"role": "user", "content": "给 JSON"}],
        lambda kind, text: collected.append((kind, text)),
    )
    assert result.name == "demo"
    assert any(kind == "reasoning" for kind, _ in collected)
    assert any(kind == "content" for kind, _ in collected)


class _StubService:
    def __init__(self, provider: FakeLLMProvider) -> None:
        self.provider = provider

    async def chat_stream(self, messages, **kwargs):
        allowed = {"tools", "response_format", "temperature", "max_tokens"}
        filtered = {key: value for key, value in kwargs.items() if key in allowed}
        async for delta in self.provider.chat_stream(messages, **filtered):
            yield delta
