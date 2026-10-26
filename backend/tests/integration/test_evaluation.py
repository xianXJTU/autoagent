from __future__ import annotations

from backend.app.config import Settings
from backend.app.db.models import Evaluation, Project, Run, TestResult
from backend.app.events.service import EventService
from backend.app.evaluation.service import EvaluationService


class StubEvaluator:
    def __init__(self) -> None:
        from backend.app.agents.schemas import DimensionScore, EvaluationDraft

        self.draft = EvaluationDraft(
            dimensions=[
                DimensionScore(
                    dimension="业务拆分质量", score=3, evidence=["events:1"]
                ),
                DimensionScore(
                    dimension="代码质量", score=4, evidence=[]
                ),
            ],
            summary="整体可用",
        )

    async def score(self, metrics, evidence):
        return self.draft


async def test_evaluation_persists_and_compares(
    db_session, memory_session_factory, test_settings: Settings
) -> None:
    project = Project(name="评测项目", workspace_path="/tmp/e")
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-eval", status="验收中")
    db_session.add(run)
    db_session.flush()
    db_session.add(
        TestResult(
            run_id=run.id, kind="acceptance", case_name="整体验收", result="pass"
        )
    )
    db_session.commit()

    events = EventService(memory_session_factory, test_settings.data_root)
    service = EvaluationService(memory_session_factory, events, evaluator=StubEvaluator())
    metrics, rows = await service.evaluate(run.id, evidence={"events": 1})
    assert metrics["tests_passed"] == 1
    assert any(row["dimension"] == "可运行性" for row in rows)
    model_rows = {row["dimension"]: row for row in rows if row.get("judge") == "model"}
    assert model_rows["业务拆分质量"]["score"] == 3
    assert model_rows["代码质量"]["score"] == 0
    assert "缺少证据" in model_rows["代码质量"]["issue"]

    scores = service.scores_for(run.id)
    assert len(scores) == len(rows)
    comparison = service.compare([run.id])
    assert comparison[run.id]["业务拆分质量"] == 3

    db_session.expire_all()
    assert db_session.get(Run, run.id).usage_json.get("evaluated") is True
    assert db_session.query(Evaluation).count() == len(rows)
