from __future__ import annotations

from functools import lru_cache

from app.chat.entity_resolver import EntityResolver
from app.chat.graph import ChatGraphRunner
from app.chat.llm import build_chat_answer_generator
from app.chat.models import ProjectCatalogEntry
from app.chat.structured_query_service import StructuredQueryService
from app.chat.understanding import QuestionUnderstandingService
from app.chat.vector_retrieval_service import VectorRetrievalService
from app.core.config import get_settings
from app.extract.repository import SQLiteProjectRepository
from app.schemas.chat import ChatRequest, ChatResponse, ResolvedContext
from app.vector.embedding import build_bailian_embedder
from app.vector.repository import ChromaVectorRepository


class ChatService:
    def __init__(
        self,
        *,
        understanding_service: QuestionUnderstandingService,
        entity_resolver: EntityResolver,
        structured_query_service: StructuredQueryService,
        vector_retrieval_service: VectorRetrievalService,
        answer_generator,
        citation_limit: int = 4,
    ) -> None:
        self.graph_runner = ChatGraphRunner(
            understanding_service=understanding_service,
            entity_resolver=entity_resolver,
            structured_query_service=structured_query_service,
            vector_retrieval_service=vector_retrieval_service,
            answer_generator=answer_generator,
            citation_limit=citation_limit,
        )

    def answer(self, request: ChatRequest) -> ChatResponse:
        result = self.graph_runner.run(messages=request.messages)
        return ChatResponse(
            answer=result.answer,
            citations=result.citations,
            resolved_context=ResolvedContext(
                school_name=None if result.primary_project is None else result.primary_project.school_name,
                program_name=None
                if result.primary_project is None
                else result.primary_project.program_name,
                question_type=result.question_type,
            ),
        )


@lru_cache(maxsize=1)
def get_chat_service() -> ChatService:
    settings = get_settings()
    project_repository = SQLiteProjectRepository(settings.sqlite_path)
    vector_repository = ChromaVectorRepository(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.vector_collection_name,
    )
    projects = [
        ProjectCatalogEntry(
            school_slug=project.school_slug,
            school_name=project.school_name,
            program_slug=project.program_slug,
            program_name=project.program_name,
            degree_type=project.degree_type,
        )
        for project in project_repository.list_projects()
    ]

    return ChatService(
        understanding_service=QuestionUnderstandingService(),
        entity_resolver=EntityResolver(projects),
        structured_query_service=StructuredQueryService(project_repository),
        vector_retrieval_service=VectorRetrievalService(
            vector_repository=vector_repository,
            embedder=build_bailian_embedder(settings),
            top_k=settings.chat_vector_top_k,
        ),
        answer_generator=build_chat_answer_generator(settings),
        citation_limit=settings.chat_citation_limit,
    )
