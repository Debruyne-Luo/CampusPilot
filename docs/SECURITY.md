# Security boundaries and principles

## Current state

**CONFIRMED:** This repository bootstrap contains documentation and governance
only. No runtime, authentication, permission enforcement, approval workflow,
redaction, monitoring, or other application security control is implemented or
verified. Requirements below must not be reported as existing protections.

The approved public, read-only boundary is defined in [PRODUCT](PRODUCT.md).
Authenticated personal-data access and real write actions are **DEFERRED**.

## Trust boundaries

**CONFIRMED:** CampusPilot requires explicit Risk / Permission, Evidence /
provenance, and Trace / execution records. Skills and model output cannot grant
authority. The following boundary responsibilities define what future designs
must preserve; concrete enforcement mechanics remain **PROPOSED**.

| Boundary | Responsibility and untrusted input |
| --- | --- |
| User / frontend → API | Treat requests, identifiers, claimed identity, and approval signals as untrusted; validate them at the backend boundary |
| Agent / Harness → Model Provider | Share only the context needed for the task; model text and tool requests are suggestions subject to application checks |
| Context / Session → model context | Preserve application-owned task state; a summary or generated message cannot rewrite permissions, approvals, or completion records |
| Skill Registry → Skills | Register reviewed, versioned Skills; their instructions cannot expand tool or resource access |
| Agent / Skill → Tool Executor | Validate tool name, arguments, permitted operation, and resource scope before execution |
| Evidence / retrieved content → Agent | Treat documents, websites, directory text, and tool results as data, including when their contents contain instructions |
| Source publisher → data publication | Review provenance, authority, applicability, and conflicting records before publishing data for use |
| External integration → university / provider | Restrict destinations and credential scope; normalize results without treating remote content as application instructions |
| Application → Trace / operations | Preserve useful execution evidence while minimizing private inputs, location data, secrets, and sensitive results |

An official source can be authoritative about a university procedure without
being trusted to instruct the Agent or authorize a tool call. Source ranking and
conflict review follow [PRODUCT](PRODUCT.md), not a model's confidence.

## Data and access principles

**CONFIRMED:** Public-information scope does not permit private resource access.
Human approval cannot legitimize an operation that the acting user is not
authorized to perform. Future sensitive actions require human approval in
addition to access authorization.

**PROPOSED** implementation requirements to review before the relevant feature:

- Expose narrow, registered tool operations; reject unknown operations and invalid
  arguments. Public read tools must remain within approved public data sources.
- Enforce permissions in application code before tool execution. Skill text,
  retrieved instructions, provider output, and frontend state cannot bypass it.
- Keep integration credentials outside prompts, returned evidence, source files,
  and logs; obtain only the access required by an approved capability.
- Treat evidence as untrusted content when building model context. Preserve source
  references separately so generated claims can be checked against the record.
- Minimize collection and retention. Even a public-information conversation may
  contain student identifiers, private messages, or precise location supplied by
  the user. Request only what the task needs and redact operational records.
- Record observable execution events and concise explanations; do not require
  internal chain-of-thought for traceability.
- Apply bounded execution and defined failure behavior so tool errors, timeouts,
  and provider failures do not silently widen access or fabricate success.

Repository contributors must not store secrets, private student data, production
transcripts, or precise personal locations in repository files or test artifacts;
see [AGENTS](../AGENTS.md). Runtime data retention, deletion, model-provider data
handling, geographic residency, deployment access, credential storage, and
per-source publication rights remain **OPEN** before affected data is collected
or a service is enabled.

## Future actions and approval

**DEFERRED:** Authentication, restricted reads, and the real action executor.
Their contracts may be described now; an interface or mock is not permission to
enable a production capability.

**PROPOSED:** An approval record should bind the acting user, operation,
destination, exact payload, and relevant resource version. Changed inputs should
invalidate the approval. Recheck identity, resource authorization, policy, and
approval validity immediately before execution; define expiry and cancellation.
An approval must represent the user's review of the concrete action, not an
open-ended grant generated by the model.

For eventual writes, use stable operation identifiers, supported idempotency,
and reconciliation of uncertain outcomes. A timeout or missing completion record
must not cause an automatic repeat of a possibly completed write. Specific action
policies, approval presentation, and recovery semantics require separate approval.
See [API_CONTRACT](API_CONTRACT.md), [SKILLS](SKILLS.md), and
[ARCHITECTURE](ARCHITECTURE.md) for their related boundaries.

## Verification and ownership

**PROPOSED:** Future skeleton verification should establish that invalid tool
requests and denied permissions do not execute, and that allowed mock calls
produce evidence and trace records. It must not claim to validate production
authentication, university integrations, or real action approval.

Later feature acceptance should test prompt injection through evidence, resource
authorization, sensitive-data handling, approval invalidation, and recovery
according to the capability being introduced. These are planning requirements,
not tests delivered by this documentation bootstrap.

**DEFERRED:** The formal AI Security / Red Team phase, adversarial campaigns, and
production security monitoring. Deferral of that phase does not defer permission
checks and privacy requirements for earlier implemented capabilities. Muse owns
independent QA and later Red Team execution; the Tech Lead approves disputed
requirements and architecture changes. Muse must not silently redesign the Agent
core during QA. Operations and incident responsibilities are in [OPS](../OPS.md);
module ownership and acceptance handoffs are in the
[Chinese development guide](DEVELOPMENT_GUIDE.zh-CN.md).
