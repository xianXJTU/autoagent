from __future__ import annotations

from backend.app.agents.schemas import AlignmentQuestions, Question
from backend.app.services.alignment import format_questions


def test_questions_show_recommendation_and_reason() -> None:
    questions = AlignmentQuestions(
        questions=[
            Question(
                question="这个工具主要给谁用？",
                recommendation="只给你自己用",
                reason="一个人使用不需要登录和权限，能更快做出来。",
            )
        ]
    )
    text = format_questions(questions, 1)
    assert "这个工具主要给谁用？" in text
    assert "推荐做法：只给你自己用" in text
    assert "推荐理由：一个人使用不需要登录和权限" in text
