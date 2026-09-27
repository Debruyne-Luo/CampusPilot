# CampusPilot

CampusPilot is a campus task-completion Agent for students and staff. Its first pilot is
**Chengdu University of Technology (成都理工大学)**. It helps users find the verified procedure,
responsible service, required information, location, route, official source, and next action.

## Current status

**Documentation bootstrap only.** There is no executable application, installed framework,
runtime, dataset, or deployment. The Core Framework Skeleton is planned, not implemented.
No run or test commands are available yet.

**CONFIRMED:** v1 provides public-information and read-only task assistance through one primary
Agent with modular Skills in a modular monolith. Model providers are replaceable. Evidence,
execution records, and permission boundaries are explicit parts of the architecture.

Authenticated personal-data access and real write actions are **DEFERRED**. Language, Agent
runtime, frameworks, model provider, storage, and GIS provider remain **OPEN**. See the
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

Next proposed Issue: **CampusPilot Core Framework Skeleton**. Its approval prerequisites and
acceptance checklist are in [ARCHITECTURE](docs/ARCHITECTURE.md). This bootstrap does not
authorize implementation of that Issue.
