"""DeepSeek 对话客户端（OpenAI 兼容接口）。"""

from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI

from .base import ChatResult, ToolCallOut, ensure_json_hint


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (429,) or (isinstance(status, int) and status >= 500):
        return True
    return type(exc).__name__ in {
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
    }


class DeepSeekProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        max_retries: int = 3,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.client = client or AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = response_format
            if response_format.get("type") == "json_object":
                payload["messages"] = ensure_json_hint(messages)
        if max_tokens:
            payload["max_tokens"] = max_tokens

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(**payload)
                return self._parse(response)
            except Exception as exc:  # noqa: BLE001 - 需要按状态码分类
                last_error = exc
                if attempt >= self.max_retries or not _is_retryable(exc):
                    raise
                await asyncio.sleep(min(2**attempt, 8))
        raise RuntimeError(f"模型调用失败：{last_error}")

    def _parse(self, response: Any) -> ChatResult:
        choice = response.choices[0]
        message = choice.message
        calls: list[ToolCallOut] = []
        for call in getattr(message, "tool_calls", None) or []:
            function = call.function
            calls.append(
                ToolCallOut(
                    id=getattr(call, "id", ""),
                    name=function.name,
                    arguments=function.arguments or "{}",
                )
            )
        usage = getattr(response, "usage", None)
        return ChatResult(
            content=getattr(message, "content", "") or "",
            tool_calls=calls,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=getattr(response, "model", self.model) or self.model,
        )
