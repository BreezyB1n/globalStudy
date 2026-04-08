from __future__ import annotations

import json
from pathlib import Path

from app.core.exceptions import FileMissingError, InvalidRequestError

from app.crawl.models import CrawlTarget, ProgramSource


def load_source_catalog(path: Path) -> list[ProgramSource]:
    if not path.exists():
        raise FileMissingError(f"Source catalog not found: {path}")

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_data, list):
        raise InvalidRequestError("source catalog must be a JSON array")

    return [ProgramSource.model_validate(item) for item in raw_data]


def select_targets(
    catalog: list[ProgramSource],
    *,
    school_slug: str | None = None,
    program_slug: str | None = None,
    page_type: str | None = None,
    crawl_all: bool = False,
) -> list[CrawlTarget]:
    if not crawl_all and not any((school_slug, program_slug, page_type)):
        raise InvalidRequestError("Specify at least one filter or use --all")

    selected_targets: list[CrawlTarget] = []
    for program in catalog:
        if school_slug and program.school_slug != school_slug:
            continue
        if program_slug and program.program_slug != program_slug:
            continue

        for page in program.pages:
            if page_type and page.page_type != page_type:
                continue
            selected_targets.append(
                CrawlTarget(
                    school_slug=program.school_slug,
                    school_name=program.school_name,
                    country=program.country,
                    program_slug=program.program_slug,
                    program_name=program.program_name,
                    degree_type=program.degree_type,
                    page_type=page.page_type,
                    source_url=page.url,
                )
            )

    if not selected_targets:
        raise InvalidRequestError("No crawl targets matched the given filters")

    return selected_targets
