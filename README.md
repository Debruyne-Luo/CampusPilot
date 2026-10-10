# CampusPilot

CampusPilot is a campus task-completion Agent for students and staff. Its first pilot is
**Chengdu University of Technology (成都理工大学)**. It helps users find the verified procedure,
responsible service, required information, location, route, official source, and next action.

## Current status

**2026-10-11：本分支收录完整项目代码及后端迁移实现，离线验证通过，尚未上线。** 两阶段后端路由、
HTTPS 模型直连、不可变知识发布、轻量词法 RAG 和 OpenRouter Jev 影子评测已实现。
默认仍为 legacy；Dify 当前发布基线、真实模型/付费评测及独立 QA 未完成时，
发布门槛保持关闭。配置、维护命令和具体状态见
[迁移交付与验收](docs/RUNTIME_MIGRATION.zh-CN.md)、
[ADR 0005](docs/adr/0005-backend-runtime-and-knowledge-publication.md)。
Grok 重构从 `handoff/grok-refactor-20261011` 分支开始，阅读
[重构交接](docs/GROK_REFACTOR_HANDOFF.zh-CN.md)。

**2026-10-08: 提交版持续交付记录。**
主线是需求 → 官方资料/步骤 → 地点 → 站内步行参考路线。FastAPI/原生网页与 Dify/Amap
已通过真实联通与上线检查。现有4项事务、20条地点目录（14个高德坐标候选）、5位教师，
新增6条官方知识资料及时间/人群筛选。地图与事务助手分为两种空间，高德热点、周边搜索
和地图目的地扩展目录覆盖；网页前台步行引导支持持续定位/进度与偏航重规划。
室内、后台导航和校园真机步行尚未验收；网安楼及当前补卡设备准确位置继续补齐。详见
[提交版交付状态与设计](docs/SUBMISSION_STATUS.zh-CN.md)、
[部署与回滚](docs/SUBMISSION_DEPLOY.zh-CN.md)、[ADR 0004](docs/adr/0004-submission-web-map-and-dify.md)。

Core Framework Skeleton and Phase 1 local directory are merged into main.
Muse reports a 22/22 golden eval baseline on Python 3.14.7 at `554d7cb1`; see
[the QA handoff](OPS.md#review-and-release-workflow) for evidence and remaining review boundaries.
The synthetic demo stays separate from the public inventory, all `needs_review`.
The demo/CLI remain offline; the web adapter can call Dify Cloud. No university actions run.
Python 3.14.7, uv, Protocol, Pydantic 2, pytest, mypy strict and Ruff are approved in
[ADR 0003](docs/adr/0003-python-skeleton-toolchain.md).

**CONFIRMED:** v1 provides public-information and read-only task assistance through one primary
Agent with modular Skills in a modular monolith. Model providers are replaceable. Evidence,
execution records, and permission boundaries are explicit parts of the architecture.

Authenticated personal-data access and real write actions are **DEFERRED**. The submission version
uses Dify Cloud, Python/FastAPI, plain HTML/CSS/JS, Amap and in-memory sessions under ADR 0004.
Domestic campus-network, physical walking and independent QA checks remain outstanding.

## Start here

| Document | Read it for |
| --- | --- |
| [Product](docs/PRODUCT.md) | Users, pilot, v1 scope, source authority, success criteria |
| [Architecture](docs/ARCHITECTURE.md) | Approved boundaries, decision statuses, next-task plan |
| [API and domain contracts](docs/API_CONTRACT.md) | Framework-independent integration proposals |
| [Skills](docs/SKILLS.md) | Skill, registry, Tool, execution, and risk responsibilities |
| [中文开发协作手册](docs/DEVELOPMENT_GUIDE.zh-CN.md) | Module ownership, phases, handoffs, collaboration |
| [Engineering rules](AGENTS.md) | Durable instructions for coding agents |
| [DeepSeek Harness 交接](docs/DEEPSEEK_HANDOFF.zh-CN.md) | Current local workspace, delivered features, evidence and continuation notes |
| [Operations and QA](OPS.md) | Muse's Independent QA, DataOps, Security Validation / Release Gate responsibilities |
| [Security](docs/SECURITY.md) | Trust boundaries and current requirements versus future controls |
| [官方知识资料](docs/KNOWLEDGE.zh-CN.md) | Source adoption, date filters, import/export and WeChat attribution |
| [后端问答迁移](docs/RUNTIME_MIGRATION.zh-CN.md) | Two-stage runtime, immutable releases, private configuration and acceptance gates |
| [网页步行引导](docs/WEB_GUIDANCE.zh-CN.md) | Two workspaces, dynamic places, foreground location and limitations |
| [比赛展示思路](docs/DEMO_STRATEGY.zh-CN.md) | Proposed audience, pain points and reproducible demo |
| [Approved decisions](docs/adr/README.md) | Human-approved ADRs |

## Team and workflow

The human Product Owner / Tech Lead owns product decisions, architecture and fact approval,
and final Review / Merge. Codex is the primary implementation engineer; its selected development
model is independent of the deployed application's Dify model. The human
teammate owns Frontend & Product Experience, including UI/UX and map interaction.
Muse owns Independent QA + DataOps + Security Validation / Release Gate, with Agent Red Team
work later. ChatGPT supports architecture, research, planning,
evaluation design, and review. See the [responsibility matrix](docs/DEVELOPMENT_GUIDE.zh-CN.md).

GitHub is the single source of truth. Work proceeds through Issue → Codex / teammate
implementation on a short-lived branch → PR → Muse independent QA / source verification
(for real data) → Codex fixes → Muse regression → Tech Lead final review → Merge.
Muse locks the Tested Commit SHA and reports PASS / FAIL with blocking / non-blocking findings.
Agents never merge themselves. Templates live in [.github](.github/); [CODEOWNERS](.github/CODEOWNERS) is a
placeholder until real reviewer identities are confirmed.

Muse may precollect official public sources in a browser before feature development; candidates
remain `needs_review`. After Tech Lead source approval, Codex structures the formal data, Muse
rechecks it against official sources in the PR, and the Tech Lead decides whether it is `verified`.
Muse cannot write candidates to `data/cdut` without explicit Tech Lead authorization or independently
mark them `verified`. See [OPS](OPS.md) for QA, data, and production-code boundaries.

## Run and verify

The optional [CampusPilot web + Dify pilot](docs/WEB_DIFY_SETUP.zh-CN.md) adds a local
browser UI, public service cards, and a server-side Dify adapter. Run
`uv run --locked --extra api python -m campuspilot.web` and open <http://127.0.0.1:8766>.
Without a Dify app credential, service guides work and AI chat is explicitly disabled.
For real chat, use `--prompt-key` after publishing the Chatflow. The fake harness is not
part of this path. Set `DIFY_STRUCTURED_ANSWERS=1` only for the new structured candidate workflow.
Production deployment and Dify-to-directory live callbacks remain outstanding.

An optional local Dify directory API pilot is available; see
[API setup](docs/DIFY_API_SETUP.zh-CN.md) and [data preparation](docs/DATA_PREPARATION.zh-CN.md).
Use `uv sync --locked --extra api` for its checks. It has not been deployed or connected to
Dify Cloud. The submission architecture is confirmed in ADR 0004; the CLI stays independent.

Run from the repository root with uv installed. Initial environment setup downloads locked
packages; the installed demo and checks can then run offline.

```powershell
uv sync --locked --extra api
uv run --offline --locked --extra api python -m campuspilot demo
uv run --offline --locked --extra api campuspilot demo
uv run --offline --locked --extra api campuspilot search-service "校园卡挂失"
uv run --offline --locked --extra api campuspilot search-service "缴费票据" --academic-year 2026-2027
uv run --offline --locked --extra api campuspilot find-office cdut:office:graduate-school
uv run --offline --locked --extra api pytest -q
uv run --offline --locked --extra api mypy
uv run --offline --locked --extra api ruff check
uv run --offline --locked --extra api ruff format --check
```

On Windows, if uv is not on PATH after installation, invoke it as
`& "$env:USERPROFILE\.local\bin\uv.exe"` in place of `uv`.
Python is pinned to 3.14.7; no fallback to another minor version is supported.

For CLI-only use, omit `--extra api`; full development/type checks above include the optional API.

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

No dependencies or production integrations were added. Next handoff: **archive the Muse golden eval
baseline and browser Source Review for the three Phase 1 records**, including missing office
fields and current validity of the 2023 trial rules. Passing tests does not approve `verified` status.
