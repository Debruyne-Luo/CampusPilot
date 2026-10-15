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
- CONFIRMED (2026-10-14): The user removed the mandatory Muse independent QA stage.
  Codex owns implementation, automated regression, source verification and security checks,
  and reports evidence directly to the Tech Lead. Historical documents assigning Muse a
  required QA/release gate are superseded; do not wait for Muse or dispatch work to it.
- Follow Issue → implementation and verification → PR when authorized → Tech Lead final
  review → Merge when authorized. Product-effect experiments can run before PR preparation.
- For important changes, test boundary/negative/adversarial behavior, identify the tested
  commit or base commit plus working-tree changes, and report passes, failures and limitations.
  Changed implementation requires relevant regression. The Tech Lead retains final
  architecture and merge authority and resolves disputed requirements.
- Official public sources may be collected, checked against their stated applicability, and
  adopted into `data/cdut` without asking the user to review every item. Record provenance,
  dates and limitations. Escalate only substantial uncertainty or unresolved contradictions
  after independent research. `official_document` means source adoption, not field inspection;
  do not relabel legacy records as human-verified. See [OPS](OPS.md).
- Update the smallest authoritative document affected; link to it instead of copying rules.
  Use the module handoff template in the development guide for transfers of ownership.

## Current repository stage

2026-10-13 user direction: deploy the handling checklist from its branch, without merging main,
then hand off desktop redesign from this released baseline. Live source is
`258ff205b73d6b2207d0234d26f04fcdec09134a`, release `r-994da5858c65`.
Read [the live baseline](docs/LIVE_BASELINE.zh-CN.md) before inferring deployment state from
older plans. Preserve this checklist behavior and saved-data compatibility during desktop redesign.
The earlier coordinate-conversion fix is isolated in another worktree and is not deployed.
The user reports mobile maps work; investigate the desktop issue separately before applying
a shared map change. Do not interpret this feedback as full device or navigation acceptance.

### Historical implementation stages

The approved Python Core Framework Skeleton uses synthetic mocks and in-memory state.
Issue #2 adds the approved three-service CDUT JSON inventory and isolated source-backed queries;
all real records remain needs_review. See data/cdut/README.md for source and review limitations.
Skeleton and Phase 1 implementation PRs are merged. Muse's reported QA baseline and remaining
source-review handoff are recorded in [OPS](OPS.md); implementation acceptance does not verify data.
The 2026-10-07 explicit user instruction approves the submission increment in ADR 0004:
FastAPI/plain web + Dify Cloud + Amap + lightweight VPS deployment preparation.
Preserve the older offline demo; public inventory additions remain needs_review. Live callbacks,
provider access and public deployment require real evidence; mock tests cannot establish them.
