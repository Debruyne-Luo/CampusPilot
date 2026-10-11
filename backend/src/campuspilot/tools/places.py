"""Place lookup with category filter, returning map-ready cards."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, JsonValue

from campuspilot.contracts import Contract
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.presentation import place_card


class PlaceQuery(Contract):
    query: Annotated[str, Field(max_length=120)] = ""
    category: Annotated[str, Field(max_length=40)] | None = None


class PlaceCardsTool:
    name = "list_places"
    description = "列出已收录的校园地点卡片（可按名称或类别筛选），用于地图展示。"
    params_model: type[BaseModel] = PlaceQuery

    def __init__(self, repository: DirectoryRepository) -> None:
        self._repository = repository

    def run(self, params: Any) -> dict[str, JsonValue]:
        records = self._repository.search_place(params.query, params.category)
        return {
            "places": [place_card(p) for p in records],
            "sources": [s.model_dump(mode="json") for s in self._repository.evidence_for(records)],
        }
