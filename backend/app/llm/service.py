"""模型调用服务：统一记账与错误记录。"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ..db.models import ModelCall
from .base import (
    ChatProvider,
    ChatResult,
    EmbeddingProvider,
    EmbeddingResult,
)


class ModelService:
    def __init__(
        self,
        chat_provider: ChatProvider,
        embedding_provider: EmbeddingProvider,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.chat_provider = chat_provider
        self.embedding_provider = embedding_provider
        self.session_factory = session_factory

    def _record(
        self,
        run_id: str | None,
        agent_id: str | None,
        purpose: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        status: str,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                ModelCall(
                    run_id=run_id,
                    agent_id=agent_id,
                    purpose=purpose,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    status=status,
                )
            )
            session.commit()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        run_id: str | None = None,
        agent_id: str | None = None,
        purpose: str = "",
        **kwargs: Any,
    ) -> ChatResult:
        started = time.perf_counter()
        try:
            result = await self.chat_provider.chat(messages, **kwargs)
        except Exception:
            self._record(
                run_id,
                agent_id,
                purpose,
                self.chat_provider.model,
                0,
                0,
                int((time.perf_counter() - started) * 1000),
                "error",
            )
            raise
        self._record(
            run_id,
            agent_id,
            purpose,
            result.model or self.chat_provider.model,
            result.prompt_tokens,
            result.completion_tokens,
            int((time.perf_counter() - started) * 1000),
            "ok",
        )
        return result

    async def embed(
        self,
        texts: list[str],
        run_id: str | None = None,
        agent_id: str | None = None,
        purpose: str = "embedding",
    ) -> EmbeddingResult:
        started = time.perf_counter()
        try:
            result = await self.embedding_provider.embed(texts)
        except Exception:
            self._record(
                run_id,
                agent_id,
                purpose,
                self.embedding_provider.model,
                0,
                0,
                int((time.perf_counter() - started) * 1000),
                "error",
            )
            raise
        self._record(
            run_id,
            agent_id,
            purpose,
            result.model or self.embedding_provider.model,
            result.prompt_tokens,
            0,
            int((time.perf_counter() - started) * 1000),
            "ok",
        )
        return result
