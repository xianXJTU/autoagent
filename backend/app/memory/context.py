"""上下文压缩。

token 数用启发式估算（中文约两字符一 token，英文也按字符近似），
真实调用仍以接口返回的 usage 为准；这里只用于触发阈值判断。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..config import Settings


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(estimate_tokens(str(message.get("content", ""))) + 4 for message in messages)


@dataclass
class CompressionOutcome:
    messages: list[dict[str, Any]]
    compressed: bool
    summary: str = ""
    archived: list[dict[str, Any]] = field(default_factory=list)
    compression_count: int = 0
    new_session_required: bool = False


class ContextManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.compression_count = 0

    @property
    def trigger_tokens(self) -> int:
        by_window = int(self.settings.model_context_window * self.settings.compression_ratio)
        return max(
            self.settings.compression_min_tokens,
            min(by_window, self.settings.compression_absolute_tokens),
        )

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        return estimate_messages_tokens(messages) >= self.trigger_tokens

    async def compress(
        self,
        messages: list[dict[str, Any]],
        summarize: Callable[[list[dict[str, Any]]], Awaitable[str]],
        hard_constraints: list[str] | None = None,
    ) -> CompressionOutcome:
        if not self.should_compress(messages):
            return CompressionOutcome(
                messages=list(messages),
                compressed=False,
                compression_count=self.compression_count,
            )

        recent: list[dict[str, Any]] = []
        recent_tokens = 0
        for message in reversed(messages):
            cost = estimate_messages_tokens([message])
            if recent and recent_tokens + cost > self.settings.recent_tokens_keep:
                break
            recent.insert(0, message)
            recent_tokens += cost

        archived = messages[: len(messages) - len(recent)]
        summary = await summarize(archived) if archived else ""

        rebuilt: list[dict[str, Any]] = []
        if hard_constraints:
            rebuilt.append(
                {
                    "role": "system",
                    "content": "硬约束（来自磁盘，必须遵守）：\n"
                    + "\n".join(f"- {item}" for item in hard_constraints),
                }
            )
        if summary:
            rebuilt.append({"role": "system", "content": f"历史摘要：{summary}"})
        rebuilt.extend(recent)

        self.compression_count += 1
        new_session = (
            self.compression_count >= self.settings.max_compressions_per_session
        )
        result = CompressionOutcome(
            messages=rebuilt,
            compressed=True,
            summary=summary,
            archived=archived,
            compression_count=self.compression_count,
            new_session_required=new_session,
        )
        if new_session:
            self.compression_count = 0
        return result

    def reset_session(self) -> None:
        self.compression_count = 0
