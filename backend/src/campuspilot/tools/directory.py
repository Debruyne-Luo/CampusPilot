"""Adapters exposing the source-backed directory tools through the unified Tool interface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, JsonValue

from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools
from campuspilot.places_discovery import DiscoveryQuery, PlaceDiscovery

DESCRIPTIONS = {
    "search_service": "按关键词查询校园办事事项（材料、步骤、办理地点与来源）。",
    "find_office": "按办公室 ID 查询办公室信息与来源。",
    "search_place": "按名称或教室编号查询校园地点，优先目录，未精确匹配时查询高德地图。",
    "search_teacher": "按姓名查询已收录的教师办公地点与来源。",
}


class DirectoryTool:
    """Wraps one existing directory tool; output is the tool's validated result or empty."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.name: str = inner.descriptor.tool_id
        self.description: str = DESCRIPTIONS.get(self.name, self.name)
        self.params_model: type[BaseModel] = inner.input_model

    def run(self, params: Any) -> dict[str, JsonValue]:
        result = self._inner.execute(params.model_dump(mode="json", exclude_none=True))
        if result is None:
            return {"status": "empty"}
        return {"status": "success", **result.model_dump(mode="json")}


class PlaceDiscoveryTool:
    name = "search_place"
    description = DESCRIPTIONS["search_place"]
    params_model: type[BaseModel] = DiscoveryQuery

    def __init__(self, discovery: PlaceDiscovery) -> None:
        self.discovery = discovery

    def run(self, params: Any) -> dict[str, JsonValue]:
        return self.discovery.search(params.query, params.category)


def directory_agent_tools(
    repository: DirectoryRepository, discovery: PlaceDiscovery | None = None
) -> tuple[DirectoryTool | PlaceDiscoveryTool, ...]:
    return tuple(
        PlaceDiscoveryTool(discovery)
        if discovery is not None and t.descriptor.tool_id == "search_place"
        else DirectoryTool(t)
        for t in directory_tools(repository)
    )
