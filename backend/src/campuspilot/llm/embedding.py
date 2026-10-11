"""Text embeddings via Cloudflare Workers AI (@cf/baai/bge-m3, 1024 dimensions).

Timeouts and bounded retries; a query LRU cache lets the synchronous retrieval path read
vectors prefetched asynchronously. Any failure raises EmbeddingUnavailable so callers can
degrade to BM25-only retrieval. Credentials never appear in repr, logs or errors.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_MODEL = "@cf/baai/bge-m3"
DIMENSIONS = 1024
MAX_BATCH = 50
MAX_TEXT_CHARS = 4000


class EmbeddingUnavailable(Exception):
    """Embedding provider failed; the message never contains credentials or input text."""


def _vectors(payload: Any, expected: int, dimensions: int) -> list[list[float]]:
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise EmbeddingUnavailable("invalid_response")
    result = payload.get("result")
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, list) or len(data) != expected:
        raise EmbeddingUnavailable("invalid_response")
    vectors: list[list[float]] = []
    for row in data:
        if not isinstance(row, list) or len(row) != dimensions:
            raise EmbeddingUnavailable("invalid_response")
        vector = [float(x) for x in row]
        if not all(math.isfinite(x) for x in vector):
            raise EmbeddingUnavailable("invalid_response")
        vectors.append(vector)
    return vectors


@dataclass
class CloudflareEmbedder:
    account_id: str = field(repr=False)
    api_token: str = field(repr=False)
    model: str = DEFAULT_MODEL
    dimensions: int = DIMENSIONS
    timeout: float = 4.0
    retries: int = 2
    cache_size: int = 512
    base_url: str = "https://api.cloudflare.com/client/v4"
    transport: httpx.BaseTransport | None = field(default=None, repr=False)
    async_transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    _cache: OrderedDict[str, list[float]] = field(default_factory=OrderedDict, repr=False)

    def __post_init__(self) -> None:
        if not self.account_id or not self.api_token:
            raise ValueError("Embedding credentials are not configured")
        if not self.account_id.replace("-", "").isalnum():
            raise ValueError("Invalid Cloudflare account identifier")

    @property
    def url(self) -> str:
        return f"{self.base_url}/accounts/{self.account_id}/ai/run/{self.model}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.api_token}

    @staticmethod
    def _key(text: str) -> str:
        return text.strip()[:MAX_TEXT_CHARS]

    def cached(self, text: str) -> list[float] | None:
        key = self._key(text)
        vector = self._cache.get(key)
        if vector is not None:
            self._cache.move_to_end(key)
        return vector

    def _remember(self, text: str, vector: list[float]) -> None:
        key = self._key(text)
        self._cache[key] = vector
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        cleaned = [self._key(t) for t in texts]
        if any(not t for t in cleaned):
            raise ValueError("Empty text cannot be embedded")
        return [cleaned[i : i + MAX_BATCH] for i in range(0, len(cleaned), MAX_BATCH)]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Blocking batch embedding (release builds, evaluation, tools run off-loop)."""
        out: list[list[float]] = []
        with httpx.Client(
            timeout=self.timeout, transport=self.transport, follow_redirects=False
        ) as client:
            for batch in self._batches(texts):
                for attempt in range(self.retries + 1):
                    try:
                        response = client.post(
                            self.url, headers=self._headers(), json={"text": batch}
                        )
                        if response.status_code == 200:
                            out.extend(_vectors(response.json(), len(batch), self.dimensions))
                            break
                        if response.status_code not in {429, 500, 502, 503, 504}:
                            raise EmbeddingUnavailable(f"http_{response.status_code}")
                    except (httpx.HTTPError, ValueError):
                        pass
                    if attempt == self.retries:
                        raise EmbeddingUnavailable("unavailable")
                    time.sleep(0.2 * (2**attempt))
        return out

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.async_transport, follow_redirects=False
        ) as client:
            for batch in self._batches(texts):
                for attempt in range(self.retries + 1):
                    try:
                        response = await client.post(
                            self.url, headers=self._headers(), json={"text": batch}
                        )
                        if response.status_code == 200:
                            out.extend(_vectors(response.json(), len(batch), self.dimensions))
                            break
                        if response.status_code not in {429, 500, 502, 503, 504}:
                            raise EmbeddingUnavailable(f"http_{response.status_code}")
                    except (httpx.HTTPError, ValueError):
                        pass
                    if attempt == self.retries:
                        raise EmbeddingUnavailable("unavailable")
                    await asyncio.sleep(0.2 * (2**attempt))
        return out

    def embed_query(self, text: str) -> list[float]:
        cached = self.cached(text)
        if cached is not None:
            return cached
        vector = self.embed([text])[0]
        self._remember(text, vector)
        return vector

    async def prefetch(self, text: str) -> list[float] | None:
        """Fill the cache for the sync retrieval path; returns None on provider failure."""
        cached = self.cached(text)
        if cached is not None:
            return cached
        try:
            vector = (await self.aembed([text]))[0]
        except (EmbeddingUnavailable, ValueError):
            return None
        self._remember(text, vector)
        return vector
