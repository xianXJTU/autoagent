from __future__ import annotations

import json
from pathlib import Path

from backend.app.agents.base import AgentContext
from backend.app.agents.coder import CoderAgent
from backend.app.agents.evaluator import EvaluatorAgent
from backend.app.agents.planner import PlannerAgent
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.agents.tools import ToolRegistry
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.workspace.runner import CommandRunner


def _context(memory_session_factory, root: Path, responses: list[dict]) -> AgentContext:
    provider = FakeLLMProvider(responses)
    service = ModelService(provider, provider, memory_session_factory)
    tools = ToolRegistry(root, runner=CommandRunner(root))
    return AgentContext(
        project_id="p1", run_id=None, model_service=service, tools=tools
    )


async def test_planner_questions_and_plan(
    memory_session_factory, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    questions = {
        "questions": [
            {"question": "给谁用？", "recommendation": "只给你自己", "options": []},
            {"question": "记哪些字段？", "recommendation": "金额与分类", "options": []},
            {"question": "要导出吗？", "recommendation": "导出 CSV", "options": []},
        ]
    }
    plan = {
        "modules": [
            {
                "name": "数据层",
                "description": "数据模型",
                "files": ["app/models.py"],
                "depends_on": [],
                "tests": ["tests/test_models.py"],
            },
            {
                "name": "接口",
                "description": "记录接口",
                "files": ["app/api.py"],
                "depends_on": ["数据层"],
                "tests": ["tests/test_api.py"],
            },
        ],
        "interfaces": "JSON",
        "acceptance_map": {"能记一笔": "tests/test_api.py"},
    }
    context = _context(
        memory_session_factory,
        root,
        [{"content": json.dumps(questions)}, {"content": json.dumps(plan)}],
    )
    planner = PlannerAgent(context)
    result = await planner.ask_questions("用户想记账", round_no=1)
    assert len(result.questions) == 3

    draft = await planner.draft_plan("# 需求")
    assert len(draft.modules) == 2
    assert draft.modules[0].name == "数据层"


async def test_coder_writes_files(memory_session_factory, tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = _context(
        memory_session_factory,
        root,
        [{"content": json.dumps({"files": [{"path": "app/main.py", "content": "print(1)"}]})}],
    )
    coder = CoderAgent(context)
    draft = await coder.write_module({"name": "入口"}, "无", "无", "无")
    written = await coder.apply(draft)
    assert written == ["app/main.py"]
    assert (root / "app" / "main.py").read_text(encoding="utf-8") == "print(1)"


async def test_reviewer_tests_and_verdict(
    memory_session_factory, tmp_path: Path
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = _context(
        memory_session_factory,
        root,
        [
            {
                "content": json.dumps(
                    {
                        "files": [
                            {
                                "path": "tests/test_main.py",
                                "content": "def test_ok(): assert True",
                            }
                        ]
                    }
                )
            },
            {
                "content": json.dumps(
                    {"passed": True, "score": 4, "issues": [], "evidence": ["tests/test_main.py:1"]}
                )
            },
        ],
    )
    reviewer = ReviewerAgent(context)
    draft = await reviewer.design_tests(
        type("Plan", (), {"model_dump_json": lambda self: "{}"})()
    )
    await reviewer.apply_tests(draft)
    assert (root / "tests" / "test_main.py").exists()

    verdict = await reviewer.review(
        "需求", type("Plan", (), {"model_dump": lambda self: {}})(), "代码", "通过"
    )
    assert verdict.passed
    assert verdict.evidence


async def test_evaluator_scores(memory_session_factory, tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    context = _context(
        memory_session_factory,
        root,
        [
            {
                "content": json.dumps(
                    {
                        "dimensions": [
                            {
                                "dimension": "可运行性",
                                "score": 4,
                                "evidence": ["events:12"],
                                "issue": "",
                            }
                        ],
                        "summary": "良好",
                    }
                )
            }
        ],
    )
    evaluator = EvaluatorAgent(context)
    draft = await evaluator.score({"started": True}, {"events": 12})
    assert draft.dimensions[0].score == 4
    assert draft.summary == "良好"
