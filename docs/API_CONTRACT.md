# API and domain contract proposals

**Status: PROPOSED.** These are framework-independent responsibilities and field proposals,
not implemented APIs, approved wire schemas, or a choice of HTTP/REST/streaming transport.
The architecture boundaries are [CONFIRMED](ARCHITECTURE.md); contract details need review
before the Skeleton. No endpoint, authentication protocol, or persistence engine is selected.

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
