"""向量存储封装，默认使用 Chroma 持久化。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb


@dataclass
class VectorHit:
    id: str
    document: str
    metadata: dict[str, Any]
    distance: float


class ChromaVectorStore:
    def __init__(
        self,
        path: Path | None = None,
        client: Any | None = None,
        name: str = "memories",
    ) -> None:
        self.client = client or chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )

    def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete(self, ids: list[str]) -> None:
        self.collection.delete(ids=ids)

    def query(
        self,
        embedding: list[float],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[VectorHit] = []
        for index, identifier in enumerate(ids):
            hits.append(
                VectorHit(
                    id=identifier,
                    document=documents[index] or "",
                    metadata=dict(metadatas[index] or {}),
                    distance=float(distances[index]),
                )
            )
        return hits

    def count(self) -> int:
        return self.collection.count()
