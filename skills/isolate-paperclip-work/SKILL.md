---
name: isolate-paperclip-work
description: Keep Paperclip software collaboration local and separate from durable project assets, excluding public-network, cloud-device, release, deployment, and GitHub work while enforcing local Git scope, naming, verification, delivery evidence, cleanup, and auditable decision gates. Use whenever an agent develops or verifies a software project inside Paperclip, creates process artifacts, closes a run, or audits Paperclip-to-project coupling.
---

# Isolate Paperclip Work

Treat Paperclip as an execution environment, not as part of the project's domain. Preserve durable product and engineering knowledge; isolate how Paperclip assigned and executed the work.

## Keep Collaboration Local

This boundary takes precedence over later execution and approval guidance. Complete collaborative engineering through repository-local implementation, tests, fixtures, mocks, local builds, and local emulators only.

Do not plan, request, provision, execute, or make completion depend on public IPs, internet-facing environments, cloud real-device services, remote hardware, releases, deployments, or GitHub operations such as issues, pull requests, Actions, releases, and pushes. Local Git inspection and scope auditing remain required; they are not GitHub operations.

When a task mentions an excluded external resource or operation, narrow the work to a locally reproducible path, substitute a fixture, mock, or local emulator where useful, and record that external validation was not performed. Do not create a blocker, permission request, or board gate merely to obtain an excluded resource. Never claim remote, device-cloud, release, or production verification from local evidence.

## Establish The Boundary

Read [paperclip-project-boundary-standard.md](references/paperclip-project-boundary-standard.md) before creating files or identifiers.

Classify every artifact before writing it:

| Class | Location | Allowed content |
| --- | --- | --- |
| Durable project asset | Repository-owned canonical path | Stable product facts, domain concepts, engineering decisions, implementation, and verification |
| Paperclip process artifact | `.run/paperclip/sessions/<session-key>/` | Opaque task, agent, and approval references; execution TODOs, handoffs, screenshots, logs, notes, and scratch output |
| Intentional Paperclip integration | Explicit product-owned path | Code or documentation whose actual product domain integrates with Paperclip, excluding the current run's metadata |

Do not put Paperclip task titles, task IDs, task URLs, agent names or IDs, prompts, assignment state, retry history, or run status in project documentation, source code, tests, configuration, migrations, assets, release notes, branches, or code identifiers. Do not name any durable file, directory, symbol, module, test, or migration after a task title or task reference.

Rewrite requirements received through a task as tool-neutral domain statements. Name artifacts after the capability, behavior, or decision they own. A matching phrase is not automatically acceptable merely because it appeared in the task.

## Protect The Paperclip Service

Treat the Paperclip service, control plane, installation, source, configuration, deployment, and running process as immutable platform infrastructure. Never modify, patch, upgrade, deploy, reconfigure, replace, stop, restart, kill, disable, suspend, or uninstall them. Do not call a Paperclip administrative endpoint that performs any of those actions.

This boundary applies to every task and cannot become a board gate or approval option. If the workspace or requested paths are the Paperclip service itself, refuse that part before creating a session or changing files. If a task mixes prohibited service work with independent project work, omit the prohibited actions and continue only with the separable project work.

Normal use of supported Paperclip task, assignment, handoff, status, and approval APIs is allowed. These operations use the service; they do not modify or control the service itself.

## Prepare Local Process Space

Create a process session only when intermediate artifacts are needed:

```bash
python3 scripts/paperclip_session.py create \
  --workspace /path/to/repo \
  --slug payment-timeout \
  --allow-path 'src/payment/**' \
  --allow-path 'docs/development/payment-timeout/**' \
  --forbid-path 'src/payment/secrets/**' \
  --expect-output 'src/payment/timeout.py' \
  --verify-command 'python3 -m pytest tests/payment' \
  --task-ref '<opaque-paperclip-ref>' \
  --agent-ref '<opaque-agent-ref>'
```

Choose `--slug` from a stable domain concept, never from a task title, task number, agent identity, or status. Start from a Git repository with at least one commit. Declare the smallest permitted paths, any explicit exclusions, concrete outputs, and repeatable verification commands. Commands are stored as argument arrays and run without a shell.

The command creates a timestamped session under `.run/paperclip/sessions/`, adds a narrow ignore rule when needed, and snapshots HEAD plus all pre-existing dirty paths. Treat unchanged baseline dirt as user-owned; never overwrite, revert, stage, or commit it outside the declared scope.

Keep all execution-only material inside the current session:

- Track only the current run's actions in `todo.md`; move durable backlog items into the project's canonical backlog after rewriting them.
- Record cross-agent state in `handoff.md`; include the current state, evidence paths, next action, and risks, but no credentials or copied prompt.
- Put screenshots in `screens/`, use the required sequence/type/surface name, index them in `evidence.md`, and redact secrets and personal data.
- Put exploratory notes, logs, and disposable output in `notes/`, `logs/`, and `scratch/`. Never import, link, or depend on these paths from project assets.

## Minimize And Route Decision Gates

Default to execution. Do not create a gate merely because a task mentions approval or authorization, or because the agent must call a local API, generate an artifact, edit an allowed file, run a local command, or retry local work. Execute these operations directly when they are within task scope and have limited, recoverable impact. Excluded external operations remain out of scope and cannot be reintroduced through a gate.

Create a decision gate only for one of these core categories:

| Category | Use only when |
| --- | --- |
| `agent-permission` | An agent needs a permission it does not already hold; the card states the resource, least-privilege scope, purpose, and expiry or revocation condition |
| `board-mandated` | The authority matrix or binding project policy explicitly assigns the decision to the board |
| `material-commitment` | The decision creates a material legal, financial, or organization-wide strategic commitment |
| `security-privacy` | The decision changes privileged access or materially changes sensitive-data disclosure, retention, or use |
| `irreversible-production` | The production action is destructive or not safely reversible and has a material blast radius |

If none applies, do not gate: the agent performs and verifies the operation. Never treat missing agent permission as ordinary execution or ask for it in chat; create an `agent-permission` card before the dependent action. Scope violations, credential exposure, invalid process state, missing outputs, failed verification, and any attempt to modify or control the Paperclip service are invariant failures; they are not decisions the board can approve away.

Every operation that genuinely needs a decision gate must create its own auditable Paperclip board approval card. Do not combine unrelated decisions in one card or use chat confirmation, a manual authorization step, a permission handoff, or any other substitute. Stop before the dependent action and create the card:

```bash
python3 scripts/paperclip_session.py request-approval \
  --workspace /path/to/repo \
  --session 20260715T103000Z-payment-timeout \
  --approval-id cancellation-window \
  --gate-category board-mandated \
  --decision 'Whether cancellation remains available for 24 or 48 hours' \
  --rationale 'Project policy assigns this business rule to the board' \
  --option '24-hours=Allow cancellation for 24 hours' \
  --option '48-hours=Allow cancellation for 48 hours' \
  --recommended-option 24-hours \
  --impact 'The selected window changes checkout behavior and tests' \
  --agent-action 'Agent implements the selected rule locally and runs its tests'
```

Submit the returned card through Paperclip's approval mechanism. The board only approves or rejects a listed option there. For an `agent-permission` card, approval authorizes only its stated least-privilege scope and lifetime; the existing access-control workflow applies or revokes it and records evidence. Never ask the board to configure access manually, provide credentials, call an API, run a command, upload a file, edit the repository, perform an excluded external operation, collect evidence, or approve changes to the Paperclip service.

For `--gate-category agent-permission`, the session must have an opaque `--agent-ref`, and `request-approval` also requires `--permission-scope` plus `--permission-lifetime`.

After Paperclip returns the board decision, the agent records it. For approval, the declared executor performs every card action and the agent records completion evidence:

```bash
python3 scripts/paperclip_session.py resolve-approval \
  --workspace /path/to/repo --session <session-key> \
  --approval-id cancellation-window --status approved \
  --selected-option 24-hours --approval-ref '<opaque-approval-ref>'

# Agent implements and verifies the approved rule locally here.

python3 scripts/paperclip_session.py complete-approval \
  --workspace /path/to/repo --session <session-key> \
  --approval-id cancellation-window \
  --evidence 'tests/cancellation-window verification=passed'
```

The request, Paperclip approval reference, selected option, timestamps, execution status, and evidence remain on the same digest-protected card. For rejection, record `--status rejected` without `--selected-option`, cancel the dependent TODOs, and do not perform the actions. Pending approvals, altered cards, and approved-but-incomplete actions block closure. Read the approval contract in [paperclip-project-boundary-standard.md](references/paperclip-project-boundary-standard.md) before requesting or resolving an approval.

During work, attribute the Git diff to the current session and pass task identity only at runtime:

```bash
PAPERCLIP_TASK_TITLE='<runtime title>' \
python3 scripts/paperclip_hygiene_checker.py \
  --workspace /path/to/repo \
  --session 20260715T103000Z-payment-timeout \
  --scan changed \
  --fail-on revise
```

Use `--scan staged` before a commit to inspect index content rather than the working copy. The checker also accepts `PAPERCLIP_TASK_REF` and `PAPERCLIP_AGENT_REF`; never persist the task title merely to enable detection.

When an aggregate commit has already charged another owner's path to an older session, do not edit the older session's `allowed_paths`, `forbidden_paths`, baseline, or digest. Add a commit-bound ownership attestation instead:

```bash
python3 scripts/paperclip_session.py attest-commit \
  --workspace /path/to/repo \
  --session 20260715T103000Z-payment-timeout \
  --commit <commit> \
  --path 'docs/checkout-policy.md' \
  --owner-session 20260715T103001Z-checkout-policy
```

Use repeatable `--path`. If a verified legacy owner has no surviving session evidence, first create a new session whose contract names only the exact legacy paths and a real verification command; use that session as `--owner-session`. The attestation command requires each path to be changed by the named commit, rejects uncommitted path changes, and binds commit/HEAD/path-history fingerprints plus owner scope into `committed-path-ownership.json`. Source `forbidden_paths` can be migrated only when the other owner proves the path; an owner session's own forbidden paths remain ineligible. A later commit touching an attested path or any manifest tampering invalidates the claim, so close fails closed.

## Promote Outcomes, Not Process

Do not treat a Paperclip task or prompt as the project's source of truth. Link the outcome to the canonical PRD, issue, architecture decision, test evidence, or other repository-approved system. When an intermediate result becomes durable:

1. Extract the verified product fact, decision, code change, or test evidence.
2. Rewrite it without Paperclip provenance or execution narration.
3. Place it in the repository's canonical domain path and apply project-native naming.
4. Cite project-owned evidence, not `.run/paperclip/` paths.
5. Keep the original process artifact local until cleanup; do not move it into `docs/` or source directories.

If the product intentionally integrates with Paperclip, state that boundary explicitly and keep current task/run metadata isolated. An integration exception permits product behavior such as a Paperclip client or API contract; it does not permit leaking the agent's current assignment or changing the Paperclip service, configuration, deployment, or running process.

## Close And Audit

Before reporting completion, complete or explicitly cancel every TODO, then close through the session manager:

```bash
PAPERCLIP_TASK_TITLE='<runtime title>' \
python3 scripts/paperclip_session.py close \
  --workspace /path/to/repo \
  --session 20260715T103000Z-payment-timeout
```

The close command blocks unresolved board approvals first, then verifies expected outputs, runs every declared command, generates `delivery.json`, checks scope and leakage, and marks the session closed. It automatically deletes `retention: discard` sessions. For `external-archive`, pass `--archive-ref` during close and delete the closed local session with `paperclip_session.py purge` after confirming the external record.

Use close's repeatable `--integration-path`, or the checker's `--allow-path`, only for verified product-owned Paperclip integrations. Never allow an entire repository or a generic parent such as `src`, `docs`, or `tests`.

Do not bypass a failed close. Resolve scope, naming, output, verification, evidence, or secret findings and rerun it. Use `purge --force` only to remove explicitly abandoned local work, never to represent successful delivery.

Return `allow`, `revise`, or `block`. Include exact paths, leaked context type, scope violation, and repair action. Treat task-title similarity as `revise`, not proof; manually confirm that names remain natural project concepts after deleting the Paperclip task.
