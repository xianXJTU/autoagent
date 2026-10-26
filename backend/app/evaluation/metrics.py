"""确定性评测指标。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Event, ModelCall, Module, Project, Run, TestResult, ToolCall


def _duration_seconds(run: Run, events: list[Event]) -> float:
    started = run.started_at
    ended = run.ended_at
    if ended is None and events:
        ended = events[-1].created_at
    if ended is None:
        ended = datetime.now(timezone.utc)
    if started is None:
        return 0.0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if ended.tzinfo is None:
        ended = ended.replace(tzinfo=timezone.utc)
    return max(0.0, (ended - started).total_seconds())


def compute_metrics(session: Session, run_id: str) -> dict[str, Any]:
    run = session.get(Run, run_id)
    if run is None:
        raise ValueError("运行不存在")
    project = session.get(Project, run.project_id)
    events = session.scalars(
        select(Event).where(Event.run_id == run_id).order_by(Event.seq.asc())
    ).all()
    calls = session.scalars(
        select(ModelCall).where(ModelCall.run_id == run_id)
    ).all()
    tools = session.scalars(
        select(ToolCall).where(ToolCall.run_id == run_id)
    ).all()
    tests = session.scalars(
        select(TestResult).where(TestResult.run_id == run_id)
    ).all()
    modules = session.scalars(
        select(Module).where(Module.run_id == run_id)
    ).all()

    passed = [item for item in tests if item.result == "pass"]
    failed = [item for item in tests if item.result == "fail"]
    by_kind: dict[str, dict[str, int]] = {}
    for item in tests:
        bucket = by_kind.setdefault(item.kind, {"pass": 0, "fail": 0})
        bucket["pass" if item.result == "pass" else "fail"] += 1

    return {
        "run_id": run_id,
        "project_id": run.project_id,
        "project_name": project.name if project else "",
        "status": run.status,
        "duration_seconds": _duration_seconds(run, events),
        "events": len(events),
        "event_ids": [f"events:{item.id}" for item in events[:5]],
        "model_calls": len(calls),
        "prompt_tokens": sum(item.prompt_tokens for item in calls),
        "completion_tokens": sum(item.completion_tokens for item in calls),
        "total_tokens": sum(item.prompt_tokens + item.completion_tokens for item in calls),
        "tool_calls": len(tools),
        "tool_errors": sum(1 for item in tools if item.status != "ok"),
        "tests_total": len(tests),
        "tests_passed": len(passed),
        "tests_failed": len(failed),
        "test_ids": [f"tests:{item.id}" for item in tests[:5]],
        "by_kind": by_kind,
        "modules_total": len(modules),
        "modules_completed": sum(1 for item in modules if item.status == "已完成"),
        "modules_failed": sum(1 for item in modules if item.status == "失败"),
        "modules_merged": sum(1 for item in modules if item.status == "已合并"),
        "acceptance_passed": any(
            item.kind == "acceptance" and item.result == "pass" for item in tests
        ),
    }


def _score_time(seconds: float) -> int:
    if seconds <= 3600:
        return 4
    if seconds <= 7200:
        return 3
    if seconds <= 14400:
        return 2
    return 1


def _score_tokens(tokens: int) -> int:
    if tokens <= 100_000:
        return 4
    if tokens <= 500_000:
        return 3
    if tokens <= 1_000_000:
        return 2
    return 1


def deterministic_scores(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = (metrics.get("event_ids") or []) + (metrics.get("test_ids") or [])
    total = metrics.get("tests_total", 0)
    passed = metrics.get("tests_passed", 0)
    pass_rate = (passed / total) if total else 0.0
    runnability = 4 if metrics.get("acceptance_passed") else (
        2 if metrics.get("modules_completed", 0) > 0 else 0
    )
    retry = 4 if metrics.get("tests_failed", 0) == 0 else (
        2 if metrics.get("tests_passed", 0) > 0 else 0
    )
    return [
        {
            "dimension": "可运行性",
            "score": runnability,
            "evidence": evidence,
            "issue": "" if runnability == 4 else "验收尚未通过",
        },
        {
            "dimension": "测试通过率",
            "score": int(round(4 * pass_rate)),
            "evidence": metrics.get("test_ids") or [],
            "issue": "",
        },
        {
            "dimension": "耗时效率",
            "score": _score_time(metrics.get("duration_seconds", 0)),
            "evidence": metrics.get("event_ids") or [],
            "issue": "",
        },
        {
            "dimension": "token 效率",
            "score": _score_tokens(metrics.get("total_tokens", 0)),
            "evidence": metrics.get("event_ids") or [],
            "issue": "",
        },
        {
            "dimension": "重试策略",
            "score": retry,
            "evidence": metrics.get("test_ids") or [],
            "issue": "",
        },
    ]
