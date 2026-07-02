# Development Workflow

This page is the public developer path for the code/ops mirror.

## Setup

```bash
make help
make dev-install
make bootstrap-preflight
```

`make help` prints the compact operator index for setup, source checks,
report-contract, public mirror, mechanism, and release entrypoints.
`make dev-install` creates `.venv`, exports the frozen dev dependency set from
`uv.lock`, and installs that locked requirements file into the environment. The
export omits the project itself, then installs the local project separately as
editable with `--no-deps`, so local setup and CI both replay the same frozen
third-party dependency authority without losing editable source behavior.
Local install replay uses `DEV_INSTALL_INDEX_URL`, which defaults to
`UV_CANONICAL_INDEX_URL` but can be overridden for a local package mirror
without changing the canonical lock-check policy.
Root `requirements.txt` and `requirements-dev.txt` are retired from the public
source surface. Historical or sample reports may still classify those paths as
optional compatibility evidence, but their absence must not be treated as a
canonical dependency failure. `make bootstrap-preflight` records a schema-backed
environment report when dependency or interpreter drift needs to be diagnosed.

`uv.lock` is the canonical dependency lockfile. When dependency inputs change,
refresh the lock intentionally; in review or check-only contexts, use
`make uv-lock-check` to verify the lockfile is current without rewriting it.
That target passes the repository canonical package index explicitly through
`UV_CANONICAL_INDEX_URL` and `UV_LOCK_CHECK_INDEX_FLAGS`.
Operator-facing lock freshness must mirror that check result directly: a failing
`make uv-lock-check` is a failing lock freshness state, not a pass with local
interpretation. Status views also report the ambient `uv lock --check` result
separately from the canonical-index check so local index configuration drift is
visible as environment normalization work instead of being mistaken for lockfile
staleness.

## Supported Test Entrypoints

Use Make targets for repository-owned test lanes. They apply the documented
virtualenv, plugin-autoload, bytecode/cache, marker, and xdist policy. Bare
`pytest` is unsupported. `.venv/bin/python -m pytest tests/...` is supported for
focused selectors and serial/isolation debugging; selectorless raw module pytest
belongs behind Make-owned lanes because it runs the full suite serially without
the repository lane policy.

When a request says "full pytest", choose the lane by intent:

| Intent | Command | Notes |
| --- | --- | --- |
| Developer full regression | `make test-all` | Runs all current pytest tests with the default parallel/cache policy and does not write canonical release evidence. |
| Exact serial reproduction or xdist isolation debugging | `make test-all-serial` or focused `.venv/bin/python -m pytest tests/...` | Use only when the serial behavior itself is the thing being investigated. |
| Release-grade full-suite evidence | `make test-execution-summary-full` | Runs the full-suite summary lane and records canonical release evidence. |
| Runnable release authority | `make release-run-ready` | Owns the runnable release stage, including full-suite evidence plus release smoke, public-check, package, and manifest authority. |

The registry-backed test lane inventory is recorded in
`ops/test-lane-registry.json`, reconciled against `mk/test.mk` and sibling
Makefiles, and summarized for operators by `make help`.
Treat registry surfaces by ownership rather than by name alone: raw registry
state preserves full-vault source trace and ingest lifecycle, test-lane registry
state owns Make/CI/pytest lane semantics, and policy registries own runtime
validation authority.

Operator Make entrypoints are indexed in `ops/make-target-inventory-operator.json`
and surfaced through `make help`. High-signal targets include `make check`,
`make sync-derived`, `make sync-derived-check`, `make make-target-inventory-check`,
`make review-surface-manifest`, `make generated-artifact-runs-compress`, and
`make system-log-split`.
Implementation-only Make recipes use the `_internal-*` prefix and are excluded
from the operator inventory; public wrappers such as `make runtime-hotspot-goldens-check`
delegate to them. `docs/REVIEW_SCOPE.md` is the tracked canonical reviewer inventory; the
companion JSON under `tmp/review-surface-manifest.json` is intentionally
ephemeral. Anti-slop admission rules for new gates and reports
live in `docs/anti-slop-admission.md`. `ops/script-output-surfaces.json` is
narrower: it is an AST-derived material output/fallback registry and should
track only scripts with `--out`/`*-out`, `resolve_output_path`,
`resolve_repo_output_path`, or an explicit direct-script fallback marker.
`ops/script-lifecycle-policy.json` and `ops/script-module-surfaces.json` are
tracked projections refreshed by `make sync-derived`. Their small override
files keep only the manual judgments: lifecycle/replacement guidance in
`ops/script-lifecycle-overrides.json`, and module surface roles in
`ops/script-module-surface-overrides.json`. Legacy flat import re-exports are
retained separately in `ops/script-flat-import-aliases.json`, so changing script
lifecycle guidance does not create a new `ops.scripts.<stem>` import surface.
The generators derive console-script exposure from `pyproject.toml`, Make recipe
module references, material output/fallback surfaces, literal `__all__` exports,
and direct-entrypoint flags.

Goal-runtime Codex execution has a separate outer-tool contract: the operator
Codex CLI must resolve outside the repository `.venv`, while Python and pytest
inside the run should use the repository virtualenv. Document and diagnose
Codex CLI shadowing or missing `python`/`pytest`/`jsonschema` as local
environment setup issues before treating a mechanism proposal as failed.

`make fast-smoke` is the curated Subagent/developer precheck pytest slice. It is
intentionally smaller than lint/eval, integration-heavy generator smoke, and
full release smoke. `make runtime-hotspot-smoke` is the focused runtime
decomposition check for hotspot façade refactors before a broader batch gate.

## Cost-Aware Test Use

Use the smallest authoritative lane that proves the change under review.
`make fast-smoke`, `make runtime-hotspot-smoke`, and focused
`.venv/bin/python -m pytest ...` commands are the default tight-loop checks.
`make test` / `make test-fast` are broader batch checks for ordinary Python
changes. `make test` chains the fast unit lane with `make test-boundary-contract-smoke`, a
curated public/report_contract slice that catches script bootstrap, lifecycle
inventory, and selector-registry drift before the full `make public-check` lane. `make test-all` is the non-release full regression lane and should be
treated as checkpoint-grade work.
`make test-report-contract-core` is the preferred tight-loop report-contract
proof for schema, Make/CI, and generated artifact contract edits.
`make test-report-contract-all` intentionally sweeps every `report_contract`
marker and is a checkpoint, release-style, or final contract proof, not the
default for every vertical slice. Report-contract, release-sealing, and
full-suite Make lanes use their own pytest flag variables so isolation fixes can
be applied without changing every recipe. Override those variables to
`$(PYTEST_SERIAL_FLAGS)` only when investigating a parallel-isolation failure.
Volatile counts and durations belong in the generated execution summaries,
JUnit XML, and logs, not in durable docs.

Before spending release-grade runtime, prefer the check/plan targets:
`make release-run-ready-check`, `make release-sealed-run-ready-check`,
`make release-sealed-run-ready-plan`, and
`make release-auto-promotion-ready-plan`. Run the corresponding refresh target
only when the check/plan shows stale authority that is relevant to the change.
`test-execution-summary-full`, and therefore `release-run-ready`, uses
`TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS` which defaults to the parallel
`PYTEST_FLAGS`; set it to `$(PYTEST_SERIAL_FLAGS)` only when debugging a
known parallel-isolation failure.
`release-test-current` checks schema samples first, then reuses current full
and report-contract summaries when their source-tree fingerprints still match,
so clean release runs do not replay the same expensive suite more than once.
To avoid source-tree fingerprint loops, stabilize mutation-prone generated and
check surfaces before refreshing expensive summaries. Finish code, docs,
generator, policy, and schema edits first; then run `make sync-derived` when
tracked source-derived projections should be regenerated, including pytest
marker registration and selector projections, or `make sync-derived-check` in
check-only contexts. Keep targeted
`generated-artifact-converge` work for release/report finality surfaces, then
run `make static`. `test-execution-summary-full` runs
`make full-pytest-generated-preflight` before the expensive full suite, so stale
schema samples, script output surfaces, and runtime hotspot golden digests fail
early with the owning repair target. After that point, do not edit source or
docs unless restarting this sequence. Refresh
`make test-execution-summary-current-or-refresh` last, and reserve
`make test-execution-summary-full-current-or-refresh` for
explicit full-proof lanes such as `make release-run-ready` or
`make release-source-ready-prepare`. Use
`test-execution-summary-full-refresh-no-converge` only as the explicit fallback
when current full-suite evidence cannot be reused and generated-artifact
convergence must be deferred to a later release lane. The full-suite shard
wrapper emits an outer heartbeat by default (`suite`, shard label, elapsed
seconds, quiet seconds, timeout, and execution log path), so a quiet raw pytest
period should be treated as observable progress unless the heartbeat itself
stops. Use
`make release-converge-preflight` before committing, which refreshes
`generated-artifact-script-output` before report-contract evidence, then refresh
summaries last. This keeps
report/full summaries from becoming stale immediately after they are rebuilt.
Pytest subprocess probes disable cacheprovider and Make exports
`PYTHONDONTWRITEBYTECODE=1` to keep xdist workers and child collection checks
from writing shared repo-local cache artifacts. The broad `PYTEST_FLAGS`
default also includes `-p no:cacheprovider`.
For WSL-first local work, `make static` and strict-preview Make targets keep
Ruff `--preview` and mypy caches under `tmp/tool-cache/<platform>`; WSL resolves that
platform namespace to `wsl`, so it does not reuse root `.ruff_cache` or
`.mypy_cache` metadata that may have been produced from Windows paths.
Use `make local-cache-clean` to remove only ignored, regenerable local caches:
`.pytest_cache`, `.hypothesis`, root Ruff/mypy caches, `tmp/tool-cache`, and
source `__pycache__` / `*.pyc` / `*.pyo` under `ops`, `tests`, and `tools`.
The target intentionally leaves `.venv`, global uv caches, `ops/reports`,
`build/release`, `runs`, and corpus/private surfaces alone.
Use `make local-tool-state-clean` only when you explicitly want to remove
ignored local tool/editor state such as `.agents`, `.obsidian`, `.serena`,
`.vscode`, `.ouroboros`, and `.ouroboros_eval_artifact.md`.
When the global uv cache itself is too large, use `make uv-cache-prune`; it
runs `uv cache prune` without `--force`, removing only unreachable uv cache
objects. Do not use `uv cache clean` as routine hygiene because it clears all uv
entries and can force broad re-downloads or Python/toolchain rehydration.
The shared Hypothesis profile defaults to 30 derandomized examples with the
example database disabled; set `LLMWIKI_HYPOTHESIS_MAX_EXAMPLES=100` for an
audit-strength property sweep.
If a full-vault `external-reports/` directory exists, refresh the reference
manifest and action matrix before broad report-contract sweeps so local-only
review intake drift does not obscure the code or schema result being checked.
Before archiving active reports, run or request an external-report action audit
that records per-report action matches, unmatched recommendation counts, and any
operator-only rationale; open archive-reconciliation observations intentionally
keep the corresponding actions active in the matrix.
`public-check-summary` records per-command heartbeat counts, quiet seconds,
timeout termination reason, signal sent, and final observed process state; use
those diagnostics before assuming a timed-out public pytest is still running.
Reuse-only public-check paths also compare the stored
`input_fingerprints.public_check_config` against the requested public export
directory, export boundary, public Python identity, pytest flags, and
ruff/mypy targets, plus the runner timeout and heartbeat settings. The
temporary pytest summary cache path is intentionally not part of that
fingerprint.
When CI public-check fails, inspect the printed `failure_causes` and uploaded
`public-check-summary-*` candidate before rerunning the full lane. Keep release
authority failures separate: missing finality attestation or sealed evidence is
settled through the release evidence targets, not by softening CI upload steps.

## CI Tier Shape

CI splits registry-backed lanes into parallel jobs; see
`.github/workflows/ci.yml` and `ops/test-lane-registry.json` for the executable
shape. Docs should point to registry-backed Make targets rather than
hand-maintained pytest marker expressions.
The `report-contract` CI tier uses `make test-report-contract-core` on pull
requests to keep review latency bounded. The full `make test-report-contract-all`
sweep remains a checkpoint-grade lane for workflow dispatch, release branch
pushes, tag pushes, and the release workflow before release artifacts are built.

Dependabot and other PR branches are checked through the `pull_request` event;
the CI `push` trigger is limited to release branches and tags so one PR SHA does
not spend two full CI waves. When a PR check run has empty job steps and its check-run
annotation says the job was not started because an Actions budget prevented
use, classify it as infrastructure/budget triage. Do not debug action pins,
test failures, or release evidence until the budget is available and a rerun or
rebase produces jobs that reach checkout.

## Change-Type Gates

| Change type | Minimum local check | Extra check |
| --- | --- | --- |
| Docs only | `make test-public` | `make sync-derived-check` if tracked source-derived projections or public boundary templates may be stale |
| Python runtime | `make static` | focused `.venv/bin/python -m pytest ...` or `make test` |
| CLI output/path surface | `make sync-derived-check` | Run `make sync-derived` when the check reports a stale tracked source-derived projection, then rerun the check before committing |
| Make/CI changed-path minimum proof | `make static` + `make workflow-dependency-planner-check` | proves planner recommendations and changed-path minimums |
| Registry/Make/CI lane-contract proof | `make test-report-contract-core` | proves registry/Make/CI lane-contract parity after lane selector, CI routing, or report-contract semantics changed |
| Complexity ratchet / touched complexity gate | focused `.venv/bin/python -m pytest tests/test_complexity_ratchet_runtime.py tests/test_structural_complexity_budget_cli.py tests/test_makefile_static_gates.py` | Before and after structural edits, prefer `make function-budget-edit-check STRUCTURAL_COMPLEXITY_BUDGET_TARGETS="path/to/file.py"` (or `CHANGED_FILES_MANIFEST=<manifest>`); it refreshes function-budget proposals and then runs the touched complexity ratchet. Without touched inputs, `complexity-budget-touched-check` skips and the ratchet stays inactive |
| Dependency input | `make uv-lock-check` | `make static` after any intentional lock refresh |
| Schema/report contract | `make test-report-contract-core` | `make sync-derived`, then rerun the focused schema/report tests |
| Public export policy | `make sync-derived` | `make public-check` |
| Release evidence | `make changed-path-minimum-plan`, then `make release-run-ready-plan-check` and `make release-run-ready-check` | Run `make release-evidence-converge` when generated report payloads are stale; run `make release-run-ready` from the committed tree before release; after a source-ready commit run `make release-post-commit-finalize` for check-only HEAD readback, or `make release-authority-settle` when staged authority manifests should be rewritten for unattended promotion |
| Sealed release evidence | `make release-sealed-run-ready-check` | `make release-sealed-run-ready`; its planner requires current passing run-ready and auto-promotion preseal evidence and reports the minimal next action |
| Auto-promotion evidence | `make release-auto-promotion-ready-check` | Run with `GOAL_RUN_ID=<goal-run-id>` when a run id is known or let `make release-auto-promotion-goal-run-id-guard` infer it from matching current verified `goal-run-status` and `goal-runtime-certificate` evidence; after stale generated evidence is converged, prefer `make release-authority-settle` to rewrite staged authority for unattended promotion, or run `make release-auto-promotion-preflight`, `make release-run-ready`, `make release-auto-promotion-preseal`, `make release-sealed-run-ready`, then `make release-auto-promotion-ready` when stepping through failures manually; preflight/preseal keep missing verified runtime evidence as final promotion blockers instead of creating runtime-trial evidence, preseal uses `make release-auto-promotion-safe-cleanup-cleanup-only`, and Stage 3 directly verifies the goal-runtime certificate while reusing the sealed operator summary generated by the sealed stage |
| Supply chain | `make supply-chain-check` | `make sbom-readiness-check` for SBOM readiness |

## Editing Discipline

- Prefer Make targets in docs; use `llm-wiki-*` only for lifecycle policy public CLIs.
- Use canonical package paths such as `ops.scripts.release.release_smoke` when a module path is needed.
- Keep flat `ops.scripts.<name>` references as compatibility notes only.
- If a contract changes, update the related docs, tests, schema, and policy in the same patch.
