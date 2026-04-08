import importlib
import json
import sys
from hashlib import sha256


def _clear_modules() -> None:
    for module_name in (
        "app.core.config",
        "app.crawl.models",
        "app.crawl.catalog",
        "app.extract.models",
        "app.extract.loader",
        "app.vector.models",
        "app.vector.cleaning",
        "app.vector.chunking",
        "app.vector.embedding",
        "app.vector.repository",
        "app.vector.service",
        "app.vector.cli",
    ):
        sys.modules.pop(module_name, None)


def _load_module(module_name: str):
    _clear_modules()
    return importlib.import_module(module_name)


def _sample_catalog() -> list[dict]:
    return [
        {
            "school_slug": "imperial",
            "school_name": "Imperial College London",
            "country": "UK",
            "program_slug": "msc-artificial-intelligence",
            "program_name": "MSc Artificial Intelligence",
            "degree_type": "MSc",
            "pages": [
                {
                    "page_type": "overview",
                    "url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                },
                {
                    "page_type": "entry_requirements",
                    "url": "https://www.imperial.ac.uk/computing/prospective-students/pg/mai/",
                },
            ],
        }
    ]


def _write_catalog(settings, catalog: list[dict]) -> None:
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _seed_raw_project(settings, *, school_slug: str, program_slug: str, pages: list[dict]) -> None:
    output_dir = settings.raw_data_dir / school_slug / program_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    for page in pages:
        markdown = page["markdown"]
        markdown_path = output_dir / f"{page['page_type']}.md"
        metadata_path = output_dir / f"{page['page_type']}.meta.json"
        markdown_path.write_text(markdown, encoding="utf-8")
        content_hash = page.get("content_hash") or f"sha256:{sha256(markdown.encode('utf-8')).hexdigest()}"
        metadata_path.write_text(
            json.dumps(
                {
                    "school_slug": school_slug,
                    "school_name": page.get("school_name", "Imperial College London"),
                    "program_slug": program_slug,
                    "program_name": page.get("program_name", "MSc Artificial Intelligence"),
                    "page_type": page["page_type"],
                    "page_title": page["page_title"],
                    "source_url": page["source_url"],
                    "final_url": page["source_url"],
                    "fetched_at": "2026-04-08T21:00:00+08:00",
                    "content_hash": content_hash,
                    "status": "success",
                    "http_status": 200,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(len(text)), float(index + 1)] for index, text in enumerate(texts)]


class FakeCollection:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def count(self) -> int:
        return len(self.rows)

    def upsert(self, *, ids, embeddings, documents, metadatas):
        for index, row_id in enumerate(ids):
            self.rows[row_id] = {
                "embedding": embeddings[index],
                "document": documents[index],
                "metadata": metadatas[index],
            }

    def get(self, *, ids=None, where=None, include=None):
        include = include or []
        rows = self._select_rows(ids=ids, where=where)
        return {
            "ids": [row_id for row_id, _ in rows],
            "documents": [payload["document"] for _, payload in rows] if "documents" in include else None,
            "metadatas": [payload["metadata"] for _, payload in rows] if "metadatas" in include else None,
            "embeddings": [payload["embedding"] for _, payload in rows] if "embeddings" in include else None,
        }

    def delete(self, *, ids=None, where=None):
        for row_id, _ in self._select_rows(ids=ids, where=where):
            self.rows.pop(row_id, None)

    def query(self, *, query_embeddings, n_results, where=None, include=None):
        include = include or []
        rows = self._select_rows(where=where)
        all_ids = []
        all_documents = []
        all_metadatas = []
        all_distances = []
        for query_embedding in query_embeddings:
            ranked = sorted(
                rows,
                key=lambda item: _squared_distance(query_embedding, item[1]["embedding"]),
            )[:n_results]
            all_ids.append([row_id for row_id, _ in ranked])
            all_documents.append([payload["document"] for _, payload in ranked] if "documents" in include else [])
            all_metadatas.append([payload["metadata"] for _, payload in ranked] if "metadatas" in include else [])
            all_distances.append(
                [
                    _squared_distance(query_embedding, payload["embedding"])
                    for _, payload in ranked
                ]
                if "distances" in include
                else []
            )
        return {
            "ids": all_ids,
            "documents": all_documents,
            "metadatas": all_metadatas,
            "distances": all_distances,
        }

    def _select_rows(self, *, ids=None, where=None):
        selected = []
        id_filter = set(ids) if ids is not None else None
        for row_id, payload in self.rows.items():
            if id_filter is not None and row_id not in id_filter:
                continue
            metadata = payload["metadata"]
            if where and any(metadata.get(key) != value for key, value in where.items()):
                continue
            selected.append((row_id, payload))
        return selected


def _squared_distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))


def test_chunk_builder_removes_noise_and_preserves_source_metadata(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    _write_catalog(settings, _sample_catalog())
    _seed_raw_project(
        settings,
        school_slug="imperial",
        program_slug="msc-artificial-intelligence",
        pages=[
            {
                "page_type": "overview",
                "page_title": "MSc Artificial Intelligence",
                "source_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "markdown": "\n".join(
                    [
                        "Skip to main content",
                        "Home | Study | Research | Search",
                        "# MSc Artificial Intelligence",
                        "## Course overview",
                        "Learn machine learning, optimisation, and probabilistic reasoning in depth.",
                        "",
                        "## Entry requirements",
                        "You should have a first-class degree in computing or a closely related subject.",
                    ]
                ),
            }
        ],
    )

    loader_module = _load_module("app.extract.loader")
    chunking_module = _load_module("app.vector.chunking")
    catalog = loader_module.load_source_catalog(settings.source_catalog_path)
    program = loader_module.select_programs(catalog, school_slug="imperial")[0]
    bundle = loader_module.load_project_bundle(settings, program)

    chunks = chunking_module.build_project_chunks(bundle, chunk_size=220, chunk_overlap=40)

    assert len(chunks) >= 2
    assert all("Skip to main content" not in chunk.document for chunk in chunks)
    assert all("Home | Study | Research | Search" not in chunk.document for chunk in chunks)
    assert chunks[0].metadata.school_slug == "imperial"
    assert chunks[0].metadata.program_slug == "msc-artificial-intelligence"
    assert chunks[0].metadata.page_type == "overview"
    assert chunks[0].metadata.page_title == "MSc Artificial Intelligence"
    assert chunks[0].metadata.source_url.endswith("/artificial-intelligence/")
    assert chunks[0].metadata.content_hash.startswith("sha256:")


def test_vector_build_service_persists_chunks_and_skips_unchanged_programs(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    _write_catalog(settings, _sample_catalog())
    _seed_raw_project(
        settings,
        school_slug="imperial",
        program_slug="msc-artificial-intelligence",
        pages=[
            {
                "page_type": "overview",
                "page_title": "MSc Artificial Intelligence",
                "source_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "markdown": "\n".join(
                    [
                        "# MSc Artificial Intelligence",
                        "## Course overview",
                        "Learn machine learning, optimisation, and probabilistic reasoning in depth.",
                        "",
                        "## Tuition fees",
                        "Home students pay £24,600 and overseas students pay £46,000.",
                    ]
                ),
            },
            {
                "page_type": "entry_requirements",
                "page_title": "Entry requirements",
                "source_url": "https://www.imperial.ac.uk/computing/prospective-students/pg/mai/",
                "markdown": "# Entry requirements\nYou should have a first-class degree in computing or a closely related subject.",
            },
        ],
    )

    loader_module = _load_module("app.extract.loader")
    repository_module = _load_module("app.vector.repository")
    service_module = _load_module("app.vector.service")

    catalog = loader_module.load_source_catalog(settings.source_catalog_path)
    programs = loader_module.select_programs(catalog, school_slug="imperial")
    repository = repository_module.ChromaVectorRepository(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.vector_collection_name,
        collection=FakeCollection(),
    )
    embedder = FakeEmbedder()
    service = service_module.VectorStoreBuildService(
        settings=settings,
        embedder=embedder,
        repository=repository,
    )

    first_result = service.build_programs(programs, force=False)
    second_result = service.build_programs(programs, force=False)
    stored_rows = list(repository.collection.rows.values())
    first_embedding = stored_rows[0]["embedding"]
    search_hits = repository.query(
        query_embedding=first_embedding,
        top_k=2,
        filters={"school_slug": "imperial"},
    )

    assert first_result.success_count == 1
    assert first_result.failure_count == 0
    assert repository.collection.count() >= 2
    assert len(embedder.calls) == 1
    assert second_result.skipped_count == 1
    assert stored_rows[0]["metadata"]["program_name"] == "MSc Artificial Intelligence"
    assert stored_rows[0]["metadata"]["source_url"].startswith("https://www.imperial.ac.uk/")
    assert stored_rows[0]["metadata"]["chunk_index"] == 0
    assert stored_rows[0]["metadata"]["content_hash"].startswith("sha256:")
    assert search_hits[0].metadata.program_slug == "msc-artificial-intelligence"
    assert "machine learning" in search_hits[0].document.lower()


def test_vector_build_service_rebuilds_when_source_content_changes(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    _write_catalog(settings, _sample_catalog())
    _seed_raw_project(
        settings,
        school_slug="imperial",
        program_slug="msc-artificial-intelligence",
        pages=[
            {
                "page_type": "overview",
                "page_title": "MSc Artificial Intelligence",
                "source_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "markdown": "# MSc Artificial Intelligence\n## Course overview\nOriginal overview text.",
            }
        ],
    )

    loader_module = _load_module("app.extract.loader")
    repository_module = _load_module("app.vector.repository")
    service_module = _load_module("app.vector.service")

    catalog = loader_module.load_source_catalog(settings.source_catalog_path)
    programs = loader_module.select_programs(catalog, school_slug="imperial")
    repository = repository_module.ChromaVectorRepository(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.vector_collection_name,
        collection=FakeCollection(),
    )
    embedder = FakeEmbedder()
    service = service_module.VectorStoreBuildService(
        settings=settings,
        embedder=embedder,
        repository=repository,
    )

    first_result = service.build_programs(programs, force=False)
    _seed_raw_project(
        settings,
        school_slug="imperial",
        program_slug="msc-artificial-intelligence",
        pages=[
            {
                "page_type": "overview",
                "page_title": "MSc Artificial Intelligence",
                "source_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "markdown": "# MSc Artificial Intelligence\n## Course overview\nUpdated overview text with new module information.",
            }
        ],
    )
    second_result = service.build_programs(programs, force=False)
    search_hits = repository.query(
        query_embedding=list(repository.collection.rows.values())[0]["embedding"],
        top_k=1,
        filters={"program_slug": "msc-artificial-intelligence"},
    )

    assert first_result.success_count == 1
    assert second_result.success_count == 1
    assert second_result.skipped_count == 0
    assert len(embedder.calls) == 2
    assert "updated overview text" in search_hits[0].document.lower()


def test_vector_build_service_persists_and_queries_with_real_chroma(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    _write_catalog(settings, _sample_catalog())
    _seed_raw_project(
        settings,
        school_slug="imperial",
        program_slug="msc-artificial-intelligence",
        pages=[
            {
                "page_type": "overview",
                "page_title": "MSc Artificial Intelligence",
                "source_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "markdown": "# MSc Artificial Intelligence\n## Course overview\nLearn machine learning systems and optimisation methods in depth.",
            }
        ],
    )

    loader_module = _load_module("app.extract.loader")
    repository_module = _load_module("app.vector.repository")
    service_module = _load_module("app.vector.service")

    catalog = loader_module.load_source_catalog(settings.source_catalog_path)
    programs = loader_module.select_programs(catalog, school_slug="imperial")
    repository = repository_module.ChromaVectorRepository(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.vector_collection_name,
    )
    embedder = FakeEmbedder()
    service = service_module.VectorStoreBuildService(
        settings=settings,
        embedder=embedder,
        repository=repository,
    )

    result = service.build_programs(programs, force=True)
    stored = repository.collection.get(include=["embeddings", "documents", "metadatas"])
    hits = repository.query(
        query_embedding=stored["embeddings"][0],
        top_k=1,
        filters={"school_slug": "imperial"},
    )

    assert result.success_count == 1
    assert repository.collection.count() >= 1
    assert "machine learning systems" in hits[0].document.lower()
