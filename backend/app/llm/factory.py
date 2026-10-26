from __future__ import annotations

from ..config import Settings
from .base import ChatProvider, EmbeddingProvider
from .deepseek import DeepSeekProvider
from .embeddings import QwenEmbeddingProvider
from .fake import FakeLLMProvider


def build_chat_provider(settings: Settings) -> ChatProvider:
    if settings.fake_llm:
        return FakeLLMProvider()
    return DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.fake_llm:
        return FakeLLMProvider()
    return QwenEmbeddingProvider(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        batch_size=settings.embedding_batch_size,
    )
