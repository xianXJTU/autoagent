from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.agents.tools import ToolPermissionError, ToolRegistry
from backend.app.workspace.runner import CommandRunner


def _tools(tmp_path: Path) -> ToolRegistry:
    root = tmp_path / "project"
    root.mkdir()
    return ToolRegistry(root, runner=CommandRunner(root))


async def test_coder_can_write_but_not_tests_or_outside(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    written = await tools.execute(
        "coder", "write_file", path="app/main.py", content="print('ok')"
    )
    assert written == "app/main.py"
    with pytest.raises(ToolPermissionError):
        await tools.execute("coder", "write_file", path="tests/test_a.py", content="x")
    with pytest.raises(ToolPermissionError):
        await tools.execute("coder", "write_file", path="../evil.py", content="x")


async def test_reviewer_can_only_write_tests(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    await tools.execute(
        "reviewer", "write_test", path="tests/test_a.py", content="def test_a(): pass"
    )
    with pytest.raises(ToolPermissionError):
        await tools.execute("reviewer", "write_file", path="app/main.py", content="x")
    with pytest.raises(ToolPermissionError):
        await tools.execute(
            "reviewer", "write_test", path="app/test_a.py", content="x"
        )


async def test_planner_and_evaluator_cannot_write_code(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    with pytest.raises(ToolPermissionError):
        await tools.execute("planner", "write_file", path="app/main.py", content="x")
    with pytest.raises(ToolPermissionError):
        await tools.execute("evaluator", "write_file", path="app/main.py", content="x")
    path = await tools.execute(
        "planner", "write_document", path="README.md", content="# 需求"
    )
    assert path == "README.md"


async def test_role_tool_lists_are_scoped(tmp_path: Path) -> None:
    tools = _tools(tmp_path)
    coder = {spec.name for spec in tools.specs("coder")}
    reviewer = {spec.name for spec in tools.specs("reviewer")}
    evaluator = {spec.name for spec in tools.specs("evaluator")}
    assert "write_file" in coder and "write_test" not in coder
    assert "write_test" in reviewer and "write_file" not in reviewer
    assert "write_test" not in evaluator and "run_command" not in evaluator
