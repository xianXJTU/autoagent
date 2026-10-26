"""运行级接口：评测查询。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ...db.models import Run
from ...evaluation.metrics import compute_metrics
from ...evaluation.service import EvaluationService

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{run_id}/evaluation")
async def run_evaluation(run_id: str, request: Request) -> dict:
    services = request.app.state.services
    with services.session_factory() as session:
        run = session.get(Run, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="运行不存在")
        metrics = compute_metrics(session, run_id)
    evaluation = EvaluationService(services.session_factory, services.events)
    return {"run_id": run_id, "metrics": metrics, "scores": evaluation.scores_for(run_id)}
