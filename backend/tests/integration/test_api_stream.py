from __future__ import annotations

import json

from httpx import ASGITransport, AsyncClient


def _questions() -> dict:
    return {
        "reasoning": "先确认使用者和记账范围。",
        "content": json.dumps(
            {
                "questions": [
                    {
                        "question": "给谁用？",
                        "recommendation": "只给你自己",
                        "reason": "一个人使用更简单",
                        "options": [],
                    }
                ]
            },
            ensure_ascii=False,
        ),
    }


async def _read_events(client, url: str, body: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", url, json=body) as response:
        assert response.status_code == 200
        current = ""
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current = line[7:]
            elif line.startswith("data: "):
                events.append((current, json.loads(line[6:])))
                if current == "result":
                    break
    return events


async def test_alignment_and_message_streaming(api_app) -> None:
    provider = api_app.state.services.model_service.chat_provider
    provider.responses.extend(
        [
            _questions(),
            {"reasoning": "用户说够了，开始写需求文档。", "content": "# 需求\n记账工具"},
        ]
    )
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/projects", json={"name": "流式项目", "requirement": "做个记账工具"}
        )
        project_id = created.json()["project_id"]

        events = await _read_events(
            client, f"/api/projects/{project_id}/align/stream", {}
        )
        kinds = [kind for kind, _ in events]
        assert "thinking" in kinds
        assert "content" in kinds
        assert kinds[-1] == "result"
        assert events[-1][1]["questions"]["questions"][0]["question"] == "给谁用？"

        events = await _read_events(
            client,
            f"/api/projects/{project_id}/messages/stream",
            {"text": "够了"},
        )
        kinds = [kind for kind, _ in events]
        assert "thinking" in kinds
        assert "content" in kinds
        assert events[-1][1]["action"] == "review"
