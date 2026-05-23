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
