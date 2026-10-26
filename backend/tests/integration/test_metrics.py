from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.app.db.models import (
    Event,
    ModelCall,
    Module,
    Project,
    Run,
    TestResult,
    ToolCall,
)
from backend.app.evaluation.metrics import compute_metrics, deterministic_scores


def test_metrics_counts_and_scores(db_session) -> None:
    project = Project(name="指标项目", workspace_path="/tmp/m")
    db_session.add(project)
    db_session.flush()
    now = datetime.now(timezone.utc)
    run = Run(
        project_id=project.id,
        thread_id="thread-metrics",
        status="验收中",
        started_at=now - timedelta(hours=1),
        ended_at=now,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(Event(run_id=run.id, seq=1, type="a", stage="编码中", payload_json={}))
    db_session.add(Event(run_id=run.id, seq=2, type="b", stage="验收中", payload_json={}))
    db_session.add(
        ModelCall(
            run_id=run.id, model="deepseek-flash", prompt_tokens=100,
            completion_tokens=50, status="ok",
        )
    )
    db_session.add(ToolCall(run_id=run.id, tool="run_tests", status="ok"))
    db_session.add(
        TestResult(
            run_id=run.id, kind="acceptance", case_name="整体验收", result="pass"
        )
    )
    db_session.add(
        Module(
            run_id=run.id, project_id=project.id, name="模块1", status="已合并",
            spec_json={},
        )
    )
    db_session.commit()

    metrics = compute_metrics(db_session, run.id)
    assert metrics["events"] == 2
    assert metrics["model_calls"] == 1
    assert metrics["total_tokens"] == 150
    assert metrics["tests_passed"] == 1
    assert metrics["acceptance_passed"]
    assert metrics["modules_merged"] == 1
    assert 3500 < metrics["duration_seconds"] < 3700

    rows = {row["dimension"]: row for row in deterministic_scores(metrics)}
    assert rows["可运行性"]["score"] == 4
    assert rows["测试通过率"]["score"] == 4
    assert rows["耗时效率"]["score"] == 4
    assert rows["token 效率"]["score"] == 4
    assert rows["可运行性"]["evidence"]
