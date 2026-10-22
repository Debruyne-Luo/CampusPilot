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

**CONFIRMED (2026-10-21, user-approved implementation plan):** Prioritize Chengdu-campus
undergraduate arrival and campus orientation, followed by continuing-student services. Give
the official entry for online services and the supported place for offline services. Default
answers are brief; preserve material conditions and expand materials, steps and saved
checklists only on request. Known entries and exact directory places can return directly;
insufficient, conflicting or time-sensitive evidence uses bounded web supplementation.
CampusPilot provides public guidance without logging in, paying or applying for the user.
The main interface has no laboratory entry or reading settings, and answers do not append
a fixed applicability notice; material business conditions remain part of the answer itself.
Harness² stays offline. Video recording, push, merge and production deployment are deferred.
See the [implementation handoff](STUDENT_EXPERIENCE.zh-CN.md) for behavior and measured limits.

**CONFIRMED (2026-10-17):** The knowledge-quality increment covers public Chengdu-campus and
university-wide guidance for enrolled undergraduate and graduate students. Directory entries,
partial guides and evidence-backed complete procedures have distinct completeness levels;
only explicit complete procedures create new step checklists. Historical evidence remains
archived, with no new history-query feature in this increment. See
[ADR 0007](adr/0007-knowledge-quality-and-recollection.md) for source governance and acceptance.

**CONFIRMED (2026-10-14):** The backend evidence increment adds chat access to transient
campus map places, Jev-controlled web supplementation and session-owned campus images.
Unique exact map matches offer a navigation card; uncertain candidates require selection.
User image text remains attributed input, never official policy. See
[ADR 0006](adr/0006-online-evidence-and-user-images.md) and
[implementation handoff](EVIDENCE_MEDIA.zh-CN.md) for limits and acceptance evidence.

**CONFIRMED (2026-10-08, latest user request):** Provide campus-map and task-assistant
spaces, improve mobile touch use, extend place interaction beyond the curated directory,
and address the gap between route planning and navigation. The current web increment adds
transient Amap POI discovery/map destinations and foreground walking guidance. Explicitly
starting guidance requests continuous browser location; leaving the foreground or assistant
mode pauses it. No personal location reaches Dify or durable storage. Provider discoveries
do not create faculty-office/service-machine associations. Native background navigation,
indoor/floor routing and verified campus entrances remain **DEFERRED**.

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

These are approved production capability areas, not implemented production features.
The local Skeleton demonstrates a synthetic service/office/route sequence. Issue #2 separately
approves three source-backed local directory queries; see the [inventory](../data/cdut/README.md).
The 2026-10-07 submission increment is **CONFIRMED** in
[ADR 0004](adr/0004-submission-web-map-and-dify.md): card replacement and faculty office lookup,
prioritizing the computer/network security college, with 15–25 selected place candidates and
3–5 faculty records. At least one current, confirmed office-to-building example and the card
replacement service point are required before claiming acceptance. See [status](SUBMISSION_STATUS.zh-CN.md).
An official deep link does not authorize CampusPilot to log in, automate the
destination, or submit anything on the user's behalf.

**CONFIRMED (2026-10-08):** The current increment adds query-result cards and embedded,
one-shot walking reference routes using Amap. The 14 provider-coordinate candidates may be
used without upgrading their review status. Missing faculty/card-machine locations do not block
this increment; their real business-location acceptance remains separate. Users explicitly choose
their current location, a catalogue origin or a map point. See ADR 0004 for the approved boundary.

**DEFERRED:** Authenticated personal-data access and all real write actions,
including form submissions, application cancellations, record modifications,
payments, identity changes, and other sensitive or irreversible actions. Future
authorization requirements are in [SECURITY](SECURITY.md).

**REJECTED FOR V1:** A multi-agent product architecture and foundation-model
training. The approved component boundaries are in
[ARCHITECTURE](ARCHITECTURE.md); engineering team roles do not create runtime Agents.

## Browser handling checklist

**CONFIRMED (2026-10-13, user-approved plan):** Students explicitly save a whole structured
service from a chat answer into a browser-local handling checklist. A compact entry opens the
list and service details in the existing assistant panel. Preparation checks are distinct from
the student's own “finished” record; finishing removes the item with a brief undo, with no
completion history. Same-service additions reuse the saved snapshot without overwriting
progress. Saved public instructions, applicability, sources and service-linked places remain
available after a new conversation. Storage is independent of the anonymous chat session.

**REJECTED FOR V1:** Account sync, custom task editing, deadlines and notification reminders
for this increment. No school-system write or verified institutional completion is introduced.
See the [implementation and verification handoff](HANDLING_CHECKLIST.zh-CN.md).

## Source authority and applicability

**CONFIRMED (2026-10-08, current policy):** The user explicitly authorizes direct use of
clear official files/pages found through research. No per-information human confirmation is
required. Check issuer, audience, campus and effective dates, retain the exact source, and
adopt supported facts. Ask the user only when substantial uncertainty or contradictory evidence
cannot be resolved independently and materially affects the outcome. Official WeChat articles
may be adopted when publisher identity is attributable to an official campus source.
The new knowledge inventory uses `adoption=official_document`; it does not imply on-site
inspection or live availability. Legacy `needs_review` metadata remains historical provenance,
not a queue requiring the user to approve each fact. This policy supersedes older per-item
approval gates in the Phase 1 documents. Architecture, merge and sensitive-action boundaries
remain as previously defined.

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

**CONFIRMED:** The first local inventory covers campus card loss reporting, graduate enrollment
proof, and 2026–2027 tuition electronic receipts. Source collection and inventory approval do not
mean that university facts are verified: all Phase 1 records remain `needs_review`.
**OPEN:** Additional corpus, ongoing source owners, missing locations/contacts/hours,
public faculty fields, GIS coverage, refresh thresholds and verified publication. Data review and publication
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

The Core Framework Skeleton technical plan is **CONFIRMED** and implemented locally
with synthetic fixtures. It introduces no real university integrations; the separately approved
Phase 1 adds a local public-data inventory pending source review and independent QA.
See [ADR 0003](adr/0003-python-skeleton-toolchain.md) for the original Skeleton scope.
See the [architecture decision register](ARCHITECTURE.md) for unresolved choices
and the [ADR index](adr/README.md) for approved decisions.
