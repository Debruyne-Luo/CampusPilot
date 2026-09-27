# ADR 0002: Single-Agent modular architecture and authority boundaries

- Status: **CONFIRMED**
- Date: 2026-09-27
- Approving authority: human Product Owner / Tech Lead
- Approval evidence: explicit bootstrap instruction, [recorded here](README.md)

## Context

Campus task assistance combines different information and capability types. The core must
remain understandable, traceable, and independent of a particular LLM or runtime framework.

## Decision

- Use one primary Agent with modular Skills in a modular monolith.
- Separate Model Provider from Agent / Harness; keep the base LLM replaceable.
- Keep RAG, structured data, GIS, external integrations, and future actions distinct.
- Start with a static trusted Skill Registry and application-owned task/session state.
- Make Evidence/provenance, Trace/execution records, and Risk/Permission explicit.
- Support future human-in-the-loop approval for sensitive actions.
- Prioritize authoritative university sources; third-party information must not silently
  override official university service information. [PRODUCT](../PRODUCT.md) defines the hierarchy.
- The Tech Lead retains product/architecture approval, acceptance, and merge authority.
  GitHub is the source of truth; Codex does not merge. Muse performs independent QA/Ops/DataOps
  and may not silently redesign the core during validation.

## Consequences and limits

These are responsibility boundaries, not separate services or a mandated package layout.
Detailed schemas and runtime implementation remain unresolved. In particular, no choice among
a custom loop, LangGraph, or another lightweight runtime has been made. Compare them in a later
ADR when orchestration requirements are concrete.

No framework, LLM provider, database, GIS provider, MCP, Redis, Docker, Kubernetes, or event bus
is authorized by this ADR. Microservices and a multi-agent product conflict with this v1 baseline.
The [architecture register](../ARCHITECTURE.md) tracks proposals and open choices.

This ADR does not assert that controls have been implemented, that comparative runtime trials
have occurred, or that the Core Framework Skeleton is authorized.
