# Product scope

**CONFIRMED:** Chengdu University of Technology (成都理工大学) is the first pilot
university. CampusPilot is a campus task-completion Agent. It helps a user move
from “I want to do something” to a verified procedure, responsible service,
required information, location, route, official source, and next action, as
applicable to that task.

Retrieval is one capability within this process. Finding a relevant passage
alone does not establish that the user has a usable next step or that a university
service has completed their request.

## V1 boundary

**CONFIRMED:** V1 provides public-information, read-only task assistance:

| Capability | Intended user outcome |
| --- | --- |
| Campus service discovery | Identify the responsible service and how to proceed |
| Official policy guidance | Explain applicable requirements with official evidence |
| Department / office lookup | Find the responsible organizational unit |
| Verified public contacts | Find a published, reviewed contact channel |
| Public faculty information | Find relevant publicly available faculty information |
| Campus place lookup | Resolve a campus place from maintained public information |
| Campus route planning | Provide a route supported by available, approved map data |
| Multi-step task guidance | Track what is known, missing, completed, and still required |
| Official online-service deep links | Hand the user to the relevant official service |

These are approved capability areas, not implemented features. Their first
service set, data coverage, rollout order, and acceptance thresholds are **OPEN**.
An official deep link does not authorize CampusPilot to log in, automate the
destination, or submit anything on the user's behalf.

**DEFERRED:** Authenticated personal-data access and all real write actions,
including form submissions, application cancellations, record modifications,
payments, identity changes, and other sensitive or irreversible actions. Future
authorization requirements are in [SECURITY](SECURITY.md).

**REJECTED FOR V1:** A multi-agent product architecture and foundation-model
training. The approved component boundaries are in
[ARCHITECTURE](ARCHITECTURE.md); engineering team roles do not create runtime Agents.

## Source authority and applicability

**CONFIRMED:** Prefer sources in this order:

1. Official university systems and the university website.
2. Official administrative department websites.
3. Official school / college websites.
4. Manually verified project data with recorded provenance and reviewer.
5. Third-party maps or supporting data.

This hierarchy guides source selection; it is not an automatic conflict-resolution
algorithm. Determine the governing issuer and the source's campus, service,
audience, effective period, and other applicable scope. A department may be the
responsible issuer for a particular procedure. A newer timestamp alone does not
establish authority or repeal an applicable policy. Unresolved contradictions
require review and an explicit limitation in the user-facing guidance.

Third-party information must never silently override authoritative university
service information. Map geometry may support navigation without becoming the
authority for service eligibility, contacts, opening hours, or procedures.
Manual verification must identify what was checked and against which source;
it does not create institutional authority.

**OPEN:** The actual service corpus, approved source inventory, source owners,
public faculty fields, locations, contacts, opening hours, official URLs, GIS
coverage, and refresh thresholds. No record in this repository should imply that
these facts have already been collected or verified. Data review and publication
responsibilities are defined in [OPS](../OPS.md).

## Task outcomes and acceptance

**PROPOSED:** Evaluate a task by whether the user can take the next justified step:

- Clarify missing information that materially changes the applicable procedure.
- Connect the objective to applicable evidence, responsible service, and steps.
- Show source references and distinguish verified facts from unknown information.
- Give contacts, locations, routes, and official links only when supported.
- Preserve partial progress and explain failures, contradictions, or missing data.
- Distinguish guidance delivered, user action pending, and university resolution.

A route must disclose material unknowns such as unavailable entrance or
accessibility information; it must not imply that unverified access is available.
When evidence is insufficient, a supported handoff or a clear unresolved step is
preferable to an invented answer. Exact evaluation cases and release thresholds
remain **OPEN** and require Tech Lead approval.

## Delivery and decision ownership

**CONFIRMED:** The human Product Owner / Tech Lead controls product scope,
architecture approval, acceptance, and merge decisions. GitHub is the project's
single source of truth. The responsibility matrix and future delivery phases are
in the [Chinese development guide](DEVELOPMENT_GUIDE.zh-CN.md).

This bootstrap records decisions and contracts only. The Core Framework Skeleton
is a **PROPOSED** next task requiring separate approval; it must use clearly
synthetic fixtures and must not introduce real university data or integrations.
See the [architecture decision register](ARCHITECTURE.md) for unresolved choices
and the [ADR index](adr/README.md) for approved decisions.
