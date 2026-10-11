"""Tools: the permission-checked executor and the unified agent Tool interface.

`from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor` keeps working (the
former campuspilot/tools.py now lives in tools/executor.py). Concrete agent tools are
imported lazily to avoid import cycles with campuspilot.directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from campuspilot.tools.base import Tool, ToolError, ToolRegistry, tool_schema
from campuspilot.tools.executor import ReadOnlyPermissionPolicy, ToolExecutor

if TYPE_CHECKING:
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import KnowledgeStore

__all__ = [
    "ReadOnlyPermissionPolicy",
    "Tool",
    "ToolError",
    "ToolExecutor",
    "ToolRegistry",
    "default_registry",
    "tool_schema",
]


def default_registry(repository: DirectoryRepository, store: KnowledgeStore) -> ToolRegistry:
    from campuspilot.tools.directory import directory_agent_tools
    from campuspilot.tools.knowledge import KnowledgeSearchTool
    from campuspilot.tools.places import PlaceCardsTool

    return ToolRegistry(
        (
            *directory_agent_tools(repository),
            KnowledgeSearchTool(store),
            PlaceCardsTool(repository),
        )
    )
