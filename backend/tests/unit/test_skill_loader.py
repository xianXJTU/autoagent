from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.skills.loader import load_skills, parse_skill_text
from backend.app.skills.schema import SkillValidationError

ROOT = Path(__file__).resolve().parents[3]


def test_loads_bundled_skills() -> None:
    documents = load_skills(ROOT / "skills")
    names = {document.meta.name for document in documents}
    assert {"python-api-basic", "database-sqlite", "testing-basic", "generic-python"} <= names
    generic = next(document for document in documents if document.meta.name == "generic-python")
    assert generic.meta.category == "generic"


def test_rejects_missing_description(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: broken\n---\n正文", encoding="utf-8")
    with pytest.raises(SkillValidationError):
        parse_skill_text(path.read_text(encoding="utf-8"), path)


def test_rejects_missing_frontmatter(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text("没有头部", encoding="utf-8")
    with pytest.raises(SkillValidationError):
        parse_skill_text(path.read_text(encoding="utf-8"), path)
