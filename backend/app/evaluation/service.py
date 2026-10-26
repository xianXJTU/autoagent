"""评测服务：确定性分数 + 模型评审 + 对比。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Evaluation, Run
from ..events.service import EventService
from ..memory.service import MemoryService
from .metrics import compute_metrics, deterministic_scores


class EvaluationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        events: EventService,
        evaluator: Any | None = None,
        memory: MemoryService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.events = events
        self.evaluator = evaluator
        self.memory = memory

    async def evaluate(
        self, run_id: str, evidence: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        with self.session_factory() as session:
            metrics = compute_metrics(session, run_id)
        rows = deterministic_scores(metrics)

        if self.evaluator is not None:
            draft = await self.evaluator.score(
                metrics,
                evidence
                or {
                    "event_ids": metrics.get("event_ids", []),
                    "test_ids": metrics.get("test_ids", []),
                },
            )
            for item in draft.dimensions:
                problems = list(item.evidence)
                score = item.score
                issue = item.issue
                if not problems:
                    score = 0
                    issue = (issue + "；缺少证据，不计分").strip("；")
                rows.append(
                    {
                        "dimension": item.dimension,
                        "score": score,
                        "evidence": problems,
                        "issue": issue,
                        "judge": "model",
                    }
                )

        with self.session_factory() as session:
            session.execute(
                delete(Evaluation).where(Evaluation.run_id == run_id)
            )
            for row in rows:
                session.add(
                    Evaluation(
                        run_id=run_id,
                        dimension=row["dimension"],
                        score=row["score"],
                        evidence_json={"evidence": row.get("evidence", [])},
                        judge=row.get("judge", "deterministic"),
                    )
                )
            run = session.get(Run, run_id)
            if run is not None:
                run.usage_json = {**(run.usage_json or {}), "evaluated": True}
            session.commit()

        await self.events.emit(
            run_id, "evaluation.completed", stage="已交付", agent_id="evaluator",
            payload={"metrics": metrics, "dimensions": len(rows)},
        )
        if self.memory is not None:
            summary = (
                f"评测完成：可运行性={self._get(rows, '可运行性')}，"
                f"测试通过率={self._get(rows, '测试通过率')}，"
                f"总 token={metrics['total_tokens']}"
            )
            await self.memory.record_case(
                summary, f"evaluation:{run_id}", metrics.get("project_id"),
                meta={"metrics": metrics},
            )
        return metrics, rows

    def scores_for(self, run_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Evaluation).where(Evaluation.run_id == run_id)
            ).all()
            return [
                {
                    "dimension": row.dimension,
                    "score": row.score,
                    "evidence": (row.evidence_json or {}).get("evidence", []),
                    "judge": row.judge,
                }
                for row in rows
            ]

    def compare(self, run_ids: list[str]) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for run_id in run_ids:
            result[run_id] = {
                row["dimension"]: row["score"] for row in self.scores_for(run_id)
            }
        return result

    @staticmethod
    def _get(rows: list[dict[str, Any]], dimension: str) -> float:
        for row in rows:
            if row["dimension"] == dimension:
                return float(row["score"])
        return 0.0
