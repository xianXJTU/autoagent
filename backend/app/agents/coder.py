from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent
from .prompts import CODER_SYSTEM
from .schemas import CodeDraft


class CoderAgent(BaseAgent):
    role = "coder"
    system_prompt = CODER_SYSTEM

    async def write_module(
        self,
        module_spec: dict[str, Any],
        interfaces: str,
        skills: str,
        test_cases: str,
    ) -> CodeDraft:
        content = (
            "请为下面这个模块编写代码。只输出 JSON，字段为 files 与 notes。\n"
            "files 是文件数组，每个元素包含 path 与 content；path 必须是相对路径。\n"
            f"模块规格：\n{json.dumps(module_spec, ensure_ascii=False)}\n\n"
            f"接口契约：\n{interfaces}\n\n"
            f"已注入技能：\n{skills}\n\n"
            f"必须通过的测试：\n{test_cases}\n"
        )
        draft, _ = await self._structured(CodeDraft, content, purpose="模块编码")
        if not draft.files:
            raise ValueError("编码结果没有文件")
        return draft

    async def fix_module(
        self,
        module_spec: dict[str, Any],
        failure: str,
        previous_notes: str = "",
    ) -> CodeDraft:
        content = (
            "本模块测试失败，请修复。只输出 JSON，字段为 files 与 notes。\n"
            f"模块规格：\n{json.dumps(module_spec, ensure_ascii=False)}\n\n"
            f"上一次说明：\n{previous_notes}\n\n"
            f"失败信息：\n{failure}\n"
        )
        draft, _ = await self._structured(CodeDraft, content, purpose="模块修复")
        if not draft.files:
            raise ValueError("修复结果没有文件")
        return draft

    async def apply(self, draft: CodeDraft) -> list[str]:
        if self.context.tools is None:
            raise RuntimeError("编码者没有工具上下文")
        written: list[str] = []
        for file in draft.files:
            written.append(
                await self.context.tools.execute(
                    "coder", "write_file", path=file.path, content=file.content
                )
            )
        return written
