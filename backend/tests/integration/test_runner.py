from __future__ import annotations

import os
import sys
from pathlib import Path

from backend.app.workspace.runner import CommandRunner


def test_runner_captures_output_and_redacts_environment(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    os.environ["DEEPSEEK_API_KEY"] = "top-secret"
    runner = CommandRunner(root)
    result = runner.run(
        [sys.executable, "-c", "import os; print('你好'); print(os.environ.get('DEEPSEEK_API_KEY', 'NONE'))"]
    )
    assert result.exit_code == 0
    assert "你好" in result.stdout
    assert "top-secret" not in result.stdout
    assert "NONE" in result.stdout


def test_runner_blocks_outside_cwd(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    runner = CommandRunner(root)
    result = runner.run([sys.executable, "-c", "print(1)"], cwd=tmp_path)
    assert result.blocked
    assert "超出项目范围" in result.block_reason


def test_runner_blocks_destructive(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    runner = CommandRunner(root)
    result = runner.run(["format", "C:"])
    assert result.blocked


def test_runner_timeout(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    runner = CommandRunner(root)
    result = runner.run(
        [sys.executable, "-c", "import time; time.sleep(10)"], timeout=1
    )
    assert result.timed_out
    assert not result.ok


def test_runner_network_off_sets_proxy(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    runner = CommandRunner(root)
    result = runner.run(
        [sys.executable, "-c", "import os; print(os.environ.get('HTTP_PROXY'))"]
    )
    assert "127.0.0.1:9" in result.stdout
