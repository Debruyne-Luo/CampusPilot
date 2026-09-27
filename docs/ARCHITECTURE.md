# Architecture and decision register

This is the canonical architecture status document. Product scope and source authority live in
[PRODUCT](PRODUCT.md); domain/interface proposals in [API_CONTRACT](API_CONTRACT.md); module
handoffs and development phases in the [Chinese guide](DEVELOPMENT_GUIDE.zh-CN.md).
The approved Python Skeleton is implemented locally with deterministic synthetic mocks;
human Review and Muse independent QA are pending. No production integration is implemented.

## Decision labels

| Label | Meaning |
| --- | --- |
| CONFIRMED | Explicitly approved by the human Product Owner / Tech Lead |
| PROPOSED | Recommendation requiring approval before adoption |
| DEFERRED | Potential future capability outside the current authorized scope |
| REJECTED FOR V1 | Excluded from v1; a change needs explicit human approval |
| OPEN | A choice or requirement is unresolved; no default is implicitly selected |

Only approved decisions enter [ADRs](adr/README.md). This register owns unresolved choices;
other documents link here rather than introducing competing decision lists.

## CONFIRMED direction

- Chengdu University of Technology is the pilot; public-information and read-only assistance
  defines v1. Authenticated personal data and real writes are deferred.
- One primary Agent uses modular Skills in a **modular monolith**.
- Model Provider and Agent / Harness are separate. The base LLM is replaceable.
- Retrieval/RAG, structured data, GIS, external integrations, and future actions remain
  separate capabilities. Not every request uses RAG.
- Begin with a static trusted Skill Registry and application-owned task/session state.
- Evidence/provenance, Trace/execution records, and Risk/Permission are explicit concerns.
- Sensitive future actions require human-in-the-loop approval.
- No foundation-model training for v1. Security boundaries must support later security work.
- GitHub records project history; the Tech Lead approves architecture and merges.

See [ADR 0001](adr/0001-pilot-and-v1-scope.md) and
[ADR 0002](adr/0002-architecture-boundaries.md) for the approved baseline.

## Capability boundaries

These responsibilities are CONFIRMED direction; interface details remain PROPOSED.
They are internal module boundaries, not separate services or mandatory directories.

| Boundary | Owns | Must not own |
| --- | --- | --- |
| API / frontend boundary | Input validation, session access, stable user-facing results | Provider SDK objects or client-side authorization as enforcement |
| Agent / Harness | Objective interpretation, Skill selection, bounded orchestration | Provider protocols, direct database/GIS/API access |
| Model Provider | Model requests/results, capability and error normalization | Campus authority, permissions, authoritative task state |
| Context / Session | Task progress and model-context assembly | Treating a model summary as approval or verified evidence |
| Skills / Registry | Versioned procedures and trusted capability descriptions | Self-granted permissions or autonomous secondary Agents |
| Tools / Executor | Validated operations, permission checks, structured results | Unrestricted code, arbitrary SQL, or arbitrary network destinations |
| Retrieval / RAG | Applicable document passages with source references | Universal routing for every question |
| Directory | Exact service, office, contact, faculty, and place records | Unsourced inferred university facts |
| GIS | Place resolution and routing over approved data | Invented paths, accessibility guarantees, or service policy |
| Integrations | Provider-specific translation and connection behavior | Deciding campus policy or bypassing tool permissions |
| Future Actions | Later preparation/execution/reconciliation of writes | Any enabled real write in current v1 scope |
| Permission / Approval | Access and operation decisions; future approval lifecycle | Allowing model/Skill text to confer authority |
| Evidence / Trace | Inspectable sources and observable execution history | Hidden reasoning as a required audit artifact |
| Evaluation / Tests | Task outcomes, contract correctness, failure behavior | Silently redefining product requirements |

PROPOSED call path: frontend → API → primary Agent/Harness → permission-checked Tool Executor
→ selected capability → typed result/evidence → Harness → API/frontend. The harness also uses
the model, registry, session, and trace contracts. A known exact contact can use Directory;
a policy explanation can use Retrieval; a route uses GIS. One task may combine them.

## PROPOSED state, evidence, and recovery semantics

- Separate conversation, task, run, tool call, and external operation identifiers. One active
  run owns a conversation initially; concurrent messages and cancellation have explicit ordering.
- Distinguish a run ending from a campus task being completed. Guidance or an official deep
  link can leave the task waiting for the user or university.
- Keep authoritative task state and evidence references outside compacted model context.
- Use a checkpoint and execution journal with an agreed committed position. A future durable
  store should commit state and its journal position consistently; no database is selected.
- Unfinished or inconsistent records are interrupted/unknown, not successful. Resume must not
  infer that an external operation is safe to repeat. Mock-only in-memory state is proposed for
  the Skeleton and provides no process-restart durability.
- Give tools explicit budgets, cancellation, typed failures, and retry rules. Retry only where
  the operation contract permits it. Future writes require idempotency/reconciliation design.
- Evidence identifies source, version, field/passage, applicability, update/retrieval/verification
  times, and reviewer status. Unknown values remain unknown; retrieval time is not freshness.
- DataOps proposes review and refresh processes; designated reviewers establish verification.
  A model cannot mark its own inference as verified. See [PRODUCT](PRODUCT.md) and [OPS](../OPS.md).
- Trace observable choices, policy decisions, redacted tool results, and failures. Keep evidence
  available through compaction; do not require private chain-of-thought or raw sensitive prompts.

## Technology disposition

| Item | Status | Boundary / reconsideration trigger |
| --- | --- | --- |
| Agent runtime: custom loop, LangGraph, or lightweight alternative | OPEN | Later ADR based on actual orchestration/recovery requirements; no preferred implementation is approved |
| Skeleton language and tools | CONFIRMED | Python 3.14, uv, Protocol, Pydantic 2, pytest, mypy strict, Ruff and CLI; [ADR 0003](adr/0003-python-skeleton-toolchain.md) |
| Backend Web framework / HTTP transport | OPEN | Not needed for the local Skeleton |
| Frontend technology | OPEN | Frontend owner and Tech Lead decide before UI scaffolding |
| Specific LLM provider/model | OPEN | Evaluate capability, quality, permitted data handling, latency, cost |
| Specific database/persistence engine | OPEN | Decide before durable state or data-store implementation |
| Specific GIS/map provider | OPEN | Decide from licensed data coverage and routing requirements |
| MCP | DEFERRED | An actual integration must justify the protocol |
| Embeddings / vector database | DEFERRED | Representative retrieval evaluation must justify them |
| Redis | DEFERRED | Demonstrated shared coordination or caching requirement |
| Docker | DEFERRED | Deployment/reproducibility requirements may justify it |
| Kubernetes / distributed event bus | DEFERRED | No approved v1 need; do not add infrastructure implicitly |
| Microservices / multi-agent product architecture | REJECTED FOR V1 | Conflicts with the approved monolith / single-primary-Agent baseline |
| Large embedded agent/RAG platform or dynamic plugin marketplace | PROPOSED | Recommendation is to exclude from v1; not a separately approved platform decision |
| Foundation-model training | REJECTED FOR V1 | Confirmed project constraint |

## Remaining OPEN requirements

1. Exact first services, corpus, authoritative source inventory, campus/site coverage, languages,
   and measurable acceptance thresholds; broad capability areas are already confirmed.
2. Approved source reviewers/data owners, refresh intervals, conflict escalation, and verification rules.
3. API transport, domain field/enumeration details, error model, and session/concurrency/recovery behavior.
4. User/session isolation, personal-input and location handling, retention/deletion, and logging access.
5. GIS data licensing, entrances, closures, accessibility coverage, and uncertainty presentation.
6. Performance/cost budgets, model capability requirements, and release gates.
7. Deployment environment, hosting/residency, secrets, backups, and operational objectives.
8. Real GitHub reviewer handles, repository permissions, branch protections, license, and visibility.

Technology choices are listed separately above. These unknowns do not authorize real data
collection, authentication or infrastructure during the Skeleton task.

## Core Framework Skeleton — implemented locally

The Tech Lead approved the Python toolchain and mock-only scope in
[ADR 0003](adr/0003-python-skeleton-toolchain.md). Actual commands live in [README](../README.md).
Python 3.14.7 and dependency versions are pinned; dependency installation succeeded without
changing Python minor version or the approved tools.

### Implemented path

CLI → FakeAgentHarness → FakeModelProvider → ToolExecutor → synthetic Tool → typed result.
The harness uses StaticSkillRegistry and InMemorySessionStore; the executor applies the
PermissionPolicy Protocol and writes to InMemoryExecutionJournal. Every successful result
carries synthetic Evidence. The single demonstration Skill requires service, office and route
results in that order. It produces synthetic guidance, never real-world completion.

The fake model chooses its next fixed response from the current run's typed results; it has no
LLM reasoning. Registry dependencies are checked at construction. Tool input/output validation
uses strict Pydantic records; Tool permissions cannot be changed through arguments.
Unknown Tools, unknown risk, restricted reads and writes are denied.

### State and failure semantics

- Frozen records and copy-on-read session snapshots preserve application-owned state.
- A session stores immutable run history and increments a revision on each recorded terminal run.
  Attempts have distinct run IDs even after failure. Reentrant runs on an active session fail.
- The implementation supports sequential local use, not thread-safe or distributed execution.
  Continuation means another run in the same session; partial-run checkpoint recovery is absent.
- A configurable step count bounds fake orchestration. Cancellation is checked between steps
  and after model responses. No hard execution timeout or forced mid-call cancellation exists.
- Journal sequence numbers provide deterministic ordering; wall-clock timestamps and global
  durable IDs are deferred. No raw objective, arguments, exception text, or reasoning is logged.
- Request/permission journal failure prevents Tool execution. Outcome journal failure propagates
  an explicit JournalError without reporting success. A failed final run record prevents the
  completed session update. State and journal are not a durable atomic transaction.
- The three mock Tools only return fixed synthetic fixtures or empty results. Missing evidence,
  validation errors, denials, provider/tool failures and step limits produce distinct outcomes.

See [API_CONTRACT](API_CONTRACT.md) for concrete local schema details and
[SKILLS](SKILLS.md) for the policy. Tests verify the offline demo, type contracts, registry
failures, permission non-execution, output validation, journal failure, isolation and cancellation.
Developer verification is not Muse QA or human acceptance.

### Remaining scope

Production Agent runtime remains OPEN. There is no real LLM, RAG, university data, database,
GIS/AMap, YanhuyiBan, authentication, write action, multi-agent runtime, MCP or deployment.
The Evidence and result models currently support synthetic fixtures only; a reviewed real-source
contract is required before Phase 1. No empty future capability directories have been created.

Next proposed Issue after Review: **Phase 1 Structured Campus Data — source inventory and
field contract**. First select a few public services, approved official sources, reviewers,
refresh policy, storage needs and acceptance cases. Do not ingest real data by inference.

## Research lineage (references, not dependencies)

The approved boundaries were informed by harness/context separation in
[Codex](https://developers.openai.com/blog/codex-as-a-platform), capability interfaces in
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md),
[Claude Code permissions](https://code.claude.com/docs/en/permissions),
[Pi's minimal core](https://pi.dev/), and
[OpenHands component boundaries](https://docs.openhands.dev/sdk/arch/design).
[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) inform recovery
questions; [Dify knowledge](https://docs.dify.ai/en/cloud/use-dify/knowledge/readme),
[RAGFlow](https://ragflow.io/docs/), and
[FastGPT citation inspection](https://doc.fastgpt.io/en/guide/chat/quoteList) inform data/evidence
questions. Sources were reviewed during planning on 2026-09-27; none selects a library or platform.
