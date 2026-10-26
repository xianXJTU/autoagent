from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.app.workspace.policy import BlockedCommand, CommandPolicy
from backend.app.workspace.ports import PortAllocator


def test_port_allocate_and_release() -> None:
    allocator = PortAllocator(start=18800, end=18802)
    first = allocator.allocate()
    second = allocator.allocate()
    assert first != second
    allocator.release(first)
    assert first in {first, second}
    assert allocator.allocated() >= {second}


def test_policy_blocks_destructive() -> None:
    policy = CommandPolicy(Path.cwd())
    with pytest.raises(BlockedCommand):
        policy.check(["format", "C:"])
    with pytest.raises(BlockedCommand):
        policy.check(["cmd", "/c", "del", "/s", "/q", "x"])


def test_policy_blocks_outside_paths(tmp_path: Path) -> None:
    policy = CommandPolicy(tmp_path)
    with pytest.raises(BlockedCommand):
        policy.check(["cmd", str(tmp_path.parent / "outside.txt")])
    with pytest.raises(BlockedCommand):
        policy.check([sys.executable, "-c", "print(1)"], cwd=tmp_path.parent)


def test_policy_allows_python() -> None:
    policy = CommandPolicy(Path.cwd())
    policy.check([sys.executable, "-c", "print(1)"])
