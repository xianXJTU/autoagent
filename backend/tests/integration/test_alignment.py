from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from backend.app.agents.base import AgentContext
from backend.app.agents.planner import PlannerAgent
from backend.app.config import Settings
from backend.app.db.models import Document, Project, Run
from backend.app.db.session import build_session_factory
from backend.app.events.service import EventService
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.services.alignment import AlignmentService


class FakeMemory:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def record_project_decision(self, content: str, source: str, project_id: str):
        self.calls.append((content, source, project_id))


def _question_response(round_no: int) -> dict:
    return {
        "content": json.dumps(
            {
                "questions": [
                    {
                        "question": f"第{round_no}轮问题",
                        "recommendation": "推荐答案",
                        "options": [],
                    }
                ]
            },
            ensure_ascii=False,
        )
    }


def _service(
    db_engine,
    db_session,
    memory_session_factory,
    test_settings: Settings,
    tmp_path: Path,
    responses: list[dict],
):
    project = Project(name="对齐项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-align")
    db_session.add(run)
    db_session.commit()

    workspace = tmp_path / "workspace" / project.id / "repo"
    workspace.mkdir(parents=True)

    provider = FakeLLMProvider(responses)
    model_service = ModelService(provider, provider, memory_session_factory)
    planner = PlannerAgent(
        AgentContext(
            project_id=project.id,
            run_id=run.id,
            model_service=model_service,
        )
    )
    events = EventService(memory_session_factory, test_settings.data_root)
    memory = FakeMemory()
    service = AlignmentService(
        memory_session_factory,
        planner,
        events,
        memory=memory,
        workspace_root=tmp_path / "workspace",
    )
    return project, run, service, memory


async def test_alignment_rounds_approval_and_revision(
    db_engine, db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project, run, service, memory = _service(
        db_engine,
        db_session,
        memory_session_factory,
        test_settings,
        tmp_path,
        [
            _question_response(1),
            {"content": "# 需求文档\n记账工具"},
            {"content": "# 需求文档\n记账工具，带预算提醒"},
        ],
    )

    first = await service.start(project.id, run.id)
    assert len(first.questions) == 1

    result = await service.answer(project.id, run.id, "够了")
    assert result["action"] == "review"
    assert result["version"] == 1

    approved = await service.approve(project.id, result["document_id"])
    assert approved["version"] == 1
    assert memory.calls
    db_session.expire_all()
    assert db_session.get(Run, run.id).status == "已批准"
    assert (tmp_path / "workspace" / project.id / "repo" / "README.md").read_text(
        encoding="utf-8"
    ).startswith("# 需求文档")

    revised = await service.request_changes(
        project.id, result["document_id"], "加一个预算提醒"
    )
    assert revised["version"] == 2
    diff = service.diff_latest(project.id)
    assert "预算提醒" in diff
    db_session.expire_all()
    old = db_session.get(Document, result["document_id"])
    assert old.status == "approved"


async def test_max_rounds_forces_readme(
    db_engine, db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    responses = [_question_response(index) for index in range(1, 6)]
    responses.append({"content": "# 需求文档\n第五轮后定稿"})
    project, run, service, _ = _service(
        db_engine, db_session, memory_session_factory, test_settings, tmp_path, responses
    )

    await service.start(project.id, run.id)
    for index in range(1, 5):
        result = await service.answer(project.id, run.id, f"回答{index}")
        assert result["action"] == "questions"
    result = await service.answer(project.id, run.id, "回答5")
    assert result["action"] == "review"
    assert result["version"] == 1

    with memory_session_factory() as session:
        assert len(session.scalars(select(Document)).all()) == 1
