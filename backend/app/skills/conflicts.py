"""技能冲突检测与裁决。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..db.models import Skill

PRIORITY = {"user": 0, "project": 1, "domain": 2, "generic": 3}


def _version_key(version: str) -> tuple[int, ...]:
    numbers = tuple(int(item) for item in re.findall(r"\d+", version))
    return numbers or (0,)


@dataclass
class SkillConflict:
    decision_point: str
    values: dict[str, str] = field(default_factory=dict)
    winner: Skill | None = None
    reason: str = ""


def _best(group: list[Skill]) -> tuple[Skill | None, str]:
    min_priority = min(PRIORITY.get(skill.category, 9) for skill in group)
    top = [skill for skill in group if PRIORITY.get(skill.category, 9) == min_priority]
    top.sort(key=lambda skill: _version_key(skill.version), reverse=True)
    if len(top) >= 2 and _version_key(top[0].version) == _version_key(top[1].version):
        return None, "同优先级且版本相同，需要策划者裁决"
    return top[0], "按优先级与版本裁决"


def detect_conflicts(skills: list[Skill]) -> list[SkillConflict]:
    by_point: dict[str, list[Skill]] = {}
    for skill in skills:
        for point in (skill.decision_points_json or {}):
            by_point.setdefault(point, []).append(skill)

    conflicts: list[SkillConflict] = []
    for point, group in sorted(by_point.items()):
        values: dict[str, str] = {}
        for skill in group:
            values[skill.name] = str(skill.decision_points_json[point])
        if len(set(values.values())) <= 1:
            continue
        winner, reason = _best(group)
        conflicts.append(
            SkillConflict(
                decision_point=point, values=values, winner=winner, reason=reason
            )
        )
    return conflicts
