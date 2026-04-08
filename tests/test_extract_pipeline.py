import importlib
import json
import sys
from pathlib import Path

import httpx


def _clear_modules() -> None:
    for module_name in (
        "app.core.config",
        "app.crawl.models",
        "app.crawl.catalog",
        "app.extract.models",
        "app.extract.loader",
        "app.extract.bailian",
        "app.extract.repository",
        "app.extract.service",
        "app.extract.cli",
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
                    "url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                },
                {
                    "page_type": "entry_requirements",
                    "url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/#entry-requirements",
                },
                {
                    "page_type": "fees",
                    "url": "https://www.imperial.ac.uk/study/fees-and-funding/tuition-fees/postgraduate-taught-fees/",
                },
            ],
        },
        {
            "school_slug": "oxford",
            "school_name": "University of Oxford",
            "country": "UK",
            "program_slug": "msc-advanced-computer-science",
            "program_name": "MSc Advanced Computer Science",
            "degree_type": "MSc",
            "pages": [
                {
                    "page_type": "overview",
                    "url": "https://www.ox.ac.uk/admissions/graduate/courses/msc-advanced-computer-science",
                }
            ],
        },
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
        markdown_path = output_dir / f"{page['page_type']}.md"
        metadata_path = output_dir / f"{page['page_type']}.meta.json"
        markdown_path.write_text(page["markdown"], encoding="utf-8")
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
                    "content_hash": f"sha256:{page['page_type']}",
                    "status": "success",
                    "http_status": 200,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _build_extraction(models_module, *, tuition: str, overview: str):
    field = models_module.ExtractedField
    return models_module.StructuredProjectExtraction(
        school_name=field(
            value="Imperial College London",
            evidence_text="Imperial College London",
            source_page_type="overview",
        ),
        school_country=field(value="UK", evidence_text="Imperial College London", source_page_type="overview"),
        program_name=field(
            value="MSc Artificial Intelligence",
            evidence_text="MSc Artificial Intelligence",
            source_page_type="overview",
        ),
        degree_type=field(value="MSc", evidence_text="MSc Artificial Intelligence", source_page_type="overview"),
        department=field(
            value="Department of Computing",
            evidence_text="Department of Computing",
            source_page_type="overview",
        ),
        study_mode=field(value="Full time", evidence_text="Study mode: Full-time", source_page_type="overview"),
        duration=field(value="1 year full-time", evidence_text="Duration: 1 year full-time", source_page_type="overview"),
        tuition=field(value=tuition, evidence_text=f"Tuition fee: {tuition}", source_page_type="fees"),
        application_deadline=None,
        language_requirement=field(
            value="IELTS 7.0 overall with 6.5 in all elements",
            evidence_text="You must hold IELTS 7.0 overall with 6.5 in all elements.",
            source_page_type="entry_requirements",
        ),
        academic_requirement=field(
            value="First-class degree in computing or a closely related subject",
            evidence_text="You should normally hold a first-class degree in computing or a closely related subject.",
            source_page_type="entry_requirements",
        ),
        overview=field(value=overview, evidence_text=overview, source_page_type="overview"),
    )


def test_extract_service_persists_sqlite_records_and_snapshot(crawl_app_env):
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
                "source_url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                "markdown": "# MSc Artificial Intelligence\nDepartment of Computing\nStudy mode: Full-time\nDuration: 1 year full-time\nLearn machine learning and intelligent systems.",
            },
            {
                "page_type": "entry_requirements",
                "page_title": "Entry requirements",
                "source_url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/#entry-requirements",
                "markdown": "# Entry requirements\nYou must hold IELTS 7.0 overall with 6.5 in all elements.\nYou should normally hold a first-class degree in computing or a closely related subject.",
            },
            {
                "page_type": "fees",
                "page_title": "Tuition fees",
                "source_url": "https://www.imperial.ac.uk/study/fees-and-funding/tuition-fees/postgraduate-taught-fees/",
                "markdown": "# Tuition fees\nTuition fee: £43,250",
            },
        ],
    )

    loader_module = _load_module("app.extract.loader")
    models_module = _load_module("app.extract.models")
    repo_module = _load_module("app.extract.repository")
    service_module = _load_module("app.extract.service")

    catalog = loader_module.load_source_catalog(settings.source_catalog_path)
    programs = loader_module.select_programs(catalog, school_slug="imperial")

    class FakeExtractor:
        def extract(self, bundle):
            assert bundle.program_slug == "msc-artificial-intelligence"
            assert len(bundle.pages) == 3
            return _build_extraction(
                models_module,
                tuition="£43,250",
                overview="This programme covers machine learning, optimisation, and intelligent systems.",
            )

    repository = repo_module.SQLiteProjectRepository(settings.sqlite_path)
    service = service_module.ProjectExtractionService(
        settings=settings,
        extractor=FakeExtractor(),
        repository=repository,
    )
    result = service.extract_programs(programs, force=False)

    project = repository.get_project("imperial", "msc-artificial-intelligence")
    source_pages = repository.list_source_pages("imperial", "msc-artificial-intelligence")
    tuition_evidence = repository.get_field_evidence(
        "imperial",
        "msc-artificial-intelligence",
        "tuition",
    )
    snapshot = json.loads(settings.projects_snapshot_path.read_text(encoding="utf-8"))

    assert result.total_count == 1
    assert result.success_count == 1
    assert result.failure_count == 0
    assert project is not None
    assert project.tuition == "£43,250"
    assert project.study_mode == "full-time"
    assert project.duration_months == 12
    assert len(source_pages) == 3
    assert tuition_evidence is not None
    assert tuition_evidence.evidence_text == "Tuition fee: £43,250"
    assert tuition_evidence.source_url.endswith("/postgraduate-taught-fees/")
    assert snapshot[0]["program_slug"] == "msc-artificial-intelligence"
    assert snapshot[0]["field_evidences"]["tuition"]["field_value"] == "£43,250"


def test_extract_service_allows_null_fields_and_overwrites_existing_rows(crawl_app_env):
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
                "source_url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                "markdown": "# MSc Artificial Intelligence\nDepartment of Computing\nStudy mode: Full-time\nDuration: 1 year full-time",
            },
            {
                "page_type": "entry_requirements",
                "page_title": "Entry requirements",
                "source_url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/#entry-requirements",
                "markdown": "# Entry requirements\nYou must hold IELTS 7.0 overall with 6.5 in all elements.",
            },
            {
                "page_type": "fees",
                "page_title": "Tuition fees",
                "source_url": "https://www.imperial.ac.uk/study/fees-and-funding/tuition-fees/postgraduate-taught-fees/",
                "markdown": "# Tuition fees\nTuition fee: £43,250",
            },
        ],
    )

    loader_module = _load_module("app.extract.loader")
    models_module = _load_module("app.extract.models")
    repo_module = _load_module("app.extract.repository")
    service_module = _load_module("app.extract.service")
    programs = loader_module.select_programs(
        loader_module.load_source_catalog(settings.source_catalog_path),
        school_slug="imperial",
    )

    responses = [
        _build_extraction(
            models_module,
            tuition="£43,250",
            overview="This programme covers machine learning and optimisation.",
        ),
        _build_extraction(
            models_module,
            tuition="£45,000",
            overview="This programme covers machine learning, robotics, and optimisation.",
        ),
    ]

    class FakeExtractor:
        def __init__(self) -> None:
            self.calls = 0

        def extract(self, bundle):
            response = responses[self.calls]
            self.calls += 1
            return response

    repository = repo_module.SQLiteProjectRepository(settings.sqlite_path)
    service = service_module.ProjectExtractionService(
        settings=settings,
        extractor=FakeExtractor(),
        repository=repository,
    )

    first_result = service.extract_programs(programs, force=False)
    second_result = service.extract_programs(programs, force=True)
    project = repository.get_project("imperial", "msc-artificial-intelligence")
    evidences = repository.list_field_evidences("imperial", "msc-artificial-intelligence")

    assert first_result.success_count == 1
    assert second_result.success_count == 1
    assert project is not None
    assert project.tuition == "£45,000"
    assert project.application_deadline is None
    assert project.overview == "This programme covers machine learning, robotics, and optimisation."
    assert len([item for item in evidences if item.field_name == "application_deadline"]) == 0
    assert len(repository.list_source_pages("imperial", "msc-artificial-intelligence")) == 3


def test_extract_service_backfills_high_frequency_fields_from_markdown_when_llm_misses_them(crawl_app_env):
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
                "page_title": "Artificial Intelligence MSc | Study | Imperial College London",
                "source_url": "https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                "markdown": "\n".join(
                    [
                        "# Artificial Intelligence",
                        "- ### Duration",
                        "#### 1 year",
                        "- ### Study mode",
                        "#### Full-time",
                        "- ### Fees",
                        "- #### £24,600 Home",
                        "- #### £46,000 Overseas",
                        "### Minimum entry standard",
                        "- #### First-Class Honours in Mathematics, Physics, Engineering or other degree with substantial Mathematics content",
                        "English language requirement",
                        "All candidates must demonstrate a minimum level of English language proficiency for admission to Imperial.",
                        "For admission to this course, you must achieve the **higher university requirement** in the appropriate English language qualification.",
                    ]
                ),
            }
        ],
    )

    loader_module = _load_module("app.extract.loader")
    models_module = _load_module("app.extract.models")
    repo_module = _load_module("app.extract.repository")
    service_module = _load_module("app.extract.service")
    programs = loader_module.select_programs(
        loader_module.load_source_catalog(settings.source_catalog_path),
        school_slug="imperial",
    )

    class FakeExtractor:
        def extract(self, bundle):
            field = models_module.ExtractedField
            return models_module.StructuredProjectExtraction(
                school_name=field(
                    value="Imperial College London",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                school_country=field(
                    value="UK",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                program_name=field(
                    value="MSc Artificial Intelligence",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                degree_type=field(
                    value="MSc",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                department=field(
                    value="Department of Computing",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                study_mode=field(
                    value="Full-time",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                duration=field(
                    value="1 year",
                    evidence_text="Artificial Intelligence MSc | Study | Imperial College London",
                    source_page_type="overview",
                ),
                tuition=None,
                application_deadline=None,
                language_requirement=None,
                academic_requirement=None,
                overview=None,
            )

    repository = repo_module.SQLiteProjectRepository(settings.sqlite_path)
    service = service_module.ProjectExtractionService(
        settings=settings,
        extractor=FakeExtractor(),
        repository=repository,
    )

    result = service.extract_programs(programs, force=True)
    project = repository.get_project("imperial", "msc-artificial-intelligence")
    tuition_evidence = repository.get_field_evidence("imperial", "msc-artificial-intelligence", "tuition")
    language_evidence = repository.get_field_evidence("imperial", "msc-artificial-intelligence", "language_requirement")
    academic_evidence = repository.get_field_evidence("imperial", "msc-artificial-intelligence", "academic_requirement")

    assert result.success_count == 1
    assert project is not None
    assert project.tuition == "£24,600 Home; £46,000 Overseas"
    assert project.language_requirement == "Higher university requirement in the appropriate English language qualification."
    assert project.academic_requirement == "First-Class Honours in Mathematics, Physics, Engineering or other degree with substantial Mathematics content"
    assert tuition_evidence is not None
    assert tuition_evidence.page_type == "overview"
    assert "£46,000 Overseas" in tuition_evidence.evidence_text
    assert language_evidence is not None
    assert "higher university requirement" in language_evidence.evidence_text.lower()
    assert academic_evidence is not None
    assert "First-Class Honours" in academic_evidence.evidence_text


def test_extract_service_logs_missing_raw_input_and_continues(crawl_app_env):
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
                "source_url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                "markdown": "# Overview\nStudy mode: Full-time",
            }
        ],
    )

    loader_module = _load_module("app.extract.loader")
    models_module = _load_module("app.extract.models")
    repo_module = _load_module("app.extract.repository")
    service_module = _load_module("app.extract.service")
    programs = loader_module.select_programs(
        loader_module.load_source_catalog(settings.source_catalog_path),
        crawl_all=True,
    )

    class FakeExtractor:
        def __init__(self) -> None:
            self.calls = 0

        def extract(self, bundle):
            self.calls += 1
            field = models_module.ExtractedField
            return models_module.StructuredProjectExtraction(
                school_name=field(
                    value="Imperial College London",
                    evidence_text="Imperial College London",
                    source_page_type="overview",
                ),
                school_country=field(value="UK", evidence_text="Imperial College London", source_page_type="overview"),
                program_name=field(
                    value="MSc Artificial Intelligence",
                    evidence_text="MSc Artificial Intelligence",
                    source_page_type="overview",
                ),
                degree_type=field(value="MSc", evidence_text="MSc Artificial Intelligence", source_page_type="overview"),
                department=None,
                study_mode=field(value="Full-time", evidence_text="Study mode: Full-time", source_page_type="overview"),
                duration=None,
                tuition=None,
                application_deadline=None,
                language_requirement=None,
                academic_requirement=None,
                overview=field(
                    value="This programme covers machine learning.",
                    evidence_text="This programme covers machine learning.",
                    source_page_type="overview",
                ),
            )

    extractor = FakeExtractor()
    repository = repo_module.SQLiteProjectRepository(settings.sqlite_path)
    service = service_module.ProjectExtractionService(
        settings=settings,
        extractor=extractor,
        repository=repository,
    )
    result = service.extract_programs(programs, force=False)
    failures = [
        json.loads(line)
        for line in settings.extraction_failure_log_path.read_text(encoding="utf-8").strip().splitlines()
    ]

    assert result.total_count == 2
    assert result.success_count == 1
    assert result.failure_count == 1
    assert extractor.calls == 1
    assert failures[0]["failure_reason"] == "RAW_INPUT_NOT_FOUND"
    assert failures[0]["program_slug"] == "msc-advanced-computer-science"


def test_bailian_client_uses_structured_request_and_parses_response(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()

    models_module = _load_module("app.extract.models")
    bailian_module = _load_module("app.extract.bailian")
    bundle = models_module.ProjectSourceBundle(
        school_slug="imperial",
        school_name="Imperial College London",
        school_country="UK",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
        pages=[
            models_module.RawSourcePage(
                page_type="overview",
                page_title="MSc Artificial Intelligence",
                source_url="https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                raw_file_path="/tmp/overview.md",
                content_hash="sha256:overview",
                fetched_at="2026-04-08T21:00:00+08:00",
                markdown="# MSc Artificial Intelligence\nDepartment of Computing\nStudy mode: Full-time",
            )
        ],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL("https://example.com/bailian/chat/completions")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "qwen-plus"
        assert payload["enable_thinking"] is False
        assert payload["response_format"]["type"] == "json_object"
        assert "json" in payload["messages"][0]["content"].lower()
        assert "overview" in payload["messages"][1]["content"]
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "school_name": {
                                        "value": "Imperial College London",
                                        "evidence_text": "Imperial College London",
                                        "source_page_type": "overview",
                                    },
                                    "school_country": {
                                        "value": "UK",
                                        "evidence_text": "Imperial College London",
                                        "source_page_type": "overview",
                                    },
                                    "program_name": {
                                        "value": "MSc Artificial Intelligence",
                                        "evidence_text": "MSc Artificial Intelligence",
                                        "source_page_type": "overview",
                                    },
                                    "degree_type": {
                                        "value": "MSc",
                                        "evidence_text": "MSc Artificial Intelligence",
                                        "source_page_type": "overview",
                                    },
                                    "department": {
                                        "value": "Department of Computing",
                                        "evidence_text": "Department of Computing",
                                        "source_page_type": "overview",
                                    },
                                    "study_mode": {
                                        "value": "Full-time",
                                        "evidence_text": "Study mode: Full-time",
                                        "source_page_type": "overview",
                                    },
                                    "duration": None,
                                    "tuition": None,
                                    "application_deadline": None,
                                    "language_requirement": None,
                                    "academic_requirement": None,
                                    "overview": {
                                        "value": "Machine learning programme.",
                                        "evidence_text": "Machine learning programme.",
                                        "source_page_type": "overview",
                                    },
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = bailian_module.BailianStructuredExtractor(
        api_key="test-bailian-key",
        base_url="https://example.com/bailian",
        model="qwen-plus",
        timeout_ms=60000,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    extraction = client.extract(bundle)

    assert extraction.department is not None
    assert extraction.department.value == "Department of Computing"
    assert extraction.overview is not None
    assert extraction.overview.value == "Machine learning programme."


def test_bailian_client_accepts_flat_json_response_shape(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    _ = config.get_settings()

    models_module = _load_module("app.extract.models")
    bailian_module = _load_module("app.extract.bailian")
    bundle = models_module.ProjectSourceBundle(
        school_slug="imperial",
        school_name="Imperial College London",
        school_country="UK",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
        pages=[
            models_module.RawSourcePage(
                page_type="overview",
                page_title="MSc Artificial Intelligence",
                source_url="https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                raw_file_path="/tmp/overview.md",
                content_hash="sha256:overview",
                fetched_at="2026-04-08T21:00:00+08:00",
                markdown="# MSc Artificial Intelligence\nDepartment of Computing\nStudy mode: Full-time",
            )
        ],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "school_name": "Imperial College London",
                                    "school_country": "UK",
                                    "program_name": "MSc Artificial Intelligence",
                                    "degree_type": "MSc",
                                    "overview": "Machine learning programme.",
                                    "school_slug": "imperial",
                                    "program_slug": "msc-artificial-intelligence",
                                    "page_type": "overview",
                                    "evidence_text": "MSc Artificial Intelligence | Faculty of Engineering | Imperial College London",
                                    "url": "https://www.imperial.ac.uk/computing/prospective-students/courses/pg/mai/",
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = bailian_module.BailianStructuredExtractor(
        api_key="test-bailian-key",
        base_url="https://example.com/bailian",
        model="qwen-plus",
        timeout_ms=60000,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    extraction = client.extract(bundle)

    assert extraction.school_name is not None
    assert extraction.school_name.value == "Imperial College London"
    assert extraction.school_name.source_page_type == "overview"
    assert extraction.school_name.evidence_text == "MSc Artificial Intelligence | Faculty of Engineering | Imperial College London"
    assert extraction.overview is not None
    assert extraction.overview.value == "Machine learning programme."


def test_bailian_client_falls_back_to_first_page_type_when_field_object_omits_source(crawl_app_env):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    _ = config.get_settings()

    models_module = _load_module("app.extract.models")
    bailian_module = _load_module("app.extract.bailian")
    bundle = models_module.ProjectSourceBundle(
        school_slug="imperial",
        school_name="Imperial College London",
        school_country="UK",
        program_slug="msc-artificial-intelligence",
        program_name="MSc Artificial Intelligence",
        degree_type="MSc",
        pages=[
            models_module.RawSourcePage(
                page_type="overview",
                page_title="Artificial Intelligence MSc | Study | Imperial College London",
                source_url="https://www.imperial.ac.uk/study/courses/postgraduate-taught/artificial-intelligence/",
                raw_file_path="/tmp/overview.md",
                content_hash="sha256:overview",
                fetched_at="2026-04-08T21:00:00+08:00",
                markdown="# Artificial Intelligence\n- Fees\n- Minimum entry standard",
            ),
            models_module.RawSourcePage(
                page_type="entry_requirements",
                page_title="MSc Artificial Intelligence | Faculty of Engineering | Imperial College London",
                source_url="https://www.imperial.ac.uk/computing/prospective-students/pg/mai/",
                raw_file_path="/tmp/entry.md",
                content_hash="sha256:entry",
                fetched_at="2026-04-08T21:00:00+08:00",
                markdown="# MSc Artificial Intelligence",
            ),
        ],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "school_name": {
                                        "value": "Imperial College London",
                                        "evidence_text": "Artificial Intelligence MSc | Study | Imperial College London",
                                    },
                                    "school_country": {
                                        "value": "UK",
                                        "evidence_text": "Artificial Intelligence MSc | Study | Imperial College London",
                                    },
                                    "program_name": {
                                        "value": "MSc Artificial Intelligence",
                                        "evidence_text": "Artificial Intelligence MSc | Study | Imperial College London",
                                    },
                                    "degree_type": {
                                        "value": "MSc",
                                        "evidence_text": "Artificial Intelligence MSc | Study | Imperial College London",
                                    },
                                    "tuition": {
                                        "value": "£46,000 Overseas",
                                        "evidence_text": "£46,000 Overseas",
                                    },
                                    "application_deadline": None,
                                    "language_requirement": None,
                                    "academic_requirement": None,
                                    "overview": None,
                                }
                            )
                        }
                    }
                ]
            },
        )

    client = bailian_module.BailianStructuredExtractor(
        api_key="test-bailian-key",
        base_url="https://example.com/bailian",
        model="qwen-plus",
        timeout_ms=60000,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    extraction = client.extract(bundle)

    assert extraction.school_name is not None
    assert extraction.school_name.source_page_type == "overview"
    assert extraction.tuition is not None
    assert extraction.tuition.source_page_type == "overview"


def test_extract_cli_filters_programs_and_passes_force_flag(crawl_app_env, monkeypatch):
    config = _load_module("app.core.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    _write_catalog(settings, _sample_catalog())

    cli_module = _load_module("app.extract.cli")
    observed: dict[str, object] = {}

    class FakeService:
        def extract_programs(self, programs, force: bool):
            observed["programs"] = programs
            observed["force"] = force
            return type(
                "ExtractionResult",
                (),
                {
                    "total_count": len(programs),
                    "success_count": len(programs),
                    "failure_count": 0,
                    "skipped_count": 0,
                },
            )()

    monkeypatch.setattr(cli_module, "build_extraction_service", lambda settings: FakeService())

    exit_code = cli_module.main(["--school", "imperial", "--force"])

    assert exit_code == 0
    assert observed["force"] is True
    assert len(observed["programs"]) == 1
    assert observed["programs"][0].school_slug == "imperial"
