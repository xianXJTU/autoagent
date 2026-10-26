"""按需预览：启动生成物并在停止时释放端口。"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from ..workspace.ports import PortAllocator
from ..workspace.runner import safe_environment


@dataclass
class PreviewSession:
    project_id: str
    port: int
    process: subprocess.Popen
    url: str


class PreviewManager:
    def __init__(
        self, allocator: PortAllocator | None = None, host: str = "127.0.0.1"
    ) -> None:
        self.allocator = allocator or PortAllocator()
        self.host = host
        self._sessions: dict[str, PreviewSession] = {}

    def start(
        self,
        project_id: str,
        repo: Path,
        python: Path | None = None,
        timeout: float = 20.0,
    ) -> PreviewSession:
        existing = self._sessions.get(project_id)
        if existing is not None:
            return existing
        interpreter = str(python or sys.executable)
        port = self.allocator.allocate()
        command = self._command(repo, interpreter, port)
        process = subprocess.Popen(
            command,
            cwd=str(repo),
            env=safe_environment(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if not self._wait(port, timeout):
            self._terminate(process)
            self.allocator.release(port)
            output = ""
            try:
                stdout, stderr = process.communicate(timeout=2)
                output = (stdout or "") + (stderr or "")
            except Exception:
                pass
            raise RuntimeError(f"预览启动失败：{output[-2000:]}")
        session = PreviewSession(
            project_id=project_id,
            port=port,
            process=process,
            url=f"http://{self.host}:{port}/",
        )
        self._sessions[project_id] = session
        return session

    def stop(self, project_id: str) -> bool:
        session = self._sessions.pop(project_id, None)
        if session is None:
            return False
        self._terminate(session.process)
        self.allocator.release(session.port)
        return True

    def stop_all(self) -> None:
        for project_id in list(self._sessions):
            self.stop(project_id)

    def _command(self, repo: Path, interpreter: str, port: int) -> list[str]:
        if (repo / "main.py").exists():
            return [interpreter, "main.py", "--port", str(port)]
        if (repo / "app" / "main.py").exists():
            return [
                interpreter,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                self.host,
                "--port",
                str(port),
            ]
        raise RuntimeError("找不到可启动入口：app/main.py 或 main.py")

    def _wait(self, port: int, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection((self.host, port), timeout=0.5):
                    return True
            except OSError:
                time.sleep(0.2)
        return False

    def _terminate(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                process.kill()
