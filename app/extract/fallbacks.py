from __future__ import annotations

import re

from app.extract.models import ExtractedField, ProjectSourceBundle, StructuredProjectExtraction


def enrich_extraction_from_markdown(
    bundle: ProjectSourceBundle,
    extraction: StructuredProjectExtraction,
) -> StructuredProjectExtraction:
    field_map = extraction.field_map()
    enriched = extraction.model_copy(deep=True)

    if field_map.get("tuition") is None:
        fallback = _extract_tuition(bundle)
        if fallback is not None:
            enriched.tuition = fallback

    if field_map.get("academic_requirement") is None:
        fallback = _extract_academic_requirement(bundle)
        if fallback is not None:
            enriched.academic_requirement = fallback

    if field_map.get("language_requirement") is None:
        fallback = _extract_language_requirement(bundle)
        if fallback is not None:
            enriched.language_requirement = fallback

    return enriched


def _extract_tuition(bundle: ProjectSourceBundle) -> ExtractedField | None:
    for page in bundle.pages:
        matches = re.findall(r"####\s*(£[^\n]+)", page.markdown)
        fee_lines = [item.strip() for item in matches if "Home" in item or "Overseas" in item]
        if fee_lines:
            evidence_text = "; ".join(fee_lines)
            return ExtractedField(
                value=evidence_text,
                evidence_text=evidence_text,
                source_page_type=page.page_type,
            )
    return None


def _extract_academic_requirement(bundle: ProjectSourceBundle) -> ExtractedField | None:
    patterns = (
        r"Minimum academic requirement\s+\*\*(.+?)\*\*",
        r"### Minimum entry standard\s+- ####\s*([^\n]+)",
    )
    for page in bundle.pages:
        for pattern in patterns:
            match = re.search(pattern, page.markdown, flags=re.DOTALL)
            if not match:
                continue
            raw_value = _clean_markdown_text(match.group(1))
            value = _first_sentence(raw_value)
            if value:
                return ExtractedField(
                    value=value,
                    evidence_text=value,
                    source_page_type=page.page_type,
                )
    return None


def _extract_language_requirement(bundle: ProjectSourceBundle) -> ExtractedField | None:
    pattern = (
        r"English language requirement\s+"
        r"(.+?)"
        r"(?:\n\s*International qualifications|\n\s*## |\Z)"
    )
    for page in bundle.pages:
        match = re.search(pattern, page.markdown, flags=re.DOTALL)
        if not match:
            continue

        block = _clean_markdown_text(match.group(1))
        if not block:
            continue

        preferred_match = re.search(
            r"(higher university requirement in the appropriate English language qualification\.?)",
            block,
            flags=re.IGNORECASE,
        )
        value = (
            _capitalize_first(_normalize_sentence(preferred_match.group(1)))
            if preferred_match
            else _first_sentence(block)
        )
        evidence_text = block
        if value:
            return ExtractedField(
                value=value,
                evidence_text=evidence_text,
                source_page_type=page.page_type,
            )
    return None


def _clean_markdown_text(text: str) -> str:
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _first_sentence(text: str) -> str | None:
    normalized = _normalize_sentence(text)
    if not normalized:
        return None
    match = re.search(r"(.+?[.])(?:\s|$)", normalized)
    if match:
        return match.group(1).strip()
    return normalized


def _normalize_sentence(text: str) -> str:
    normalized = " ".join(text.split())
    return normalized.strip()


def _capitalize_first(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]
