from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VectorChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    school_slug: str
    school_name: str
    program_slug: str
    program_name: str
    degree_type: str
    page_type: str
    page_title: str
    source_url: str
    chunk_index: int
    content_hash: str
    project_key: str
    chunking_version: str

    @field_validator(
        "school_slug",
        "school_name",
        "program_slug",
        "program_name",
        "degree_type",
        "page_type",
        "page_title",
        "source_url",
        "content_hash",
        "project_key",
        "chunking_version",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("metadata text value must not be empty")
        return normalized


class VectorChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document: str
    metadata: VectorChunkMetadata

    @field_validator("id", "document", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("chunk text value must not be empty")
        return normalized


class VectorSearchHit(BaseModel):
    id: str
    document: str
    metadata: VectorChunkMetadata
    distance: float | None = None


class VectorBuildFailureRecord(BaseModel):
    school_slug: str
    program_slug: str
    failure_reason: str
    message: str
    attempted_at: str


class VectorBuildBatchResult(BaseModel):
    total_count: int
    success_count: int
    failure_count: int
    skipped_count: int
    failures: list[VectorBuildFailureRecord] = Field(default_factory=list)

