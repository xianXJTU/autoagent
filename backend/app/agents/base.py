from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..llm.service import ModelService
from ..llm.structured import chat_structured
from .tools import ToolRegistry


@dataclass
class AgentContext:
    project_id: str
    run_id: str | None
    model_service: ModelService
    tools: ToolRegistry | None = None
    module_id: str | None = None


class BaseAgent:
    role = ""
    system_prompt = ""

    def __init__(self, context: AgentContext) -> None:
        self.context = context

    def _messages(self, content: str) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": content},
        ]

    async def _structured(self, schema, content: str, purpose: str):
        return await chat_structured(
            self.context.model_service,
            schema,
            self._messages(content),
            run_id=self.context.run_id,
            agent_id=self.role,
            purpose=purpose,
        )
