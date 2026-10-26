from __future__ import annotations

import json

from .base import BaseAgent
from .prompts import EVALUATOR_SYSTEM
from .schemas import EvaluationDraft


class EvaluatorAgent(BaseAgent):
    role = "evaluator"
    system_prompt = EVALUATOR_SYSTEM

    async def score(self, metrics: dict, evidence: dict) -> EvaluationDraft:
        content = (
            "请为这次运行打分。只输出 JSON，字段为 dimensions 与 summary。\n"
            "每个维度包含 dimension、score（0 到 4）、evidence（事件编号或文件行号）、issue。\n"
            f"确定性指标：\n{json.dumps(metrics, ensure_ascii=False)}\n\n"
            f"证据：\n{json.dumps(evidence, ensure_ascii=False)}\n"
        )
        draft, _ = await self._structured(
            EvaluationDraft, content, purpose="运行评测"
        )
        return draft
