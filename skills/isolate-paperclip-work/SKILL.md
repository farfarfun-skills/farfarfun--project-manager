---
name: isolate-paperclip-work
description: Keep Paperclip execution context separate from durable project assets, execute routine reversible operations without approval, route only core decision gates through concrete Paperclip board approvals, and enforce Git scope, naming, verification, delivery evidence, and cleanup. Use whenever an agent works on a software project inside Paperclip, declares change scope, encounters an approval, authorization, gate, or board decision, creates process artifacts, scans changes, closes a run, or audits Paperclip-to-project coupling.
---

# Isolate Paperclip Work

Treat Paperclip as an execution environment, not as part of the project's domain. Preserve durable product and engineering knowledge; isolate how Paperclip assigned and executed the work.

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

Default to execution. Do not create a gate merely because a task mentions approval or authorization, or because the agent must call an API, upload an artifact, edit an allowed file, run a command, retry work, or perform a routine deployment with a tested rollback. Execute these operations directly when they are within task scope, use existing authorized access, and have limited, recoverable impact.

Create a decision gate only for one of these core categories:

| Category | Use only when |
| --- | --- |
| `board-mandated` | The authority matrix or binding project policy explicitly assigns the decision to the board |
| `material-commitment` | The decision creates a material legal, financial, or organization-wide strategic commitment |
| `security-privacy` | The decision changes privileged access or materially changes sensitive-data disclosure, retention, or use |
| `irreversible-production` | The production action is destructive or not safely reversible and has a material blast radius |

If none applies, do not gate: the agent performs and verifies the operation. Scope violations, credential exposure, invalid process state, missing outputs, and failed verification are invariant failures that the agent must repair; they are not decisions the board can approve away.

Every task that genuinely needs a decision gate must use a concrete Paperclip board approval. Do not use chat confirmation, a manual authorization step, a permission handoff, or any other substitute. Stop before the dependent action and create the approval:

```bash
python3 scripts/paperclip_session.py request-approval \
  --workspace /path/to/repo \
  --session 20260715T103000Z-payment-timeout \
  --approval-id account-id-migration \
  --gate-category irreversible-production \
  --decision 'Whether to run the one-way account ID migration in production' \
  --rationale 'The migration rewrites production identifiers and has no safe rollback' \
  --option 'proceed=Run the migration' \
  --option 'defer=Keep the current identifiers' \
  --recommended-option defer \
  --impact 'Proceed permanently rewrites production account identifiers' \
  --agent-action 'Agent applies the selected option, verifies the result, and records evidence'
```

Submit the returned request through Paperclip's approval mechanism. The board only approves or rejects a listed option there. Never ask the board to authorize manually, grant access, provide credentials, call an API, run a command, upload a file, edit the repository, deploy a release, or collect evidence.

After Paperclip returns the board decision, the agent records it. For approval, the agent then performs every declared action and records completion evidence:

```bash
python3 scripts/paperclip_session.py resolve-approval \
  --workspace /path/to/repo --session <session-key> \
  --approval-id account-id-migration --status approved \
  --selected-option proceed --approval-ref '<opaque-approval-ref>'

# Agent performs the approved API, upload, deployment, or repository work here.

python3 scripts/paperclip_session.py complete-approval \
  --workspace /path/to/repo --session <session-key> \
  --approval-id account-id-migration \
  --evidence 'migration-record:account-id verification=passed'
```

For rejection, record `--status rejected` without `--selected-option`, cancel the dependent TODOs, and do not perform the actions. Pending approvals and approved-but-incomplete agent actions block closure. Read the approval contract in [paperclip-project-boundary-standard.md](references/paperclip-project-boundary-standard.md) before requesting or resolving an approval.

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

If the product intentionally integrates with Paperclip, state that boundary explicitly and keep current task/run metadata isolated. An integration exception permits product behavior such as a Paperclip client or API contract; it does not permit leaking the agent's current assignment into those assets.

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
