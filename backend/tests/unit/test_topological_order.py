from __future__ import annotations

import pytest

from backend.app.db.models import Module
from backend.app.services.merging import topological_order


def _module(name: str, depends_on: list[str]) -> Module:
    return Module(
        run_id="r", project_id="p", name=name, depends_on=depends_on,
        spec_json={},
    )


def test_orders_dependencies() -> None:
    modules = [_module("接口", ["数据"]), _module("数据", []), _module("页面", ["接口"])]
    ordered = [module.name for module in topological_order(modules)]
    assert ordered.index("数据") < ordered.index("接口") < ordered.index("页面")


def test_detects_cycle() -> None:
    modules = [_module("a", ["b"]), _module("b", ["a"])]
    with pytest.raises(ValueError):
        topological_order(modules)
