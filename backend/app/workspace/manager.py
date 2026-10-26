"""项目工作区与 Git 工作树。"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class MergeResult:
    merged: bool
    conflict: bool = False
    commit: str = ""
    message: str = ""


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        self._validate(project_id)
        return self.root / project_id

    def repo_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "repo"

    def module_path(self, project_id: str, module_id: str) -> Path:
        self._validate(module_id)
        return self.project_dir(project_id) / "modules" / module_id

    def create(self, project_id: str, name: str) -> Path:
        directory = self.project_dir(project_id)
        repo = directory / "repo"
        (directory / "modules").mkdir(parents=True, exist_ok=True)
        if not (repo / ".git").exists():
            repo.mkdir(parents=True, exist_ok=True)
            self._git(repo, "init", "-b", "main")
            self._git(repo, "config", "user.name", "autoagent")
            self._git(repo, "config", "user.email", "autoagent@local")
            (repo / "README.md").write_text(
                f"# {name}\n\n由 autoagent 生成。\n", encoding="utf-8"
            )
            (repo / ".gitignore").write_text(
                ".venv/\n__pycache__/\n*.pyc\ndata/\n.env\n", encoding="utf-8"
            )
            self._git(repo, "add", "-A")
            self._git(repo, "commit", "-m", "初始化项目")
        return directory

    def create_module(
        self, project_id: str, module_id: str, base_branch: str = "main"
    ) -> Path:
        repo = self.repo_path(project_id)
        worktree = self.module_path(project_id, module_id)
        if worktree.exists():
            return worktree
        worktree.parent.mkdir(parents=True, exist_ok=True)
        branch = f"module/{module_id}"
        self._git(
            repo, "worktree", "add", "-b", branch, str(worktree), base_branch
        )
        return worktree

    def commit_module(
        self, project_id: str, module_id: str, message: str
    ) -> str | None:
        worktree = self.module_path(project_id, module_id)
        status = self._git(worktree, "status", "--porcelain")
        if not status.strip():
            return None
        self._git(worktree, "add", "-A")
        self._git(worktree, "commit", "-m", message)
        return self._git(worktree, "rev-parse", "HEAD").strip()

    def merge_module(
        self, project_id: str, module_id: str, message: str | None = None
    ) -> MergeResult:
        repo = self.repo_path(project_id)
        branch = f"module/{module_id}"
        self._git(repo, "checkout", "main")
        result = subprocess.run(
            [
                "git",
                "merge",
                "--no-ff",
                branch,
                "-m",
                message or f"合并模块 {module_id}",
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=str(repo),
                capture_output=True,
                text=True,
            )
            return MergeResult(
                merged=False,
                conflict="CONFLICT" in (result.stdout + result.stderr),
                message=(result.stdout + result.stderr).strip()[:2000],
            )
        commit = self._git(repo, "rev-parse", "HEAD").strip()
        return MergeResult(merged=True, commit=commit, message="合并成功")

    def remove_module(self, project_id: str, module_id: str) -> None:
        worktree = self.module_path(project_id, module_id)
        if not worktree.exists():
            return
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree)],
            cwd=str(self.repo_path(project_id)),
            capture_output=True,
            text=True,
        )
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)

    def list_modules(self, project_id: str) -> list[str]:
        repo = self.repo_path(project_id)
        output = self._git(repo, "worktree", "list", "--porcelain")
        modules = []
        for line in output.splitlines():
            if line.startswith("worktree ") and "/modules/" in line.replace("\\", "/"):
                modules.append(Path(line.split(" ", 1)[1]).name)
        return modules

    def delete_project(self, project_id: str) -> bool:
        directory = self.project_dir(project_id)
        if not directory.exists():
            return False
        shutil.rmtree(directory, ignore_errors=True)
        return True

    def _git(self, cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} 失败：{(result.stderr or result.stdout).strip()}"
            )
        return result.stdout

    def _validate(self, identifier: str) -> None:
        if not _SAFE_ID.match(identifier):
            raise ValueError(f"非法标识：{identifier}")
