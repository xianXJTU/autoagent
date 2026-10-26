from __future__ import annotations

import asyncio
import json

from httpx import ASGITransport, AsyncClient


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _questions() -> dict:
    return {
        "content": json.dumps(
            {
                "questions": [
                    {
                        "question": "给谁用？",
                        "recommendation": "只给你自己",
                        "options": [],
                    }
                ]
            },
            ensure_ascii=False,
        )
    }


async def test_project_crud_and_alignment(api_app) -> None:
    async with _client(api_app) as client:
        created = await client.post(
            "/api/projects", json={"name": "接口项目", "requirement": "做个记账工具"}
        )
        assert created.status_code == 200
        data = created.json()
        project_id = data["project_id"]
        run_id = data["run_id"]

        listing = await client.get("/api/projects")
        assert listing.status_code == 200
        assert any(item["id"] == project_id for item in listing.json())

        detail = await client.get(f"/api/projects/{project_id}")
        assert detail.status_code == 200
        assert detail.json()["messages"][0]["content"] == "做个记账工具"

        provider = api_app.state.services.model_service.chat_provider
        provider.responses.append(_questions())
        aligned = await client.post(f"/api/projects/{project_id}/align")
        assert aligned.status_code == 200
        assert aligned.json()["questions"]["questions"][0]["question"] == "给谁用？"

        detailed = (await client.get(f"/api/projects/{project_id}")).json()
        planner_message = next(
            message for message in detailed["messages"] if message["role"] == "planner"
        )
        question = planner_message["meta"]["questions"]["questions"][0]
        assert question["recommendation"] == "只给你自己"
        assert question["reason"] == ""

        provider.responses.append({"content": "# 需求\n记账工具"})
        answered = await client.post(
            f"/api/projects/{project_id}/messages", json={"text": "够了"}
        )
        assert answered.status_code == 200
        assert answered.json()["action"] == "review"
        document_id = answered.json()["document_id"]

        documents = await client.get(f"/api/projects/{project_id}/documents")
        assert documents.status_code == 200
        assert documents.json()[0]["version"] == 1

        provider.responses.append({"content": "# 需求\n记账工具，带预算提醒"})
        changed = await client.post(
            f"/api/projects/{project_id}/documents/{document_id}/changes",
            json={"feedback": "加预算提醒"},
        )
        assert changed.status_code == 200
        assert changed.json()["version"] == 2

        diff = await client.get(f"/api/projects/{project_id}/documents/diff")
        assert "预算提醒" in diff.json()["diff"]

        files = await client.get(f"/api/projects/{project_id}/files")
        assert files.status_code == 200
        assert any(item["path"] == "README.md" for item in files.json())

        download = await client.get(f"/api/projects/{project_id}/download")
        assert download.status_code == 200
        assert "zip" in download.headers["content-type"]

        after = await client.get(f"/api/projects/{project_id}")
        assert after.json()["run_id"] == run_id


async def test_pause_resume_cancel(api_app) -> None:
    async with _client(api_app) as client:
        created = await client.post(
            "/api/projects", json={"name": "状态项目", "requirement": "做个待办"}
        )
        project_id = created.json()["project_id"]

        paused = await client.post(f"/api/projects/{project_id}/pause")
        assert paused.status_code == 200
        assert paused.json()["status"] == "暂停"

        resumed = await client.post(f"/api/projects/{project_id}/resume")
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "对齐中"

        cancelled = await client.post(f"/api/projects/{project_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "取消"


async def test_delete_project_and_running_guard(api_app) -> None:
    async with _client(api_app) as client:
        created = await client.post(
            "/api/projects", json={"name": "待删除项目", "requirement": "任意"}
        )
        project_id = created.json()["project_id"]
        run_id = created.json()["run_id"]
        services = api_app.state.services
        workspace = services.workspace.project_dir(project_id)
        run_dir = services.settings.data_root / "runs" / run_id
        assert workspace.exists()
        assert run_dir.exists()

        task = asyncio.create_task(asyncio.sleep(10))
        services.tasks[run_id] = task
        try:
            blocked = await client.delete(f"/api/projects/{project_id}")
            assert blocked.status_code == 409
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            services.tasks.pop(run_id, None)

        deleted = await client.delete(
            f"/api/projects/{project_id}?keep_traces=false"
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"]
        assert not workspace.exists()
        assert not run_dir.exists()
        assert (await client.get(f"/api/projects/{project_id}")).status_code == 404
        listing = await client.get("/api/projects")
        assert all(item["id"] != project_id for item in listing.json())


async def test_evaluation_endpoint(api_app) -> None:
    async with _client(api_app) as client:
        created = await client.post(
            "/api/projects", json={"name": "评测接口", "requirement": "任意"}
        )
        run_id = created.json()["run_id"]
        response = await client.get(f"/api/runs/{run_id}/evaluation")
        assert response.status_code == 200
        body = response.json()
        assert body["run_id"] == run_id
        assert "metrics" in body
        assert body["scores"] == []
