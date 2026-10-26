"""黄金集用例。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable


@dataclass
class GoldenCase:
    id: str
    prompt: str
    expectations: list[str]


def load_golden_set(path: Path) -> list[GoldenCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("黄金集必须是非空数组")
    cases: list[GoldenCase] = []
    for item in payload:
        case = GoldenCase(
            id=str(item["id"]),
            prompt=str(item["prompt"]),
            expectations=list(item.get("expectations", [])),
        )
        if not case.id or not case.prompt:
            raise ValueError("黄金集用例缺少编号或提示词")
        cases.append(case)
    if len({case.id for case in cases}) != len(cases):
        raise ValueError("黄金集编号重复")
    return cases


class GoldenRunner:
    def __init__(self, cases: list[GoldenCase]) -> None:
        self.cases = cases

    async def run_all(
        self, runner: Callable[[str], Awaitable[str]]
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for case in self.cases:
            run_id = await runner(case.prompt)
            results.append(
                {"case_id": case.id, "prompt": case.prompt, "run_id": run_id}
            )
        return results
