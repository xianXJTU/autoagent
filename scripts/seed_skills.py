"""把技能目录同步到 MySQL 与 Chroma。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.db.session import build_engine, build_session_factory  # noqa: E402
from backend.app.llm.factory import (  # noqa: E402
    build_chat_provider,
    build_embedding_provider,
)
from backend.app.llm.service import ModelService  # noqa: E402
from backend.app.memory.vector_store import ChromaVectorStore  # noqa: E402
from backend.app.skills.indexer import SkillIndexer  # noqa: E402


async def main() -> None:
    settings = get_settings()
    settings.ensure_dirs()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    model_service = ModelService(
        build_chat_provider(settings),
        build_embedding_provider(settings),
        factory,
    )
    vector_store = ChromaVectorStore(path=settings.chroma_path, name="skills")
    indexer = SkillIndexer(factory, model_service, vector_store)
    skills = await indexer.index_all(settings.skills_root)
    print(f"已同步技能 {len(skills)} 条，向量库总数 {vector_store.count()}")
    engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
