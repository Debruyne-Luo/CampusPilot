# Operations and independent QA

**CONFIRMED:** Muse = Independent QA + DataOps + Security Validation / Release Gate;
later it also owns Agent Red Team work. The Tech Lead retains fact approval and final Review / Merge.
GitHub Issues, PRs, and repository documents are the project record.

The local Python Skeleton implements mock-tool permissions, synthetic evidence, an
in-memory journal and developer tests. It has no deployment, monitoring, backup or release
pipeline. Skeleton and Phase 1 implementation PRs are merged. Future operational procedures
below are not claims of production controls; run commands are in [README](README.md).

## Responsibilities

| Role | Operational responsibility |
| --- | --- |
| Muse | Independently test important PRs, review official sources in a browser, maintain QA/DataOps evidence, and perform security validation and release gate checks |
| Codex | Own primary implementation, supply developer verification and a reproducible handoff, structure approved data, and fix production bugs |
| Frontend teammate | Own Frontend & Product Experience, including UI/UX, map interaction, mobile usability and error states |
| ChatGPT | Support evaluation design, research, and technical review |
| Product Owner / Tech Lead | Own product, architecture and fact approval (including `verified` status), final Review, and Merge |

Muse may organize QA tests, DataOps tools, and test scripts, and propose architecture changes
through an Issue. Muse has no final architecture or Merge authority and must not unilaterally refactor
Agent Core or modify core production code to make QA pass. Report production bugs first;
Codex fixes them. Use the module handoff template in the
[development guide](docs/DEVELOPMENT_GUIDE.zh-CN.md); engineering rules are in
[AGENTS.md](AGENTS.md).

## Review and release workflow

Issue → Codex / teammate implementation on a short-lived branch → PR → Muse independent
QA / source verification (for real data) → Codex fixes → Muse regression
→ Tech Lead final review → Merge.

For important PRs, Muse uses an independent environment and actively designs boundary,
negative, and adversarial tests beyond reproducing developer checks. Record and lock the
**Tested Commit SHA** in the QA report; results apply only to that commit. After fixes or
other commit changes, Muse runs regression and records the newly tested SHA.

Every handoff identifies the allowed scope, acceptance criteria, relevant contracts,
environment, checks performed, results, known limitations, and unresolved findings.
Muse reports **PASS / FAIL** and **blocking / non-blocking findings**, with reproduction
steps and evidence in GitHub. Release gate validation does not grant Merge or deployment authority.
Unresolved acceptance failures return to the owner; disputed requirements go to the
Tech Lead. A merge is not deployment authorization.

For the Skeleton, validate links and decision consistency, run pytest/mypy/Ruff and the
offline demo, and independently challenge permission denial, invalid inputs/outputs, empty
results, journal failures and session isolation. Confirm every fixture is synthetic.
Developer results do not substitute for Muse QA; production checks remain not applicable.

Current handoff (2026-09-28): [Skeleton PR #1](https://github.com/Debruyne-Luo/CampusPilot/pull/1)
and [Phase 1 PR #3](https://github.com/Debruyne-Luo/CampusPilot/pull/3) are merged.
In the report supplied by the Tech Lead, Muse reports a golden eval baseline of **22/22 passing**
on Python 3.14.7, pinned to `554d7cb1c43f2c75c0576f179b6c71044254c75e`. Muse withdrew the
`tools.py:100` P0 report after identifying a Python 3.12 environment mismatch, reports adding
an interpreter-version gate, and updated an outdated fixture assertion from `verification`
to `verification_status`. This records Muse's report, not a local rerun or an archived QA artifact.
The runner, cases and report still need repository handoff; browser source-review evidence and
Tech Lead fact approval remain separate requirements. All three real records remain `needs_review`.

**PROPOSED** future release evidence, once implementation and an environment exist:

- Contract and task acceptance results, failure-path checks, and regression results.
- Evidence support, freshness, source applicability, and missing/conflicting-data cases.
- Permission-denial behavior and absence of real writes in v1.
- Frontend/backend compatibility, mobile interaction, and accessible error handling.
- Operational configuration, recovery procedure, known risks, and release decision.

The Tech Lead approves release gates and any explicit exception before release.
Numerical thresholds, release approvers beyond merge authority, deployment access,
and rollback procedures remain **OPEN**.

## DataOps

Follow the source authority hierarchy in [PRODUCT](docs/PRODUCT.md) and the
privacy boundaries in [SECURITY](docs/SECURITY.md). Do not infer university facts or
promote third-party information over authoritative service information.

**CONFIRMED** source review and structured-data workflow:

Muse browser collection / review of official sources → `needs_review` → Tech Lead source
approval → Codex structured implementation → Muse browser recheck against official sources
→ Tech Lead decision on `verified`.

1. Muse may proactively precollect real public campus data before feature development,
   using a browser to visit official sources and organize a Source Inventory and candidate facts.
2. Record and check source URLs, page titles, publishing units, dates, field-level evidence,
   versions, applicability, and conflict or staleness risks. Keep missing or conflicting facts
   explicit; do not infer them.
3. Precollection produces candidate data, not formal CampusPilot data. The default is
   `verification_status=needs_review`. Without explicit Tech Lead authorization, Muse must not
   write candidates into the formal `data/cdut` dataset.
4. After Tech Lead source approval, Codex structures the formal data according to the data
   contracts, preserving source and field evidence. Source approval alone does not mark data
   `verified`; the default remains `needs_review`.
5. During PR QA, Muse uses a browser again to compare formal fields with official sources and
   reports discrepancies and risks. Only the Tech Lead can finally approve `verified` status;
   Muse cannot independently upgrade it.

Retrieval time is not source update time or verification time. Keep unknown dates
explicit. Record conflicts and escalate unresolved institutional facts for review;
Muse cannot declare a fact authoritative merely by collecting or importing it. Source authority
and verification status remain separate; `needs_review` data must not be presented as verified.
Track corrections, superseded records, and withdrawal needs without losing source history.

**OPEN:** institutional source owners, additional approved sources, detailed verification
criteria, refresh intervals, retention, and withdrawal rules. The three Phase 1 records remain
`needs_review`; see [the source inventory](data/cdut/README.md). Mock fixtures remain explicitly
synthetic and separate from real data.

## DevOps and incident readiness

Hosting, storage, environments, configuration and secret delivery, observability,
retention, backup/recovery objectives, and deployment technology remain **OPEN** or
**DEFERRED** as recorded in [ARCHITECTURE](docs/ARCHITECTURE.md). No platform is
selected by this document. Do not create infrastructure before its Issue and
technology decisions are approved.

Muse's release role is validation and gate evidence; it does not assign blanket deployment
or infrastructure implementation ownership. Those responsibilities require a scoped Issue.

**PROPOSED** future incident procedure: record impact and affected versions without
exposing private data; notify the designated human owner through an approved channel;
contain the affected capability or dataset using approved procedures; validate a fix
and recovery; then record follow-up work. Incident contacts, escalation channels,
containment authority, and recovery drills are **OPEN**. Public GitHub records must
not contain credentials, private student information, or production transcripts.

Later Red Team work follows [SECURITY](docs/SECURITY.md) and requires a scoped Issue,
approved targets, test data, and acceptance criteria. No attack testing or live-system
access is authorized by this operations plan.
