# ADR 0003: Python Core Framework Skeleton

- Status: **CONFIRMED**
- Date: 2026-09-27
- Approving authority: human Product Owner / Tech Lead
- Approval evidence: explicit task instruction approving the CampusPilot Core Framework
  Skeleton technical plan and authorizing local implementation; no GitHub approval URL yet.

## Decision

Use Python 3.14, uv, typing.Protocol, Pydantic 2, pytest, mypy strict, Ruff, and a CLI/module
entry point. Use an in-memory SessionStore and execution journal, a static Skill Registry,
and deterministic Fake ModelProvider / Fake AgentHarness implementations.

The Skeleton includes typed contracts, permission-checked mock Tools, synthetic Evidence,
execution traces, and an offline demo. All mock data must be explicitly synthetic.
Stop and report Python 3.14 dependency incompatibility; do not switch language/version silently.

## Consequences

The implementation pins Python 3.14.7 and locks compatible package versions in uv.lock.
uv_build is uv's packaging backend for the local module; it is not an application framework.
The local CLI and test doubles do not select a production Agent runtime. The final runtime,
HTTP transport/framework, frontend, model provider, database and GIS provider remain OPEN.

No real university data, LLM, RAG, GIS/AMap, YanhuyiBan, authentication, writes, multi-agent,
MCP or deployment is included. This approval does not authorize commit, push or merge.
Human Review and Muse independent QA remain pending after developer verification.
