import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _load_main_module():
    for module_name in ("app.main", "app.core.config", "app.api.chat"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("app.main")


def test_chat_endpoint_returns_answer_with_citations(app_env):
    from app.schemas.chat import ChatResponse, Citation, ResolvedContext
    from app.api.chat import get_chat_service

    class FakeChatService:
        def __init__(self, response: ChatResponse) -> None:
            self.response = response
            self.requests = []

        def answer(self, request):
            self.requests.append(request)
            return self.response

    main = _load_main_module()
    app = main.create_app()
    fake_service = FakeChatService(
        ChatResponse(
            answer="根据已收录的官网页面，该项目的语言要求为 Higher university requirement in the appropriate English language qualification.",
            citations=[
                Citation(
                    school_name="Imperial College London",
                    program_name="MSc Artificial Intelligence",
                    page_title="Artificial Intelligence MSc | Study | Imperial College London",
                    source_url="https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                    evidence_text="Higher university requirement in the appropriate English language qualification.",
                    evidence_type="structured_field",
                )
            ],
            resolved_context=ResolvedContext(
                school_name="Imperial College London",
                program_name="MSc Artificial Intelligence",
                question_type="field",
            ),
        )
    )
    app.dependency_overrides[get_chat_service] = lambda: fake_service
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "介绍一下帝国理工的 AI 硕士项目"},
                {"role": "assistant", "content": "这是帝国理工的 MSc Artificial Intelligence 项目。"},
                {"role": "user", "content": "那它的雅思要求呢"},
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["resolved_context"]["question_type"] == "field"
    assert response.json()["citations"][0]["evidence_type"] == "structured_field"
    assert fake_service.requests[0].messages[-1].content == "那它的雅思要求呢"


def test_chat_endpoint_rejects_empty_messages(app_env):
    main = _load_main_module()
    client = TestClient(main.create_app())

    response = client.post("/api/chat", json={"messages": []})

    assert response.status_code == 422


def test_question_understanding_detects_field_follow_up():
    from app.chat.understanding import QuestionUnderstandingService

    service = QuestionUnderstandingService()

    result = service.understand("那它的雅思要求呢")

    assert result.question_type == "field"
    assert result.field_names == ["language_requirement"]
    assert result.is_follow_up is True


def test_entity_resolver_inherits_project_from_recent_messages():
    from app.chat.entity_resolver import EntityResolver
    from app.chat.models import ChatMessage, ProjectCatalogEntry

    resolver = EntityResolver(
        projects=[
            ProjectCatalogEntry(
                school_slug="imperial",
                school_name="Imperial College London",
                program_slug="msc-artificial-intelligence",
                program_name="MSc Artificial Intelligence",
                degree_type="MSc",
            )
        ]
    )

    resolution = resolver.resolve(
        current_question="那它的雅思要求呢",
        messages=[
            ChatMessage(role="user", content="介绍一下帝国理工的 AI 硕士项目"),
            ChatMessage(role="assistant", content="这是帝国理工的 MSc Artificial Intelligence 项目。"),
            ChatMessage(role="user", content="那它的雅思要求呢"),
        ],
    )

    assert resolution.primary_project is not None
    assert resolution.primary_project.school_slug == "imperial"
    assert resolution.primary_project.program_slug == "msc-artificial-intelligence"


def test_entity_resolver_does_not_match_ai_inside_other_words():
    from app.chat.entity_resolver import EntityResolver
    from app.chat.models import ChatMessage, ProjectCatalogEntry

    resolver = EntityResolver(
        projects=[
            ProjectCatalogEntry(
                school_slug="imperial",
                school_name="Imperial College London",
                program_slug="msc-artificial-intelligence",
                program_name="MSc Artificial Intelligence",
                degree_type="MSc",
            )
        ]
    )

    resolution = resolver.resolve(
        current_question="What are its main topics?",
        messages=[ChatMessage(role="user", content="What are its main topics?")],
    )

    assert resolution.primary_project is None
    assert resolution.unresolved_reason == "missing_project"


def test_chat_service_uses_structured_path_for_field_questions():
    from app.chat.models import (
        ChatQuestionAnalysis,
        EntityResolution,
        ProjectCatalogEntry,
        StructuredEvidence,
    )
    from app.chat.service import ChatService
    from app.schemas.chat import ChatMessage, ChatRequest

    project = ProjectCatalogEntry(
        school_slug="imperial",
        school_name="Imperial College London",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
    )

    class FakeUnderstandingService:
        def understand(self, _: str) -> ChatQuestionAnalysis:
            return ChatQuestionAnalysis(
                question_type="field",
                field_names=["language_requirement"],
                is_follow_up=True,
            )

    class FakeEntityResolver:
        def resolve(self, **kwargs) -> EntityResolution:
            return EntityResolution(primary_project=project)

    class FakeStructuredQueryService:
        def __init__(self) -> None:
            self.calls = []

        def fetch(self, **kwargs):
            self.calls.append(kwargs)
            return [
                StructuredEvidence(
                    school_name=project.school_name,
                    program_name=project.program_name,
                    field_name="language_requirement",
                    field_value="IELTS 7.0 overall",
                    page_title="Entry requirements",
                    source_url="https://example.com/entry",
                    evidence_text="Minimum IELTS score is 7.0 overall.",
                )
            ]

    class FakeVectorRetrievalService:
        def __init__(self) -> None:
            self.calls = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return []

    class FakeAnswerGenerator:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, **kwargs) -> str:
            self.calls.append(kwargs)
            return "语言要求是 IELTS 7.0 overall。"

    structured = FakeStructuredQueryService()
    vector = FakeVectorRetrievalService()
    generator = FakeAnswerGenerator()
    service = ChatService(
        understanding_service=FakeUnderstandingService(),
        entity_resolver=FakeEntityResolver(),
        structured_query_service=structured,
        vector_retrieval_service=vector,
        answer_generator=generator,
    )

    response = service.answer(
        ChatRequest(messages=[ChatMessage(role="user", content="那它的雅思要求呢")])
    )

    assert response.answer == "语言要求是 IELTS 7.0 overall。"
    assert response.resolved_context.question_type == "field"
    assert response.citations[0].evidence_type == "structured_field"
    assert len(structured.calls) == 1
    assert vector.calls == []
    assert len(generator.calls) == 1


def test_chat_service_uses_vector_path_for_explanatory_questions():
    from app.chat.models import (
        ChatQuestionAnalysis,
        EntityResolution,
        ProjectCatalogEntry,
        VectorEvidence,
    )
    from app.chat.service import ChatService
    from app.schemas.chat import ChatMessage, ChatRequest

    project = ProjectCatalogEntry(
        school_slug="imperial",
        school_name="Imperial College London",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
    )

    class FakeUnderstandingService:
        def understand(self, _: str) -> ChatQuestionAnalysis:
            return ChatQuestionAnalysis(question_type="explanatory")

    class FakeEntityResolver:
        def resolve(self, **kwargs) -> EntityResolution:
            return EntityResolution(primary_project=project)

    class FakeStructuredQueryService:
        def fetch(self, **kwargs):
            raise AssertionError("structured path should not be used for explanatory questions")

    class FakeVectorRetrievalService:
        def __init__(self) -> None:
            self.calls = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return [
                VectorEvidence(
                    school_name=project.school_name,
                    program_name=project.program_name,
                    page_title="Course overview",
                    source_url="https://example.com/overview",
                    evidence_text="This programme delivers intensive training in programming and the fundamentals of artificial intelligence.",
                    distance=0.72,
                )
            ]

    class FakeAnswerGenerator:
        def generate(self, **kwargs) -> str:
            return "这个项目主要学习编程基础和人工智能核心内容。"

    vector = FakeVectorRetrievalService()
    service = ChatService(
        understanding_service=FakeUnderstandingService(),
        entity_resolver=FakeEntityResolver(),
        structured_query_service=FakeStructuredQueryService(),
        vector_retrieval_service=vector,
        answer_generator=FakeAnswerGenerator(),
    )

    response = service.answer(
        ChatRequest(messages=[ChatMessage(role="user", content="这个项目主要学什么")])
    )

    assert response.resolved_context.question_type == "explanatory"
    assert response.citations[0].evidence_type == "vector_chunk"
    assert len(vector.calls) == 1


def test_chat_service_returns_clarification_when_project_is_unresolved():
    from app.chat.models import ChatQuestionAnalysis, EntityResolution
    from app.chat.service import ChatService
    from app.schemas.chat import ChatMessage, ChatRequest

    class FakeUnderstandingService:
        def understand(self, _: str) -> ChatQuestionAnalysis:
            return ChatQuestionAnalysis(question_type="field", field_names=["tuition"])

    class FakeEntityResolver:
        def resolve(self, **kwargs) -> EntityResolution:
            return EntityResolution(unresolved_reason="missing_project")

    class FailIfCalledService:
        def fetch(self, **kwargs):
            raise AssertionError("downstream services should not run when context is unresolved")

        def retrieve(self, **kwargs):
            raise AssertionError("downstream services should not run when context is unresolved")

        def generate(self, **kwargs) -> str:
            raise AssertionError("generator should not run when context is unresolved")

    service = ChatService(
        understanding_service=FakeUnderstandingService(),
        entity_resolver=FakeEntityResolver(),
        structured_query_service=FailIfCalledService(),
        vector_retrieval_service=FailIfCalledService(),
        answer_generator=FailIfCalledService(),
    )

    response = service.answer(
        ChatRequest(messages=[ChatMessage(role="user", content="它的学费是多少")])
    )

    assert response.answer == "我暂时无法确定你指的是哪个学校或项目，请补充学校名称或项目名称。"
    assert response.citations == []


def test_chat_service_uses_both_paths_for_comparison_questions():
    from app.chat.models import (
        ChatQuestionAnalysis,
        EntityResolution,
        ProjectCatalogEntry,
        StructuredEvidence,
        VectorEvidence,
    )
    from app.chat.service import ChatService
    from app.schemas.chat import ChatMessage, ChatRequest

    imperial = ProjectCatalogEntry(
        school_slug="imperial",
        school_name="Imperial College London",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
    )
    edinburgh = ProjectCatalogEntry(
        school_slug="edinburgh",
        school_name="The University of Edinburgh",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
    )

    class FakeUnderstandingService:
        def understand(self, _: str) -> ChatQuestionAnalysis:
            return ChatQuestionAnalysis(
                question_type="comparison",
                field_names=["language_requirement"],
            )

    class FakeEntityResolver:
        def resolve(self, **kwargs) -> EntityResolution:
            return EntityResolution(
                primary_project=imperial,
                comparison_project=edinburgh,
            )

    class FakeStructuredQueryService:
        def __init__(self) -> None:
            self.calls = []

        def fetch(self, **kwargs):
            self.calls.append(kwargs)
            return [
                StructuredEvidence(
                    school_name=imperial.school_name,
                    program_name=imperial.program_name,
                    field_name="language_requirement",
                    field_value="IELTS 7.0",
                    page_title="Entry requirements",
                    source_url="https://example.com/imperial",
                    evidence_text="Imperial requires IELTS 7.0 overall.",
                ),
                StructuredEvidence(
                    school_name=edinburgh.school_name,
                    program_name=edinburgh.program_name,
                    field_name="language_requirement",
                    field_value="IELTS 6.5",
                    page_title="Entry requirements",
                    source_url="https://example.com/edinburgh",
                    evidence_text="Edinburgh requires IELTS 6.5 overall.",
                ),
            ]

    class FakeVectorRetrievalService:
        def __init__(self) -> None:
            self.calls = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return [
                VectorEvidence(
                    school_name=imperial.school_name,
                    program_name=imperial.program_name,
                    page_title="Programme overview",
                    source_url="https://example.com/imperial-overview",
                    evidence_text="Imperial emphasises intensive technical training.",
                    distance=0.61,
                ),
                VectorEvidence(
                    school_name=edinburgh.school_name,
                    program_name=edinburgh.program_name,
                    page_title="Programme overview",
                    source_url="https://example.com/edinburgh-overview",
                    evidence_text="Edinburgh emphasises applied AI and data-driven systems.",
                    distance=0.65,
                ),
            ]

    class FakeAnswerGenerator:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, **kwargs) -> str:
            self.calls.append(kwargs)
            return "Imperial 的语言要求更高，Edinburgh 的要求相对更低。"

    structured = FakeStructuredQueryService()
    vector = FakeVectorRetrievalService()
    generator = FakeAnswerGenerator()
    service = ChatService(
        understanding_service=FakeUnderstandingService(),
        entity_resolver=FakeEntityResolver(),
        structured_query_service=structured,
        vector_retrieval_service=vector,
        answer_generator=generator,
    )

    response = service.answer(
        ChatRequest(messages=[ChatMessage(role="user", content="它和爱丁堡的 AI 硕士相比语言要求有什么差别")])
    )

    assert response.resolved_context.question_type == "comparison"
    assert len(structured.calls) == 1
    assert len(vector.calls) == 1
    assert len(generator.calls) == 1
    assert len(response.citations) == 4


def test_chat_service_reads_real_sqlite_evidence_for_imperial_language_requirement(app_env):
    from app.chat.entity_resolver import EntityResolver
    from app.chat.models import ProjectCatalogEntry
    from app.chat.service import ChatService
    from app.chat.structured_query_service import StructuredQueryService
    from app.chat.understanding import QuestionUnderstandingService
    from app.extract.repository import SQLiteProjectRepository
    from app.schemas.chat import ChatMessage, ChatRequest

    repository = SQLiteProjectRepository(Path("data/sqlite/app.db"))
    projects = [
        ProjectCatalogEntry(
            school_slug=project.school_slug,
            school_name=project.school_name,
            program_slug=project.program_slug,
            program_name=project.program_name,
            degree_type=project.degree_type,
        )
        for project in repository.list_projects()
    ]

    class FailIfCalledVectorService:
        def retrieve(self, **kwargs):
            raise AssertionError("vector retrieval should not run when structured evidence exists")

    class FakeAnswerGenerator:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, **kwargs) -> str:
            self.calls.append(kwargs)
            return "官网显示语言要求为 Higher university requirement in the appropriate English language qualification."

    generator = FakeAnswerGenerator()
    service = ChatService(
        understanding_service=QuestionUnderstandingService(),
        entity_resolver=EntityResolver(projects),
        structured_query_service=StructuredQueryService(repository),
        vector_retrieval_service=FailIfCalledVectorService(),
        answer_generator=generator,
    )

    response = service.answer(
        ChatRequest(
            messages=[
                ChatMessage(role="user", content="帝国理工 AI 硕士的雅思要求是什么"),
            ]
        )
    )

    assert response.resolved_context.school_name == "Imperial College London"
    assert response.resolved_context.question_type == "field"
    assert len(response.citations) == 1
    assert "English language proficiency" in response.citations[0].evidence_text
    assert len(generator.calls) == 1
