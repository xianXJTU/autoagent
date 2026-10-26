"""代理工具与权限矩阵。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from ..workspace.runner import CommandRunner

ROLE_TOOLS: dict[str, set[str]] = {
    "planner": {
        "read_file",
        "list_files",
        "write_document",
        "recall_skills",
        "query_memory",
    },
    "coder": {
        "read_file",
        "list_files",
        "write_file",
        "run_command",
        "run_tests",
    },
    "reviewer": {"read_file", "list_files", "write_test", "run_tests"},
    "evaluator": {"read_file", "list_files", "query_events"},
}


class ToolPermissionError(PermissionError):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str]


_TOOL_SPECS = {
    "read_file": ToolSpec("read_file", "读取项目内文件", {"path": "相对路径"}),
    "list_files": ToolSpec("list_files", "列出项目内文件", {"path": "相对路径，默认根"}),
    "write_file": ToolSpec("write_file", "写入本模块文件", {"path": "相对路径", "content": "文本"}),
    "write_test": ToolSpec("write_test", "写入测试脚本", {"path": "tests/ 下的路径", "content": "文本"}),
    "write_document": ToolSpec("write_document", "写入需求文档或计划", {"path": "README.md 或 docs/ 下路径", "content": "文本"}),
    "run_command": ToolSpec("run_command", "在项目内执行命令", {"command": "命令数组"}),
    "run_tests": ToolSpec("run_tests", "运行测试", {"args": "pytest 参数数组，可选"}),
    "recall_skills": ToolSpec("recall_skills", "按查询召回技能", {"query": "查询文本"}),
    "query_memory": ToolSpec("query_memory", "查询记忆", {"query": "查询文本"}),
    "query_events": ToolSpec("query_events", "查询运行事件", {"run_id": "运行标识"}),
}


class ToolRegistry:
    def __init__(
        self,
        root: Path,
        runner: CommandRunner | None = None,
        venv_python: Path | None = None,
        skill_recall: Callable[[str], Awaitable[list[Any]]] | None = None,
        memory_query: Callable[[str], Awaitable[list[Any]]] | None = None,
        event_query: Callable[[str], Awaitable[list[Any]]] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.runner = runner
        self.venv_python = venv_python
        self.skill_recall = skill_recall
        self.memory_query = memory_query
        self.event_query = event_query

    def specs(self, role: str) -> list[ToolSpec]:
        return [
            _TOOL_SPECS[name]
            for name in sorted(ROLE_TOOLS.get(role, set()))
            if name in _TOOL_SPECS
        ]

    async def execute(self, role: str, tool: str, **kwargs: Any) -> Any:
        if tool not in ROLE_TOOLS.get(role, set()):
            raise ToolPermissionError(f"角色 {role} 无权调用工具 {tool}")

        if tool == "read_file":
            return self._read_file(kwargs["path"])
        if tool == "list_files":
            return self._list_files(kwargs.get("path", "."))
        if tool == "write_file":
            if role != "coder":
                raise ToolPermissionError("只有编码者可以写业务文件")
            path = kwargs["path"]
            if path.replace("\\", "/").startswith("tests/"):
                raise ToolPermissionError("测试脚本已冻结，编码者不得修改")
            return self._write(path, kwargs["content"])
        if tool == "write_test":
            if role != "reviewer":
                raise ToolPermissionError("只有验收者可以写测试")
            path = kwargs["path"].replace("\\", "/")
            if not path.startswith("tests/"):
                raise ToolPermissionError("测试脚本必须放在 tests/ 目录")
            return self._write(path, kwargs["content"])
        if tool == "write_document":
            if role != "planner":
                raise ToolPermissionError("只有策划者可以写共享文档")
            path = kwargs["path"].replace("\\", "/")
            if path not in {"README.md", "PLAN.md"} and not path.startswith("docs/"):
                raise ToolPermissionError("只允许写 README.md、PLAN.md 或 docs/ 下的文档")
            return self._write(path, kwargs["content"])
        if tool == "run_command":
            if self.runner is None:
                raise RuntimeError("未配置命令执行器")
            return self._command_result(
                self.runner.run(list(kwargs["command"]), allow_network=False)
            )
        if tool == "run_tests":
            if self.runner is None:
                raise RuntimeError("未配置命令执行器")
            args = list(kwargs.get("args", []))
            python = str(self.venv_python or sys.executable)
            return self._command_result(
                self.runner.run(
                    [python, "-m", "pytest", *args], allow_network=False
                )
            )
        if tool == "recall_skills":
            if self.skill_recall is None:
                return []
            return await self.skill_recall(kwargs["query"])
        if tool == "query_memory":
            if self.memory_query is None:
                return []
            return await self.memory_query(kwargs["query"])
        if tool == "query_events":
            if self.event_query is None:
                return []
            return await self.event_query(kwargs["run_id"])
        raise ToolPermissionError(f"未知工具：{tool}")

    def _resolve(self, path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ToolPermissionError(f"路径超出项目范围：{path}") from exc
        return resolved

    def _read_file(self, path: str) -> str:
        return self._resolve(path).read_text(encoding="utf-8")

    def _list_files(self, path: str) -> list[str]:
        base = self._resolve(path)
        if not base.exists():
            return []
        return sorted(
            item.relative_to(self.root).as_posix()
            for item in base.rglob("*")
            if item.is_file()
        )

    def _write(self, path: str, content: str) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
        return target.relative_to(self.root).as_posix()

    @staticmethod
    def _command_result(result: Any) -> dict[str, Any]:
        return {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
            "blocked": result.blocked,
            "block_reason": result.block_reason,
        }
