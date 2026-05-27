# Self-Improvement Runtime

The self-improvement runtime changes the maintainer mechanism itself. It should
stay bounded, evidence-backed, and reversible.

## Main Loop

1. `make mechanism-review` finds candidate mechanism improvements.
2. `make mutation-proposal` narrows candidates into runnable proposals.
3. `make auto-improve-readiness` checks worktree, queue, learning, and promotion readiness.
4. `make auto-improve-goal-run` can execute a long-running bounded goal loop.
5. Promotion requires current runtime evidence plus release/public/source checks.

## Goal Runtime

Goal runtime hot state lives under `runs/goal-$(GOAL_RUN_ID)/state/`.
Both `runs/` and `ops/reports/` are local-only evidence surfaces, so heartbeat,
resume, and report refreshes do not dirty public source after those surfaces are
removed from the Git index.

Useful targets:

- `make auto-improve-goal-contract`
- `make auto-improve-goal-status`
- `make auto-improve-goal-run`
- `make auto-improve-goal-finalize`
- `make goal-runtime-pre-run-cleanup`
- `make goal-runtime-between-run-settle`
- `make goal-runtime-certificate`
- `make goal-runtime-closeout`

Default goal runs do not spend the remaining wall-clock budget after one
promotion. `GOAL_POST_PROMOTE_MAINTENANCE_CYCLES ?= 1` keeps a single
post-promote stabilization cycle, while `GOAL_MAINTAIN_UNTIL_BUDGET ?= 0`
keeps long soak maintenance opt-in. Set `GOAL_MAINTAIN_UNTIL_BUDGET=1` only
when the goal explicitly needs soak evidence across the remaining
`GOAL_MAX_MINUTES`.

The file-backed goal contract records this as
`execution_policy.post_promote_maintenance.minimum_meaningful_cycles=1` with
`allow_zero_cycles_for_certificate=false`. `goal-runtime-certificate` therefore
requires meaningful post-promote maintenance for a promoted
`proposal_budget_exhausted` session; the exception is a terminal
`queue_exhausted` session, where no runnable follow-up maintenance remains.

Maintenance cycles are meaningful only when they establish a new post-promote
observation or change queue/readiness state. If the same runnable queue snapshot
repeats, the runtime stops the maintenance loop early and records a
`queue_action` with the proposal ids and next step. For
`recent_log_overlap_queue_blocked__...` snapshots, the next step is not only
recorded. Run `make auto-improve-goal-maintenance-action`; it settles the
between-run state, verifies that the queued proposal is still runnable and
unattempted, raises the resume proposal budget by one slot, and resumes the
session through the normal goal runner. If the selector cannot find an
unattempted proposal, the action stops before launching another run because
repeating maintenance refreshes alone is not progress.

## Executor Environment

Goal runs use two Python/tooling scopes. The outer Codex executor must resolve
the operator-local Codex CLI outside the repository `.venv`; commands executed
inside the Codex session may then prepend the repository `.venv/bin` for Python,
pytest, and project entrypoints. Do not create or rely on a repository-local
`.venv/bin/codex` shim for goal execution. If a run is blocked by `python`,
`pytest`, `jsonschema`, or Codex resolution, diagnose it as an environment
contract problem before classifying the mechanism proposal as failed.

Useful checks:

```bash
make goal-runtime-python-preflight
.venv/bin/python -m pytest --version
```

`goal-runtime-python-preflight` records the Codex executable visible outside
the repository virtualenv and fails the goal-runtime environment check when the
only resolvable Codex command is a repository-local `.venv/bin/codex` shim. Use
`command -v codex` only as a local diagnostic when the report's executor tooling
section points at a shadowed or missing Codex command.

## Trial Triage Runbook

Use this runbook before starting another goal-native trial or when
`auto-improve-readiness` says the next run is blocked. It is documented here
instead of as a Codex skill because the source of truth is the repository's
runtime evidence and Make target contract.

Before a new run:

1. Confirm the workspace is a Git worktree and the source tree is clean enough
   for the requested runtime mode.
2. Run `make goal-runtime-pre-run-cleanup` or a target that includes it. This
   applies the standard transient cleanup, tmp JSON cleanup, run-local evidence
   convergence, and artifact freshness refresh before admission reads the state.
3. Run the cheap admission checks before starting a trial:
   `make goal-runtime-run-admission` or the narrower preflight targets it
   reports, such as `goal-runtime-quarantine-preflight`,
   `goal-runtime-local-evidence-refresh`, and `goal-runtime-fixed-point-check`.
   If learning readiness is uncertain, admission/start requires
   `GOAL_ALLOW_LEARNING_UNCERTAIN=1` or an active file-backed goal contract with
   `execution_policy.learning_uncertain.allow_bounded_trial=true` and
   `authorization_source=codex_goal_contract`.
4. Inspect the previous failed run before starting the next one. If the previous
   run produced no candidate artifacts or is explicitly identified as a broken
   failure-evidence run, exclude it from active mechanism history with the
   official mechanism-history status path rather than physically moving the run
   directory first.
5. If an open `next_run_failure_repair` proposal exists, treat it as the
   selected/emitted proposal class until resolved. Other candidates may remain
   visible in queue diagnostics, but they should not be promoted over the repair
   proposal.
6. Verify schema/currentness inputs that can block admission, especially fast
   smoke report fields, goal runtime certificate inputs, readiness reports, and
   run-local remediation backlog evidence.

Between runs, prefer `make goal-runtime-between-run-settle` before starting the
next trial. It runs the same pre-run cleanup, republishes run-local evidence to
the global report surfaces, and verifies the fixed point. It is meant for the
gap after a run finishes and before a repair/resume run starts; release closeout
still uses the release-specific cleanup lane described in `docs/release.md`.
When the previous session's maintenance evidence contains a `queue_action` with
`runner_action=resume_session_with_additional_proposal_budget`, use
`make auto-improve-goal-maintenance-action` instead of a manual resume. The
target computes the next `GOAL_MAX_PROPOSALS` from the session evidence and
reuses `auto-improve-goal-resume`, so the actual unblock attempt is captured by
runner heartbeat, checkpoint, and resume evidence. It also writes
`tmp/goal-runtime-maintenance-action.json` before launching the resume and
validates that plan against `ops/schemas/goal-runtime-maintenance-action-plan.schema.json`,
which keeps the budget-increase decision inspectable and admission-checkable.

Do not start `make auto-improve-goal-run` while any of these remain unresolved:

- quarantine preflight requires a history status repair
- `auto-improve-readiness` has `can_execute=false` or `can_promote=false`
- `goal-runtime-run-admission` reports strict blockers
- the runtime certificate or closeout report is stale for the intended goal
  contract
- the worktree contains unrelated source changes that would make promotion or
  release evidence ambiguous

After a trial, classify its result before the next trial. A successful trial can
move toward certificate and closeout. A failed trial should either produce a
repair proposal, a quarantine/history update, or a documented blocker; leaving
it undecided is what causes repeated preflight churn.

## Generated Artifact Convergence

When a self-improvement run changes report producers or canonical evidence,
close the generated-artifact order explicitly:

```bash
make report-schema-samples-check
make generated-artifact-converge
make release-smoke-full-reuse
make goal-runtime-closeout
```

This order keeps schema samples, reusable release smoke, and goal closeout from
drifting apart. Release promotion still requires the separate
`make release-run-ready`, `make release-sealed-run-ready`, and
`make release-auto-promotion-ready` manifest authorities for the committed tree.

## Promotion Principles

- A dirty Git worktree blocks result promotion.
- ZIP/source extracts are replay-only and not promotable.
- Same-eval promotion needs non-regression plus at least one strict secondary improvement.
- Generated artifacts are evidence only when current, schema-backed, and tied to the source fingerprint.
- Human signoff is explicit when a policy path requires it; otherwise runtime gates must carry the claim.

## Where To Look

- Current orientation: [../ops/runtime-decomposition-plan.md](../ops/runtime-decomposition-plan.md)
- Make targets: `mk/mechanism.mk`
- Schemas: `ops/schemas/*goal*`, `ops/schemas/*promotion*`, `ops/schemas/run-telemetry.schema.json`
- Agent roles: [../.codex/agents/README.md](../.codex/agents/README.md)
