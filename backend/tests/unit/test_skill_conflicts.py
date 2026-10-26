from __future__ import annotations

from backend.app.db.models import Skill
from backend.app.skills.conflicts import detect_conflicts


def _skill(
    name: str,
    category: str,
    version: str,
    database: str,
) -> Skill:
    return Skill(
        name=name,
        category=category,
        version=version,
        decision_points_json={"database": database},
    )


def test_detects_and_resolves_by_category() -> None:
    domain = _skill("domain-db", "domain", "1.0.0", "sqlite")
    generic = _skill("generic-db", "generic", "2.0.0", "mysql")
    conflicts = detect_conflicts([domain, generic])
    assert len(conflicts) == 1
    assert conflicts[0].decision_point == "database"
    assert conflicts[0].winner is domain
    assert conflicts[0].values == {"domain-db": "sqlite", "generic-db": "mysql"}


def test_tie_needs_planner() -> None:
    first = _skill("a", "domain", "1.0.0", "sqlite")
    second = _skill("b", "domain", "1.0.0", "mysql")
    conflicts = detect_conflicts([first, second])
    assert conflicts[0].winner is None
    assert "策划者" in conflicts[0].reason


def test_same_value_is_not_conflict() -> None:
    first = _skill("a", "domain", "1.0.0", "sqlite")
    second = _skill("b", "generic", "1.0.0", "sqlite")
    assert detect_conflicts([first, second]) == []
