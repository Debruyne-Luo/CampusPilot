"""Unified tool interface for the future agent loop.

Each tool declares a name, a description, a pydantic parameter model (its JSON schema is the
function-calling schema) and a read-only run(). Arguments are always validated before run().
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, JsonValue, ValidationError


class ToolError(Exception):
    """Raised for unknown tools or invalid arguments; never carries caller input back."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    params_model: type[BaseModel]

    def run(self, params: Any) -> dict[str, JsonValue]: ...


def tool_schema(tool: Tool) -> dict[str, JsonValue]:
    """OpenAI-compatible function description."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.params_model.model_json_schema(),
        },
    }


class ToolRegistry:
    def __init__(self, tools: tuple[Tool, ...]) -> None:
        names = [t.name for t in tools]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate tool name")
        self._tools = {t.name: t for t in tools}

    @property
    def tools(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def schemas(self) -> list[dict[str, JsonValue]]:
        return [tool_schema(t) for t in self._tools.values()]

    def call(self, name: str, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError("unknown_tool")
        try:
            params = tool.params_model.model_validate(arguments)
        except ValidationError:
            raise ToolError("invalid_arguments") from None
        return tool.run(params)
