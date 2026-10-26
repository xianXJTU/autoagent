from __future__ import annotations

import sys
from pathlib import Path

from backend.app.workspace.runner import CommandRunner
from backend.app.workspace.venv import create_venv


def test_create_venv_and_run(tmp_path: Path) -> None:
    venv = tmp_path / "project" / ".venv"
    python = create_venv(venv, with_pip=False)
    assert python.exists()

    root = tmp_path / "project"
    runner = CommandRunner(root)
    result = runner.run([str(python), "-c", "print('venv-ok')"])
    assert result.exit_code == 0
    assert "venv-ok" in result.stdout
