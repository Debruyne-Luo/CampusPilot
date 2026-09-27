# Engineering agent rules

CampusPilot's product and authority boundaries are defined in [PRODUCT](docs/PRODUCT.md),
its approved architecture and open decisions in [ARCHITECTURE](docs/ARCHITECTURE.md),
and practical module handoffs in the [Chinese development guide](docs/DEVELOPMENT_GUIDE.zh-CN.md).
Read the relevant contracts and accepted [ADRs](docs/adr/README.md) before changing a module.

## Authority and scope

- The human Product Owner / Tech Lead approves product scope and architecture, accepts work,
  and has merge authority. Coding agents must never merge changes themselves.
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
- Follow the Issue → short-lived branch → implementation → PR → human review → Muse QA
  → fixes/regression → Tech Lead merge workflow when publication is authorized.
- Muse independently validates behavior and operations. QA findings may propose design changes,
  but must not silently redesign the Agent core. The Tech Lead resolves disputed requirements.
- Update the smallest authoritative document affected; link to it instead of copying rules.
  Use the module handoff template in the development guide for transfers of ownership.

## Current repository stage

The approved Python Core Framework Skeleton uses synthetic mocks and in-memory state.
Issue #2 adds the approved three-service CDUT JSON inventory and isolated source-backed queries;
all real records remain needs_review. See data/cdut/README.md for source and review limitations.
The Phase 1 implementation awaits human Review and Muse independent QA.
Production capabilities and runtime selection remain OPEN; see ARCHITECTURE and ADR 0003.
Do not expand into real integrations or claim that mock tests establish production security.
