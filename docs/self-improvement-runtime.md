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
- `make goal-runtime-status-finalize`
- `make goal-runtime-certificate-report`
- `make goal-runtime-certificate`
- `make goal-runtime-closeout`

`goal-runtime-status-finalize` is the explicit mutating status writer for the
certificate lane. It runs `auto-improve-goal-status`, then promotes the
run-local `goal-run-status` snapshot to `ops/reports/goal-run-status.json`. The
status generator preserves an existing terminal status and `completed_at` for
the same run when no explicit replacement clock is provided, but operators
should still bind `GOAL_RUN_ID` to the intended completed run and use
`make auto-improve-goal-finalize` with `GOAL_FINAL_STATUS=completed` and
`GOAL_COMPLETED_AT=<timestamp>` first when creating completion evidence.

`goal-runtime-certificate-report` is the read-only certificate renderer with
respect to goal runtime inputs: it reads the existing run-local goal contract
and status report, then writes only the certificate candidate.
`goal-runtime-certificate` promotes that certificate candidate to
`ops/reports/goal-runtime-certificate.json`; it does not run
`auto-improve-goal-status` and does not promote `goal-run-status`. For
readback-only release checks, use the release auto-promotion check targets that
read the current status and certificate instead of invoking status finalization.

The status finalization and certificate publish targets share the same guard.
They run a run-id guard before mutating evidence: if Make's default
`GOAL_RUN_ID=auto-improve-trial` would overwrite canonical status or
certificate evidence for another run, it fails and asks for an explicit
`GOAL_RUN_ID=<completed-run-id>`.
The canonical publish targets, including `goal-runtime-publish-snapshot` and
`goal-runtime-publish-local-evidence`, use the same guard. Release freshness
refreshes intentionally do not publish goal status snapshots or rewrite
canonical goal prompt/contract surfaces; refresh the goal runtime lane with the
intended explicit run ID when canonical status or certificate evidence needs to
move.

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
General pytest lane selection lives in [development.md](development.md); this
section only covers the goal-runtime executor environment split.

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
   The report separates the start and promotion gates: `start_status=pass`
   means a run may start, `promotion_status=blocked` keeps promotion banned,
   and `admission_mode=bounded_repair_allowed` means only bounded repair work is
   allowed until promotion evidence converges.
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

Run admission applies the touched structural-complexity gate to source targets,
not generated evidence surfaces. For example, `ops/script-output-surfaces.json`
may remain a supporting material output/fallback registry to refresh after an
ops script edit, but it is excluded from the start-time complexity budget.
Mutation proposal selection also skips over-budget primary target options unless
the proposal is explicitly a structural-complexity repair, so the queue should
prefer a smaller runnable rotation target instead of starting a run that
admission will immediately block.

Between runs, prefer `make goal-runtime-between-run-settle` before starting the
next trial. It refreshes generated core reports, runs quarantine preflight for
active history cleanup, records stale session/ledger closeout and archive path
resolution diagnostics, then applies the same pre-run cleanup, republishes
run-local evidence to the global report surfaces, and verifies the fixed point.
It is meant for the gap after a run finishes and before a repair/resume run
starts; release closeout still uses the release-specific cleanup lane described
in `docs/release.md`. `goal-runtime-stale-closeout` is diagnostic by default;
rerun it with `GOAL_RUNTIME_STALE_CLOSEOUT_APPLY=1` when the report shows old
`running` sessions or ledgers that should be closed to blocked local evidence.
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
- `auto-improve-readiness` has `can_execute=false`
- `goal-runtime-run-admission` has `start_status=fail` or
  `admission_mode=blocked`
- `goal-runtime-run-admission` has `promotion_status=blocked` and the intended
  action is broader than bounded repair
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

`generated-artifact-converge` is now the generated-report finality suffix, not
the owner of every generated contract fixture. It refreshes
`artifact-freshness`, `external-report-action-matrix`, and
`generated-artifact-index` in that order. `script-output-surfaces` is a separate
material output/fallback registry slice owned by
`generated-artifact-script-output`; it records scripts with material output path
surfaces or direct-script fallback entrypoints, and no longer carries
generated-at, source-revision, source-tree-fingerprint, or currentness envelope
fields in the tracked fixture.

`release-finality-resettle-current-or-refresh` first replay-checks current
finality and reuses it when possible. When a refresh is needed,
`release-finality-resettle` refreshes the sealed rehearsal authority with
`release-authority-sealed-preflight`, then uses the generated-artifact finality
suffix (`artifact-freshness -> external-report-action-matrix ->
generated-artifact-index`), refreshes `release-closeout-summary-report`, runs
`release-closeout-fixed-point`, and verifies finality. `release-closeout-fixed-point`
owns the last action-matrix refresh before it writes the finality attestation:
after the post-promote artifact-freshness bootstrap, it refreshes the action
matrix readback and only then writes the attestation. No canonical report writer
should run between that attestation and `release-closeout-finality-verify`. Treat
the finality verify as terminal: if any finality-tracked report writer runs afterward, rerun
`make release-finality-resettle-current-or-refresh` instead of hand-patching the attestation.
Observation registry edits that change tracked source, including
`ops/observation-closeout-registry.json`, must happen before this terminal seal.
Open or planned observations remain registry-owned even when their artifact is
generated/local-only; after finality, either keep only closed observations with
resolution evidence in generated artifacts, or update the registry and restart
the resettle lane so the source-tree fingerprint and finality evidence stay
aligned.
Within `release-closeout-fixed-point`, raw digests still prove convergence, but
the next iteration's target list is selected from per-report semantic digest
changes so envelope/currentness churn does not repeatedly schedule the expensive
generated-artifact feedback suffix. When
`generated-artifact-index-body`, `artifact-freshness`, or
`external-report-action-matrix` is selected again, the fixed-point engine also
reuses the existing writer output and records a skipped command result if that
writer's input fingerprint, output semantic digest, and tracked-context semantic
digest have not changed.
If the terminal finality current check still fails after this reuse path,
`release-finality-resettle-current-check` emits a non-mutating diagnosis from
`release-finality-resettle-current-diagnose`. Its
`failure_classification`, together with the batch replay verifier's
`batch manifest replay mismatch classification` JSON, separates batch-manifest
source freshness/content drift, freshness/index/cohort digest drift, sealed
preflight drift, fixed-point tracked-writer drift, and attestation-only digest
drift so operators can rerun the narrow writer or seal lane before choosing full
`release-finality-resettle`.
The workflow planner now records the generated-artifact fan-out explicitly in
each selected step's `fanout_targets` field so the repair suffix is inspectable
rather than implicit in Make recipes alone.

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
