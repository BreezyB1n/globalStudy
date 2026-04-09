from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.exceptions import DatabaseOperationError

from app.extract.models import (
    FieldEvidenceRecord,
    ProjectRecord,
    ProjectSourceBundle,
    SourcePageRecord,
    StructuredProjectExtraction,
)


class SQLiteProjectRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def project_exists(self, school_slug: str, program_slug: str) -> bool:
        row = self._fetch_one(
            "SELECT 1 FROM projects WHERE school_slug = ? AND program_slug = ?",
            (school_slug, program_slug),
        )
        return row is not None

    def upsert_project(
        self,
        *,
        bundle: ProjectSourceBundle,
        extraction: StructuredProjectExtraction,
        normalized_values: dict[str, str | int | None],
        extracted_at: str,
    ) -> None:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, created_at FROM projects WHERE school_slug = ? AND program_slug = ?",
                (bundle.school_slug, bundle.program_slug),
            ).fetchone()
            created_at = extracted_at if existing is None else existing["created_at"]

            if existing is None:
                cursor = conn.execute(
                    """
                    INSERT INTO projects (
                        school_slug,
                        school_name,
                        school_country,
                        program_slug,
                        program_name,
                        degree_type,
                        department,
                        study_mode,
                        duration,
                        duration_months,
                        tuition,
                        application_deadline,
                        language_requirement,
                        academic_requirement,
                        overview,
                        last_verified_at,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bundle.school_slug,
                        normalized_values["school_name"],
                        normalized_values["school_country"],
                        bundle.program_slug,
                        normalized_values["program_name"],
                        normalized_values["degree_type"],
                        normalized_values["department"],
                        normalized_values["study_mode"],
                        normalized_values["duration"],
                        normalized_values["duration_months"],
                        normalized_values["tuition"],
                        normalized_values["application_deadline"],
                        normalized_values["language_requirement"],
                        normalized_values["academic_requirement"],
                        normalized_values["overview"],
                        extracted_at,
                        created_at,
                        extracted_at,
                    ),
                )
                project_id = int(cursor.lastrowid)
            else:
                project_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE projects
                    SET school_name = ?,
                        school_country = ?,
                        program_name = ?,
                        degree_type = ?,
                        department = ?,
                        study_mode = ?,
                        duration = ?,
                        duration_months = ?,
                        tuition = ?,
                        application_deadline = ?,
                        language_requirement = ?,
                        academic_requirement = ?,
                        overview = ?,
                        last_verified_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_values["school_name"],
                        normalized_values["school_country"],
                        normalized_values["program_name"],
                        normalized_values["degree_type"],
                        normalized_values["department"],
                        normalized_values["study_mode"],
                        normalized_values["duration"],
                        normalized_values["duration_months"],
                        normalized_values["tuition"],
                        normalized_values["application_deadline"],
                        normalized_values["language_requirement"],
                        normalized_values["academic_requirement"],
                        normalized_values["overview"],
                        extracted_at,
                        extracted_at,
                        project_id,
                    ),
                )

            conn.execute("DELETE FROM field_evidences WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM source_pages WHERE project_id = ?", (project_id,))

            source_page_ids: dict[str, int] = {}
            for page in bundle.pages:
                cursor = conn.execute(
                    """
                    INSERT INTO source_pages (
                        project_id,
                        page_type,
                        page_title,
                        source_url,
                        raw_file_path,
                        content_hash,
                        fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        page.page_type,
                        page.page_title,
                        page.source_url,
                        str(page.raw_file_path),
                        page.content_hash,
                        page.fetched_at,
                    ),
                )
                source_page_ids[page.page_type] = int(cursor.lastrowid)

            for field_name, field in extraction.field_map().items():
                if field is None or field.value is None:
                    continue
                source_page_id = source_page_ids.get(field.source_page_type)
                if source_page_id is None:
                    raise DatabaseOperationError(
                        f"Evidence page_type {field.source_page_type} was not found for field {field_name}"
                    )
                conn.execute(
                    """
                    INSERT INTO field_evidences (
                        project_id,
                        field_name,
                        field_value,
                        evidence_text,
                        source_page_id,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        field_name,
                        field.value,
                        field.evidence_text,
                        source_page_id,
                        extracted_at,
                    ),
                )

    def get_project(self, school_slug: str, program_slug: str) -> ProjectRecord | None:
        row = self._fetch_one(
            """
            SELECT id, school_slug, school_name, school_country, program_slug, program_name, degree_type,
                   department, study_mode, duration, duration_months, tuition, application_deadline,
                   language_requirement, academic_requirement, overview, last_verified_at, created_at, updated_at
            FROM projects
            WHERE school_slug = ? AND program_slug = ?
            """,
            (school_slug, program_slug),
        )
        return ProjectRecord.model_validate(dict(row)) if row else None

    def list_projects(self) -> list[ProjectRecord]:
        rows = self._fetch_all(
            """
            SELECT id, school_slug, school_name, school_country, program_slug, program_name, degree_type,
                   department, study_mode, duration, duration_months, tuition, application_deadline,
                   language_requirement, academic_requirement, overview, last_verified_at, created_at, updated_at
            FROM projects
            ORDER BY school_name, program_name
            """,
            (),
        )
        return [ProjectRecord.model_validate(dict(row)) for row in rows]

    def list_source_pages(self, school_slug: str, program_slug: str) -> list[SourcePageRecord]:
        rows = self._fetch_all(
            """
            SELECT sp.id, sp.project_id, sp.page_type, sp.page_title, sp.source_url, sp.raw_file_path,
                   sp.content_hash, sp.fetched_at
            FROM source_pages sp
            JOIN projects p ON p.id = sp.project_id
            WHERE p.school_slug = ? AND p.program_slug = ?
            ORDER BY sp.page_type
            """,
            (school_slug, program_slug),
        )
        return [SourcePageRecord.model_validate(dict(row)) for row in rows]

    def get_field_evidence(
        self,
        school_slug: str,
        program_slug: str,
        field_name: str,
    ) -> FieldEvidenceRecord | None:
        row = self._fetch_one(
            """
            SELECT fe.id, fe.project_id, fe.field_name, fe.field_value, fe.evidence_text, fe.source_page_id,
                   sp.page_type, sp.page_title, sp.source_url, fe.created_at
            FROM field_evidences fe
            JOIN projects p ON p.id = fe.project_id
            JOIN source_pages sp ON sp.id = fe.source_page_id
            WHERE p.school_slug = ? AND p.program_slug = ? AND fe.field_name = ?
            """,
            (school_slug, program_slug, field_name),
        )
        return FieldEvidenceRecord.model_validate(dict(row)) if row else None

    def list_field_evidences(self, school_slug: str, program_slug: str) -> list[FieldEvidenceRecord]:
        rows = self._fetch_all(
            """
            SELECT fe.id, fe.project_id, fe.field_name, fe.field_value, fe.evidence_text, fe.source_page_id,
                   sp.page_type, sp.page_title, sp.source_url, fe.created_at
            FROM field_evidences fe
            JOIN projects p ON p.id = fe.project_id
            JOIN source_pages sp ON sp.id = fe.source_page_id
            WHERE p.school_slug = ? AND p.program_slug = ?
            ORDER BY fe.field_name
            """,
            (school_slug, program_slug),
        )
        return [FieldEvidenceRecord.model_validate(dict(row)) for row in rows]

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    school_slug TEXT NOT NULL,
                    school_name TEXT NOT NULL,
                    school_country TEXT NOT NULL,
                    program_slug TEXT NOT NULL,
                    program_name TEXT NOT NULL,
                    degree_type TEXT,
                    department TEXT,
                    study_mode TEXT,
                    duration TEXT,
                    duration_months INTEGER,
                    tuition TEXT,
                    application_deadline TEXT,
                    language_requirement TEXT,
                    academic_requirement TEXT,
                    overview TEXT,
                    last_verified_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (school_slug, program_slug)
                );

                CREATE TABLE IF NOT EXISTS source_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    page_type TEXT NOT NULL,
                    page_title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    raw_file_path TEXT NOT NULL,
                    content_hash TEXT,
                    fetched_at TEXT,
                    UNIQUE (project_id, page_type),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS field_evidences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    field_name TEXT NOT NULL,
                    field_value TEXT NOT NULL,
                    evidence_text TEXT NOT NULL,
                    source_page_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (project_id, field_name),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (source_page_id) REFERENCES source_pages(id) ON DELETE CASCADE
                );
                """
            )

    def _fetch_one(self, sql: str, params: tuple[object, ...]) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return row

    def _fetch_all(self, sql: str, params: tuple[object, ...]) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return list(rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
