"""测试替身：脚本化对话与确定性向量。"""

from __future__ import annotations

import hashlib
from typing import Any

from .base import ChatResult, EmbeddingResult


class FakeLLMProvider:
    model = "fake-model"

    def __init__(
        self,
        responses: list[ChatResult | dict[str, Any]] | None = None,
        embedding_dim: int = 1024,
    ) -> None:
        self.responses = list(responses or [])
        self.embedding_dim = embedding_dim
        self.calls: list[dict[str, Any]] = []
        self.embedding_calls: list[list[str]] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "response_format": response_format,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if not self.responses:
            raise RuntimeError("测试替身没有剩余响应")
        item = self.responses.pop(0)
        if isinstance(item, ChatResult):
            return item
        return ChatResult(**item)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        self.embedding_calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vector = [
                (digest[index % len(digest)] / 255.0) * 2 - 1
                for index in range(self.embedding_dim)
            ]
            vectors.append(vector)
        return EmbeddingResult(
            vectors=vectors,
            prompt_tokens=sum(max(1, len(text) // 2) for text in texts),
            model=self.model,
        )
