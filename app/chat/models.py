from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.chat import ChatMessage, Citation, QuestionType


class ProjectCatalogEntry(BaseModel):
    school_slug: str
    school_name: str
    program_slug: str
    program_name: str
    degree_type: str | None = None

    @field_validator(
        "school_slug",
        "school_name",
        "program_slug",
        "program_name",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project catalog text must not be empty")
        return normalized


class ChatQuestionAnalysis(BaseModel):
    question_type: QuestionType
    field_names: list[str] = Field(default_factory=list)
    is_follow_up: bool = False


class EntityResolution(BaseModel):
    primary_project: ProjectCatalogEntry | None = None
    comparison_project: ProjectCatalogEntry | None = None
    unresolved_reason: str | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "EntityResolution":
        if self.primary_project is None and self.comparison_project is not None:
            raise ValueError("comparison project cannot exist without a primary project")
        return self


class StructuredEvidence(BaseModel):
    school_name: str
    program_name: str
    field_name: str
    field_value: str
    page_title: str
    source_url: str
    evidence_text: str

    def to_citation(self) -> Citation:
        return Citation(
            school_name=self.school_name,
            program_name=self.program_name,
            page_title=self.page_title,
            source_url=self.source_url,
            evidence_text=self.evidence_text,
            evidence_type="structured_field",
        )


class VectorEvidence(BaseModel):
    school_name: str
    program_name: str
    page_title: str
    source_url: str
    evidence_text: str
    distance: float | None = None

    def to_citation(self) -> Citation:
        return Citation(
            school_name=self.school_name,
            program_name=self.program_name,
            page_title=self.page_title,
            source_url=self.source_url,
            evidence_text=self.evidence_text,
            evidence_type="vector_chunk",
        )


class ChatGraphResult(BaseModel):
    answer: str
    question_type: QuestionType
    primary_project: ProjectCatalogEntry | None = None
    comparison_project: ProjectCatalogEntry | None = None
    citations: list[Citation] = Field(default_factory=list)


RouteName = Literal["field", "field_with_vector_fallback", "explanatory", "comparison", "clarify"]
