# Operations and independent QA

**CONFIRMED:** Muse owns independent QA, DevOps, DataOps, and release validation;
later it also owns Red Team work. The Tech Lead accepts work and authorizes merges.
GitHub Issues, PRs, and repository documents are the project record.

The local Python Skeleton implements mock-tool permissions, synthetic evidence, an
in-memory journal and developer tests. It has no deployment, monitoring, backup or release
pipeline. Human Review and Muse independent QA remain pending. Future operational procedures
below are not claims of production controls; run commands are in [README](README.md).

## Responsibilities

| Role | Operational responsibility |
| --- | --- |
| Muse | Independently reproduce behavior, test failures and regressions, report evidence, maintain data review and operational procedures, and assess release readiness |
| Codex | Supply developer verification and a reproducible handoff; fix accepted findings within the Issue's scope |
| Frontend teammate | Supply UI and map interaction verification, including mobile usability and error states |
| ChatGPT | Support evaluation design, research, and technical review |
| Product Owner / Tech Lead | Resolve requirements, approve operational and architectural decisions, accept results, and merge |

Muse may propose architecture changes through an Issue. QA does not authorize silent
redesign of the Agent core. Use the module handoff template in the
[development guide](docs/DEVELOPMENT_GUIDE.zh-CN.md); engineering rules are in
[AGENTS.md](AGENTS.md).

## Review and release workflow

Issue → short-lived branch → implementation → PR → human review → Muse independent
QA → fixes / regression → Tech Lead merge.

Every handoff should identify the reviewed revision or local diff, allowed scope,
acceptance criteria, relevant contracts, checks performed, results, known limitations,
and unresolved findings. Muse records reproduction steps and severity in GitHub.
Unresolved acceptance failures return to the owner; disputed requirements go to the
Tech Lead. A merge is not deployment authorization.

For the Skeleton, validate links and decision consistency, run pytest/mypy/Ruff and the
offline demo, and independently challenge permission denial, invalid inputs/outputs, empty
results, journal failures and session isolation. Confirm every fixture is synthetic.
Developer results do not substitute for Muse QA; production checks remain not applicable.

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

**PROPOSED** data publication workflow:

1. Register the source, access basis, institutional owner, project maintainer, and
   intended use before importing it.
2. Preserve source identifiers, URLs or authorized references, versions, relevant
   locations within the source, applicability, and available date information.
3. Have an identified reviewer check extraction, authority, conflicts, and freshness.
4. Publish an approved version with evidence references and a change record.
5. Track corrections, refresh due dates, superseded records, and withdrawal needs.

Retrieval time is not source update time or verification time. Keep unknown dates
explicit. Record conflicts and escalate unresolved institutional facts for review;
Muse cannot declare a fact authoritative merely by importing it. Keep unverified
or withdrawn data out of published answers according to the future approved policy.

**OPEN:** actual source owners and reviewers, approved sources, permitted acquisition
methods, verification criteria, refresh intervals, retention, and withdrawal rules.
No university dataset is included. Existing mock fixtures are explicitly synthetic;
new fixtures must preserve that distinction.

## DevOps and incident readiness

Hosting, storage, environments, configuration and secret delivery, observability,
retention, backup/recovery objectives, and deployment technology remain **OPEN** or
**DEFERRED** as recorded in [ARCHITECTURE](docs/ARCHITECTURE.md). No platform is
selected by this document. Do not create infrastructure before its Issue and
technology decisions are approved.

**PROPOSED** future incident procedure: record impact and affected versions without
exposing private data; notify the designated human owner through an approved channel;
contain the affected capability or dataset using approved procedures; validate a fix
and recovery; then record follow-up work. Incident contacts, escalation channels,
containment authority, and recovery drills are **OPEN**. Public GitHub records must
not contain credentials, private student information, or production transcripts.

Later Red Team work follows [SECURITY](docs/SECURITY.md) and requires a scoped Issue,
approved targets, test data, and acceptance criteria. No attack testing or live-system
access is authorized by this operations plan.
