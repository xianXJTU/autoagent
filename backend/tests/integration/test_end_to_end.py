from __future__ import annotations

import asyncio
import json
import zipfile

from httpx import ASGITransport, AsyncClient


def _questions() -> dict:
    return {
        "content": json.dumps(
            {
                "questions": [
                    {
                        "question": "只给你自己用吗？",
                        "recommendation": "是",
                        "options": [],
                    }
                ]
            },
            ensure_ascii=False,
        )
    }


PLAN = {
    "modules": [
        {
            "name": "入口模块",
            "description": "提供 FastAPI 入口",
            "files": ["app/main.py"],
            "depends_on": [],
            "tests": ["tests/test_app.py"],
        }
    ],
    "interfaces": "无",
    "acceptance_map": {"能生成入口文件": "tests/test_app.py"},
}

TESTS = {
    "files": [
        {
            "path": "tests/test_app.py",
            "content": (
                "from pathlib import Path\n\n"
                "def test_entry():\n"
                "    assert (Path(__file__).resolve().parents[1] / 'app' / 'main.py').exists()\n"
            ),
        }
    ]
}

CODE = {
    "files": [
        {
            "path": "app/main.py",
            "content": "from fastapi import FastAPI\n\napp = FastAPI()\n",
        }
    ]
}

VERDICT = {
    "passed": True,
    "score": 4,
    "issues": [],
    "evidence": ["tests/test_app.py:1"],
}

EVALUATION = {
    "dimensions": [
        {
            "dimension": "业务拆分质量",
            "score": 4,
            "evidence": ["events:1"],
            "issue": "",
        }
    ],
    "summary": "链路通过",
}


async def test_full_pipeline_from_requirement_to_delivery(api_app) -> None:
    services = api_app.state.services
    provider = services.model_service.chat_provider
    provider.responses.extend(
        [
            _questions(),
            {"content": "# 需求\n做一个最小可运行项目"},
            {"content": json.dumps(PLAN, ensure_ascii=False)},
            {"content": json.dumps(TESTS, ensure_ascii=False)},
            {"content": json.dumps(CODE, ensure_ascii=False)},
            {"content": json.dumps(VERDICT, ensure_ascii=False)},
            {"content": json.dumps(EVALUATION, ensure_ascii=False)},
        ]
    )

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/projects",
            json={"name": "端到端项目", "requirement": "做一个最小可运行项目"},
        )
        assert created.status_code == 200
        project_id = created.json()["project_id"]
        run_id = created.json()["run_id"]

        aligned = await client.post(f"/api/projects/{project_id}/align")
        assert aligned.status_code == 200

        answered = await client.post(
            f"/api/projects/{project_id}/messages", json={"text": "够了"}
        )
        assert answered.status_code == 200
        assert answered.json()["action"] == "review"
        document_id = answered.json()["document_id"]

        approved = await client.post(
            f"/api/projects/{project_id}/documents/{document_id}/approve"
        )
        assert approved.status_code == 200

        task = services.tasks.get(run_id)
        if task is not None:
            result = await asyncio.wait_for(task, timeout=240)
            assert result.get("stage") == "已交付", result.get("last_error")

        detail = None
        for _ in range(60):
            detail = (await client.get(f"/api/projects/{project_id}")).json()
            if detail["run_status"] == "已交付":
                break
            await asyncio.sleep(0.5)
        assert detail is not None
        assert detail["run_status"] == "已交付", detail

        files = (await client.get(f"/api/projects/{project_id}/files")).json()
        paths = {item["path"] for item in files}
        assert "app/main.py" in paths
        assert "tests/test_app.py" in paths
        assert "start.ps1" in paths

        evaluation = (await client.get(f"/api/runs/{run_id}/evaluation")).json()
        dimensions = {row["dimension"] for row in evaluation["scores"]}
        assert "可运行性" in dimensions
        assert "业务拆分质量" in dimensions

        documents = (await client.get(f"/api/projects/{project_id}/documents")).json()
        assert all(item["kind"] != "plan" for item in documents)

        download = await client.get(f"/api/projects/{project_id}/download")
        assert download.status_code == 200
        archive_path = services.settings.data_root / "exports" / f"{project_id}.zip"
        assert archive_path.exists()
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
        assert "app/main.py" in names
        assert "tests/test_app.py" in names
        assert "start.ps1" in names
