from __future__ import annotations

from typing import TypedDict

from app.chat.entity_resolver import EntityResolver
from app.chat.llm import ChatAnswerGenerator
from app.chat.models import (
    ChatGraphResult,
    ChatQuestionAnalysis,
    EntityResolution,
    RouteName,
    StructuredEvidence,
    VectorEvidence,
)
from app.chat.structured_query_service import StructuredQueryService
from app.chat.understanding import QuestionUnderstandingService
from app.chat.vector_retrieval_service import VectorRetrievalService
from app.core.exceptions import ConfigError
from app.schemas.chat import ChatMessage, Citation

CLARIFY_MESSAGE = "我暂时无法确定你指的是哪个学校或项目，请补充学校名称或项目名称。"
COMPARISON_MESSAGE = "我暂时无法确定你要对比的另一个学校或项目，请补充完整的比较对象。"
INSUFFICIENT_EVIDENCE_MESSAGE = "未在当前已收录的官网页面中找到明确答案，建议查看原始链接进一步确认。"


class ChatGraphState(TypedDict, total=False):
    messages: list[ChatMessage]
    current_question: str
    question_analysis: ChatQuestionAnalysis
    entity_resolution: EntityResolution
    structured_evidences: list[StructuredEvidence]
    vector_evidences: list[VectorEvidence]
    citations: list[Citation]
    final_answer: str


class ChatGraphRunner:
    def __init__(
        self,
        *,
        understanding_service: QuestionUnderstandingService,
        entity_resolver: EntityResolver,
        structured_query_service: StructuredQueryService,
        vector_retrieval_service: VectorRetrievalService,
        answer_generator: ChatAnswerGenerator,
        citation_limit: int,
    ) -> None:
        self.understanding_service = understanding_service
        self.entity_resolver = entity_resolver
        self.structured_query_service = structured_query_service
        self.vector_retrieval_service = vector_retrieval_service
        self.answer_generator = answer_generator
        self.citation_limit = citation_limit
        self.graph = self._compile_graph()

    def run(self, *, messages: list[ChatMessage]) -> ChatGraphResult:
        final_state = self.graph.invoke({"messages": messages})
        resolution = final_state.get("entity_resolution") or EntityResolution()
        analysis = final_state.get("question_analysis") or ChatQuestionAnalysis(question_type="explanatory")
        return ChatGraphResult(
            answer=final_state.get("final_answer", INSUFFICIENT_EVIDENCE_MESSAGE),
            question_type=analysis.question_type,
            primary_project=resolution.primary_project,
            comparison_project=resolution.comparison_project,
            citations=final_state.get("citations", []),
        )

    def _compile_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:  # pragma: no cover - exercised in runtime after dependency install
            raise ConfigError(
                "langgraph is not installed. Run `uv sync --dev` after adding the dependency."
            ) from exc

        graph = StateGraph(ChatGraphState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("understand_question", self._understand_question)
        graph.add_node("resolve_entities", self._resolve_entities)
        graph.add_node("query_structured_data", self._query_structured_data)
        graph.add_node("retrieve_vector_chunks", self._retrieve_vector_chunks)
        graph.add_node("merge_evidences", self._merge_evidences)
        graph.add_node("generate_answer", self._generate_answer)

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "understand_question")
        graph.add_edge("understand_question", "resolve_entities")
        graph.add_conditional_edges(
            "resolve_entities",
            self._route_after_resolution,
            {
                "field": "query_structured_data",
                "field_with_vector_fallback": "query_structured_data",
                "explanatory": "retrieve_vector_chunks",
                "comparison": "query_structured_data",
                "clarify": "generate_answer",
            },
        )
        graph.add_conditional_edges(
            "query_structured_data",
            self._route_after_structured_query,
            {
                "merge": "merge_evidences",
                "vector": "retrieve_vector_chunks",
            },
        )
        graph.add_edge("retrieve_vector_chunks", "merge_evidences")
        graph.add_edge("merge_evidences", "generate_answer")
        graph.add_edge("generate_answer", END)
        return graph.compile()

    def _load_context(self, state: ChatGraphState) -> ChatGraphState:
        messages = state["messages"]
        return {
            "current_question": messages[-1].content,
        }

    def _understand_question(self, state: ChatGraphState) -> ChatGraphState:
        return {
            "question_analysis": self.understanding_service.understand(state["current_question"]),
        }

    def _resolve_entities(self, state: ChatGraphState) -> ChatGraphState:
        return {
            "entity_resolution": self.entity_resolver.resolve(
                current_question=state["current_question"],
                messages=state["messages"],
            )
        }

    def _query_structured_data(self, state: ChatGraphState) -> ChatGraphState:
        resolution = state["entity_resolution"]
        analysis = state["question_analysis"]
        if resolution.primary_project is None:
            return {"structured_evidences": []}
        return {
            "structured_evidences": self.structured_query_service.fetch(
                primary_project=resolution.primary_project,
                comparison_project=resolution.comparison_project,
                question_type=analysis.question_type,
                field_names=analysis.field_names,
            )
        }

    def _retrieve_vector_chunks(self, state: ChatGraphState) -> ChatGraphState:
        resolution = state["entity_resolution"]
        if resolution.primary_project is None:
            return {"vector_evidences": []}
        return {
            "vector_evidences": self.vector_retrieval_service.retrieve(
                question=state["current_question"],
                primary_project=resolution.primary_project,
                comparison_project=resolution.comparison_project,
            )
        }

    def _merge_evidences(self, state: ChatGraphState) -> ChatGraphState:
        structured = [evidence.to_citation() for evidence in state.get("structured_evidences", [])]
        vectors = [evidence.to_citation() for evidence in state.get("vector_evidences", [])]
        deduped: list[Citation] = []
        seen: set[tuple[str, str, str]] = set()
        for citation in [*structured, *vectors]:
            key = (citation.source_url, citation.evidence_text, citation.evidence_type)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(citation)
            if len(deduped) >= self.citation_limit:
                break
        return {"citations": deduped}

    def _generate_answer(self, state: ChatGraphState) -> ChatGraphState:
        resolution = state.get("entity_resolution") or EntityResolution()
        analysis = state.get("question_analysis") or ChatQuestionAnalysis(question_type="explanatory")

        if resolution.primary_project is None:
            return {"final_answer": CLARIFY_MESSAGE}
        if resolution.unresolved_reason == "missing_comparison":
            return {"final_answer": COMPARISON_MESSAGE}

        citations = state.get("citations", [])
        if not citations:
            return {"final_answer": INSUFFICIENT_EVIDENCE_MESSAGE}

        answer = self.answer_generator.generate(
            question=state["current_question"],
            question_type=analysis.question_type,
            primary_project=resolution.primary_project,
            comparison_project=resolution.comparison_project,
            citations=citations,
        )
        return {"final_answer": answer}

    def _route_after_resolution(self, state: ChatGraphState) -> RouteName:
        resolution = state["entity_resolution"]
        analysis = state["question_analysis"]
        if resolution.primary_project is None or resolution.unresolved_reason == "missing_project":
            return "clarify"
        if resolution.unresolved_reason == "missing_comparison":
            return "clarify"
        if analysis.question_type == "comparison":
            return "comparison"
        if analysis.question_type == "field":
            return "field_with_vector_fallback"
        return "explanatory"

    def _route_after_structured_query(self, state: ChatGraphState) -> str:
        analysis = state["question_analysis"]
        if analysis.question_type == "comparison":
            return "vector"
        if analysis.question_type == "field" and not state.get("structured_evidences"):
            return "vector"
        return "merge"
