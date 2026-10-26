"""项目删除、导出与轨迹匿名化。"""

from __future__ import annotations

import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..db.models import Event, Memory, Project, Run
from ..redaction import redact_obj
from .delivery import package_project


@dataclass
class DeleteResult:
    deleted: bool
    archive_path: Path | None = None
    export_path: Path | None = None


class RetentionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        workspace_root: Path,
        data_root: Path,
        vector_store: Any | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.workspace_root = workspace_root
        self.data_root = data_root
        self.vector_store = vector_store

    def delete_project(
        self,
        project_id: str,
        keep_traces: bool = True,
        export: bool = False,
    ) -> DeleteResult:
        workspace = self.workspace_root / project_id
        repo = workspace / "repo"
        export_path: Path | None = None
        if export and repo.exists():
            export_path = package_project(
                repo, self.data_root / "exports" / f"{project_id}.zip"
            )

        archive_path = self.data_root / "archive" / f"{project_id}.jsonl"
        if keep_traces:
            self._archive_traces(project_id, archive_path)
        elif archive_path.exists():
            archive_path.unlink()

        with self.session_factory() as session:
            memories = session.scalars(
                select(Memory).where(Memory.project_id == project_id)
            ).all()
            memory_ids = [memory.id for memory in memories]
            run_ids = [
                row
                for row in session.scalars(
                    select(Run.id).where(Run.project_id == project_id)
                ).all()
            ]
            session.execute(
                delete(Memory).where(Memory.project_id == project_id)
            )
            session.execute(delete(Project).where(Project.id == project_id))
            session.commit()

        if self.vector_store is not None and memory_ids:
            self.vector_store.delete(memory_ids)
        for run_id in run_ids:
            run_dir = self.data_root / "runs" / run_id
            if run_dir.exists():
                _force_remove(run_dir)
        if not export:
            stale_export = self.data_root / "exports" / f"{project_id}.zip"
            if stale_export.exists():
                stale_export.unlink()

        if workspace.exists():
            _force_remove(workspace)
        return DeleteResult(
            deleted=True, archive_path=archive_path if keep_traces else None,
            export_path=export_path,
        )

    def _archive_traces(self, project_id: str, path: Path) -> None:
        with self.session_factory() as session:
            rows = session.execute(
                select(Event)
                .join(Run, Event.run_id == Run.id)
                .where(Run.project_id == project_id)
                .order_by(Event.created_at.asc())
            ).scalars().all()
            records = [
                {
                    "type": row.type,
                    "stage": row.stage,
                    "agent_id": row.agent_id,
                    "seq": row.seq,
                    "created_at": row.created_at.isoformat(),
                    "payload": redact_obj(row.payload_json or {}),
                }
                for row in rows
            ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _force_remove(path: Path) -> None:
    """Windows 上 Git 会留下只读文件，删除前先去掉只读属性。"""

    def _retry(function, target, _error):
        try:
            os.chmod(target, stat.S_IWRITE)
            function(target)
        except Exception:
            pass

    try:
        shutil.rmtree(path, onexc=_retry)
    except TypeError:
        shutil.rmtree(path, onerror=_retry)
