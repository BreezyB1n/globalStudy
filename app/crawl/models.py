from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class SourcePage(BaseModel):
    page_type: str
    url: str

    @field_validator("page_type")
    @classmethod
    def normalize_page_type(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("page_type must not be empty")
        return normalized

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("page url must not be empty")
        return normalized


class ProgramSource(BaseModel):
    school_slug: str
    school_name: str
    country: str
    program_slug: str
    program_name: str
    degree_type: str
    pages: list[SourcePage]

    @model_validator(mode="after")
    def ensure_unique_page_types(self) -> "ProgramSource":
        page_types = [page.page_type for page in self.pages]
        if len(page_types) != len(set(page_types)):
            raise ValueError("page_type must be unique within a program")
        return self


class CrawlTarget(BaseModel):
    school_slug: str
    school_name: str
    country: str
    program_slug: str
    program_name: str
    degree_type: str
    page_type: str
    source_url: str


class ScrapeResult(BaseModel):
    requested_url: str
    final_url: str
    page_title: str
    markdown: str
    http_status: int | None = None
    warning: str | None = None


class CrawlFailureRecord(BaseModel):
    school_slug: str
    program_slug: str
    page_type: str
    source_url: str
    failure_reason: str
    message: str
    attempted_at: str


class CrawlBatchResult(BaseModel):
    total_count: int
    success_count: int
    failure_count: int
    skipped_count: int
    failures: list[CrawlFailureRecord] = Field(default_factory=list)
