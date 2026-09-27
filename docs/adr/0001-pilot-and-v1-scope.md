# ADR 0001: Pilot university and v1 capability boundary

- Status: **CONFIRMED**
- Date: 2026-09-27
- Approving authority: human Product Owner / Tech Lead
- Approval evidence: explicit bootstrap instruction, [recorded here](README.md)

## Context

CampusPilot needs a bounded first deployment and a clear separation between helping users
complete campus tasks and performing sensitive operations on their behalf.

## Decision

Chengdu University of Technology is the first pilot. CampusPilot is a task-completion Agent.
V1 provides public-information and read-only assistance: service discovery, official policy
guidance, department/office lookup, verified public contacts, public faculty information,
place lookup, campus routes, multi-step guidance, and appropriate official online-service links.

Authenticated personal-data access and real writes are deferred, including submissions,
cancellations, record modifications, payments, and identity-related changes.

## Consequences

The university and capability boundary are approved; individual service records, actual sources,
maps, and acceptance thresholds are not supplied by this decision. Never invent them.
An official deep link does not imply authentication, automation, submission, or task resolution.
Future capability expansion requires a separate human-approved decision.

See [PRODUCT](../PRODUCT.md) for the maintained product definition. No runtime, provider,
database, or framework is selected here. No alternatives are presented as having been evaluated.
