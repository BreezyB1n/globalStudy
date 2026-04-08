import importlib
import json
import sys
from types import SimpleNamespace


def _clear_modules() -> None:
    for module_name in (
        "app.core.config",
        "app.crawl.models",
        "app.crawl.catalog",
        "app.crawl.firecrawl",
        "app.crawl.service",
        "app.crawl.cli",
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
                    "url": "https://www.imperial.ac.uk/study/courses/postgraduate/artificial-intelligence/",
                },
                {
                    "page_type": "entry_requirements",
                    "url": "https://www.imperial.ac.uk/study/courses/postgraduate/artificial-intelligence/#entry-requirements",
                },
            ],
        }
    ]


def test_source_catalog_loads_and_filters_targets(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(
        json.dumps(_sample_catalog(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    catalog_module = _load_module("app.crawl.catalog")
    catalog = catalog_module.load_source_catalog(settings.source_catalog_path)
    targets = catalog_module.select_targets(
        catalog,
        school_slug="imperial",
        page_type="overview",
    )

    assert len(catalog) == 1
    assert len(targets) == 1
    assert targets[0].school_slug == "imperial"
    assert targets[0].program_slug == "msc-artificial-intelligence"
    assert targets[0].page_type == "overview"


def test_crawl_service_persists_markdown_and_metadata(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(json.dumps(_sample_catalog()), encoding="utf-8")

    catalog_module = _load_module("app.crawl.catalog")
    service_module = _load_module("app.crawl.service")
    models_module = _load_module("app.crawl.models")

    targets = catalog_module.select_targets(
        catalog_module.load_source_catalog(settings.source_catalog_path),
        school_slug="imperial",
        page_type="overview",
    )

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []

        def scrape(self, url: str):
            self.calls.append(url)
            return models_module.ScrapeResult(
                requested_url=url,
                final_url=url,
                page_title="Artificial Intelligence",
                markdown="# MSc Artificial Intelligence\nThis programme covers machine learning and statistics in depth.",
                http_status=200,
            )

    service = service_module.CrawlService(settings=settings, client=FakeClient())
    result = service.crawl_targets(targets, force=False)

    markdown_path = settings.raw_data_dir / "imperial" / "msc-artificial-intelligence" / "overview.md"
    metadata_path = settings.raw_data_dir / "imperial" / "msc-artificial-intelligence" / "overview.meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert result.total_count == 1
    assert result.success_count == 1
    assert result.failure_count == 0
    assert markdown_path.read_text(encoding="utf-8").startswith("# MSc Artificial Intelligence")
    assert metadata["page_title"] == "Artificial Intelligence"
    assert metadata["status"] == "success"
    assert metadata["content_hash"].startswith("sha256:")
    assert metadata["source_url"] == targets[0].source_url


def test_crawl_service_skips_existing_files_without_force(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(json.dumps(_sample_catalog()), encoding="utf-8")

    catalog_module = _load_module("app.crawl.catalog")
    service_module = _load_module("app.crawl.service")
    models_module = _load_module("app.crawl.models")
    targets = catalog_module.select_targets(catalog_module.load_source_catalog(settings.source_catalog_path), school_slug="imperial")

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def scrape(self, url: str):
            self.calls += 1
            return models_module.ScrapeResult(
                requested_url=url,
                final_url=url,
                page_title="Artificial Intelligence",
                markdown="# Artificial Intelligence\nDetailed course information that is safely above the validation threshold.",
                http_status=200,
            )

    client = FakeClient()
    service = service_module.CrawlService(settings=settings, client=client)
    first_result = service.crawl_targets(targets[:1], force=False)
    second_result = service.crawl_targets(targets[:1], force=False)

    assert first_result.success_count == 1
    assert second_result.skipped_count == 1
    assert client.calls == 1


def test_crawl_service_logs_failures_and_continues(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(json.dumps(_sample_catalog()), encoding="utf-8")

    catalog_module = _load_module("app.crawl.catalog")
    service_module = _load_module("app.crawl.service")
    models_module = _load_module("app.crawl.models")
    targets = catalog_module.select_targets(catalog_module.load_source_catalog(settings.source_catalog_path), school_slug="imperial")

    class FakeClient:
        def scrape(self, url: str):
            if url.endswith("#entry-requirements"):
                return models_module.ScrapeResult(
                    requested_url=url,
                    final_url=url,
                    page_title="Entry requirements",
                    markdown="Too short",
                    http_status=200,
                )
            return models_module.ScrapeResult(
                requested_url=url,
                final_url=url,
                page_title="Artificial Intelligence",
                markdown="# Artificial Intelligence\nThis programme covers machine learning, optimisation, and applied statistics in depth.",
                http_status=200,
            )

    service = service_module.CrawlService(settings=settings, client=FakeClient())
    result = service.crawl_targets(targets, force=False)

    failure_log_lines = settings.crawl_failure_log_path.read_text(encoding="utf-8").strip().splitlines()
    first_failure = json.loads(failure_log_lines[0])

    assert result.total_count == 2
    assert result.success_count == 1
    assert result.failure_count == 1
    assert first_failure["page_type"] == "entry_requirements"
    assert first_failure["failure_reason"] == "CONTENT_TOO_SHORT"
    assert first_failure["source_url"].endswith("#entry-requirements")


def test_crawl_service_allows_same_site_redirect_between_www_and_apex(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(json.dumps(_sample_catalog()), encoding="utf-8")

    catalog_module = _load_module("app.crawl.catalog")
    service_module = _load_module("app.crawl.service")
    models_module = _load_module("app.crawl.models")
    targets = catalog_module.select_targets(
        catalog_module.load_source_catalog(settings.source_catalog_path),
        school_slug="imperial",
        page_type="overview",
    )

    class FakeClient:
        def scrape(self, url: str):
            return models_module.ScrapeResult(
                requested_url=url,
                final_url="https://imperial.ac.uk/study/courses/postgraduate/artificial-intelligence/",
                page_title="Artificial Intelligence",
                markdown="# Artificial Intelligence\nThis programme covers machine learning, optimisation, and applied statistics in depth.",
                http_status=200,
            )

    service = service_module.CrawlService(settings=settings, client=FakeClient())
    result = service.crawl_targets(targets, force=False)

    assert result.success_count == 1
    assert result.failure_count == 0


def test_crawl_service_invalid_url_is_logged_without_breaking_batch(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog = _sample_catalog()
    catalog[0]["pages"][1]["url"] = "not-a-valid-url"
    settings.source_catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    catalog_module = _load_module("app.crawl.catalog")
    service_module = _load_module("app.crawl.service")
    models_module = _load_module("app.crawl.models")
    targets = catalog_module.select_targets(
        catalog_module.load_source_catalog(settings.source_catalog_path),
        school_slug="imperial",
    )

    class FakeClient:
        def scrape(self, url: str):
            return models_module.ScrapeResult(
                requested_url=url,
                final_url=url,
                page_title="Artificial Intelligence",
                markdown="# Artificial Intelligence\nThis programme covers machine learning, optimisation, and applied statistics in depth.",
                http_status=200,
            )

    service = service_module.CrawlService(settings=settings, client=FakeClient())
    result = service.crawl_targets(targets, force=False)
    failures = [
        json.loads(line)
        for line in settings.crawl_failure_log_path.read_text(encoding="utf-8").strip().splitlines()
    ]

    assert result.success_count == 1
    assert result.failure_count == 1
    assert failures[0]["failure_reason"] == "INVALID_URL"
    assert failures[0]["source_url"] == "not-a-valid-url"


def test_cli_filters_targets_and_passes_force_flag(crawl_app_env, monkeypatch):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    settings.source_catalog_path.parent.mkdir(parents=True, exist_ok=True)
    settings.source_catalog_path.write_text(json.dumps(_sample_catalog()), encoding="utf-8")

    cli_module = _load_module("app.crawl.cli")
    captured: dict[str, object] = {}

    class FakeService:
        def crawl_targets(self, targets, force: bool):
            captured["targets"] = targets
            captured["force"] = force
            return SimpleNamespace(
                total_count=len(targets),
                success_count=len(targets),
                failure_count=0,
                skipped_count=0,
            )

    monkeypatch.setattr(cli_module, "build_crawl_service", lambda settings: FakeService())

    exit_code = cli_module.main(
        ["--school", "imperial", "--page-type", "overview", "--force"],
    )

    assert exit_code == 0
    assert captured["force"] is True
    assert len(captured["targets"]) == 1
    assert captured["targets"][0].page_type == "overview"
