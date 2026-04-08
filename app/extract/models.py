from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STRUCTURED_FIELD_NAMES = (
    "school_name",
    "school_country",
    "program_name",
    "degree_type",
    "department",
    "study_mode",
    "duration",
    "tuition",
    "application_deadline",
    "language_requirement",
    "academic_requirement",
    "overview",
)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class ExtractedField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    evidence_text: str | None = None
    source_page_type: str | None = None

    @field_validator("value", "evidence_text", "source_page_type", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)

    @model_validator(mode="after")
    def validate_evidence_mapping(self) -> "ExtractedField":
        if self.value is None:
            self.evidence_text = None
            self.source_page_type = None
            return self
        if not self.evidence_text:
            raise ValueError("evidence_text is required when value is present")
        if not self.source_page_type:
            raise ValueError("source_page_type is required when value is present")
        return self


class StructuredProjectExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_name: ExtractedField | None = None
    school_country: ExtractedField | None = None
    program_name: ExtractedField | None = None
    degree_type: ExtractedField | None = None
    department: ExtractedField | None = None
    study_mode: ExtractedField | None = None
    duration: ExtractedField | None = None
    tuition: ExtractedField | None = None
    application_deadline: ExtractedField | None = None
    language_requirement: ExtractedField | None = None
    academic_requirement: ExtractedField | None = None
    overview: ExtractedField | None = None

    def field_map(self) -> dict[str, ExtractedField | None]:
        return {field_name: getattr(self, field_name) for field_name in STRUCTURED_FIELD_NAMES}


class RawSourcePage(BaseModel):
    page_type: str
    page_title: str
    source_url: str
    raw_file_path: Path
    content_hash: str | None = None
    fetched_at: str | None = None
    markdown: str

    @field_validator("page_type", "page_title", "source_url", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text field must not be empty")
        return normalized

    @field_validator("content_hash", "fetched_at", "markdown", mode="before")
    @classmethod
    def normalize_optional_page_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class ProjectSourceBundle(BaseModel):
    school_slug: str
    school_name: str
    school_country: str
    program_slug: str
    program_name: str
    degree_type: str
    pages: list[RawSourcePage]


class ProjectRecord(BaseModel):
    id: int
    school_slug: str
    school_name: str
    school_country: str
    program_slug: str
    program_name: str
    degree_type: str | None = None
    department: str | None = None
    study_mode: str | None = None
    duration: str | None = None
    duration_months: int | None = None
    tuition: str | None = None
    application_deadline: str | None = None
    language_requirement: str | None = None
    academic_requirement: str | None = None
    overview: str | None = None
    last_verified_at: str
    created_at: str
    updated_at: str


class SourcePageRecord(BaseModel):
    id: int
    project_id: int
    page_type: str
    page_title: str
    source_url: str
    raw_file_path: str
    content_hash: str | None = None
    fetched_at: str | None = None


class FieldEvidenceRecord(BaseModel):
    id: int
    project_id: int
    field_name: str
    field_value: str
    evidence_text: str
    source_page_id: int
    page_type: str
    page_title: str
    source_url: str
    created_at: str


class ExtractionFailureRecord(BaseModel):
    school_slug: str
    program_slug: str
    failure_reason: str
    message: str
    attempted_at: str


class ExtractionBatchResult(BaseModel):
    total_count: int
    success_count: int
    failure_count: int
    skipped_count: int
    failures: list[ExtractionFailureRecord] = Field(default_factory=list)
