# CampusPilot

CampusPilot is a campus task-completion Agent for students and staff. Its first pilot is
**Chengdu University of Technology (成都理工大学)**. It helps users find the verified procedure,
responsible service, required information, location, route, official source, and next action.

## Current status

**Core Framework Skeleton and Phase 1 local directory implemented; Phase 1 Review and Muse QA pending.**
The synthetic demo stays separate from three source-backed CDUT records, all `needs_review`.
Neither path calls external services or performs university actions.
Python 3.14.7, uv, Protocol, Pydantic 2, pytest, mypy strict and Ruff are approved in
[ADR 0003](docs/adr/0003-python-skeleton-toolchain.md).

**CONFIRMED:** v1 provides public-information and read-only task assistance through one primary
Agent with modular Skills in a modular monolith. Model providers are replaceable. Evidence,
execution records, and permission boundaries are explicit parts of the architecture.

Authenticated personal-data access and real write actions are **DEFERRED**. Production Agent
runtime, Web frameworks, model provider, durable storage, and GIS provider remain **OPEN**. See the
[decision register and Skeleton plan](docs/ARCHITECTURE.md).

## Start here

| Document | Read it for |
| --- | --- |
| [Product](docs/PRODUCT.md) | Users, pilot, v1 scope, source authority, success criteria |
| [Architecture](docs/ARCHITECTURE.md) | Approved boundaries, decision statuses, next-task plan |
| [API and domain contracts](docs/API_CONTRACT.md) | Framework-independent integration proposals |
| [Skills](docs/SKILLS.md) | Skill, registry, Tool, execution, and risk responsibilities |
| [中文开发协作手册](docs/DEVELOPMENT_GUIDE.zh-CN.md) | Module ownership, phases, handoffs, collaboration |
| [Engineering rules](AGENTS.md) | Durable instructions for coding agents |
| [Operations and QA](OPS.md) | Muse's QA, DataOps, operations, and release responsibilities |
| [Security](docs/SECURITY.md) | Trust boundaries and current requirements versus future controls |
| [Approved decisions](docs/adr/README.md) | Human-approved ADRs |

## Team and workflow

The human Product Owner / Tech Lead owns product decisions, architecture approval, acceptance,
and merges. Codex + GPT-6 Astra is the primary implementation engineer. The human frontend
teammate owns UI/UX and map interaction. Muse owns independent QA, DevOps, DataOps, and release
validation, with Red Team work later. ChatGPT supports architecture, research, planning,
evaluation design, and review. See the [responsibility matrix](docs/DEVELOPMENT_GUIDE.zh-CN.md).

GitHub is the single source of truth. Work proceeds through an Issue, a short-lived branch,
implementation, PR, human review, Muse QA, fixes/regression, and Tech Lead merge. Agents never
merge themselves. Templates live in [.github](.github/); [CODEOWNERS](.github/CODEOWNERS) is a
placeholder until real reviewer identities are confirmed.

## Run and verify

Run from the repository root with uv installed. Initial environment setup downloads locked
packages; the installed demo and checks can then run offline.

```powershell
uv sync --locked
uv run --offline --locked python -m campuspilot demo
uv run --offline --locked campuspilot demo
uv run --offline --locked campuspilot search-service "校园卡挂失"
uv run --offline --locked campuspilot search-service "缴费票据" --academic-year 2026-2027
uv run --offline --locked campuspilot find-office cdut:office:graduate-school
uv run --offline --locked pytest -q
uv run --offline --locked mypy
uv run --offline --locked ruff check
uv run --offline --locked ruff format --check
```

On Windows, if uv is not on PATH after installation, invoke it as
`& "$env:USERPROFILE\.local\bin\uv.exe"` in place of `uv`.
Python is pinned to 3.14.7; no fallback to another minor version is supported.

The JSON demo contains three synthetic results, source references, a session snapshot and
12 ordered events. It is not campus guidance or navigation. Running the CLI again starts a
fresh in-memory application. The session API preserves completed/failed run history within
one process; it does not resume a partially executed run or survive restart.

## Source layout and limitations

`backend/src/campuspilot/` contains contracts, Protocol interfaces, Skills, mock Tools,
permission-checked execution, memory state, fake orchestration and the CLI.
`tests/test_skeleton.py` checks contracts, rejection paths, failures, isolation and offline
repeatability. The core is synchronous and intended for sequential local use. Step limits
and cooperative cancellation are supported; hard timeouts, parallel execution, durable
recovery, authentication and real approval execution are not implemented.

## Phase 1 structured campus data

Issue #2 adds a separate offline public directory for three approved CDUT matters. See the
[source inventory and review limitations](data/cdut/README.md). All records are `needs_review`,
including official sources; the data is not verified current campus guidance.

`domain.py` contains shared service/department models; `contracts.py` owns public Tool results.
`directory/` contains a read-only JSON repository and two Tools that depend on these core contracts.
`evidence.py` contains shared SyntheticEvidence / SourceEvidence / FieldEvidence contracts.
The `search-service` and `find-office` commands call the permission-checked ToolExecutor directly,
without the fake model or harness. Results include field provenance, limitations and trace IDs.
An office result may identify a department while its physical location remains unknown.

Search matches names and aliases using trimmed, case-insensitive substrings and returns all
candidates in ID order. `--academic-year` excludes records scoped to another year; omitting it
returns records with their explicit applicability, never an implicit claim of current validity.
`find-office` accepts exact IDs returned by service lookup. Missing matches return `empty`.

The default data path is `data/cdut` relative to the working directory. When running elsewhere,
pass `--data-dir D:/Projects/CampusPilot/data/cdut` (adjust for your checkout). The data is a
reviewable checkout snapshot, not bundled into the Python wheel. CLI JSON uses UTF-8.
Missing/malformed datasets fail with exit code 2; they never select synthetic data instead.
Real and synthetic Tools are assembled in separate executors with distinct payload/Evidence types.
Each Tool's declared output schema is checked by the executor. No real route
Tool is registered. Demo/session behavior remains synthetic and deterministic.

No dependencies or production integrations were added. Next suggested Issue: **independent
Muse QA and designated-source review for the three Phase 1 records**, including missing office
fields and current validity of the 2023 trial rules. Commit, publication and merge are not implied.
