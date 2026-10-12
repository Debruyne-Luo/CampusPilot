"""Adapters exposing the source-backed directory tools through the unified Tool interface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, JsonValue

from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools

DESCRIPTIONS = {
    "search_service": "按关键词查询校园办事事项（材料、步骤、办理地点与来源）。",
    "find_office": "按办公室 ID 查询办公室信息与来源。",
    "search_place": "按名称查询已收录的校园地点（含坐标来源与核验状态）。",
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


def directory_agent_tools(repository: DirectoryRepository) -> tuple[DirectoryTool, ...]:
    return tuple(DirectoryTool(t) for t in directory_tools(repository))
