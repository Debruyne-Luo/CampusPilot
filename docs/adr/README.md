# Architecture decision records

ADRs record decisions explicitly approved by the human Product Owner / Tech Lead. They do not
turn implementation recommendations into approved choices. Unresolved alternatives belong in
the [architecture decision register](../ARCHITECTURE.md), not an accepted ADR.

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-pilot-and-v1-scope.md) | CONFIRMED | Pilot university and public, read-only v1 scope |
| [0002](0002-architecture-boundaries.md) | CONFIRMED | Single Agent, modular monolith, capability and authority boundaries |
| [0003](0003-python-skeleton-toolchain.md) | CONFIRMED | Approved Python toolchain and mock-only executable Skeleton |
| [0004](0004-submission-web-map-and-dify.md) | CONFIRMED | 10 月 15 日提交版：事务/教师/地点、Dify ID 卡片、高德与轻量 VPS |
| [0005](0005-backend-runtime-and-knowledge-publication.md) | CONFIRMED | 两阶段迁回后端、Dify 管理正文、不可变知识发布、OpenRouter Jev 影子评测 |
| [0006](0006-online-evidence-and-user-images.md) | CONFIRMED | 在线 Jev 补证、后端高德临时地点、会话图片与网页上传 |

For a newly approved decision, record: date, status, approving authority, approval evidence,
context, decision, alternatives considered (only when actually reviewed), consequences, and
superseded ADRs if any. Link the approving GitHub Issue/PR when available. Do not invent a link,
reviewer handle, discussion, or implementation result.

The initial approval evidence is the human task instruction dated 2026-09-27, titled
"The architecture plan is approved with the amendments below." A GitHub approval link is
not yet available. Carry the approved baseline into the eventual human-reviewed bootstrap PR.
