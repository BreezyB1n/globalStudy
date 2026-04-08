from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import ThirdPartyServiceError


class BailianEmbeddingError(ThirdPartyServiceError):
    code = "BAILIAN_EMBEDDING_FAILED"


class BailianEmbeddingClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_ms: int,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_ms = timeout_ms
        self.http_client = http_client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        normalized_inputs = [text.strip() for text in texts]
        if not normalized_inputs or any(not text for text in normalized_inputs):
            raise BailianEmbeddingError("Embedding input must contain only non-empty text")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": normalized_inputs,
        }

        client = self.http_client or httpx.Client(timeout=self.timeout_ms / 1000)
        should_close = self.http_client is None
        try:
            response = client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise BailianEmbeddingError(f"Bailian embedding request failed: {exc}") from exc
        finally:
            if should_close:
                client.close()

        return _extract_embeddings(response.json())


def build_bailian_embedder(settings: Settings) -> BailianEmbeddingClient:
    return BailianEmbeddingClient(
        api_key=settings.bailian_api_key,
        base_url=settings.bailian_base_url,
        model=settings.bailian_embedding_model,
        timeout_ms=settings.bailian_timeout_ms,
    )


def _extract_embeddings(body: dict[str, Any]) -> list[list[float]]:
    raw_items = body.get("data")
    if not isinstance(raw_items, list) or not raw_items:
        raise BailianEmbeddingError("Bailian embedding response did not contain data")

    ordered_items = sorted(raw_items, key=lambda item: int(item.get("index", 0)))
    embeddings: list[list[float]] = []
    for item in ordered_items:
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise BailianEmbeddingError("Bailian embedding response contained an invalid embedding")
        embeddings.append([float(value) for value in embedding])
    return embeddings

