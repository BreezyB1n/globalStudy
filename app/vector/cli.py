from __future__ import annotations

import argparse

from app.core.config import get_settings

from app.extract.loader import load_source_catalog, select_programs
from app.vector.embedding import build_bailian_embedder
from app.vector.repository import ChromaVectorRepository
from app.vector.service import VectorStoreBuildService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Chroma vector store from crawled programme pages.")
    parser.add_argument("--school", dest="school_slug")
    parser.add_argument("--program", dest="program_slug")
    parser.add_argument("--all", dest="crawl_all", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def build_vector_service(settings) -> VectorStoreBuildService:
    return VectorStoreBuildService(
        settings=settings,
        embedder=build_bailian_embedder(settings),
        repository=ChromaVectorRepository(
            persist_dir=settings.chroma_persist_dir,
            collection_name=settings.vector_collection_name,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    settings.ensure_runtime_directories()

    catalog = load_source_catalog(settings.source_catalog_path)
    programs = select_programs(
        catalog,
        school_slug=args.school_slug,
        program_slug=args.program_slug,
        crawl_all=args.crawl_all,
    )
    result = build_vector_service(settings).build_programs(programs, force=args.force)
    print(
        f"vector build finished total={result.total_count} "
        f"success={result.success_count} failure={result.failure_count} skipped={result.skipped_count}"
    )
    return 1 if result.failure_count else 0
