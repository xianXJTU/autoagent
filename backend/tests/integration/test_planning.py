from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from backend.app.agents.base import AgentContext
from backend.app.agents.planner import PlannerAgent
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.config import Settings
from backend.app.db.models import Document, Module, Project, Run
from backend.app.db.session import build_session_factory
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.services.planning import PlanningService, verify_frozen
from backend.app.workspace.manager import WorkspaceManager


def _plan_payload(module_count: int = 2) -> dict:
    return {
        "modules": [
            {
                "name": f"模块{index}",
                "description": f"职责{index}",
                "files": [f"app/module{index}.py"],
                "depends_on": [] if index == 1 else [f"模块{index - 1}"],
                "tests": [f"tests/test_module{index}.py"],
            }
            for index in range(1, module_count + 1)
        ],
        "interfaces": "模块之间通过函数调用",
        "acceptance_map": {"能运行": "tests/test_module1.py"},
    }


def _tests_payload(module_count: int = 2) -> dict:
    return {
        "files": [
            {
                "path": f"tests/test_module{index}.py",
                "content": f"def test_module{index}(): assert True\n",
            }
            for index in range(1, module_count + 1)
        ]
    }


def _service(db_session, memory_session_factory, tmp_path: Path, responses: list[dict]):
    project = Project(name="计划项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-plan")
    db_session.add(run)
    db_session.commit()

    provider = FakeLLMProvider(responses)
    model_service = ModelService(provider, provider, memory_session_factory)
    planner = PlannerAgent(
        AgentContext(project_id=project.id, run_id=run.id, model_service=model_service)
    )
    reviewer = ReviewerAgent(
        AgentContext(project_id=project.id, run_id=run.id, model_service=model_service)
    )
    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create(project.id, "计划项目")
    service = PlanningService(memory_session_factory, planner, reviewer, manager)
    return project, run, service, manager


async def test_generate_plan_tests_freeze_and_hidden_plan(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    responses = [
        {"content": json.dumps(_plan_payload())},
        {"content": json.dumps(_tests_payload())},
    ]
    project, run, service, manager = _service(
        db_session, memory_session_factory, tmp_path, responses
    )

    result = await service.generate(project.id, run.id, "# 需求")
    assert len(result.plan.modules) == 2
    assert len(result.module_ids) == 2
    assert result.frozen

    repo = manager.repo_path(project.id)
    assert (repo / "tests" / "test_module1.py").exists()
    assert verify_frozen(repo) == []

    visible = service.visible_documents(project.id)
    assert visible == []

    db_session.expire_all()
    plan_doc = db_session.scalars(
        select(Document).where(Document.kind == "plan")
    ).one()
    assert plan_doc.status == "approved"
    modules = db_session.scalars(select(Module)).all()
    assert len(modules) == 2

    (repo / "tests" / "test_module1.py").write_text("def test_x(): pass\n", encoding="utf-8")
    assert verify_frozen(repo) == ["tests/test_module1.py"]


async def test_invalid_plan_more_than_seven_modules(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    responses = [
        {"content": json.dumps(_plan_payload(module_count=8))},
        {"content": json.dumps(_tests_payload(module_count=8))},
    ]
    project, run, service, _ = _service(
        db_session, memory_session_factory, tmp_path, responses
    )
    try:
        await service.generate(project.id, run.id, "# 需求")
    except ValueError as exc:
        assert "7" in str(exc)
    else:
        raise AssertionError("超过 7 个模块应当失败")
