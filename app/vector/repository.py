from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.exceptions import ConfigError, KnowledgeBaseNotReadyError

from app.extract.models import ProjectSourceBundle
from app.vector.chunking import build_project_key, compute_content_hash
from app.vector.models import VectorChunk, VectorSearchHit


class ChromaVectorRepository:
    def __init__(
        self,
        *,
        persist_dir: Path,
        collection_name: str,
        collection=None,
    ) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection = collection or self._build_collection()

    def project_is_current(self, bundle: ProjectSourceBundle, *, chunking_version: str) -> bool:
        project_key = build_project_key(bundle.school_slug, bundle.program_slug)
        response = self.collection.get(where={"project_key": project_key}, include=["metadatas"])
        metadatas = response.get("metadatas") or []
        if not metadatas:
            return False

        existing_versions = {metadata.get("chunking_version") for metadata in metadatas}
        existing_page_hashes = {
            (str(metadata.get("page_type")), str(metadata.get("content_hash")))
            for metadata in metadatas
            if metadata.get("page_type") and metadata.get("content_hash")
        }
        current_page_hashes = {
            (
                page.page_type,
                page.content_hash or compute_content_hash(page.markdown),
            )
            for page in bundle.pages
        }
        return existing_versions == {chunking_version} and existing_page_hashes == current_page_hashes

    def replace_project_chunks(
        self,
        *,
        bundle: ProjectSourceBundle,
        chunks: list[VectorChunk],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise KnowledgeBaseNotReadyError("Chunk and embedding counts do not match")
        project_key = build_project_key(bundle.school_slug, bundle.program_slug)
        self.collection.delete(where={"project_key": project_key})
        self.collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.document for chunk in chunks],
            metadatas=[chunk.metadata.model_dump() for chunk in chunks],
        )

    def query(
        self,
        *,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, str | int | float | bool] | None = None,
    ) -> list[VectorSearchHit]:
        response = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters or None,
            include=["documents", "metadatas", "distances"],
        )
        ids = response.get("ids") or [[]]
        documents = response.get("documents") or [[]]
        metadatas = response.get("metadatas") or [[]]
        distances = response.get("distances") or [[]]

        hits: list[VectorSearchHit] = []
        for row_id, document, metadata, distance in zip(
            ids[0],
            documents[0],
            metadatas[0],
            distances[0] if distances and distances[0] else [None] * len(ids[0]),
            strict=False,
        ):
            if not isinstance(metadata, dict):
                continue
            hits.append(
                VectorSearchHit(
                    id=str(row_id),
                    document=str(document),
                    metadata=metadata,
                    distance=None if distance is None else float(distance),
                )
            )
        return hits

    def _build_collection(self):
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - exercised in runtime, not tests
            raise ConfigError(
                "chromadb is not installed. Run `uv sync --dev` to install vector store dependencies."
            ) from exc

        client = chromadb.PersistentClient(path=str(self.persist_dir))
        return client.get_or_create_collection(
            self.collection_name,
            metadata={"owner": "globalstudy-ai"},
        )

