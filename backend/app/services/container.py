"""应用级服务容器。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import chromadb

from ..agents.base import AgentContext
from ..agents.planner import PlannerAgent
from ..config import Settings
from ..db.session import build_engine, build_session_factory
from ..events.bus import EventBus
from ..events.service import EventService
from ..llm.factory import build_chat_provider, build_embedding_provider
from ..llm.service import ModelService
from ..memory.service import MemoryService
from ..memory.vector_store import ChromaVectorStore
from ..skills.recall import SkillRecallService
from ..workspace.manager import WorkspaceManager
from .alignment import AlignmentService
from .intervention import InterventionService
from .pipeline import PipelineService
from .preview import PreviewManager


class ServiceContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = build_engine(settings.database_url)
        self.session_factory = build_session_factory(self.engine)
        self.events = EventService(self.session_factory, settings.data_root, EventBus())
        self.workspace = WorkspaceManager(settings.workspace_root)
        self.model_service = ModelService(
            build_chat_provider(settings),
            build_embedding_provider(settings),
            self.session_factory,
        )
        self.chroma = chromadb.PersistentClient(path=str(settings.chroma_path))
        self.memory_store = ChromaVectorStore(client=self.chroma, name="memories")
        self.memory = MemoryService(
            self.session_factory, self.model_service, self.memory_store
        )
        self.skill_store = ChromaVectorStore(client=self.chroma, name="skills")
        self.skill_recall = SkillRecallService(
            self.session_factory, self.model_service, self.skill_store
        )
        self.preview = PreviewManager()
        self.pipeline = PipelineService(
            settings,
            self.session_factory,
            self.workspace,
            self.events,
            self.model_service,
            self.memory,
            self.skill_recall,
            test_python=Path(sys.executable),
        )
        self.tasks: dict[str, asyncio.Task] = {}

    def alignment_for(
        self, project_id: str, run_id: str, max_rounds: int = 5
    ) -> AlignmentService:
        planner = PlannerAgent(
            AgentContext(
                project_id=project_id,
                run_id=run_id,
                model_service=self.model_service,
            )
        )
        return AlignmentService(
            self.session_factory,
            planner,
            self.events,
            memory=self.memory,
            workspace_root=self.settings.workspace_root,
            max_rounds=max_rounds,
        )

    def intervention_for(self, project_id: str, run_id: str) -> InterventionService:
        return InterventionService(
            self.session_factory, self.events, memory=self.memory
        )

    def start_pipeline(self, project_id: str, run_id: str) -> asyncio.Task:
        existing = self.tasks.get(run_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(self.pipeline.run_after_approval(project_id, run_id))
        self.tasks[run_id] = task

        def _cleanup(_: asyncio.Task) -> None:
            self.tasks.pop(run_id, None)

        task.add_done_callback(_cleanup)
        return task

    def resume_pipeline(self, project_id: str, run_id: str, stage: str) -> asyncio.Task:
        existing = self.tasks.get(run_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(self.pipeline.resume(project_id, run_id, stage))
        self.tasks[run_id] = task

        def _cleanup(_: asyncio.Task) -> None:
            self.tasks.pop(run_id, None)

        task.add_done_callback(_cleanup)
        return task

    def close(self) -> None:
        self.preview.stop_all()
        for task in list(self.tasks.values()):
            if not task.done():
                task.cancel()
        self.engine.dispose()
