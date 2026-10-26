from __future__ import annotations

import json

from .base import BaseAgent
from .prompts import REVIEWER_SYSTEM
from .schemas import PlanDraft, ReviewVerdict, TestDraft


class ReviewerAgent(BaseAgent):
    role = "reviewer"
    system_prompt = REVIEWER_SYSTEM

    async def design_tests(self, plan: PlanDraft) -> TestDraft:
        content = (
            "根据代码计划设计测试脚本。只输出 JSON，字段为 files；"
            "每个文件必须在 tests/ 目录下，使用 pytest。\n"
            f"计划：\n{plan.model_dump_json()}"
        )
        draft, _ = await self._structured(TestDraft, content, purpose="测试设计")
        for file in draft.files:
            normalized = file.path.replace("\\", "/")
            if not normalized.startswith("tests/"):
                raise ValueError("测试脚本必须位于 tests/ 目录")
        return draft

    async def apply_tests(self, draft: TestDraft) -> list[str]:
        if self.context.tools is None:
            raise RuntimeError("验收者没有工具上下文")
        written: list[str] = []
        for file in draft.files:
            written.append(
                await self.context.tools.execute(
                    "reviewer", "write_test", path=file.path, content=file.content
                )
            )
        return written

    async def review(
        self,
        readme: str,
        plan: PlanDraft,
        code_summary: str,
        test_output: str,
    ) -> ReviewVerdict:
        content = (
            "请依据需求文档与代码计划验收。只输出 JSON，字段为 passed、score、issues、evidence。\n"
            f"需求文档：\n{readme}\n\n"
            f"代码计划：\n{json.dumps(plan.model_dump(), ensure_ascii=False)}\n\n"
            f"代码摘要：\n{code_summary}\n\n"
            f"测试输出：\n{test_output}\n"
        )
        verdict, _ = await self._structured(
            ReviewVerdict, content, purpose="整体验收"
        )
        return verdict
