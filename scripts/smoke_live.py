"""真实模型连通性冒烟：只发一条极短对话与一条向量请求。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.llm.factory import (  # noqa: E402
    build_chat_provider,
    build_embedding_provider,
)


async def main() -> None:
    settings = get_settings()
    chat = build_chat_provider(settings)
    embedding = build_embedding_provider(settings)
    result = await chat.chat(
        [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=16
    )
    print("对话模型：", result.model, "返回：", result.content[:50])
    vectors = await embedding.embed(["连通性测试"])
    print("向量模型：", vectors.model, "维度：", len(vectors.vectors[0]))


if __name__ == "__main__":
    asyncio.run(main())
