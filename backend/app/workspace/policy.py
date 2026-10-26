"""命令安全策略：拦截破坏性命令与越界路径。"""

from __future__ import annotations

import re
from pathlib import Path

_DANGEROUS = [
    re.compile(r"(?i)(^|\s)format(\.com)?(\s|$)"),
    re.compile(r"(?i)\bdiskpart\b"),
    re.compile(r"(?i)\breg(edit|add|delete|query)\b"),
    re.compile(r"(?i)\bshutdown\b"),
    re.compile(r"(?i)\bmkfs\b"),
    re.compile(r"(?i)\bdd\s+if="),
    re.compile(r"(?i)rm\s+-rf\s+(/|~|[A-Za-z]:\\)"),
    re.compile(r"(?i)del\s+/[fsq]"),
    re.compile(r"(?i)(rd|rmdir)\s+/s"),
    re.compile(r"(?i)remove-item.*-recurse"),
    re.compile(r"(?i)\bbcdedit\b"),
    re.compile(r"(?i)\bwmic\s+.*\bdelete\b"),
]


class BlockedCommand(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CommandPolicy:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def check(self, command: list[str], cwd: Path | None = None) -> None:
        if not command:
            raise BlockedCommand("空命令")
        joined = " ".join(command)
        for pattern in _DANGEROUS:
            if pattern.search(joined):
                raise BlockedCommand(f"命令被安全策略拦截：{pattern.pattern}")

        workdir = (cwd or self.root).resolve()
        if not self._inside(workdir):
            raise BlockedCommand(f"工作目录超出项目范围：{workdir}")

        for argument in command[1:]:
            if argument.startswith("-"):
                continue
            if re.match(r"^[A-Za-z]:[\\/]", argument) or argument.startswith(("/", "\\")):
                if not self._inside(Path(argument).resolve()):
                    raise BlockedCommand(f"参数路径超出项目范围：{argument}")
            elif argument.startswith(".."):
                if not self._inside((workdir / argument).resolve()):
                    raise BlockedCommand(f"参数路径超出项目范围：{argument}")

    def _inside(self, path: Path) -> bool:
        try:
            path.relative_to(self.root)
            return True
        except ValueError:
            return False
