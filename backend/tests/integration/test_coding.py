from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.db.models import Module, Project, Run, TestResult
from backend.app.events.service import EventService
from backend.app.llm.fake import FakeLLMProvider
from backend.app.llm.service import ModelService
from backend.app.services.coding import CodingService
from backend.app.workspace.manager import WorkspaceManager


TEST_CODE = """\
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.module1 import add

def test_add():
    assert add(1, 2) == 3
"""


async def test_coding_fix_loop_and_commit(
    db_session, memory_session_factory, test_settings: Settings, tmp_path: Path
) -> None:
    project = Project(name="编码项目", workspace_path=str(tmp_path / "ws"))
    db_session.add(project)
    db_session.flush()
    run = Run(project_id=project.id, thread_id="thread-code")
    db_session.add(run)
    db_session.flush()

    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create(project.id, "编码项目")
    repo = manager.repo_path(project.id)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_module1.py").write_text(TEST_CODE, encoding="utf-8")
    manager.commit_main(project.id, "添加测试")

    module = Module(
        run_id=run.id,
        project_id=project.id,
        name="模块1",
        status="待开始",
        spec_json={
            "name": "模块1",
            "description": "提供加法",
            "files": ["app/module1.py"],
            "tests": ["tests/test_module1.py"],
            "interfaces": "add(a,b)",
        },
    )
    db_session.add(module)
    db_session.commit()

    provider = FakeLLMProvider(
        [
            {
                "content": json.dumps(
                    {
                        "files": [
                            {"path": "app/module1.py", "content": "def add(a, b):\n    return a - b\n"}
                        ]
                    }
                )
            },
            {
                "content": json.dumps(
                    {
                        "files": [
                            {"path": "app/module1.py", "content": "def add(a, b):\n    return a + b\n"}
                        ]
                    }
                )
            },
        ]
    )
    model_service = ModelService(provider, provider, memory_session_factory)
    events = EventService(memory_session_factory, test_settings.data_root)
    service = CodingService(
        memory_session_factory,
        manager,
        events,
        model_service,
        max_fix_rounds=3,
    )

    results = await service.code_modules(
        project.id, run.id, [module.id], test_python=Path(sys.executable)
    )
    assert results[0].status == "已完成"
    assert results[0].rounds == 2
    assert results[0].commit

    db_session.expire_all()
    loaded = db_session.get(Module, module.id)
    assert loaded.status == "已完成"
    tests = db_session.scalars(select(TestResult)).all()
    assert sorted(row.result for row in tests) == ["fail", "pass"]
    worktree_file = manager.module_path(project.id, module.id) / "app" / "module1.py"
    assert "a + b" in worktree_file.read_text(encoding="utf-8")
