from __future__ import annotations

from .base import BaseAgent
from .prompts import PLANNER_SYSTEM
from .schemas import AlignmentQuestions, PlanDraft


class PlannerAgent(BaseAgent):
    role = "planner"
    system_prompt = PLANNER_SYSTEM

    async def ask_questions(
        self, history_text: str, round_no: int, max_rounds: int = 5
    ) -> AlignmentQuestions:
        content = (
            f"这是第 {round_no} 轮提问，最多 {max_rounds} 轮。\n"
            f"已知对话与决定：\n{history_text}\n"
            "请提出 3 到 6 个当前最需要确认的问题。要求：\n"
            "1. 用普通人能听懂的中文提问，不要出现框架名、数据库术语、接口协议等技术词；\n"
            "2. 每个问题都给出你推荐的默认做法，写在 recommendation 字段；\n"
            "3. 每个问题都用一句话说明为什么推荐这样做，写在 reason 字段；\n"
            "4. 如果某个信息可以自己查或可以合理默认，就不要拿来问用户。"
        )
        result, _ = await self._structured(
            AlignmentQuestions, content, purpose="需求对齐"
        )
        return result

    async def draft_readme(self, confirmed_summary: str) -> str:
        content = (
            "根据以下已确认信息，生成一份中文需求文档。"
            "必须包含：目标用户、核心流程、功能清单、页面清单、数据实体、"
            "可检验的验收标准、明确不做的事。只输出文档正文。\n"
            f"{confirmed_summary}"
        )
        result = await self.context.model_service.chat(
            self._messages(content),
            run_id=self.context.run_id,
            agent_id=self.role,
            purpose="生成需求文档",
        )
        return result.content.strip()

    async def draft_plan(self, readme: str) -> PlanDraft:
        content = (
            "基于下面的需求文档，生成代码计划。\n"
            "要求：模块数不超过 7；每个模块给出名称、职责、文件归属、依赖模块与测试清单；"
            "给出接口契约与验收条款到测试的映射。只输出 JSON。\n\n"
            f"{readme}"
        )
        plan, _ = await self._structured(PlanDraft, content, purpose="生成代码计划")
        if not plan.modules:
            raise ValueError("代码计划没有模块")
        if len(plan.modules) > 7:
            raise ValueError("代码计划超过 7 个模块")
        names = [module.name for module in plan.modules]
        if len(set(names)) != len(names):
            raise ValueError("模块名称重复")
        owned: set[str] = set()
        for module in plan.modules:
            for path in module.files:
                if path in owned:
                    raise ValueError(f"文件归属重复：{path}")
                owned.add(path)
        return plan
