from __future__ import annotations

from backend.app.config import Settings
from backend.app.memory.context import ContextManager, estimate_messages_tokens


def _settings() -> Settings:
    base = Settings()
    return base.model_copy(
        update={
            "fake_llm": True,
            "model_context_window": 1000,
            "compression_ratio": 0.5,
            "compression_absolute_tokens": 500,
            "compression_min_tokens": 100,
            "recent_tokens_keep": 60,
            "max_compressions_per_session": 3,
        }
    )


def _messages(count: int, size: int = 40) -> list[dict[str, str]]:
    return [
        {"role": "user", "content": f"消息{index}:" + ("内容" * size)}
        for index in range(count)
    ]


async def test_threshold_and_reinjection() -> None:
    manager = ContextManager(_settings())
    messages = _messages(12)
    assert estimate_messages_tokens(messages) >= manager.trigger_tokens
    assert manager.should_compress(messages)

    seen: list[list[dict]] = []

    async def summarize(older):
        seen.append(older)
        return "较早对话摘要"

    outcome = await manager.compress(
        messages, summarize, hard_constraints=["必须使用 MySQL", "测试必须通过"]
    )
    assert outcome.compressed
    assert seen and len(seen[0]) > 0
    text = "\n".join(message["content"] for message in outcome.messages)
    assert "必须使用 MySQL" in text
    assert "历史摘要" in text
    assert outcome.archived == seen[0]
    assert outcome.messages[-1] == messages[-1]


async def test_three_compressions_require_new_session() -> None:
    manager = ContextManager(_settings())
    messages = _messages(12)

    async def summarize(older):
        return "摘要"

    flags = []
    for _ in range(3):
        outcome = await manager.compress(messages, summarize, ["约束"])
        flags.append(outcome.new_session_required)
    assert flags == [False, False, True]
    assert manager.compression_count == 0


async def test_below_threshold_is_noop() -> None:
    manager = ContextManager(_settings())
    messages = [{"role": "user", "content": "短消息"}]
    outcome = await manager.compress(messages, lambda older: None, [])
    assert not outcome.compressed
    assert outcome.messages == messages
