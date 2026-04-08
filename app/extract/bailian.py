from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ThirdPartyServiceError

from app.extract.models import (
    ExtractedField,
    ProjectSourceBundle,
    STRUCTURED_FIELD_NAMES,
    StructuredProjectExtraction,
)


class BailianExtractionError(ThirdPartyServiceError):
    code = "BAILIAN_EXTRACTION_FAILED"


class BailianStructuredExtractor:
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

    def extract(self, bundle: ProjectSourceBundle) -> StructuredProjectExtraction:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": _build_user_prompt(bundle)},
            ],
            "temperature": 0,
            "enable_thinking": False,
            "response_format": {
                "type": "json_object",
            },
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
            raise BailianExtractionError(f"Bailian extraction request failed: {exc}") from exc
        finally:
            if should_close:
                client.close()

        content = _extract_content(response.json())
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise BailianExtractionError("Bailian extraction response was not valid JSON") from exc
        try:
            return StructuredProjectExtraction.model_validate(_coerce_extraction_payload(data, bundle))
        except Exception as exc:  # noqa: BLE001
            raise BailianExtractionError(f"Bailian extraction response did not match schema: {exc}") from exc


def build_bailian_extractor(settings: Settings) -> BailianStructuredExtractor:
    return BailianStructuredExtractor(
        api_key=settings.bailian_api_key,
        base_url=settings.bailian_base_url,
        model=settings.bailian_chat_model,
        timeout_ms=settings.bailian_timeout_ms,
    )


def _build_system_prompt() -> str:
    return (
        "You are an information extraction assistant. "
        "Read the provided university programme pages and return JSON only. "
        "Use only facts that explicitly appear in the supplied content. "
        "If a field is not stated, return null for that field. "
        "When a field has a value, include the shortest evidence_text that supports it and the page_type it came from."
    )


def _build_user_prompt(bundle: ProjectSourceBundle) -> str:
    sections = [
        "Extract the programme fields into JSON.",
        f"school_slug: {bundle.school_slug}",
        f"school_name: {bundle.school_name}",
        f"school_country: {bundle.school_country}",
        f"program_slug: {bundle.program_slug}",
        f"program_name: {bundle.program_name}",
        f"degree_type: {bundle.degree_type}",
    ]
    for page in bundle.pages:
        sections.append(
            "\n".join(
                [
                    f"[page_type={page.page_type}]",
                    f"title: {page.page_title}",
                    f"url: {page.source_url}",
                    page.markdown,
                ]
            )
        )
    return "\n\n".join(sections)


def _extract_content(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BailianExtractionError("Bailian extraction response did not contain choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise BailianExtractionError("Bailian extraction response did not contain a message")
    content = message.get("content")
    if isinstance(content, str):
        return content
    raise BailianExtractionError("Bailian extraction response did not contain string content")


def _coerce_extraction_payload(data: Any, bundle: ProjectSourceBundle) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise BailianExtractionError("Bailian extraction response JSON must be an object")

    shared_evidence_text = _normalize_optional_text(data.get("evidence_text"))
    shared_page_type = _normalize_optional_text(
        data.get("source_page_type") or data.get("page_type")
    )
    fallback_page_type = _select_fallback_page_type(bundle)
    normalized: dict[str, Any] = {}

    for field_name in STRUCTURED_FIELD_NAMES:
        raw_value = data.get(field_name)
        if raw_value is None:
            normalized[field_name] = None
            continue

        if isinstance(raw_value, dict):
            field_payload = dict(raw_value)
            field_payload.setdefault("evidence_text", shared_evidence_text)
            field_payload.setdefault("source_page_type", shared_page_type or fallback_page_type)
            normalized[field_name] = field_payload
            continue

        if isinstance(raw_value, str):
            field = ExtractedField(
                value=raw_value,
                evidence_text=shared_evidence_text or raw_value,
                source_page_type=shared_page_type or fallback_page_type,
            )
            normalized[field_name] = field.model_dump()
            continue

        normalized[field_name] = raw_value

    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _select_fallback_page_type(bundle: ProjectSourceBundle) -> str | None:
    available_page_types = [page.page_type for page in bundle.pages]
    if not available_page_types:
        return None
    if "overview" in available_page_types:
        return "overview"
    return available_page_types[0]
