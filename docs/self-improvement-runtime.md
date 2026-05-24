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
- `make goal-runtime-certificate`
- `make goal-runtime-closeout`

## Trial Triage Runbook

Use this runbook before starting another goal-native trial or when
`auto-improve-readiness` says the next run is blocked. It is documented here
instead of as a Codex skill because the source of truth is the repository's
runtime evidence and Make target contract.

Before a new run:

1. Confirm the workspace is a Git worktree and the source tree is clean enough
   for the requested runtime mode.
2. Run the cheap admission checks before starting a trial:
   `make goal-runtime-run-admission` or the narrower preflight targets it
   reports, such as `goal-runtime-quarantine-preflight`,
   `goal-runtime-clean-transient`, `goal-runtime-local-evidence-refresh`, and
   `goal-runtime-fixed-point-check`.
3. Inspect the previous failed run before starting the next one. If the previous
   run produced no candidate artifacts or is explicitly identified as a broken
   failure-evidence run, exclude it from active mechanism history with the
   official mechanism-history status path rather than physically moving the run
   directory first.
4. If an open `next_run_failure_repair` proposal exists, treat it as the
   selected/emitted proposal class until resolved. Other candidates may remain
   visible in queue diagnostics, but they should not be promoted over the repair
   proposal.
5. Verify schema/currentness inputs that can block admission, especially fast
   smoke report fields, goal runtime certificate inputs, readiness reports, and
   run-local remediation backlog evidence.

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
