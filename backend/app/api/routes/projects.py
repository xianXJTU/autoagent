"""项目、对话、文档、文件、预览与运行控制接口。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select

from ...db.models import Document, Message, Module, Project, Run, new_id
from ...evaluation.metrics import compute_metrics
from ...evaluation.service import EvaluationService
from ...redaction import redact_text
from ...services.delivery import package_project
from ...services.retention import RetentionService
from ..schemas import ChangeRequest, MessageIn, ProjectCreate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _services(request: Request):
    return request.app.state.services


def _project_or_404(session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _run_for_project(session, project: Project) -> Run | None:
    if project.current_run_id:
        run = session.get(Run, project.current_run_id)
        if run is not None:
            return run
    return session.scalar(
        select(Run)
        .where(Run.project_id == project.id)
        .order_by(Run.created_at.desc())
        .limit(1)
    )


@router.post("")
async def create_project(payload: ProjectCreate, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = Project(name=payload.name, status="对齐中")
        session.add(project)
        session.flush()
        project.workspace_path = str(services.workspace.project_dir(project.id))
        run = Run(project_id=project.id, thread_id=new_id(), status="对齐中")
        session.add(run)
        session.flush()
        project.current_run_id = run.id
        if payload.requirement.strip():
            session.add(
                Message(
                    project_id=project.id,
                    run_id=run.id,
                    role="user",
                    content=payload.requirement.strip(),
                )
            )
        session.commit()
        project_id, run_id = project.id, run.id

    services.workspace.create(project_id, payload.name)
    await services.events.emit(
        run_id, "project.created", stage="对齐中", payload={"name": payload.name}
    )
    return {"project_id": project_id, "run_id": run_id, "status": "对齐中"}


@router.get("")
async def list_projects(request: Request) -> list[dict]:
    services = _services(request)
    with services.session_factory() as session:
        rows = session.scalars(
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
        ).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ]


@router.get("/{project_id}")
async def project_detail(project_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        messages = session.scalars(
            select(Message)
            .where(Message.project_id == project_id)
            .order_by(Message.created_at.asc())
            .limit(200)
        ).all()
        readme = session.scalar(
            select(Document)
            .where(Document.project_id == project_id, Document.kind == "readme")
            .order_by(Document.version.desc())
            .limit(1)
        )
        modules = session.scalars(
            select(Module).where(Module.project_id == project_id)
        ).all()
        return {
            "id": project.id,
            "name": project.name,
            "status": project.status,
            "run_id": run.id if run else None,
            "run_status": run.status if run else None,
            "messages": [
                {
                    "id": item.id,
                    "role": item.role,
                    "agent_id": item.agent_id,
                    "content": item.content,
                    "meta": item.meta or {},
                    "created_at": item.created_at.isoformat(),
                }
                for item in messages
            ],
            "readme": (
                {
                    "id": readme.id,
                    "version": readme.version,
                    "status": readme.status,
                    "content": readme.content,
                }
                if readme
                else None
            ),
            "modules": [
                {"id": item.id, "name": item.name, "status": item.status}
                for item in modules
            ],
        }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_run(
    factory: Callable[[Callable[[str, str], None]], Awaitable[dict]]
) -> StreamingResponse:
    async def generator():
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        async def runner():
            return await factory(
                lambda kind, text: queue.put_nowait((kind, text))
            )

        task = asyncio.create_task(runner())
        task.add_done_callback(lambda _: queue.put_nowait(("__done__", "")))
        try:
            while True:
                kind, text = await queue.get()
                if kind == "__done__":
                    break
                event = "thinking" if kind == "reasoning" else "content"
                yield _sse(event, {"text": text})
            try:
                result = await task
                if hasattr(result, "model_dump"):
                    result = result.model_dump()
                yield _sse("result", result)
            except Exception as exc:  # noqa: BLE001
                detail = redact_text(f"{type(exc).__name__}: {exc}")[:2000]
                yield _sse("error", {"detail": detail})
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{project_id}/align/stream")
async def start_alignment_stream(project_id: str, request: Request) -> StreamingResponse:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        if run.status != "对齐中":
            raise HTTPException(status_code=400, detail="当前不在需求对齐阶段")
        run_id = run.id
    alignment = services.alignment_for(project_id, run_id)

    async def factory(on_delta):
        questions = await alignment.start(project_id, run_id, on_delta=on_delta)
        return {"run_id": run_id, "questions": questions.model_dump()}

    return _stream_run(factory)


@router.post("/{project_id}/align")
async def start_alignment(project_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        run_id = run.id
    alignment = services.alignment_for(project_id, run_id)
    questions = await alignment.start(project_id, run_id)
    return {"run_id": run_id, "questions": questions.model_dump()}


@router.post("/{project_id}/messages/stream")
async def send_message_stream(
    project_id: str, payload: MessageIn, request: Request
) -> StreamingResponse:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        run_id, status = run.id, run.status

    if status == "对齐中":
        alignment = services.alignment_for(project_id, run_id)

        async def factory(on_delta):
            return await alignment.answer(
                project_id, run_id, payload.text, on_delta=on_delta
            )
    else:
        intervention = services.intervention_for(project_id, run_id)

        async def factory(_on_delta):
            return await intervention.handle(project_id, run_id, payload.text)

    return _stream_run(factory)


@router.post("/{project_id}/messages")
async def send_message(project_id: str, payload: MessageIn, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        run_id, status = run.id, run.status
    if status == "对齐中":
        alignment = services.alignment_for(project_id, run_id)
        return await alignment.answer(project_id, run_id, payload.text)
    intervention = services.intervention_for(project_id, run_id)
    return await intervention.handle(project_id, run_id, payload.text)


@router.post("/{project_id}/documents/{document_id}/approve")
async def approve_document(project_id: str, document_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        run_id = run.id
    alignment = services.alignment_for(project_id, run_id)
    result = await alignment.approve(project_id, document_id)
    services.start_pipeline(project_id, run_id)
    return {**result, "run_id": run_id, "pipeline_started": True}


@router.post("/{project_id}/documents/{document_id}/changes")
async def request_changes(
    project_id: str, document_id: str, payload: ChangeRequest, request: Request
) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        run_id = run.id
    alignment = services.alignment_for(project_id, run_id)
    return await alignment.request_changes(project_id, document_id, payload.feedback)


@router.get("/{project_id}/documents")
async def list_documents(project_id: str, request: Request) -> list[dict]:
    services = _services(request)
    with services.session_factory() as session:
        _project_or_404(session, project_id)
        rows = session.scalars(
            select(Document)
            .where(Document.project_id == project_id, Document.kind != "plan")
            .order_by(Document.version.asc())
        ).all()
        return [
            {
                "id": row.id,
                "kind": row.kind,
                "version": row.version,
                "status": row.status,
                "content": row.content,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


@router.get("/{project_id}/documents/diff")
async def document_diff(project_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        _project_or_404(session, project_id)
    alignment = services.alignment_for(project_id, "")
    return {"diff": alignment.diff_latest(project_id)}


@router.get("/{project_id}/files")
async def list_files(project_id: str, request: Request) -> list[dict]:
    services = _services(request)
    with services.session_factory() as session:
        _project_or_404(session, project_id)
    repo = services.workspace.repo_path(project_id)
    if not repo.exists():
        return []
    results: list[dict] = []
    for path in sorted(repo.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(repo).as_posix()
        if any(part in relative for part in (".git/", ".venv/", "__pycache__/")):
            continue
        results.append({"path": relative, "size": path.stat().st_size})
    return results


@router.get("/{project_id}/download")
async def download_project(project_id: str, request: Request) -> FileResponse:
    services = _services(request)
    with services.session_factory() as session:
        _project_or_404(session, project_id)
    repo = services.workspace.repo_path(project_id)
    if not repo.exists():
        raise HTTPException(status_code=404, detail="生成物不存在")
    archive = package_project(
        repo, services.settings.data_root / "exports" / f"{project_id}.zip"
    )
    return FileResponse(archive, filename=f"{project_id}.zip")


@router.post("/{project_id}/preview/start")
async def preview_start(project_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        _project_or_404(session, project_id)
    repo = services.workspace.repo_path(project_id)
    venv_python = Path(services.settings.workspace_root) / project_id / ".venv"
    python = venv_python / "Scripts" / "python.exe"
    if not python.exists():
        python = Path(sys.executable)
    session = services.preview.start(project_id, repo, python=python)
    return {"url": session.url, "port": session.port}


@router.post("/{project_id}/preview/stop")
async def preview_stop(project_id: str, request: Request) -> dict:
    services = _services(request)
    return {"stopped": services.preview.stop(project_id)}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    keep_traces: bool = True,
    export: bool = False,
) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        run_id = run.id if run else None
    if run_id is not None:
        task = services.tasks.get(run_id)
        if task is not None and not task.done():
            raise HTTPException(status_code=409, detail="项目正在生成中，请先取消")
    services.preview.stop(project_id)
    result = RetentionService(
        services.session_factory,
        services.settings.workspace_root,
        services.settings.data_root,
        vector_store=services.memory_store,
    ).delete_project(project_id, keep_traces=keep_traces, export=export)
    return {
        "deleted": result.deleted,
        "archive": str(result.archive_path) if result.archive_path else None,
        "export": str(result.export_path) if result.export_path else None,
    }


@router.post("/{project_id}/pause")
async def pause_project(project_id: str, request: Request) -> dict:
    return await _set_run_status(request, project_id, "暂停")


@router.post("/{project_id}/resume")
async def resume_project(project_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        previous = str((run.usage_json or {}).get("paused_from", ""))
        if run.status != "暂停" or not previous:
            raise HTTPException(status_code=400, detail="当前不是可恢复的暂停状态")
        run.status = previous
        project.status = previous
        session.commit()
        run_id = run.id
    if previous not in {"对齐中", "待审阅", "已批准"}:
        services.resume_pipeline(project_id, run_id, previous)
    return {"status": previous, "run_id": run_id}


@router.post("/{project_id}/cancel")
async def cancel_project(project_id: str, request: Request) -> dict:
    return await _set_run_status(request, project_id, "取消")


@router.get("/{project_id}/evaluation")
async def project_evaluation(project_id: str, request: Request) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        run_id = run.id
        metrics = compute_metrics(session, run_id)
    evaluation = EvaluationService(services.session_factory, services.events)
    return {"run_id": run_id, "metrics": metrics, "scores": evaluation.scores_for(run_id)}


async def _set_run_status(request: Request, project_id: str, status: str) -> dict:
    services = _services(request)
    with services.session_factory() as session:
        project = _project_or_404(session, project_id)
        run = _run_for_project(session, project)
        if run is None:
            raise HTTPException(status_code=400, detail="项目没有运行记录")
        if status == "暂停" and run.status not in {"暂停", "取消"}:
            run.usage_json = {
                **(run.usage_json or {}),
                "paused_from": run.status,
            }
        run.status = status
        project.status = status
        session.commit()
        run_id = run.id
    if status == "取消":
        services.preview.stop(project_id)
    await services.events.emit(run_id, "run.paused" if status == "暂停" else "run.cancelled", stage=status)
    return {"status": status, "run_id": run_id}
