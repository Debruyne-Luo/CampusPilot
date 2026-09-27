# Skills, registry, and tool execution

**CONFIRMED:** one primary Agent, modular Skills, a static trusted Skill Registry, explicit
Risk/Permission and Trace records. **PROPOSED:** the detailed contracts and policies below.
Nothing here is implemented. Review alongside [API_CONTRACT](API_CONTRACT.md) before the Skeleton.

## Three distinct responsibilities

- **Agent / Harness:** owns task interpretation, orchestration, clarification, and stopping.
- **Skill:** a reusable domain procedure with instructions, required capabilities, and outcome
  criteria. It may guide several Tool calls; it is not a secondary autonomous Agent.
- **Tool:** an executable, validated operation returning a typed result and evidence.

Skill instructions cannot authorize Tools, change source authority, or mark a fact verified.
A Tool must pass execution policy even when called outside a Skill or requested directly by a model.

## Proposed Skill descriptor

| Field | Meaning |
| --- | --- |
| ID / version / description | Stable identity, reviewed version, purpose |
| Applicability / input requirements | When to use it and what must be known |
| Instructions / required Tools | Procedure and the bounded capabilities it may request |
| Permissions / risk | Declared access needs and operation classification |
| Completion criteria | Observable outcome, including when only guidance is possible |
| Failure / fallback | Missing inputs, empty evidence, conflict, unavailability, and handoff |
| Owner / review status | Responsible maintainer and registration approval |

Start with trusted registrations reviewed in the repository. Reject duplicates, unknown versions,
and disabled or invalid registrations. The registry exposes descriptions; it is not a runtime
package installer. Skill file format and executable procedure support remain OPEN.

## Proposed Tool descriptor and executor

A Tool declares its identity/version, input/output schema, operation/resource scope, risk,
timeout/cancellation behavior, evidence output, and retry/idempotency characteristics.
Metadata is reviewed policy input, not proof of safe behavior.

Proposed execution sequence:

1. Resolve a registered Tool and validate its input.
2. Evaluate permissions using trusted caller context and the actual operation/resource.
3. Record the request and policy result; unknown, denied, or pending operations do not execute.
4. Execute an allowed operation within its budget; normalize success, empty results, or failure.
5. Attach evidence and record a correlated outcome before reporting completion.

The Skeleton should fail before execution if it cannot record the required request/permission
trace, and expose an explicit recording error if outcome recording fails. A later side-effecting
operation with missing outcome records must be treated as uncertain, never automatically retried.
This behavior is PROPOSED and must be accepted with the contract review.

## Proposed risk policy

| Risk class | Example | V1 / Skeleton treatment |
| --- | --- | --- |
| Public read | Published service or office lookup | Registered read-only operation may be allowed by policy |
| Restricted read | Personal application status | DEFERRED; unavailable, not silently downgraded |
| Reversible write | Modify a request | DEFERRED; deny execution |
| Sensitive / irreversible action | Submit, cancel, pay, change identity | DEFERRED; deny execution; future scoped human approval required |
| Unknown | Missing metadata or unregistered operation | Deny |

The confirmed requirement is explicit permissions and future human approval; these class names
and exact rules are proposals. Read-only scope does not remove source access restrictions or
session isolation. The model cannot lower a Tool's risk or approve itself.

## Planned Skeleton demonstrations

| Mock Tool | Purpose | Boundaries |
| --- | --- | --- |
| `search_service` | Return a synthetic service match or empty result | No real service inventory or RAG |
| `find_office` | Resolve a synthetic office record | No real contact, faculty, location, or university data |
| `route_plan` | Return a fixed synthetic route result or unavailable | No coordinates tied to real places, map API, or route calculation |

Use a small example Skill to connect these Tools through a deterministic fake harness. All
fixtures identify themselves as synthetic and must not be rendered as verified university facts.
Mock behavior is not a production workflow or runtime selection.

## Review and QA

Codex implements approved contracts; the Tech Lead reviews architecture and scope. Muse checks
registry rejection, invalid arguments, permission denial, Tool non-execution after denial,
empty results, exceptions, and correlated traces. Source-bearing Tools also need evidence checks.
Changing a shared contract requires an upstream/downstream impact note and regression coverage.
Use the [handoff template](DEVELOPMENT_GUIDE.zh-CN.md) and [OPS](../OPS.md).

Dynamic third-party Skills, MCP selection, arbitrary code execution, authenticated integrations,
and real Actions are outside the Skeleton. See [ARCHITECTURE](ARCHITECTURE.md) for decision status
and [SECURITY](SECURITY.md) for trust boundaries.
