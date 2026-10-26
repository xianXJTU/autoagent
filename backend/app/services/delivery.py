"""交付打包与启动脚本。"""

from __future__ import annotations

import zipfile
from pathlib import Path

_EXCLUDED = {".git", ".venv", "__pycache__", ".pytest_cache"}


def write_start_script(repo: Path) -> Path:
    if (repo / "app" / "main.py").exists():
        command = (
            '& $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port'
        )
    elif (repo / "main.py").exists():
        command = "& $python main.py --port $Port"
    else:
        command = 'Write-Error "找不到可启动入口：app/main.py 或 main.py"'
    content = f"""param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (Test-Path ".venv\\Scripts\\python.exe") {{
    $python = ".venv\\Scripts\\python.exe"
}} else {{
    $python = "python"
}}
{command}
"""
    path = repo / "start.ps1"
    path.write_text(content, encoding="utf-8")
    return path


def package_project(repo: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(repo.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo)
            if any(part in _EXCLUDED for part in relative.parts):
                continue
            archive.write(path, relative.as_posix())
    return output_path
