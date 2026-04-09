from __future__ import annotations

from app.chat.models import ProjectCatalogEntry, StructuredEvidence
from app.extract.repository import SQLiteProjectRepository

DEFAULT_COMPARISON_FIELDS = (
    "tuition",
    "language_requirement",
    "academic_requirement",
    "application_deadline",
    "duration",
    "overview",
)


class StructuredQueryService:
    def __init__(self, project_repository: SQLiteProjectRepository) -> None:
        self.project_repository = project_repository

    def fetch(
        self,
        *,
        primary_project: ProjectCatalogEntry,
        comparison_project: ProjectCatalogEntry | None,
        question_type: str,
        field_names: list[str],
    ) -> list[StructuredEvidence]:
        target_fields = tuple(field_names or DEFAULT_COMPARISON_FIELDS)
        target_projects = [primary_project]
        if question_type == "comparison" and comparison_project is not None:
            target_projects.append(comparison_project)

        evidences: list[StructuredEvidence] = []
        for project in target_projects:
            for field_name in target_fields:
                record = self.project_repository.get_field_evidence(
                    project.school_slug,
                    project.program_slug,
                    field_name,
                )
                if record is None:
                    continue
                evidences.append(
                    StructuredEvidence(
                        school_name=project.school_name,
                        program_name=project.program_name,
                        field_name=record.field_name,
                        field_value=record.field_value,
                        page_title=record.page_title,
                        source_url=record.source_url,
                        evidence_text=record.evidence_text,
                    )
                )
        return evidences
