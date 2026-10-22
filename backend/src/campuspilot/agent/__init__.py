"""Agent loop: understand -> plan -> execute tools -> verify.

The synthetic skeleton harness formerly in campuspilot/agent.py lives in agent/skeleton.py;
`from campuspilot.agent import FakeAgentHarness, FakeModelProvider` keeps working. Imports
are lazy so campuspilot.chat_runtime can import agent.verify without cycles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from campuspilot.agent.skeleton import FakeAgentHarness as FakeAgentHarness
    from campuspilot.agent.skeleton import FakeModelProvider as FakeModelProvider


def __getattr__(name: str) -> object:
    if name in {"FakeAgentHarness", "FakeModelProvider"}:
        from campuspilot.agent import skeleton

        return getattr(skeleton, name)
    raise AttributeError(name)
