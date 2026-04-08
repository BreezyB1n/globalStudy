from __future__ import annotations

import json
from datetime import datetime

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

from app.crawl.models import ProgramSource
from app.extract.loader import load_project_bundle
from app.vector.chunking import CHUNKING_VERSION, build_project_chunks
from app.vector.models import VectorBuildBatchResult, VectorBuildFailureRecord


class VectorBuildValidationError(AppError):
    code = "VECTOR_BUILD_VALIDATION_ERROR"

    def __init__(self, failure_reason: str, message: str) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


class VectorStoreBuildService:
    def __init__(self, *, settings: Settings, embedder, repository) -> None:
        self.settings = settings
        self.embedder = embedder
        self.repository = repository
        self.logger = get_logger("globalstudy.vector")

    def build_programs(self, programs: list[ProgramSource], *, force: bool) -> VectorBuildBatchResult:
        self.settings.ensure_runtime_directories()
        failures: list[VectorBuildFailureRecord] = []
        success_count = 0
        skipped_count = 0

        for program in programs:
            try:
                bundle = load_project_bundle(self.settings, program)
                self._validate_bundle(bundle)
                if not force and self.repository.project_is_current(bundle, chunking_version=CHUNKING_VERSION):
                    skipped_count += 1
                    continue
                chunks = build_project_chunks(
                    bundle,
                    chunk_size=self.settings.vector_chunk_size,
                    chunk_overlap=self.settings.vector_chunk_overlap,
                )
                if not chunks:
                    raise VectorBuildValidationError(
                        "NO_VALID_CHUNKS",
                        f"No readable content remained after cleaning for {bundle.school_slug}/{bundle.program_slug}",
                    )
                embeddings = self._embed_chunks([chunk.document for chunk in chunks])
                self.repository.replace_project_chunks(
                    bundle=bundle,
                    chunks=chunks,
                    embeddings=embeddings,
                )
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                failure = self._build_failure_record(program, exc)
                failures.append(failure)
                self._append_failure_log(failure)

        return VectorBuildBatchResult(
            total_count=len(programs),
            success_count=success_count,
            failure_count=len(failures),
            skipped_count=skipped_count,
            failures=failures,
        )

    def _embed_chunks(self, documents: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        batch_size = self.settings.vector_embed_batch_size
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            batch_embeddings = self.embedder.embed_texts(batch)
            if len(batch_embeddings) != len(batch):
                raise VectorBuildValidationError(
                    "EMBEDDING_COUNT_MISMATCH",
                    "Embedding response count did not match chunk count",
                )
            embeddings.extend(batch_embeddings)
        return embeddings

    def _validate_bundle(self, bundle) -> None:
        if not bundle.pages:
            raise VectorBuildValidationError(
                "RAW_INPUT_NOT_FOUND",
                f"No raw page files found for {bundle.school_slug}/{bundle.program_slug}",
            )

    def _build_failure_record(self, program: ProgramSource, exc: Exception) -> VectorBuildFailureRecord:
        if isinstance(exc, VectorBuildValidationError):
            failure_reason = exc.failure_reason
            message = exc.message
        elif isinstance(exc, AppError):
            failure_reason = exc.error_code
            message = exc.message
        else:
            failure_reason = "UNEXPECTED_ERROR"
            message = str(exc)

        self.logger.warning(
            "Failed to build vector store school=%s program=%s reason=%s",
            program.school_slug,
            program.program_slug,
            failure_reason,
            extra={"request_id": "-"},
        )
        return VectorBuildFailureRecord(
            school_slug=program.school_slug,
            program_slug=program.program_slug,
            failure_reason=failure_reason,
            message=message,
            attempted_at=datetime.now().astimezone().isoformat(),
        )

    def _append_failure_log(self, failure: VectorBuildFailureRecord) -> None:
        log_path = self.settings.vector_build_failure_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(failure.model_dump(), ensure_ascii=False))
            handle.write("\n")

