"""Official knowledge search through the unified Tool interface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, JsonValue

from campuspilot.knowledge import KnowledgeQuery, KnowledgeStore, campus_today


class KnowledgeSearchTool:
    name = "search_knowledge"
    description = "检索已收录的学校官方资料（按类别、对象、时效过滤），返回摘要与来源。"
    params_model: type[BaseModel] = KnowledgeQuery

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    def run(self, params: Any) -> dict[str, JsonValue]:
        response = self._store.response(params, campus_today())
        return {key: value for key, value in response.items()}  # type: ignore[misc]
