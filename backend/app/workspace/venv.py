"""项目独立虚拟环境。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def venv_python(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def create_venv(venv_path: Path, with_pip: bool = True, timeout: float = 300.0) -> Path:
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "venv", str(venv_path)]
    if not with_pip:
        command.append("--without-pip")
    subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=timeout
    )
    return venv_python(venv_path)


def install_packages(
    venv_path: Path,
    packages: list[str],
    index_url: str | None = None,
    timeout: float = 900.0,
) -> subprocess.CompletedProcess[str]:
    command = [str(venv_python(venv_path)), "-m", "pip", "install", *packages]
    if index_url:
        command.extend(["--index-url", index_url])
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PIP_NO_INPUT": "1"},
    )
