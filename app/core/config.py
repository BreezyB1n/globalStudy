from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="GlobalStudy AI", validation_alias="APP_NAME")
    app_env: str = Field(default="dev", validation_alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", validation_alias="APP_HOST")
    app_port: int = Field(default=8000, validation_alias="APP_PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    bailian_api_key: str = Field(validation_alias="BAILIAN_API_KEY")
    bailian_base_url: str = Field(validation_alias="BAILIAN_BASE_URL")
    bailian_chat_model: str = Field(default="qwen-plus", validation_alias="BAILIAN_CHAT_MODEL")
    bailian_embedding_model: str = Field(
        default="text-embedding-v3",
        validation_alias="BAILIAN_EMBEDDING_MODEL",
    )
    bailian_timeout_ms: int = Field(default=60000, validation_alias="BAILIAN_TIMEOUT_MS")
    firecrawl_api_key: str = Field(validation_alias="FIRECRAWL_API_KEY")
    firecrawl_base_url: str = Field(
        default="https://api.firecrawl.dev",
        validation_alias="FIRECRAWL_BASE_URL",
    )
    firecrawl_timeout_ms: int = Field(default=30000, validation_alias="FIRECRAWL_TIMEOUT_MS")

    sqlite_path: Path = Field(validation_alias="SQLITE_PATH")
    chroma_persist_dir: Path = Field(validation_alias="CHROMA_PERSIST_DIR")
    raw_data_dir: Path = Field(validation_alias="RAW_DATA_DIR")
    processed_data_dir: Path = Field(validation_alias="PROCESSED_DATA_DIR")
    source_catalog_path: Path = Field(
        default=Path("data/processed/source_catalog.json"),
        validation_alias="SOURCE_CATALOG_PATH",
    )
    projects_snapshot_path: Path = Field(
        default=Path("data/processed/projects.json"),
        validation_alias="PROJECTS_SNAPSHOT_PATH",
    )
    crawl_failure_log_path: Path = Field(
        default=Path("logs/crawl_failures.jsonl"),
        validation_alias="CRAWL_FAILURE_LOG_PATH",
    )
    extraction_failure_log_path: Path = Field(
        default=Path("logs/extract_failures.jsonl"),
        validation_alias="EXTRACTION_FAILURE_LOG_PATH",
    )
    vector_build_failure_log_path: Path = Field(
        default=Path("logs/vector_build_failures.jsonl"),
        validation_alias="VECTOR_BUILD_FAILURE_LOG_PATH",
    )
    crawl_min_content_length: int = Field(
        default=80,
        validation_alias="CRAWL_MIN_CONTENT_LENGTH",
    )
    vector_collection_name: str = Field(
        default="program_knowledge_base",
        validation_alias="VECTOR_COLLECTION_NAME",
    )
    vector_chunk_size: int = Field(default=900, validation_alias="VECTOR_CHUNK_SIZE")
    vector_chunk_overlap: int = Field(default=120, validation_alias="VECTOR_CHUNK_OVERLAP")
    vector_embed_batch_size: int = Field(default=10, validation_alias="VECTOR_EMBED_BATCH_SIZE")
    chat_vector_top_k: int = Field(default=4, validation_alias="CHAT_VECTOR_TOP_K")
    chat_citation_limit: int = Field(default=4, validation_alias="CHAT_CITATION_LIMIT")

    @field_validator(
        "sqlite_path",
        "chroma_persist_dir",
        "raw_data_dir",
        "processed_data_dir",
        "source_catalog_path",
        "projects_snapshot_path",
        "crawl_failure_log_path",
        "extraction_failure_log_path",
        "vector_build_failure_log_path",
        mode="before",
    )
    @classmethod
    def coerce_path(cls, value: str | Path) -> Path:
        return Path(value)

    @field_validator("bailian_api_key", "firecrawl_api_key", mode="after")
    @classmethod
    def validate_secret_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or normalized.startswith("replace-with-your-"):
            raise ValueError("secret value must be configured with a real credential")
        return normalized

    @model_validator(mode="after")
    def resolve_relative_paths(self) -> "Settings":
        self.sqlite_path = self._resolve_path(self.sqlite_path)
        self.chroma_persist_dir = self._resolve_path(self.chroma_persist_dir)
        self.raw_data_dir = self._resolve_path(self.raw_data_dir)
        self.processed_data_dir = self._resolve_path(self.processed_data_dir)
        self.source_catalog_path = self._resolve_path(self.source_catalog_path)
        self.projects_snapshot_path = self._resolve_path(self.projects_snapshot_path)
        self.crawl_failure_log_path = self._resolve_path(self.crawl_failure_log_path)
        self.extraction_failure_log_path = self._resolve_path(self.extraction_failure_log_path)
        self.vector_build_failure_log_path = self._resolve_path(self.vector_build_failure_log_path)
        return self

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def frontend_dir(self) -> Path:
        return self.project_root / "frontend"

    def ensure_runtime_directories(self) -> None:
        directories = (
            self.raw_data_dir,
            self.processed_data_dir,
            self.sqlite_path.parent,
            self.chroma_persist_dir,
            self.logs_dir,
            self.source_catalog_path.parent,
            self.projects_snapshot_path.parent,
            self.crawl_failure_log_path.parent,
            self.extraction_failure_log_path.parent,
            self.vector_build_failure_log_path.parent,
        )
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.project_root / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
