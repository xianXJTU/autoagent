"""Qwen 文本向量客户端（OpenAI 兼容接口）。"""

from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI

from .base import EmbeddingResult
from .deepseek import _is_retryable


class QwenEmbeddingProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        batch_size: int = 16,
        timeout: float = 60.0,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.client = client or AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors: list[list[float]] = []
        tokens = 0
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = await self._embed_batch(batch)
            vectors.extend([item.embedding for item in response.data])
            usage = getattr(response, "usage", None)
            tokens += getattr(usage, "prompt_tokens", 0) or 0
        return EmbeddingResult(vectors=vectors, prompt_tokens=tokens, model=self.model)

    async def _embed_batch(self, batch: list[str]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.client.embeddings.create(
                    model=self.model, input=batch
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.max_retries or not _is_retryable(exc):
                    raise
                await asyncio.sleep(min(2**attempt, 8))
        raise RuntimeError(f"向量调用失败：{last_error}")
