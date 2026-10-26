"""业务状态机定义。

状态字符串直接使用中文，与 INFO 和界面保持一致。
"""

from __future__ import annotations

from typing import Any, TypedDict

STAGE_ALIGNING = "对齐中"
STAGE_REVIEW = "待审阅"
STAGE_APPROVED = "已批准"
STAGE_PLANNING = "计划中"
STAGE_PLAN_READY = "计划就绪"
STAGE_CODING = "编码中"
STAGE_TESTING = "测试中"
STAGE_MERGING = "合并中"
STAGE_ACCEPTING = "验收中"
STAGE_DELIVERED = "已交付"
STAGE_PAUSED = "暂停"
STAGE_CANCELLED = "取消"
STAGE_FAILED = "失败"

TERMINAL_STAGES = {STAGE_CANCELLED, STAGE_FAILED, STAGE_DELIVERED}
STOP_STAGES = {STAGE_PAUSED, STAGE_CANCELLED, STAGE_FAILED}

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STAGE_ALIGNING: {STAGE_REVIEW, STAGE_CANCELLED, STAGE_FAILED},
    STAGE_REVIEW: {STAGE_ALIGNING, STAGE_APPROVED, STAGE_CANCELLED, STAGE_FAILED},
    STAGE_APPROVED: {STAGE_PLANNING, STAGE_CANCELLED, STAGE_FAILED},
    STAGE_PLANNING: {STAGE_PLAN_READY, STAGE_CANCELLED, STAGE_FAILED},
    STAGE_PLAN_READY: {STAGE_CODING, STAGE_CANCELLED, STAGE_FAILED},
    STAGE_CODING: {STAGE_TESTING, STAGE_CANCELLED, STAGE_FAILED},
    STAGE_TESTING: {
        STAGE_MERGING,
        STAGE_CODING,
        STAGE_CANCELLED,
        STAGE_FAILED,
    },
    STAGE_MERGING: {
        STAGE_ACCEPTING,
        STAGE_CODING,
        STAGE_CANCELLED,
        STAGE_FAILED,
    },
    STAGE_ACCEPTING: {
        STAGE_DELIVERED,
        STAGE_CODING,
        STAGE_CANCELLED,
        STAGE_FAILED,
    },
    STAGE_DELIVERED: {STAGE_ALIGNING},
    STAGE_PAUSED: {
        STAGE_ALIGNING,
        STAGE_REVIEW,
        STAGE_APPROVED,
        STAGE_PLANNING,
        STAGE_PLAN_READY,
        STAGE_CODING,
        STAGE_TESTING,
        STAGE_MERGING,
        STAGE_ACCEPTING,
        STAGE_CANCELLED,
        STAGE_FAILED,
    },
    STAGE_CANCELLED: set(),
    STAGE_FAILED: {STAGE_ALIGNING},
}


class InvalidTransition(ValueError):
    pass


class RunState(TypedDict, total=False):
    project_id: str
    run_id: str
    stage: str
    approved: bool
    user_message: str
    requirement_version: int
    plan_version: int
    module_ids: list[str]
    module_states: dict[str, str]
    usage: dict[str, Any]
    last_error: str
    paused_from: str
    evaluated: bool
    summary: str
    readme: str
    plan_json: str
    plan_document_id: str
    test_files: list[str]
    package_path: str


def initial_state(project_id: str, run_id: str) -> RunState:
    return {
        "project_id": project_id,
        "run_id": run_id,
        "stage": STAGE_ALIGNING,
        "approved": False,
        "user_message": "",
        "requirement_version": 0,
        "plan_version": 0,
        "module_ids": [],
        "module_states": {},
        "usage": {"elapsed_seconds": 0, "total_tokens": 0, "model_calls": 0},
        "last_error": "",
        "paused_from": "",
        "evaluated": False,
        "summary": "",
        "readme": "",
        "plan_json": "",
        "plan_document_id": "",
        "test_files": [],
        "package_path": "",
    }


def validate_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        raise InvalidTransition(f"未知状态：{current}")
    # 暂停与取消是全局旁路，除终态外都允许
    if target in {STAGE_PAUSED, STAGE_CANCELLED} and current not in {
        STAGE_CANCELLED,
        STAGE_FAILED,
    }:
        return
    if target not in allowed:
        raise InvalidTransition(f"不允许从「{current}」转移到「{target}」")
