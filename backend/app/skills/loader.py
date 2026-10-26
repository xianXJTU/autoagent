from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import SkillDocument, SkillMeta, SkillValidationError

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def parse_skill_text(text: str, path: Path) -> SkillDocument:
    match = _FRONTMATTER.match(text)
    if match is None:
        raise SkillValidationError(f"{path} 缺少 YAML 头部")
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillValidationError(f"{path} 头部不是合法 YAML：{exc}") from exc
    if not isinstance(data, dict):
        raise SkillValidationError(f"{path} 头部必须是键值映射")
    try:
        meta = SkillMeta.model_validate(data)
    except ValidationError as exc:
        raise SkillValidationError(f"{path} 元数据不合法：{exc}") from exc
    return SkillDocument(meta=meta, body=match.group(2).strip(), path=path)


def load_skill_file(path: Path) -> SkillDocument:
    return parse_skill_text(path.read_text(encoding="utf-8"), path)


def load_skills(root: Path) -> list[SkillDocument]:
    if not root.exists():
        return []
    documents = [load_skill_file(path) for path in sorted(root.glob("*/SKILL.md"))]
    names = [document.meta.name for document in documents]
    if len(set(names)) != len(names):
        raise SkillValidationError("技能名称重复")
    return documents
