from __future__ import annotations

from typing import Protocol

import httpx

from app.chat.models import ProjectCatalogEntry
from app.core.config import Settings
from app.core.exceptions import ThirdPartyServiceError
from app.schemas.chat import Citation


class ChatAnswerGenerator(Protocol):
    def generate(
        self,
        *,
        question: str,
        question_type: str,
        primary_project: ProjectCatalogEntry | None,
        comparison_project: ProjectCatalogEntry | None,
        citations: list[Citation],
    ) -> str: ...


class BailianChatGenerationError(ThirdPartyServiceError):
    code = "BAILIAN_CHAT_GENERATION_FAILED"


class BailianChatAnswerGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_ms: int,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_ms = timeout_ms
        self.http_client = http_client

    def generate(
        self,
        *,
        question: str,
        question_type: str,
        primary_project: ProjectCatalogEntry | None,
        comparison_project: ProjectCatalogEntry | None,
        citations: list[Citation],
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _build_system_prompt()},
                {
                    "role": "user",
                    "content": _build_user_prompt(
                        question=question,
                        question_type=question_type,
                        primary_project=primary_project,
                        comparison_project=comparison_project,
                        citations=citations,
                    ),
                },
            ],
            "temperature": 0,
            "enable_thinking": False,
        }

        client = self.http_client or httpx.Client(timeout=self.timeout_ms / 1000)
        should_close = self.http_client is None
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BailianChatGenerationError(f"Bailian chat generation failed: {exc}") from exc
        finally:
            if should_close:
                client.close()

        return _extract_message_content(response.json())


def build_chat_answer_generator(settings: Settings) -> BailianChatAnswerGenerator:
    return BailianChatAnswerGenerator(
        api_key=settings.bailian_api_key,
        base_url=settings.bailian_base_url,
        model=settings.bailian_chat_model,
        timeout_ms=settings.bailian_timeout_ms,
    )


def _build_system_prompt() -> str:
    return (
        "You are a university programme Q&A assistant. "
        "Answer only from the provided official website evidence. "
        "Do not use outside knowledge, memory, or common domain assumptions. "
        "Do not invent facts that are not in evidence. "
        "Never infer exact scores, dates, fees, rankings, deadlines, or requirements from generic wording. "
        "Do not add typical or likely values unless the evidence explicitly states them. "
        "If evidence is insufficient, explicitly say that the answer could not be confirmed from the collected official pages. "
        "Keep the answer concise and in the same language as the user's question."
    )


def _build_user_prompt(
    *,
    question: str,
    question_type: str,
    primary_project: ProjectCatalogEntry | None,
    comparison_project: ProjectCatalogEntry | None,
    citations: list[Citation],
) -> str:
    context_lines = [f"question_type: {question_type}", f"user_question: {question}"]
    if primary_project is not None:
        context_lines.append(
            f"primary_project: {primary_project.school_name} / {primary_project.program_name}"
        )
    if comparison_project is not None:
        context_lines.append(
            f"comparison_project: {comparison_project.school_name} / {comparison_project.program_name}"
        )

    evidence_lines = []
    for index, citation in enumerate(citations, start=1):
        evidence_lines.append(
            "\n".join(
                [
                    f"[evidence {index}]",
                    f"school_name: {citation.school_name}",
                    f"program_name: {citation.program_name}",
                    f"page_title: {citation.page_title}",
                    f"source_url: {citation.source_url}",
                    f"evidence_type: {citation.evidence_type}",
                    f"evidence_text: {citation.evidence_text}",
                ]
            )
        )

    return "\n\n".join(
        [
            (
                "Use the evidence below to answer the question directly. "
                "If the evidence does not state an exact value, say that the exact value could not be confirmed from the collected official pages. "
                "Respond in the user's language when saying that an exact value could not be confirmed. "
                "Do not write words such as usually, typically, generally, often, 一般, 通常, or likely unless those words appear in the evidence itself."
            ),
            "\n".join(context_lines),
            "\n\n".join(evidence_lines),
        ]
    )


def _extract_message_content(body: dict) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BailianChatGenerationError("Bailian chat response did not contain choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise BailianChatGenerationError("Bailian chat response did not contain a message")
    content = message.get("content")
    if not isinstance(content, str):
        raise BailianChatGenerationError("Bailian chat response did not contain string content")
    normalized = content.strip()
    if not normalized:
        raise BailianChatGenerationError("Bailian chat response was empty")
    return normalized
