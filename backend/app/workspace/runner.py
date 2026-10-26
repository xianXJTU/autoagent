"""受限子进程执行器。"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .policy import BlockedCommand, CommandPolicy

_BASE_ENV_KEYS = [
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
]


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    blocked: bool = False
    block_reason: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.blocked


class CommandRunner:
    def __init__(
        self,
        root: Path,
        policy: CommandPolicy | None = None,
        default_timeout: float = 300.0,
    ) -> None:
        self.root = root.resolve()
        self.policy = policy or CommandPolicy(self.root)
        self.default_timeout = default_timeout

    def run(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: float | None = None,
        allow_network: bool = False,
        extra_env: dict[str, str] | None = None,
    ) -> CommandResult:
        workdir = (cwd or self.root).resolve()
        try:
            self.policy.check(command, workdir)
        except BlockedCommand as exc:
            return CommandResult(
                command=command, exit_code=-1, blocked=True, block_reason=exc.reason
            )

        environment = self._environment(allow_network, extra_env)
        started = time.perf_counter()
        process = subprocess.Popen(
            command,
            cwd=str(workdir),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout or self.default_timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._terminate(process)
            stdout, stderr = process.communicate()
        duration = int((time.perf_counter() - started) * 1000)
        return CommandResult(
            command=command,
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_ms=duration,
            timed_out=timed_out,
        )

    def _terminate(self, process: subprocess.Popen) -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            process.kill()

    def _environment(
        self, allow_network: bool, extra: dict[str, str] | None
    ) -> dict[str, str]:
        environment = {
            key: os.environ[key] for key in _BASE_ENV_KEYS if key in os.environ
        }
        environment.update(
            {
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                "PIP_NO_INPUT": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "AUTOAGENT_PROJECT_ROOT": str(self.root),
            }
        )
        if not allow_network:
            proxy = "http://127.0.0.1:9"
            environment.update(
                {
                    "HTTP_PROXY": proxy,
                    "HTTPS_PROXY": proxy,
                    "ALL_PROXY": proxy,
                    "http_proxy": proxy,
                    "https_proxy": proxy,
                    "all_proxy": proxy,
                    "NO_PROXY": "",
                    "no_proxy": "",
                }
            )
        if extra:
            environment.update(extra)
        return environment
