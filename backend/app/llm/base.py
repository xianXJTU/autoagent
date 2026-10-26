from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ToolCallOut(BaseModel):
    id: str = ""
    name: str
    arguments: str = "{}"


class ChatResult(BaseModel):
    content: str = ""
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    raw: dict[str, Any] | None = None


class EmbeddingResult(BaseModel):
    vectors: list[list[float]]
    prompt_tokens: int = 0
    model: str = ""


class ChatProvider(Protocol):
    model: str

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult: ...


class EmbeddingProvider(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...
