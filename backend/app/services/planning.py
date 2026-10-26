"""代码计划、模块拆分与测试冻结。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..agents.planner import PlannerAgent
from ..agents.reviewer import ReviewerAgent
from ..agents.schemas import PlanDraft, TestDraft
from ..db.models import Document, Module
from ..workspace.manager import WorkspaceManager

FREEZE_FILE = ".frozen.json"


@dataclass
class PlanResult:
    plan: PlanDraft
    plan_document_id: str
    module_ids: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    frozen: dict[str, str] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_tests(repo: Path) -> dict[str, str]:
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        path.relative_to(repo).as_posix(): _sha256(path)
        for path in sorted(tests_dir.rglob("*.py"))
    }
    (tests_dir / FREEZE_FILE).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def verify_frozen(repo: Path) -> list[str]:
    manifest_path = repo / "tests" / FREEZE_FILE
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed: list[str] = []
    for relative, digest in manifest.items():
        path = repo / relative
        if not path.exists() or _sha256(path) != digest:
            changed.append(relative)
    return changed


class PlanningService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        planner: PlannerAgent,
        reviewer: ReviewerAgent,
        workspace: WorkspaceManager,
    ) -> None:
        self.session_factory = session_factory
        self.planner = planner
        self.reviewer = reviewer
        self.workspace = workspace

    async def generate(
        self, project_id: str, run_id: str, readme: str
    ) -> PlanResult:
        plan = await self.planner.draft_plan(readme)
        self._validate_plan(plan)

        draft = await self.reviewer.design_tests(plan)
        repo = self.workspace.repo_path(project_id)
        test_files = self._write_tests(repo, draft)
        self._validate_test_mapping(plan, test_files, repo)

        frozen = freeze_tests(repo)
        self.workspace.commit_main(project_id, "冻结测试脚本")

        plan_document_id = self._save_plan_document(project_id, run_id, plan)
        module_ids = self._create_modules(project_id, run_id, plan)
        return PlanResult(
            plan=plan,
            plan_document_id=plan_document_id,
            module_ids=module_ids,
            test_files=test_files,
            frozen=frozen,
        )

    def visible_documents(self, project_id: str) -> list[Document]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(Document)
                .where(Document.project_id == project_id, Document.kind != "plan")
                .order_by(Document.created_at.asc())
            ).all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def _validate_plan(self, plan: PlanDraft) -> None:
        if not plan.modules:
            raise ValueError("代码计划没有模块")
        if len(plan.modules) > 7:
            raise ValueError("代码计划超过 7 个模块")
        names = [module.name for module in plan.modules]
        if len(set(names)) != len(names):
            raise ValueError("模块名称重复")
        owned: set[str] = set()
        for module in plan.modules:
            if not module.files:
                raise ValueError(f"模块 {module.name} 没有文件归属")
            if not module.tests:
                raise ValueError(f"模块 {module.name} 没有测试清单")
            for path in module.files:
                if path in owned:
                    raise ValueError(f"文件归属重复：{path}")
                owned.add(path)

    def _write_tests(self, repo: Path, draft: TestDraft) -> list[str]:
        written: list[str] = []
        for file in draft.files:
            relative = file.path.replace("\\", "/")
            if not relative.startswith("tests/"):
                raise ValueError("测试脚本必须位于 tests/ 目录")
            target = (repo / relative).resolve()
            try:
                target.relative_to(repo.resolve())
            except ValueError as exc:
                raise ValueError(f"测试路径越界：{relative}") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(file.content, encoding="utf-8")
            written.append(relative)
        if not written:
            raise ValueError("测试设计没有产出文件")
        return written

    def _validate_test_mapping(
        self, plan: PlanDraft, test_files: list[str], repo: Path
    ) -> None:
        available = set(test_files)
        existing = {
            path.relative_to(repo).as_posix()
            for path in (repo / "tests").rglob("*.py")
        }
        available |= existing
        for module in plan.modules:
            for test in module.tests:
                normalized = test.replace("\\", "/")
                if normalized not in available:
                    raise ValueError(
                        f"模块 {module.name} 的测试不存在：{test}"
                    )

    def _save_plan_document(
        self, project_id: str, run_id: str, plan: PlanDraft
    ) -> str:
        with self.session_factory() as session:
            current = session.scalar(
                select(func.max(Document.version)).where(
                    Document.project_id == project_id, Document.kind == "plan"
                )
            )
            document = Document(
                project_id=project_id,
                run_id=run_id,
                kind="plan",
                version=int(current or 0) + 1,
                content=plan.model_dump_json(),
                status="approved",
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            session.expunge(document)
            return document.id

    def _create_modules(
        self, project_id: str, run_id: str, plan: PlanDraft
    ) -> list[str]:
        ids: list[str] = []
        with self.session_factory() as session:
            for module in plan.modules:
                record = Module(
                    run_id=run_id,
                    project_id=project_id,
                    name=module.name,
                    status="待开始",
                    owner_agent="coder",
                    spec_json=module.model_dump(),
                    depends_on=list(module.depends_on),
                )
                session.add(record)
                session.flush()
                ids.append(record.id)
            session.commit()
        return ids
