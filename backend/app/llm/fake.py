"""测试替身：脚本化对话与确定性向量。"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from .base import ChatResult, EmbeddingResult

_TOKEN = re.compile(r"[A-Za-z0-9_]+|[一-鿿]+")


def _lexical_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for chunk in _TOKEN.findall(text.lower()):
        if re.fullmatch(r"[一-鿿]+", chunk):
            tokens.extend(chunk)
            tokens.extend(chunk[index : index + 2] for index in range(len(chunk) - 1))
        else:
            tokens.append(chunk)
    return tokens


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
            vector = [0.0] * self.embedding_dim
            for token in _lexical_tokens(text):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                value = int.from_bytes(digest[:8], "big")
                index = value % self.embedding_dim
                sign = 1.0 if (value >> 63) & 1 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(item * item for item in vector)) or 1.0
            vectors.append([item / norm for item in vector])
        return EmbeddingResult(
            vectors=vectors,
            prompt_tokens=sum(max(1, len(text) // 2) for text in texts),
            model=self.model,
        )
