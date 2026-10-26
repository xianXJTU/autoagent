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


def ensure_json_hint(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DeepSeek 的 json_object 模式要求提示词里出现 json 字样。"""
    if any("json" in str(message.get("content", "")).lower() for message in messages):
        return list(messages)
    return [
        *messages,
        {
            "role": "system",
            "content": "你必须只输出一个合法的 JSON 对象，不要输出任何 JSON 之外的文字。",
        },
    ]


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
