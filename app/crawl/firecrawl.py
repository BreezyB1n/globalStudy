from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ThirdPartyServiceError

from app.crawl.models import ScrapeResult


class FirecrawlClientError(ThirdPartyServiceError):
    code = "FIRECRAWL_REQUEST_FAILED"


class FirecrawlClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_ms: int,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        self.http_client = http_client

    def scrape(self, url: str) -> ScrapeResult:
        payload = {
            "url": url,
            "onlyMainContent": True,
            "formats": ["markdown"],
            "blockAds": True,
            "storeInCache": True,
            "timeout": self.timeout_ms,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        client = self.http_client or httpx.Client(timeout=self.timeout_ms / 1000)
        should_close = self.http_client is None
        try:
            response = client.post(f"{self.base_url}/v1/scrape", headers=headers, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FirecrawlClientError(f"Firecrawl scrape failed for {url}: {exc}") from exc
        finally:
            if should_close:
                client.close()

        body = response.json()
        if not body.get("success"):
            raise FirecrawlClientError(f"Firecrawl scrape was not successful for {url}")

        data = _coerce_mapping(body.get("data"))
        metadata = _coerce_mapping(data.get("metadata"))
        return ScrapeResult(
            requested_url=url,
            final_url=str(metadata.get("sourceURL") or url),
            page_title=str(metadata.get("title") or ""),
            markdown=str(data.get("markdown") or ""),
            http_status=_coerce_status(metadata.get("statusCode")) or response.status_code,
            warning=str(data.get("warning") or "") or None,
        )


def build_firecrawl_client(settings: Settings) -> FirecrawlClient:
    return FirecrawlClient(
        api_key=settings.firecrawl_api_key,
        base_url=settings.firecrawl_base_url,
        timeout_ms=settings.firecrawl_timeout_ms,
    )


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _coerce_status(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None
