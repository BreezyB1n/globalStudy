from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ChatRole = Literal["user", "assistant"]
QuestionType = Literal["field", "explanatory", "comparison"]
EvidenceType = Literal["structured_field", "vector_chunk"]


class ChatMessage(BaseModel):
    role: ChatRole
    content: str

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message content must not be empty")
        return normalized


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_last_message(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("the last message must come from the user")
        return self


class Citation(BaseModel):
    school_name: str
    program_name: str
    page_title: str
    source_url: str
    evidence_text: str
    evidence_type: EvidenceType


class ResolvedContext(BaseModel):
    school_name: str | None = None
    program_name: str | None = None
    question_type: QuestionType


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    resolved_context: ResolvedContext
