"""Read-only management API; never imported by the production question route."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from campuspilot.chat_model import bounded_json, validate_endpoint
from campuspilot.dify import ChatUnavailable
from campuspilot.rag import canonical

VOLATILE = {"hit_count", "created_by", "updated_by", "disabled_by", "tokens", "word_count"}


def stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


@dataclass(frozen=True)
class DifyKnowledgeClient:
    api_key: str = field(repr=False)
    base_url: str = "https://api.dify.ai/v1"
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        validate_endpoint(self.base_url)
        if not self.api_key or any(c.isspace() for c in self.api_key):
            raise ValueError("Invalid knowledge API credential")

    async def export(self, dataset_ids: tuple[str, ...]) -> dict[str, Any]:
        if not dataset_ids or len(set(dataset_ids)) != len(dataset_ids) or len(dataset_ids) > 20:
            raise ValueError("Invalid dataset scope")
        for ident in dataset_ids:
            UUID(ident)
        try:
            async with asyncio.timeout(180):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    timeout=20,
                    follow_redirects=False,
                ) as client:
                    first = await self._snapshot(client, dataset_ids)
                    second = await self._snapshot(client, dataset_ids)
            if canonical(first) != canonical(second):
                raise ValueError("Dify changed during export; retry after editing stops")
            return first
        except (httpx.TimeoutException, TimeoutError):
            raise ChatUnavailable("upstream_timeout") from None
        except httpx.HTTPError:
            raise ChatUnavailable("upstream_unavailable") from None

    async def _get(self, client: httpx.AsyncClient, path: str) -> dict[str, Any]:
        result = await bounded_json(
            client,
            "GET",
            self.base_url.rstrip("/") + path,
            headers={"Authorization": "Bearer " + self.api_key},
        )
        if not isinstance(result, dict):
            raise ValueError("Invalid management response")
        return result

    async def _pages(self, client: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        ids: set[str] = set()
        for page in range(1, 102):
            value = await self._get(client, f"{path}?page={page}&limit=100")
            data = value["data"]
            if not isinstance(data, list) or len(rows) + len(data) > 10_000:
                raise ValueError("Management pagination limit")
            for row in data:
                UUID(row["id"])
                if row["id"] in ids:
                    raise ValueError("Duplicate paginated management ID")
                ids.add(row["id"])
                rows.append(row)
            if value["has_more"] is False:
                return sorted(rows, key=lambda r: r["id"])
            if not data:
                raise ValueError("Empty unfinished management page")
        raise ValueError("Management pagination limit")

    async def _snapshot(
        self, client: httpx.AsyncClient, dataset_ids: tuple[str, ...]
    ) -> dict[str, Any]:
        datasets = []
        for ident in sorted(dataset_ids):
            prefix = f"/datasets/{ident}"
            config = await self._get(client, prefix)
            metadata = await self._get(client, prefix + "/metadata")
            documents = []
            for row in await self._pages(client, prefix + "/documents"):
                docpath = prefix + "/documents/" + row["id"]
                detail = await self._get(client, docpath)
                # Listing carries activation/archive/index status on some API versions.
                # Conflicting fields cancel export; neither a missing field nor a detail
                # schema change may silently turn active content into excluded content.
                for key in ("id", "enabled", "archived", "indexing_status", "doc_form"):
                    if key in row and key in detail and row[key] != detail[key]:
                        raise ValueError("Document changed during export")
                    if key not in detail and key in row:
                        detail[key] = row[key]
                if any(key not in detail for key in ("enabled", "archived", "indexing_status")):
                    raise ValueError("Missing document activation state")
                segments = await self._pages(client, docpath + "/segments")
                if detail.get("doc_form") == "hierarchical_model":
                    for segment in segments:
                        segment["child_chunks"] = await self._pages(
                            client, docpath + "/segments/" + segment["id"] + "/child_chunks"
                        )
                documents.append({"detail": detail, "segments": segments})
            datasets.append(
                {"id": ident, "config": config, "metadata": metadata, "documents": documents}
            )
        return dict(stable(json.loads(canonical({"schema_version": 1, "datasets": datasets}))))
