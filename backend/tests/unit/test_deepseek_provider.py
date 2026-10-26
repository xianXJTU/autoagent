from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.llm.deepseek import DeepSeekProvider
from backend.app.llm.embeddings import QwenEmbeddingProvider


class _Retryable(Exception):
    status_code = 500


class _Completions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(outcomes) -> SimpleNamespace:
    return SimpleNamespace(
        chat=SimpleNamespace(completions=_Completions(outcomes))
    )


def _response(content: str = "ok", tool: bool = False) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=None)
    if tool:
        message.tool_calls = [
            SimpleNamespace(
                id="call-1",
                function=SimpleNamespace(
                    name="write_file", arguments='{"path":"a.py"}'
                ),
            )
        ]
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        model="deepseek-flash",
    )


async def test_retries_then_succeeds() -> None:
    client = _client([_Retryable("boom"), _response("成功")])
    provider = DeepSeekProvider("k", "http://x", "deepseek-flash", client=client)
    result = await provider.chat([{"role": "user", "content": "hi"}])
    assert result.content == "成功"
    assert result.prompt_tokens == 10
    assert client.chat.completions.calls == 2


async def test_parses_tool_calls() -> None:
    client = _client([_response("", tool=True)])
    provider = DeepSeekProvider("k", "http://x", "deepseek-flash", client=client)
    result = await provider.chat([{"role": "user", "content": "hi"}])
    assert result.tool_calls[0].name == "write_file"
    assert "a.py" in result.tool_calls[0].arguments


async def test_json_mode_adds_json_hint() -> None:
    client = _client([_response('{"a": 1}')])
    provider = DeepSeekProvider("k", "http://x", "deepseek-flash", client=client)
    await provider.chat(
        [{"role": "user", "content": "请给出一个对象"}],
        response_format={"type": "json_object"},
    )
    messages = client.chat.completions.last_kwargs["messages"]
    assert any("json" in message["content"].lower() for message in messages)


async def test_gives_up_after_retries() -> None:
    client = _client([_Retryable("a"), _Retryable("b")])
    provider = DeepSeekProvider(
        "k", "http://x", "deepseek-flash", max_retries=1, client=client
    )
    with pytest.raises(_Retryable):
        await provider.chat([{"role": "user", "content": "hi"}])


class _Embeddings:
    async def create(self, model, input):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input],
            usage=SimpleNamespace(prompt_tokens=len(input)),
        )


async def test_embedding_batches() -> None:
    client = SimpleNamespace(embeddings=_Embeddings())
    provider = QwenEmbeddingProvider(
        "k", "http://x", "qwen3.7-text-embedding-flash", batch_size=2, client=client
    )
    result = await provider.embed(["a", "b", "c"])
    assert len(result.vectors) == 3
    assert result.prompt_tokens == 3
