# API and domain contract proposals

## Backend runtime migration (2026-10-10, local implementation)

ADR 0005 confirms legacy, phase1, and phase2 modes. /api/chat retains answer, services,
teachers, places, excerpts, result_status and request_id. Backend results may additionally
include knowledge_version, validated source_ids and a controlled degraded_reason. Scores rank
passages and are not returned as confidence. Generated prose cannot create directory IDs,
coordinates, tools or permissions. Unknown citations are rejected before display.

POST /api/session returns runtime_mode and model_configured. In backend modes, configured
means local backend capabilities are ready; model_configured separately describes generation.
The one-hour in-memory expiry, session isolation, restart reset, per-session quota and shared
concurrency limit remain. Backend context contains at most eight turns and explicit user
conditions; a new matter removes irrelevant conditions. Switching modes starts a new session
and never imports Dify history. In phase1, each frozen Dify fallback starts a fresh upstream
conversation with bounded backend context. Phase2 constructs no Dify chat client and never
falls back to it. Details and acceptance status are in [migration delivery](RUNTIME_MIGRATION.zh-CN.md).

## Campus map/life increment (2026-10-09)

Public place records may include project retrieval `tags`. Source authority distinguishes
official CDUT pages, `map_provider` (credential-free HTTPS Amap POI references), and
`user_supplement` (attributed user message, null URL). These sources are not interchangeable;
shop/user information cannot establish official service policy. Review status is preserved.

`/api/chat` may return `answer_mode=campus_retrieval` for maintained entities, general card
replacement guidance and food/parcel discovery, with the same authoritative cards. Specific
policy questions continue through Dify. `nearby_kind` enables local recommendation controls.
Chat input accepts no personal coordinates. WGS84 fixes go only through the existing Amap
conversion proxy; the page compares distances without adding locations to Dify, storage or
transcripts. `nearby-origin` / `nearby-origin-result` retain source, origin, generation and
request ID checks. Distances refer to building/shop points and are approximate straight-line
distances; the existing walking-route flow determines the actual path.

## Implemented map discovery and foreground guidance (2026-10-08)

- No new chat/model tool. Provider POIs use transient `amap:poi:<id>` identifiers and selected
  map points use `map:point:<sequence>` only in the browser. They cannot replace `cdut:`
  business associations, official policy, room numbers, service locations or directory data.
- Same-origin iframe messages add `place-search`, `place-search-result`, `destination-pick`,
  `map-destination`, `poi-selection`, and `discovery-cancel`. Request revisions invalidate
  searches and detail callbacks. Latest pending searches run after map readiness.
  Every post-initialization message also carries a map-frame generation. Reloading only the
  iframe preserves chat while rejecting readiness/results from the previous document.
- SDK proxy adds only observed `v3/place/around` and `v3/place/detail`. Around search uses the
  fixed campus viewport centre, radius <=2000m, <=10 results/page and bounded page/keyword.
  Details require one bounded alphanumeric POI ID. Fixed upstream, credential overwrite,
  JSONP checks, time/size/rate limits and no-store continue to apply.
- `route-result` additionally includes GCJ02 `geometry` and vertex-index `step_ends` for
  progress matching. The existing distance/time/steps fields remain compatible.
- `guidance-start/update/follow/stop` and `guidance-position` carry route request and
  navigation revision IDs. Only the active route/navigation accepts updates. WGS84 fixes
  are converted with Amap, throttled to at most one conversion every six seconds and never
  included in `/api/chat`, storage or ordinary logs. See SECURITY for lifecycle controls.

## Implemented official knowledge increment (2026-10-08)

- `POST /api/knowledge/search` takes `{query, category, audience, period}`. Query is bounded
  to 2000 characters; category is all/guide/notice/event; audience is all/undergraduate/
  graduate/staff/alumni; period is all/current/week/registration/history. It requires the
  existing browser cookie, same origin and custom header. No upstream fetch or model call.
- Response includes `knowledge`, `answer`, `result_status`, `as_of`, `collected_on`,
  `answer_mode=official_retrieval`, empty legacy card arrays, and `request_id`. Time uses
  China UTC+8. Registration requires both start and deadline; unknown dates are not active.
- `POST /api/chat` handles supported public-guide/notice questions through this local retriever.
  Existing business questions still go to Dify. Only explicit references to the last result
  retain local context; unrelated business questions and session reset clear that context.
- `POST /api/session` additionally returns `knowledge_available`; `configured` still means
  that Dify is configured in legacy mode. Backend modes use the readiness contract above.
- `KnowledgeRecord` separates source publication/collection, applicability, registration and
  event dates. Sources are credential-free HTTPS CDUT URLs, or attributed WeChat article URLs.
  `adoption=official_document` records the user's direct-adoption policy, not manual verification.
- Knowledge locations use existing validated place IDs. Raw text never produces coordinates.
- See [source workflow and checks](KNOWLEDGE.zh-CN.md) for import/export and limitations.

**Status:** Architecture and Skeleton implementation scope are **CONFIRMED**. The local Python
contracts are implemented for human Review; the broader production API proposals below remain
**PROPOSED** except the bounded submission API below, confirmed by ADR 0004.
An optional local read-only HTTP pilot is implemented under the user's 2026-10-03 continuation
request; see [its concrete endpoints and error mapping](DIFY_API_SETUP.zh-CN.md).

## Confirmed submission increment (2026-10-07)

Browser GET `/api/places?q=&category=` and `/api/teachers?q=` return source-backed arrays.
POST `/v1/directory/places/search` and `/v1/directory/teachers/search` use the same snapshot,
SearchInput and permission boundary as service tools. Bearer authentication applies to all `/v1/*`.
POST `/v1/directory/assist` accepts `kind` (service/teacher/place/unknown), bounded `query`,
`service_key`, `audience` and optional `academic_year`. No ID, URL or authority can be supplied.
It returns status/message, services/teachers/places arrays, department, evidence and trace;
multiple matches are needs_clarification candidates. Unknown/failure responses have no places.
The existing `/v1/directory/lookup` remains compatible with an additive places array and replacement key.
Machine schema: [OpenAPI](dify-directory.openapi.json).

CampusPlace separates its official field evidence from optional MapPosition: coordinates,
GCJ02/WGS84, provider/onsite source URL, retrieved date, review state, reviewer/date and limitations.
CampusTeacher preserves name, department, optional campus/office/place_id and official profile.
Teacher-place associations require a matching explicit campus; service steps use optional place_ids.
Missing fields remain null. Real directory records remain needs_review.

The structured Dify answer is exactly a JSON AnswerEnvelope: schema_version=1, status, answer,
service_ids, teacher_ids, place_ids. The model provides prose only. Deterministic workflow Code
derives IDs from authenticated HTTP results; Python rejects unknown IDs and unrelated place links.
The frontend receives resolved cards and never extracts coordinates from prose. Non-success
responses contain no IDs, except needs_clarification may carry candidates. Unavailable becomes
a controlled error. Old RAG mode returns text with empty card arrays.

**CONFIRMED (2026-10-09):** CampusService adds optional `summary`, and service/step modes
accept `in_person`. Resolved browser service cards and `/api/catalog` add source-backed
`source_links` and office `contacts`. General how/where queries can use the adopted complete
short guide; specific fee/time/material questions keep the workflow answer.
Single-teacher office queries use the recorded room, or explicitly report a missing office,
without inventing an unlinked map invitation. Other teacher questions keep the workflow answer.
Chat keeps its answer visible and opens the map only after an explicit place choice; the earlier automatic
map selection rule below no longer applies to chat responses.

GET `/api/map-config` exposes only the public JS key and local proxy path. Security code stays
in the server-side fixed-host/path proxy. Only reviewed GCJ02 points receive an Amap navigation URL;
WGS84 is preserved as provenance without automatic conversion. External navigation opens a new tab.
Map SDK/tiles unavailable: directory and text cards remain usable.

**CONFIRMED (2026-10-08):** `/api/chat` additionally returns `result_status` from the validated
AnswerEnvelope; legacy unstructured replies use null. Frontend auto-selection requires success,
an unambiguous business result and exactly one associated place, not one geocoded candidate.
Embedded reference routes accept existing GCJ02 provider candidates without changing review
state or the external-navigation gate. Only transient browser GPS origins are converted from WGS84.
The map iframe accepts `route-request` (request_id, origin, destination_place_id), `route-clear`,
`route-pick` and `route-insets`; it reports `route-result` (status, distance/metres, time/seconds,
steps) and `route-origin`. Same-origin/source checks and request IDs discard stale results.
The destination must exist in the current map result set. SDK proxy additions are limited to
`v3/direction/walking` and `v3/assistant/coordinate/convert`, with finite coordinate validation,
bounded parameters, fixed upstream, server-owned credentials, existing rate/size/time limits
and `Cache-Control: no-store`. No new model tool or persisted route entity is introduced.

Production visitor password protection is at the HTTPS reverse proxy; tools use an independent token.
Same-origin browser POSTs, secure cookies, single worker and independent chat/tool quotas are
defined in [deployment](SUBMISSION_DEPLOY.zh-CN.md). Session reset works after process restart.
It does not provide student authentication or change the provider-independent domain contracts.
The subsequent [local web/chat pilot](WEB_DIFY_SETUP.zh-CN.md) adds `/api/session`,
`/api/session/reset`, `/api/chat` and `/api/catalog`. Its server owns Dify user/conversation
mapping; these routes do not accept client-supplied provider identities or tool authority.
The concrete local schema is in [contracts.py](../backend/src/campuspilot/contracts.py);
interfaces are in [interfaces.py](../backend/src/campuspilot/interfaces.py).

## Contract conventions

- IDs are opaque identifiers, not database keys or provider-specific objects exposed to clients.
- Separate caller-provided input from trusted execution context established by the application.
  A model must not provide its own identity, permission grant, or approval status.
- Results distinguish success, empty results, rejection, unsupported capability, cancellation,
  and execution failure. An empty directory result is not a provider outage.
- Errors carry a stable category, safe message, correlation ID, and retryability where meaningful.
  Raw exceptions, credentials, and private provider payloads stay out of user-facing results.
- Validate at module boundaries. Synthetic evidence is explicitly labeled and cannot pass as
  verified university information. Schemas and enum spellings remain OPEN.

## Domain records

| Record | Proposed minimum information | Invariant |
| --- | --- | --- |
| Task | task ID, objective, campus scope, supplied facts, missing inputs, progress, outcome | User assertions are distinguished from verified campus facts |
| Run | run/session/task IDs, execution status, budgets, start/end, current step | Run completion is distinct from real-world task completion |
| Session | session ID, permitted participant context, tasks, context references, state revision | No cross-session information leakage |
| ToolCall | call/run IDs, Tool ID/version, validated input, permitted execution context | Model input cannot create authority |
| ToolResult | call ID, outcome, typed data or error, evidence references, warnings | No fabricated success or source |
| PermissionDecision | allow/deny/pending outcome, reason, policy reference, operation scope | Unknown capability/risk fails closed; pending is not allow |
| Evidence | evidence/source IDs, title, source reference/URL, authority class, version, passage/field, applicability, timestamps, verification and synthetic flags | Absence of metadata is explicit; retrieved does not mean verified |
| TraceEvent | event ID/sequence, task/run/call references, type, time, component/version, safe result or error/evidence references | Observable execution record, not private chain-of-thought |

Evidence timestamps distinguish source update, retrieval, verification, and effective period.
Verification may reference a designated reviewer. Use [PRODUCT's source policy](PRODUCT.md)
for authority and conflicts, not a model-generated confidence score.

## Module interfaces

| Interface | Upstream input | Downstream output / behavior |
| --- | --- | --- |
| ModelProvider | Application messages, permitted Tool descriptions, generation constraints | Normalized model response, requested calls, usage/error; no direct execution |
| AgentHarness | Objective/message, task/session context, registered capabilities, limits | Progress, Tool requests, clarification, terminal run result |
| SessionStore | Permitted session reference, state/revision, context/evidence references | State load/update and explicit missing/conflict outcomes |
| Skill | Declared inputs, applicability, required Tools, completion criteria | Guidance for the primary Agent; optional bounded procedure definition |
| SkillRegistry | Trusted versioned Skill registrations and lookup request | Validated descriptors; duplicate/unknown/disabled outcomes |
| ToolExecutor | ToolCall plus trusted permission context | Validated, permission-checked ToolResult and correlated TraceEvents |
| Retrieval | Query, campus/audience/effective-date scope, permitted sources | Relevant passages and evidence, or empty/conflict/failure |
| Directory | Exact identifiers or search criteria for service/office/contact/faculty/place | Structured records with field-level evidence |
| Routing | Known places, route constraints, approved map dataset reference | Route result and source/constraint limitations, or unavailable |
| Integration adapter | Explicit registered operation and permitted inputs | Normalized external result/error with provenance |
| Permission policy | Tool metadata, operation/resource, trusted caller context | PermissionDecision; default denial for unregistered operations |
| Trace sink | Validated TraceEvent | Ordered observable record or explicit recording failure |

Provider-specific capabilities remain behind adapters. Unsupported tool calling or output
constraints must be visible, not silently approximated. Switching providers must preserve
domain contracts, although behavior and quality still need evaluation.

## Frontend / application boundary

Proposed logical operations: start or continue a task, obtain its current state, request
cancellation, inspect permitted evidence, and receive progress/results. These are not route names.

A response should distinguish guidance, clarification, unresolved facts, next actions, service
or place information, route data, source references, and task outcome. A route payload and a
source citation are structured data, not prose the frontend must reverse-engineer.

The frontend renders progress and uncertainty, and never treats a hidden/disabled button as
authorization enforcement. Session access must be checked at the backend boundary when the
real API exists. Deep links hand work to an official site; opening a link is not submission or
proof of completion. Credentials never pass through frontend domain contracts.

## Lifecycle and recovery

Proposed run states cover queued/running, waiting for input, future pending approval, completed,
failed, and cancelled. Task outcomes separately distinguish guidance delivered, user action
needed, and externally verified completion. Final names and transition rules are OPEN.

Continuation must preserve tool call/result pairing, selected Skill versions, evidence references,
and policy decisions. Session state is authoritative; model-context summaries are derived views.
Concurrent updates need a revision/ownership rule. Cancellation must not relabel an already
completed external effect as undone.

The Skeleton proposes in-memory sessions and a journal for deterministic continuation tests.
They do not survive process restart. Durable checkpoints, recovery, and external-operation
reconciliation require later design and cannot be claimed by mock tests.

## Future action / approval reservation

**DEFERRED:** real action APIs and approval execution. PROPOSED future records bind an approval
to the actor, action/operation ID, destination/resource, exact payload revision, expiry, and
policy context. Changed payloads or expired approvals require a new decision. Execution rechecks
authorization; approval cannot grant access to a resource the actor is not entitled to use.

Preparation, approval, execution, and reconciliation must be separate steps. Unknown external
outcomes are reconciled before retry. There is no claim of exactly-once external effects.
No real Action or approval bypass is enabled by reserving these fields.

## Skeleton contract examples and review gate

The planned `search_service`, `find_office`, and `route_plan` Tools use synthetic service/place
IDs and a fixed route fixture. They have no real campus data, live coordinates, network access,
or routing computation. Their exact inputs/outputs are approved with the Skeleton Issue.

Contract review must settle required/optional fields, status/error categories, invalid-input
behavior, session isolation, trace failure semantics, and mock risk policy. Muse should verify
both expected results and rejection paths. [SKILLS](SKILLS.md) owns execution rules;
[ARCHITECTURE](ARCHITECTURE.md) owns technology decisions and the next-task acceptance plan.

## Implemented local contract subset

- Strict, frozen Pydantic records reject extra fields and unintended input coercion. Collections
  use tuples where stored; the raw ToolCall arguments mapping is validated and copied before use.
- TaskRequest carries session/task IDs, an objective, Skill ID and max_steps (1–10; default 3).
  There is no user identity or authenticated API in this local program.
- RunResult statuses are completed/needs_input/failed/cancelled. Task outcome is only
  synthetic_guidance or unresolved; no real university completion status is emitted.
- ToolResult statuses are success/empty/denied/invalid/failed/cancelled. Only success carries
  data; unsuccessful non-empty outcomes require a safe error_code. No automatic retries occur.
- Synthetic service/office/route payloads require SyntheticEvidence. The Phase 1 extension below
  adds distinct source-backed result variants; neither origin can substitute for the other.
- PermissionDecision exposes allow/deny plus a reason. Pending approval remains a production
  proposal only. The application supplies ExecutionContext; model arguments cannot carry it.
- Session records retain terminal runs and evidence in one process. Missing IDs raise KeyError;
  duplicate sessions, active-run conflicts and incorrect run ownership raise SessionConflict.
- TraceEvent carries sequence and session/task/run/call IDs, component version, safe category
  and evidence IDs. Skill selection records ID/version. No timestamp or raw result copy is used.
  It is an observable journal, not a persistent replay engine.
- The synchronous Protocols are ModelProvider, AgentHarness, SessionStore, Skill, Tool,
  PermissionPolicy and ExecutionJournal. No provider SDK or orchestration framework is imported.

The demo completes three Tools with 12 events. Journal failures may leave an incomplete journal;
no recovery or atomic checkpoint guarantee is claimed. All mock data and CLI results identify
synthetic status. Public transport schemas, hard timeouts, async execution, privacy retention
and durable state remain OPEN. See ARCHITECTURE for the current implementation limits.

## Confirmed Phase 1 local contracts — Issue #2

The Tech Lead approved the three-service inventory and local implementation after Stage A review.
This extends local Python/CLI contracts only; it does not select an HTTP API or production Agent.

- `Evidence` is a discriminated union keyed by `synthetic`: SyntheticEvidence (`true`, status
  `synthetic`) and SourceEvidence (`false`, status `needs_review` or `verified`). Source authority
  is independent: official university / department / college. URLs, issuer, version, locator,
  applicability, access method and retrieval date are explicit. Unknown source dates remain null.
  `verified` requires reviewer/date metadata, but no automatic verification workflow exists.
- `FieldEvidence(field_path, evidence_ids, note)` uses record-relative dot paths, with numeric
  tuple indices, e.g. `availability.0`. Paths and references must resolve; all populated fact
  fields need coverage. Parent paths can cover a group from one passage. Project IDs are exempt;
  notes explain limitations rather than supplying unsourced facts. An unknown field may carry
  an empty reference list with an explanation; that is not evidence of absence.
- CampusService preserves name/aliases, department/office reference, audience, optional academic
  year, channels, required input categories/materials, conditional steps, availability, fees,
  limits and notes. CampusOffice represents a department; location/hours/contact may be null.
  Both are strictly real, immutable, use `cdut:` identifiers, and currently only accept
  `verification_status=needs_review`. A verified publication workflow remains OPEN.
- The repository checks IDs, official CDUT source hosts, office links, field paths and evidence
  references before exposing any snapshot. It performs no network access or writes.
- `search_service({query, academic_year?})` returns `directory_services` with a nonempty `matches`
  tuple. It searches names/aliases, returns every candidate in ID order, and preserves each
  record's scope. A supplied year excludes records restricted to other years. Unscoped records
  retain their source-age warnings. No match is `empty`, not a synthetic fallback.
- `find_office({office_id})` returns `directory_office` with an exact department record, or empty.
  Missing location remains null; no place ID, coordinates or route is invented.
- Both real results carry exactly the SourceEvidence referenced by returned fields and an
  unreviewed-guidance notice. Real CLI JSON exposes `verification_status=needs_review` on each
  record and source; a successful lookup is not a verified university fact.
- Shared campus records live in core `domain.py`; public result variants and ToolResult live
  in core `contracts.py`. Directory depends on Core, with no reverse implementation dependency.
- Real and synthetic application paths assemble separate executors. Each Tool's output schema
  and Evidence family are validated; fake RunResult cannot contain real payloads. ExecutionContext
  and ToolDescriptor have no `data_origin` field. Dataset selection is an assembly decision, not
  a general security boundary. Permission checks continue to use the allowlist and risk policy.

Compatibility impact: local callers constructing old `Evidence(...)` now construct
`SyntheticEvidence(...)`; its `verification` field is renamed `verification_status`. ToolResult's
discriminated union adds two real variants. Existing synthetic kinds and input keys remain;
SearchInput gains optional academic_year. CLI `demo` is unchanged. No deployed API migration is
claimed. Upstream real queries bypass the fake harness; downstream callers must inspect kind,
synthetic status, review state and missing fields. Regression coverage includes original demo,
permissions, trace, real lookup, ambiguity, missing facts, year scope and origin separation.
