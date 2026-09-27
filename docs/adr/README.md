# Architecture decision records

ADRs record decisions explicitly approved by the human Product Owner / Tech Lead. They do not
turn implementation recommendations into approved choices. Unresolved alternatives belong in
the [architecture decision register](../ARCHITECTURE.md), not an accepted ADR.

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-pilot-and-v1-scope.md) | CONFIRMED | Pilot university and public, read-only v1 scope |
| [0002](0002-architecture-boundaries.md) | CONFIRMED | Single Agent, modular monolith, capability and authority boundaries |

For a newly approved decision, record: date, status, approving authority, approval evidence,
context, decision, alternatives considered (only when actually reviewed), consequences, and
superseded ADRs if any. Link the approving GitHub Issue/PR when available. Do not invent a link,
reviewer handle, discussion, or implementation result.

The initial approval evidence is the human task instruction dated 2026-09-27, titled
"The architecture plan is approved with the amendments below." A GitHub approval link is
not yet available. Carry the approved baseline into the eventual human-reviewed bootstrap PR.
