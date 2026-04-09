from __future__ import annotations

from app.chat.models import ProjectCatalogEntry, VectorEvidence
from app.vector.chunking import build_project_key
from app.vector.embedding import BailianEmbeddingClient
from app.vector.repository import ChromaVectorRepository


class VectorRetrievalService:
    def __init__(
        self,
        *,
        vector_repository: ChromaVectorRepository,
        embedder: BailianEmbeddingClient,
        top_k: int,
    ) -> None:
        self.vector_repository = vector_repository
        self.embedder = embedder
        self.top_k = top_k

    def retrieve(
        self,
        *,
        question: str,
        primary_project: ProjectCatalogEntry,
        comparison_project: ProjectCatalogEntry | None,
    ) -> list[VectorEvidence]:
        query_embedding = self.embedder.embed_texts([question])[0]
        target_projects = [primary_project]
        if comparison_project is not None:
            target_projects.append(comparison_project)

        per_project_top_k = max(1, self.top_k // len(target_projects))
        evidences: list[VectorEvidence] = []
        for project in target_projects:
            hits = self.vector_repository.query(
                query_embedding=query_embedding,
                top_k=per_project_top_k,
                filters={"project_key": build_project_key(project.school_slug, project.program_slug)},
            )
            for hit in hits:
                evidences.append(
                    VectorEvidence(
                        school_name=hit.metadata.school_name,
                        program_name=hit.metadata.program_name,
                        page_title=hit.metadata.page_title,
                        source_url=hit.metadata.source_url,
                        evidence_text=hit.document,
                        distance=hit.distance,
                    )
                )
        return evidences
