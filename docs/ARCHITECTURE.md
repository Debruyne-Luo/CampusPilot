# Architecture and decision register

This is the canonical architecture status document. Product scope and source authority live in
[PRODUCT](PRODUCT.md); domain/interface proposals in [API_CONTRACT](API_CONTRACT.md); module
handoffs and development phases in the [Chinese guide](DEVELOPMENT_GUIDE.zh-CN.md).
The repository currently contains documentation only; no runtime control is implemented.

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
| Backend language/runtime/framework and package tools | OPEN | Agree before implementation; framework may be unnecessary for the Skeleton |
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

Technology choices are listed separately above. These unknowns do not authorize campus-data
collection, authentication, or infrastructure during documentation bootstrap.

## Next task: Core Framework Skeleton — PROPOSED, plan only

Goal: an empty but executable architecture with typed contracts and deterministic synthetic
fixtures. It must prove boundaries without choosing an Agent runtime or integrating real systems.

### Approval prerequisites

The Tech Lead must approve (1) implementation language and supported runtime version;
(2) package/dependency and test/type-check tooling; (3) a local execution entry point, such as a
small CLI/demo or test-driven entry point (HTTP framework only if explicitly chosen);
(4) the contract and behavior proposals in [API_CONTRACT](API_CONTRACT.md) and [SKILLS](SKILLS.md);
(5) deterministic fake ModelProvider/AgentHarness and in-memory SessionStore scope, explicitly
excluding durable recovery. A fake harness is a test double, not a selected production runtime.

No production model, database, frontend framework, GIS provider, MCP, container, or deployment
choice is needed for that limited scope. If the accepted scope requires one, stop and identify
the new decision before implementing it. The final Agent runtime remains OPEN.

### Proposed sequence

1. Open the bounded Skeleton Issue after approval; record approved technology choices separately.
2. Establish only the chosen minimal local execution/test setup and typed domain contracts.
3. Define ModelProvider, AgentHarness, SessionStore, Skill, SkillRegistry, ToolExecutor,
   PermissionDecision, Evidence, and TraceEvent boundaries.
4. Add deterministic test doubles and a static registry. Route every tool invocation through
   validation, permission checking, execution, and trace recording.
5. Add mock `search_service`, `find_office`, and `route_plan` Tools using unmistakably synthetic
   identifiers and `synthetic` evidence. Mock routes are fixtures, never navigation guidance.
6. Demonstrate service lookup → office lookup → route fixture with evidence and ordered traces.
   Use a scripted fake harness, with no real LLM or production orchestration loop.
7. Add meaningful contract, registry, permission, and trace tests; document executable commands
   only once those commands actually exist.
8. Human review → Muse independent QA → fixes/regression → Tech Lead acceptance and merge.

### Proposed acceptance checks

- One documented command or agreed test entry point runs locally and deterministically offline.
- Domain contracts do not import provider/runtime SDK types. No secrets or network are required.
- Duplicate Skill/Tool registration, unknown identifiers, and malformed inputs fail explicitly.
- Denied/unknown-risk operations never execute; denial and tool failures have observable traces.
- The three mocks return typed results and synthetic evidence; no fictitious record is presented
  as a real university service, office, coordinate, or route.
- Trace events correlate task/run/call and remain ordered; success, empty result, failure, and
  cancellation semantics are tested where the Skeleton contract exposes them.
- In-memory sessions demonstrate isolation and continuation, with no durability claim.
- No real writes or approval execution; a reserved future approval contract cannot enable actions.

Excluded: real university data, LLM integration, RAG, embeddings, vector databases, GIS/AMap,
YanhuyiBan authentication or automation, university SSO, real actions, multi-agent runtime,
and production deployment. This document authorizes none of that work.

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
