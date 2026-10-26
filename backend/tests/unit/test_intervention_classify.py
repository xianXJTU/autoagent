from __future__ import annotations

from backend.app.services.intervention import InterventionType, classify_intervention


def test_classify() -> None:
    assert classify_intervention("再加一个预算提醒") is InterventionType.SCOPE_CHANGE
    assert classify_intervention("把导出格式改成 Excel") is InterventionType.SCOPE_CHANGE
    assert classify_intervention("全部不要了，重新开始") is InterventionType.OVERTHROW
    assert classify_intervention("导出的时候记得带表头") is InterventionType.SUPPLEMENT
