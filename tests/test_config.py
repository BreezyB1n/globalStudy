import importlib
import sys

import pytest


def _load_config_module():
    sys.modules.pop("app.core.config", None)
    return importlib.import_module("app.core.config")


def test_settings_resolve_relative_paths_to_project_root(app_env, project_root):
    config = _load_config_module()
    config.get_settings.cache_clear()

    settings = config.get_settings()

    assert settings.project_root == project_root
    assert settings.sqlite_path == project_root / "data/sqlite/app.db"
    assert settings.chroma_persist_dir == project_root / "data/chroma"
    assert settings.raw_data_dir == project_root / "data/raw"
    assert settings.processed_data_dir == project_root / "data/processed"
    assert settings.source_catalog_path == project_root / "data/processed/source_catalog.json"
    assert settings.projects_snapshot_path == project_root / "data/processed/projects.json"
    assert settings.crawl_failure_log_path == project_root / "logs/crawl_failures.jsonl"
    assert settings.extraction_failure_log_path == project_root / "logs/extract_failures.jsonl"
    assert settings.vector_build_failure_log_path == project_root / "logs/vector_build_failures.jsonl"
    assert settings.logs_dir == project_root / "logs"


def test_settings_require_bailian_api_key(app_env, monkeypatch):
    monkeypatch.setenv("BAILIAN_API_KEY", "")
    config = _load_config_module()
    config.get_settings.cache_clear()

    with pytest.raises(Exception) as exc_info:
        config.get_settings()

    assert "BAILIAN_API_KEY" in str(exc_info.value)
