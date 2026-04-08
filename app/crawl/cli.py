from __future__ import annotations

import argparse

from app.core.config import get_settings

from app.crawl.catalog import load_source_catalog, select_targets
from app.crawl.firecrawl import build_firecrawl_client
from app.crawl.service import CrawlService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl official program pages from the source catalog.")
    parser.add_argument("--school", dest="school_slug")
    parser.add_argument("--program", dest="program_slug")
    parser.add_argument("--page-type", dest="page_type")
    parser.add_argument("--all", dest="crawl_all", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def build_crawl_service(settings) -> CrawlService:
    return CrawlService(settings=settings, client=build_firecrawl_client(settings))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    settings.ensure_runtime_directories()

    catalog = load_source_catalog(settings.source_catalog_path)
    targets = select_targets(
        catalog,
        school_slug=args.school_slug,
        program_slug=args.program_slug,
        page_type=args.page_type,
        crawl_all=args.crawl_all,
    )
    result = build_crawl_service(settings).crawl_targets(targets, force=args.force)

    print(
        f"crawl finished total={result.total_count} "
        f"success={result.success_count} failure={result.failure_count} skipped={result.skipped_count}"
    )
    return 1 if result.failure_count else 0
