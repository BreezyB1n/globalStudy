from pathlib import Path

import pytest


@pytest.fixture
def app_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env = {
        "APP_NAME": "GlobalStudy AI",
        "APP_ENV": "dev",
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "8000",
        "LOG_LEVEL": "INFO",
        "BAILIAN_API_KEY": "test-bailian-key",
        "BAILIAN_BASE_URL": "https://example.com/bailian",
        "BAILIAN_CHAT_MODEL": "qwen-plus",
        "BAILIAN_EMBEDDING_MODEL": "text-embedding-v3",
        "BAILIAN_TIMEOUT_MS": "60000",
        "FIRECRAWL_API_KEY": "test-firecrawl-key",
        "SQLITE_PATH": "data/sqlite/app.db",
        "CHROMA_PERSIST_DIR": "data/chroma",
        "RAW_DATA_DIR": "data/raw",
        "PROCESSED_DATA_DIR": "data/processed",
        "PROJECTS_SNAPSHOT_PATH": "data/processed/projects.json",
        "EXTRACTION_FAILURE_LOG_PATH": "logs/extract_failures.jsonl",
        "VECTOR_COLLECTION_NAME": "program_knowledge_base",
        "VECTOR_CHUNK_SIZE": "900",
        "VECTOR_CHUNK_OVERLAP": "120",
        "VECTOR_EMBED_BATCH_SIZE": "10",
        "VECTOR_BUILD_FAILURE_LOG_PATH": "logs/vector_build_failures.jsonl",
        "CHAT_VECTOR_TOP_K": "4",
        "CHAT_CITATION_LIMIT": "4",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def crawl_app_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, str]:
    env = {
        "APP_NAME": "GlobalStudy AI",
        "APP_ENV": "test",
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "8000",
        "LOG_LEVEL": "INFO",
        "BAILIAN_API_KEY": "test-bailian-key",
        "BAILIAN_BASE_URL": "https://example.com/bailian",
        "BAILIAN_CHAT_MODEL": "qwen-plus",
        "BAILIAN_EMBEDDING_MODEL": "text-embedding-v3",
        "BAILIAN_TIMEOUT_MS": "60000",
        "FIRECRAWL_API_KEY": "test-firecrawl-key",
        "FIRECRAWL_BASE_URL": "https://api.firecrawl.dev",
        "FIRECRAWL_TIMEOUT_MS": "30000",
        "SQLITE_PATH": str(tmp_path / "sqlite" / "app.db"),
        "CHROMA_PERSIST_DIR": str(tmp_path / "chroma"),
        "RAW_DATA_DIR": str(tmp_path / "raw"),
        "PROCESSED_DATA_DIR": str(tmp_path / "processed"),
        "SOURCE_CATALOG_PATH": str(tmp_path / "processed" / "source_catalog.json"),
        "PROJECTS_SNAPSHOT_PATH": str(tmp_path / "processed" / "projects.json"),
        "CRAWL_FAILURE_LOG_PATH": str(tmp_path / "logs" / "crawl_failures.jsonl"),
        "CRAWL_MIN_CONTENT_LENGTH": "80",
        "EXTRACTION_FAILURE_LOG_PATH": str(tmp_path / "logs" / "extract_failures.jsonl"),
        "VECTOR_COLLECTION_NAME": "program_knowledge_base",
        "VECTOR_CHUNK_SIZE": "900",
        "VECTOR_CHUNK_OVERLAP": "120",
        "VECTOR_EMBED_BATCH_SIZE": "10",
        "VECTOR_BUILD_FAILURE_LOG_PATH": str(tmp_path / "logs" / "vector_build_failures.jsonl"),
        "CHAT_VECTOR_TOP_K": "4",
        "CHAT_CITATION_LIMIT": "4",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env
