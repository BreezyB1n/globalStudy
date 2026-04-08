from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.extract.models import ProjectSourceBundle, RawSourcePage

from app.vector.cleaning import clean_markdown
from app.vector.models import VectorChunk, VectorChunkMetadata

CHUNKING_VERSION = "v1"


@dataclass(slots=True)
class _Section:
    heading: str | None
    paragraphs: list[str]


def build_project_chunks(
    bundle: ProjectSourceBundle,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[VectorChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be >= 0 and smaller than chunk_size")

    chunks: list[VectorChunk] = []
    for page in bundle.pages:
        chunks.extend(
            _build_page_chunks(
                bundle=bundle,
                page=page,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )
    return chunks


def _build_page_chunks(
    *,
    bundle: ProjectSourceBundle,
    page: RawSourcePage,
    chunk_size: int,
    chunk_overlap: int,
) -> list[VectorChunk]:
    cleaned_markdown = clean_markdown(page.markdown)
    if not cleaned_markdown:
        return []

    sections = _split_sections(cleaned_markdown)
    documents: list[str] = []
    for section in sections:
        documents.extend(
            _split_section_into_documents(
                page_title=page.page_title,
                section=section,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )

    project_key = build_project_key(bundle.school_slug, bundle.program_slug)
    normalized_content_hash = page.content_hash or compute_content_hash(page.markdown)
    chunks: list[VectorChunk] = []
    for chunk_index, document in enumerate(documents):
        chunk_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()[:16]
        chunk_id = (
            f"{bundle.school_slug}:{bundle.program_slug}:{page.page_type}:{chunk_index}:{chunk_hash}"
        )
        chunks.append(
            VectorChunk(
                id=chunk_id,
                document=document,
                metadata=VectorChunkMetadata(
                    school_slug=bundle.school_slug,
                    school_name=bundle.school_name,
                    program_slug=bundle.program_slug,
                    program_name=bundle.program_name,
                    degree_type=bundle.degree_type,
                    page_type=page.page_type,
                    page_title=page.page_title,
                    source_url=page.source_url,
                    chunk_index=chunk_index,
                    content_hash=normalized_content_hash,
                    project_key=project_key,
                    chunking_version=CHUNKING_VERSION,
                ),
            )
        )
    return chunks


def build_project_key(school_slug: str, program_slug: str) -> str:
    return f"{school_slug}:{program_slug}"


def compute_content_hash(markdown: str) -> str:
    digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _split_sections(markdown: str) -> list[_Section]:
    sections: list[_Section] = []
    current_heading: str | None = None
    current_paragraph_lines: list[str] = []
    current_paragraphs: list[str] = []

    def flush_paragraph() -> None:
        nonlocal current_paragraph_lines, current_paragraphs
        if not current_paragraph_lines:
            return
        current_paragraphs.append("\n".join(current_paragraph_lines).strip())
        current_paragraph_lines = []

    def flush_section() -> None:
        nonlocal current_heading, current_paragraphs
        flush_paragraph()
        if not current_paragraphs:
            current_heading = None
            return
        sections.append(_Section(heading=current_heading, paragraphs=current_paragraphs))
        current_heading = None
        current_paragraphs = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("#"):
            flush_section()
            current_heading = line.lstrip("#").strip()
            continue
        current_paragraph_lines.append(line)

    flush_section()
    return [section for section in sections if section.heading or section.paragraphs]


def _split_section_into_documents(
    *,
    page_title: str,
    section: _Section,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    header_lines = [f"# {page_title}"]
    if section.heading and section.heading != page_title:
        header_lines.append(f"## {section.heading}")
    header = "\n".join(header_lines)

    if not section.paragraphs:
        return [header]

    documents: list[str] = []
    current_paragraphs: list[str] = []
    for paragraph in section.paragraphs:
        candidate = _join_chunk_parts(header, current_paragraphs + [paragraph])
        if current_paragraphs and len(candidate) > chunk_size:
            documents.append(_join_chunk_parts(header, current_paragraphs))
            current_paragraphs = _build_overlap_paragraphs(current_paragraphs, chunk_overlap)
        current_paragraphs.append(paragraph)

    if current_paragraphs:
        documents.append(_join_chunk_parts(header, current_paragraphs))
    return documents


def _join_chunk_parts(header: str, paragraphs: list[str]) -> str:
    chunk_parts = [header, *paragraphs]
    return "\n\n".join(part for part in chunk_parts if part).strip()


def _build_overlap_paragraphs(paragraphs: list[str], overlap_size: int) -> list[str]:
    if overlap_size <= 0 or not paragraphs:
        return []
    selected: list[str] = []
    total_chars = 0
    for paragraph in reversed(paragraphs):
        selected.append(paragraph)
        total_chars += len(paragraph)
        if total_chars >= overlap_size:
            break
    return list(reversed(selected))
