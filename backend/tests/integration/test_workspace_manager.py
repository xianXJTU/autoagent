from __future__ import annotations

from pathlib import Path

from backend.app.workspace.manager import WorkspaceManager


def test_worktrees_are_isolated_and_merge(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create("p1", "记账小工具")

    first = manager.create_module("p1", "m1")
    second = manager.create_module("p1", "m2")
    assert first != second

    (first / "a.txt").write_text("A", encoding="utf-8")
    (second / "b.txt").write_text("B", encoding="utf-8")
    assert not (first / "b.txt").exists()
    assert not (second / "a.txt").exists()

    assert manager.commit_module("p1", "m1", "模块一") is not None
    assert manager.commit_module("p1", "m2", "模块二") is not None
    assert manager.commit_module("p1", "m1", "无改动") is None

    assert manager.merge_module("p1", "m1").merged
    assert manager.merge_module("p1", "m2").merged

    repo = manager.repo_path("p1")
    assert (repo / "a.txt").read_text(encoding="utf-8") == "A"
    assert (repo / "b.txt").read_text(encoding="utf-8") == "B"
    assert set(manager.list_modules("p1")) == {"m1", "m2"}

    manager.remove_module("p1", "m1")
    assert not first.exists()


def test_conflict_is_detected_and_aborted(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "workspace")
    manager.create("p2", "冲突项目")
    first = manager.create_module("p2", "m1")
    second = manager.create_module("p2", "m2")

    (first / "README.md").write_text("第一版", encoding="utf-8")
    (second / "README.md").write_text("第二版", encoding="utf-8")
    manager.commit_module("p2", "m1", "改一")
    manager.commit_module("p2", "m2", "改二")

    assert manager.merge_module("p2", "m1").merged
    result = manager.merge_module("p2", "m2")
    assert not result.merged
    assert result.conflict
    # 合并已中止，主干仍保留第一版
    assert (manager.repo_path("p2") / "README.md").read_text(encoding="utf-8") == "第一版"
