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
    from campuspilot.llm.embedding import CloudflareEmbedder
    from campuspilot.rag import SnapshotStore

__all__ = [
    "ReadOnlyPermissionPolicy",
    "Tool",
    "ToolError",
    "ToolExecutor",
    "ToolRegistry",
    "agent_registry",
    "default_registry",
    "tool_schema",
]


def default_registry(
    repository: DirectoryRepository,
    store: KnowledgeStore,
    snapshots: SnapshotStore | None = None,
    embedder: CloudflareEmbedder | None = None,
) -> ToolRegistry:
    """search_knowledge uses hybrid snapshot retrieval when a snapshot store is given."""
    from campuspilot.tools.directory import directory_agent_tools
    from campuspilot.tools.knowledge import HybridKnowledgeTool, KnowledgeSearchTool
    from campuspilot.tools.places import PlaceCardsTool

    knowledge: Tool = (
        HybridKnowledgeTool(snapshots, embedder)
        if snapshots is not None
        else KnowledgeSearchTool(store)
    )
    return ToolRegistry(
        (
            *directory_agent_tools(repository),
            knowledge,
            PlaceCardsTool(repository),
        )
    )


def agent_registry(
    repository: DirectoryRepository,
    store: KnowledgeStore,
    snapshots: SnapshotStore | None = None,
    embedder: CloudflareEmbedder | None = None,
) -> ToolRegistry:
    """default_registry plus make_checklist: the agent loop's tool whitelist."""
    from campuspilot.tools.checklist import ChecklistTool

    base = default_registry(repository, store, snapshots, embedder)
    return ToolRegistry((*base.tools, ChecklistTool(repository)))
