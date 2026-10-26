"""事件 JSONL 镜像，便于离线审计与评测。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_dir(data_root: Path, run_id: str) -> Path:
    return data_root / "runs" / run_id


def append_event_line(data_root: Path, run_id: str, record: dict[str, Any]) -> Path:
    directory = run_dir(data_root, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return path


def read_event_lines(data_root: Path, run_id: str) -> list[dict[str, Any]]:
    path = run_dir(data_root, run_id) / "events.jsonl"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
