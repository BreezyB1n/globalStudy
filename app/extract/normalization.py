from __future__ import annotations

import re

from app.extract.models import ProjectSourceBundle, StructuredProjectExtraction

DEGREE_ALIASES = {
    "msc": "MSc",
    "ms": "MS",
    "ma": "MA",
    "mphil": "MPhil",
    "meng": "MEng",
}

STUDY_MODE_ALIASES = {
    "full time": "full-time",
    "full-time": "full-time",
    "fulltime": "full-time",
    "part time": "part-time",
    "part-time": "part-time",
    "parttime": "part-time",
    "hybrid": "hybrid",
    "mixed": "hybrid",
}


def build_normalized_project_values(
    bundle: ProjectSourceBundle,
    extraction: StructuredProjectExtraction,
) -> dict[str, str | int | None]:
    def value(field_name: str) -> str | None:
        field = extraction.field_map().get(field_name)
        return field.value if field else None

    duration_value = _normalize_text(value("duration"))
    return {
        "school_name": _normalize_text(value("school_name")) or bundle.school_name,
        "school_country": _normalize_text(value("school_country")) or bundle.school_country,
        "program_name": _normalize_text(value("program_name")) or bundle.program_name,
        "degree_type": _normalize_degree_type(value("degree_type") or bundle.degree_type),
        "department": _normalize_text(value("department")),
        "study_mode": _normalize_study_mode(value("study_mode")),
        "duration": duration_value,
        "duration_months": _extract_duration_months(duration_value),
        "tuition": _normalize_text(value("tuition")),
        "application_deadline": _normalize_text(value("application_deadline")),
        "language_requirement": _normalize_text(value("language_requirement")),
        "academic_requirement": _normalize_text(value("academic_requirement")),
        "overview": _normalize_text(value("overview")),
    }


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _normalize_degree_type(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return DEGREE_ALIASES.get(normalized.lower(), normalized)


def _normalize_study_mode(value: str | None) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    return STUDY_MODE_ALIASES.get(normalized.lower(), normalized.lower())


def _extract_duration_months(value: str | None) -> int | None:
    if value is None:
        return None

    normalized = value.lower()
    year_match = re.search(r"(\d+(?:\.\d+)?)\s+year", normalized)
    if year_match:
        return int(float(year_match.group(1)) * 12)

    month_match = re.search(r"(\d+)\s+month", normalized)
    if month_match:
        return int(month_match.group(1))

    return None
