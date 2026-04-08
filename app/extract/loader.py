from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import InvalidRequestError

from app.crawl.catalog import load_source_catalog as load_catalog_file
from app.crawl.models import ProgramSource
from app.extract.models import ProjectSourceBundle, RawSourcePage


def load_source_catalog(path: Path) -> list[ProgramSource]:
    return load_catalog_file(path)


def select_programs(
    catalog: list[ProgramSource],
    *,
    school_slug: str | None = None,
    program_slug: str | None = None,
    crawl_all: bool = False,
) -> list[ProgramSource]:
    if not crawl_all and not any((school_slug, program_slug)):
        raise InvalidRequestError("Specify at least one filter or use --all")

    selected = [
        program
        for program in catalog
        if (not school_slug or program.school_slug == school_slug)
        and (not program_slug or program.program_slug == program_slug)
    ]
    if not selected:
        raise InvalidRequestError("No extraction targets matched the given filters")
    return selected


def load_project_bundle(settings: Settings, program: ProgramSource) -> ProjectSourceBundle:
    pages: list[RawSourcePage] = []
    base_dir = settings.raw_data_dir / program.school_slug / program.program_slug
    for page in program.pages:
        markdown_path = base_dir / f"{page.page_type}.md"
        metadata_path = base_dir / f"{page.page_type}.meta.json"
        if not markdown_path.exists() or not metadata_path.exists():
            continue

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        pages.append(
            RawSourcePage(
                page_type=str(metadata.get("page_type") or page.page_type),
                page_title=str(metadata.get("page_title") or page.page_type),
                source_url=str(metadata.get("source_url") or page.url),
                raw_file_path=markdown_path,
                content_hash=metadata.get("content_hash"),
                fetched_at=metadata.get("fetched_at"),
                markdown=markdown_path.read_text(encoding="utf-8"),
            )
        )

    return ProjectSourceBundle(
        school_slug=program.school_slug,
        school_name=program.school_name,
        school_country=program.country,
        program_slug=program.program_slug,
        program_name=program.program_name,
        degree_type=program.degree_type,
        pages=pages,
    )
