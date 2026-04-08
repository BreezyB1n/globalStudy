from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.logging import get_logger

from app.crawl.firecrawl import FirecrawlClientError
from app.crawl.models import CrawlBatchResult, CrawlFailureRecord, CrawlTarget, ScrapeResult


class CrawlService:
    def __init__(self, *, settings: Settings, client) -> None:
        self.settings = settings
        self.client = client
        self.logger = get_logger("globalstudy.crawl")

    def crawl_targets(self, targets: list[CrawlTarget], force: bool) -> CrawlBatchResult:
        self.settings.ensure_runtime_directories()
        failures: list[CrawlFailureRecord] = []
        success_count = 0
        skipped_count = 0

        for target in targets:
            markdown_path, metadata_path = self._target_paths(target)
            if markdown_path.exists() and metadata_path.exists() and not force:
                skipped_count += 1
                continue

            try:
                if not self._is_valid_source_url(target.source_url):
                    raise CrawlValidationError("INVALID_URL", f"Invalid source URL: {target.source_url}")
                result = self.client.scrape(target.source_url)
                normalized_markdown = self._validate_result(target, result)
                self._write_success(target, result, normalized_markdown, markdown_path, metadata_path)
                success_count += 1
            except Exception as exc:  # noqa: BLE001
                failure = self._build_failure_record(target, exc)
                self._append_failure_log(failure)
                failures.append(failure)

        return CrawlBatchResult(
            total_count=len(targets),
            success_count=success_count,
            failure_count=len(failures),
            skipped_count=skipped_count,
            failures=failures,
        )

    def _target_paths(self, target: CrawlTarget) -> tuple[Path, Path]:
        output_dir = self.settings.raw_data_dir / target.school_slug / target.program_slug
        output_dir.mkdir(parents=True, exist_ok=True)
        return (
            output_dir / f"{target.page_type}.md",
            output_dir / f"{target.page_type}.meta.json",
        )

    def _validate_result(self, target: CrawlTarget, result: ScrapeResult) -> str:
        if result.http_status and result.http_status >= 400:
            raise CrawlValidationError("PAGE_NOT_FOUND", f"Source page returned HTTP {result.http_status}")

        if not self._is_same_or_subdomain(target.source_url, result.final_url):
            raise CrawlValidationError(
                "DOMAIN_MISMATCH",
                f"Scrape redirected outside the source domain: {result.final_url}",
            )

        normalized_markdown = result.markdown.strip()
        if len(normalized_markdown) < self.settings.crawl_min_content_length:
            raise CrawlValidationError(
                "CONTENT_TOO_SHORT",
                "Scraped markdown is too short to be considered valid page content",
            )

        return normalized_markdown

    def _write_success(
        self,
        target: CrawlTarget,
        result: ScrapeResult,
        markdown: str,
        markdown_path: Path,
        metadata_path: Path,
    ) -> None:
        fetched_at = datetime.now().astimezone().isoformat()
        content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        metadata = {
            "school_slug": target.school_slug,
            "school_name": target.school_name,
            "program_slug": target.program_slug,
            "program_name": target.program_name,
            "page_type": target.page_type,
            "page_title": result.page_title,
            "source_url": target.source_url,
            "final_url": result.final_url,
            "fetched_at": fetched_at,
            "content_hash": f"sha256:{content_hash}",
            "status": "success",
            "http_status": result.http_status,
        }
        markdown_path.write_text(markdown, encoding="utf-8")
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_failure_record(self, target: CrawlTarget, exc: Exception) -> CrawlFailureRecord:
        if isinstance(exc, CrawlValidationError):
            failure_reason = exc.failure_reason
            message = exc.message
        elif isinstance(exc, FirecrawlClientError):
            failure_reason = "FIRECRAWL_REQUEST_FAILED"
            message = str(exc)
        else:
            failure_reason = "UNEXPECTED_ERROR"
            message = str(exc)

        self.logger.warning(
            "Failed to crawl school=%s program=%s page=%s reason=%s",
            target.school_slug,
            target.program_slug,
            target.page_type,
            failure_reason,
            extra={"request_id": "-"},
        )
        return CrawlFailureRecord(
            school_slug=target.school_slug,
            program_slug=target.program_slug,
            page_type=target.page_type,
            source_url=target.source_url,
            failure_reason=failure_reason,
            message=message,
            attempted_at=datetime.now().astimezone().isoformat(),
        )

    def _append_failure_log(self, failure: CrawlFailureRecord) -> None:
        log_path = self.settings.crawl_failure_log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(failure.model_dump_json(ensure_ascii=False))
            handle.write("\n")

    @staticmethod
    def _is_same_or_subdomain(source_url: str, final_url: str) -> bool:
        source_host = CrawlService._normalize_host(urlparse(source_url).hostname or "")
        final_host = CrawlService._normalize_host(urlparse(final_url).hostname or "")
        if not source_host or not final_host:
            return False
        return (
            final_host == source_host
            or final_host.endswith(f".{source_host}")
            or source_host.endswith(f".{final_host}")
        )

    @staticmethod
    def _is_valid_source_url(source_url: str) -> bool:
        parsed = urlparse(source_url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)

    @staticmethod
    def _normalize_host(host: str) -> str:
        if host.startswith("www."):
            return host[4:]
        return host


class CrawlValidationError(Exception):
    def __init__(self, failure_reason: str, message: str) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason
        self.message = message
