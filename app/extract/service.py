from __future__ import annotations

import json
from datetime import datetime

from app.core.config import Settings
from app.core.exceptions import AppError, DatabaseOperationError
from app.core.logging import get_logger

from app.crawl.models import ProgramSource
from app.extract.fallbacks import enrich_extraction_from_markdown
from app.extract.loader import load_project_bundle
from app.extract.models import (
    ExtractionBatchResult,
    ExtractionFailureRecord,
    ProjectSourceBundle,
)
from app.extract.normalization import build_normalized_project_values
from app.extract.repository import SQLiteProjectRepository


class ExtractionValidationError(AppError):
    code = "EXTRACTION_VALIDATION_ERROR"

    def __init__(self, failure_reason: str, message: str) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


class ProjectExtractionService:
    def __init__(self, *, settings: Settings, extractor, repository: SQLiteProjectRepository) -> None:
        self.settings = settings
        self.extractor = extractor
        self.repository = repository
        self.logger = get_logger("globalstudy.extract")

    def extract_programs(
        self,
        programs: list[ProgramSource],
        *,
        force: bool,
    ) -> ExtractionBatchResult:
        self.settings.ensure_runtime_directories()
        failures: list[ExtractionFailureRecord] = []
        success_count = 0
        skipped_count = 0

        for program in programs:
            if self.repository.project_exists(program.school_slug, program.program_slug) and not force:
                skipped_count += 1
                continue

            try:
                bundle = load_project_bundle(self.settings, program)
                self._validate_bundle(bundle)
                extraction = self.extractor.extract(bundle)
                extraction = enrich_extraction_from_markdown(bundle, extraction)
                self._validate_evidence_sources(bundle, extraction.field_map())
                normalized_values = build_normalized_project_values(bundle, extraction)
                extracted_at = datetime.now().astimezone().isoformat()
                self.repository.upsert_project(
                    bundle=bundle,
                    extraction=extraction,
                    normalized_values=normalized_values,
                    extracted_at=extracted_at,
                )
                self._write_snapshot(program.school_slug, program.program_slug)
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                failure = self._build_failure_record(program, exc)
                failures.append(failure)
                self._append_failure_log(failure)

        return ExtractionBatchResult(
            total_count=len(programs),
            success_count=success_count,
            failure_count=len(failures),
            skipped_count=skipped_count,
            failures=failures,
        )

    def _validate_bundle(self, bundle: ProjectSourceBundle) -> None:
        if not bundle.pages:
            raise ExtractionValidationError(
                "RAW_INPUT_NOT_FOUND",
                f"No raw page files found for {bundle.school_slug}/{bundle.program_slug}",
            )

    def _validate_evidence_sources(self, bundle: ProjectSourceBundle, field_map: dict[str, object]) -> None:
        available_page_types = {page.page_type for page in bundle.pages}
        for field_name, field in field_map.items():
            if field is None or field.value is None:
                continue
            if field.source_page_type not in available_page_types:
                raise ExtractionValidationError(
                    "UNKNOWN_SOURCE_PAGE",
                    f"Field {field_name} referenced unknown source page {field.source_page_type}",
                )

    def _build_failure_record(
        self,
        program: ProgramSource,
        exc: Exception,
    ) -> ExtractionFailureRecord:
        if isinstance(exc, ExtractionValidationError):
            failure_reason = exc.failure_reason
            message = exc.message
        elif isinstance(exc, DatabaseOperationError):
            failure_reason = exc.error_code
            message = exc.message
        elif isinstance(exc, AppError):
            failure_reason = exc.error_code
            message = exc.message
        else:
            failure_reason = "UNEXPECTED_ERROR"
            message = str(exc)

        self.logger.warning(
            "Failed to extract school=%s program=%s reason=%s",
            program.school_slug,
            program.program_slug,
            failure_reason,
            extra={"request_id": "-"},
        )
        return ExtractionFailureRecord(
            school_slug=program.school_slug,
            program_slug=program.program_slug,
            failure_reason=failure_reason,
            message=message,
            attempted_at=datetime.now().astimezone().isoformat(),
        )

    def _append_failure_log(self, failure: ExtractionFailureRecord) -> None:
        log_path = self.settings.extraction_failure_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(failure.model_dump_json(ensure_ascii=False))
            handle.write("\n")

    def _write_snapshot(self, school_slug: str, program_slug: str) -> None:
        project = self.repository.get_project(school_slug, program_slug)
        if project is None:
            return
        source_pages = self.repository.list_source_pages(school_slug, program_slug)
        evidences = self.repository.list_field_evidences(school_slug, program_slug)
        snapshot_item = {
            "school_slug": project.school_slug,
            "school_name": project.school_name,
            "school_country": project.school_country,
            "program_slug": project.program_slug,
            "program_name": project.program_name,
            "degree_type": project.degree_type,
            "department": project.department,
            "study_mode": project.study_mode,
            "duration": project.duration,
            "duration_months": project.duration_months,
            "tuition": project.tuition,
            "application_deadline": project.application_deadline,
            "language_requirement": project.language_requirement,
            "academic_requirement": project.academic_requirement,
            "overview": project.overview,
            "last_verified_at": project.last_verified_at,
            "source_pages": [item.model_dump() for item in source_pages],
            "field_evidences": {
                item.field_name: {
                    "field_value": item.field_value,
                    "evidence_text": item.evidence_text,
                    "page_type": item.page_type,
                    "page_title": item.page_title,
                    "source_url": item.source_url,
                }
                for item in evidences
            },
        }

        existing_items: list[dict] = []
        if self.settings.projects_snapshot_path.exists():
            existing_items = json.loads(self.settings.projects_snapshot_path.read_text(encoding="utf-8"))

        filtered_items = [
            item
            for item in existing_items
            if not (
                item.get("school_slug") == school_slug
                and item.get("program_slug") == program_slug
            )
        ]
        filtered_items.append(snapshot_item)
        filtered_items.sort(key=lambda item: (item["school_slug"], item["program_slug"]))
        self.settings.projects_snapshot_path.write_text(
            json.dumps(filtered_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
