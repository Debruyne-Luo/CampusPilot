# Engineering agent rules

CampusPilot's product and authority boundaries are defined in [PRODUCT](docs/PRODUCT.md),
its approved architecture and open decisions in [ARCHITECTURE](docs/ARCHITECTURE.md),
and practical module handoffs in the [Chinese development guide](docs/DEVELOPMENT_GUIDE.zh-CN.md).
Read the relevant contracts and accepted [ADRs](docs/adr/README.md) before changing a module.

## Authority and scope

- The human Product Owner / Tech Lead approves product scope and architecture and retains
  final Review and Merge authority. On 2026-10-08 the user authorized direct adoption of clear
  official documents without per-record human confirmation; see PRODUCT's source policy.
  Coding agents and Muse must never merge changes themselves.
- Work from the assigned Issue and its allowed modification scope. Current user authorization
  takes precedence over this document; do not infer permission to commit, push, publish, or deploy.
- Preserve unrelated work. Report boundary changes before expanding an Issue's scope.
- Use decision labels exactly: **CONFIRMED**, **PROPOSED**, **DEFERRED**,
  **REJECTED FOR V1**, **OPEN**. A recommendation is not approval.
- ADRs record human-approved decisions only. Keep unresolved choices in the architecture
  decision register until approved; never silently select a runtime, framework, or provider.

## Durable implementation rules

- Preserve one primary Agent with modular Skills and a modular monolith. Engineering team
  roles are not runtime Agents; do not introduce a multi-agent product architecture.
- Keep domain contracts independent of model providers and orchestration frameworks.
- Keep document retrieval, structured data, GIS, integrations, and future actions separate.
- Skill instructions and model output cannot grant permissions. All executable tools must
  pass the application permission boundary; future sensitive actions require human approval.
- Preserve evidence and observable execution records. Never invent university facts, URLs,
  contacts, opening hours, locations, or routes. Explicit test fixtures must be unmistakably
  synthetic and must not impersonate real university records.
- Do not put credentials, private student data, production transcripts, or precise personal
  locations into repository files, fixtures, screenshots, or ordinary logs.
- Keep changes small and explain contract changes to upstream and downstream owners.
  Add dependencies or infrastructure only when the Issue and approved decisions justify them.

## Verification and handoff

- Run checks appropriate to the change. For documentation, check links, decision consistency,
  ownership, and scope. Do not initialize tooling solely to validate documentation.
- For implementation, test meaningful contracts and failure behavior, not only happy paths.
  Record commands, results, limitations, and unresolved risks in the PR or handoff.
- Follow the Issue → Codex / teammate implementation on a short-lived branch → PR
  → Muse independent QA / source verification (for real data) → Codex fixes
  → Muse regression → Tech Lead final review → Merge workflow when publication is authorized.
- Muse owns Independent QA + DataOps + Security Validation / Release Gate. For important PRs,
  use an independent environment, design boundary/negative/adversarial tests, lock the Tested
  Commit SHA, and report PASS / FAIL with blocking / non-blocking findings. Changed commits
  require regression; developer checks do not replace independent QA.
- Muse may organize QA tests, DataOps tools, and test scripts, but must report production bugs
  for Codex to fix, not modify core production code to make tests pass or unilaterally refactor Agent Core.
  The Tech Lead retains final architecture authority and resolves disputed requirements.
- Official public sources may be collected, checked against their stated applicability, and
  adopted into `data/cdut` without asking the user to review every item. Record provenance,
  dates and limitations. Escalate only substantial uncertainty or unresolved contradictions
  after independent research. `official_document` means source adoption, not field inspection;
  do not relabel legacy records as human-verified. See [OPS](OPS.md).
- Update the smallest authoritative document affected; link to it instead of copying rules.
  Use the module handoff template in the development guide for transfers of ownership.

## Current repository stage

The approved Python Core Framework Skeleton uses synthetic mocks and in-memory state.
Issue #2 adds the approved three-service CDUT JSON inventory and isolated source-backed queries;
all real records remain needs_review. See data/cdut/README.md for source and review limitations.
Skeleton and Phase 1 implementation PRs are merged. Muse's reported QA baseline and remaining
source-review handoff are recorded in [OPS](OPS.md); implementation acceptance does not verify data.
The 2026-10-07 explicit user instruction approves the submission increment in ADR 0004:
FastAPI/plain web + Dify Cloud + Amap + lightweight VPS deployment preparation.
Preserve the older offline demo; public inventory additions remain needs_review. Live callbacks,
provider access and public deployment require real evidence; mock tests cannot establish them.
