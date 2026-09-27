# API and domain contract proposals

**Status:** Architecture and Skeleton implementation scope are **CONFIRMED**. The local Python
contracts are implemented for human Review; the broader production API proposals below remain
**PROPOSED**. No HTTP endpoint, authentication protocol, or persistence engine is selected.
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
