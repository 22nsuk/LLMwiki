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
`make dev-install` creates `.venv`, installs the authoritative dev dependency
set from `pyproject.toml` (`.[dev]`), and installs the package in editable
mode. The canonical dependency authority is `pyproject.toml` plus `uv.lock`,
with CI replay proven through a frozen `uv export` locked-requirements install.
Root `requirements.txt` and `requirements-dev.txt` are retired from the public
source surface. Historical or sample reports may still classify those paths as
optional compatibility evidence, but their absence must not be treated as a
canonical dependency failure. `make bootstrap-preflight` records a schema-backed
environment report when dependency or interpreter drift needs to be diagnosed.

`uv.lock` is the canonical dependency lockfile. When dependency inputs change,
refresh the lock intentionally; in review or check-only contexts, use
`uv lock --check` to verify the lockfile is current without rewriting it.
Operator-facing lock freshness must mirror that check result directly: a failing
`uv lock --check` is a failing lock freshness state, not a pass with local
interpretation.

## Supported Test Entrypoints

공식 pytest 진입점은 `make test*`, `make check*`, `make public-check*` 또는 `.venv/bin/python -m pytest`다.
문서, CI, 재현 절차 예시도 bare `pytest`가 아니라 `python -m pytest` 또는 Make target을 사용한다.

Goal-runtime Codex execution has a separate outer-tool contract: the operator
Codex CLI must resolve outside the repository `.venv`, while Python and pytest
inside the run should use the repository virtualenv. Document and diagnose
Codex CLI shadowing or missing `python`/`pytest`/`jsonschema` as local
environment setup issues before treating a mechanism proposal as failed.

`make fast-smoke`는 Subagent/developer precheck 전용 curated pytest slice다.
It is intentionally smaller than lint/eval, integration-heavy generator smoke,
and full release smoke.

The registry-documented entrypoints are:

- `make fast-smoke`
- `make test-fast`
- `make test`
- `make unit-tests`
- `make test-all`
- `make check-all`
- `make release-check`
- `make release-check-all-surfaces`
- `make test-report-contract`
- `make report-contracts`
- `make test-report-contract-core`
- `make test-report-contract-all`
- `make report-contracts-core`
- `make report-contracts-all`
- `make report-contracts-extended`
- `make test-release-sealing`
- `make test-release-sealing-core`
- `make test-release-sealing-all`
- `make test-subprocess`
- `make test-slow`
- `make test-integration`
- `make test-integration-heavy`
- `make test-public`
- `make public-check`
- `make release-source-package-smoke`
- `make release-source-package-check`
- `make release-run-ready`
- `make release-run-ready-plan`
- `make release-run-ready-plan-check`
- `make release-run-ready-check`
- `make release-sealed-run-ready-plan`
- `make release-sealed-run-ready`
- `make release-sealed-run-ready-check`
- `make release-auto-promotion-ready-plan`
- `make release-auto-promotion-goal-run-id-guard`
- `make release-auto-promotion-preflight`
- `make release-auto-promotion-preflight-check`
- `make release-auto-promotion-preseal`
- `make release-auto-promotion-preseal-check`
- `make release-auto-promotion-operator-summary`
- `make release-auto-promotion-ready`
- `make release-auto-promotion-ready-check`
- `make release-closeout-regression-dry-run`
- `make test-execution-summary`
- `make test-execution-summary-report-contract`

## Cost-Aware Test Use

Use the smallest authoritative lane that proves the change under review.
`make fast-smoke` and focused `.venv/bin/python -m pytest ...` commands are
the default tight-loop checks. `make test` / `make test-fast` are broader batch
validation lanes, not the smallest local proof surface. On 2026-05-31 an early
local `make test` attempt reached roughly 95% progress and hit a 900 second
timeout; the later checkpoint rerun passed in about 18 minutes and 40 seconds,
so this lane still needs checkpoint-grade time budgeting.
`make test-report-contract-core` / `make report-contracts-core` is the
preferred tight-loop report-contract proof for schema, Make/CI, and generated
artifact contract edits. `make test-report-contract-all` intentionally sweeps
every `report_contract` marker and is a checkpoint/CI or final contract proof,
not the default for every vertical slice; on 2026-05-31 it selected 463 tests
and took about 60 minutes in the local full-vault worktree.
The all target now passes the 48 known report-contract-marked test files
explicitly while retaining `-m report_contract`, so pytest no longer has to
collect the entire repository and deselect unrelated tests before that sweep.
`tests/test_makefile_static_gates.py` keeps the explicit file list aligned with
the marker surface. The report-contract lane now uses
`PYTEST_REPORT_CONTRACT_FLAGS`, defaulting to loadfile xdist plus
`-p no:cacheprovider`; override it to `$(PYTEST_SERIAL_FLAGS)` only when
investigating an isolation failure. Release-sealing has its own
`PYTEST_RELEASE_SEALING_FLAGS` for the same reason. The first local proof after
this isolation change reduced `make test-report-contract-all` to 17 minutes
49 seconds for the same 463 tests / 465 subtests, and
`make test-report-contract-core` to 3 minutes 46 seconds for 201 tests /
454 subtests.

Before spending release-grade runtime, prefer the check/plan targets:
`make release-run-ready-check`, `make release-sealed-run-ready-check`,
`make release-sealed-run-ready-plan`, and
`make release-auto-promotion-ready-plan`. Run the corresponding refresh target
only when the check/plan shows stale authority that is relevant to the change.
`test-execution-summary-full-body`, and therefore `release-run-ready`, uses
`TEST_EXECUTION_SUMMARY_FULL_PYTEST_FLAGS` which defaults to the parallel
`PYTEST_FLAGS`; set it to `$(PYTEST_SERIAL_FLAGS)` only when debugging a
known parallel-isolation failure. The first full-suite proof after adding
cache isolation passed 1859 tests / 1548 subtests in 23 minutes 22 seconds
with JUnit testcase consistency at 3407/3407.
`release-test-current` checks schema samples first, then reuses current full
and report-contract summaries when their source-tree fingerprints still match,
so clean release runs do not replay the same expensive suite more than once.
To avoid source-tree fingerprint loops, stabilize mutation-prone generated and
check surfaces before refreshing expensive summaries. Finish code, docs,
generator, policy, and schema edits first; then run the stabilizers that can
mutate or prove generated surfaces, such as `make report-schema-samples-check`,
`make script-output-surfaces` when `ops/scripts/**` changed, targeted
generated-artifact converge targets, and `make static`. After that point, do not
edit source or docs unless restarting this sequence. Refresh
`make test-execution-summary-current-or-refresh` and
`make test-execution-summary-full-current-or-refresh` last, or use
`make release-test-current`, which encodes the same ordering. This keeps
report/full summaries from becoming stale immediately after they are rebuilt.
Pytest subprocess probes disable cacheprovider and Make exports
`PYTHONDONTWRITEBYTECODE=1` to keep xdist workers and child collection checks
from writing shared repo-local cache artifacts. The broad `PYTEST_FLAGS`
default also includes `-p no:cacheprovider`.
For WSL-first local work, `make static` and strict-preview Make targets keep
Ruff and mypy caches under `tmp/tool-cache/<platform>`; WSL resolves that
platform namespace to `wsl`, so it does not reuse root `.ruff_cache` or
`.mypy_cache` metadata that may have been produced from Windows paths.
Use `make local-cache-clean` to remove only ignored, regenerable local caches:
`.pytest_cache`, `.hypothesis`, root Ruff/mypy caches, `tmp/tool-cache`, and
source `__pycache__` / `*.pyc` / `*.pyo` under `ops`, `tests`, and `tools`.
The target intentionally leaves `.venv`, global uv caches, `ops/reports`,
`build/release`, `runs`, and corpus/private surfaces alone.
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

## CI Tier Shape

`.github/workflows/ci.yml`은 test tier를 `fast`, `report-contract`, `release-closeout-regression`, `release-sealing`, `subprocess`, `slow`, `integration`, `integration-heavy`, `public`으로 나눠 병렬 job으로 실행하고, 별도 Windows/raw-registry/supply-chain job도 유지한다.

The lane contract lives in `ops/test-lane-registry.json`. CI and docs should
point to registry-backed Make targets rather than hand-maintained pytest marker
expressions.

## Change-Type Gates

| Change type | Minimum local check | Extra check |
| --- | --- | --- |
| Docs only | `make test-public` | `make sync-public-policy-check` if public boundaries changed |
| Python runtime | `make static` | focused `.venv/bin/python -m pytest ...` or `make test` |
| Make or CI lane | `make static` | `make report-contracts-core` |
| Complexity ratchet / touched complexity gate | focused `.venv/bin/python -m pytest tests/test_complexity_ratchet_runtime.py tests/test_structural_complexity_budget_cli.py tests/test_makefile_static_gates.py` | `make complexity-budget-touched-check CHANGED_FILES_MANIFEST=<manifest>` or `STRUCTURAL_COMPLEXITY_BUDGET_TARGETS=...`; without touched inputs the target skips and the ratchet stays inactive |
| Dependency input | `uv lock --check` | `make static` after any intentional lock refresh |
| Schema/report contract | `make report-contracts-core` | regenerate artifacts, then rerun the focused schema/report tests |
| Public export policy | `make sync-public-policy` | `make public-check` |
| Release evidence | `make release-run-ready-plan-check`, then `make release-run-ready-check` | `make release-run-ready` from the committed tree before release; the planner reports stale evidence causes and the minimal next target before the full refresh |
| Sealed release evidence | `make release-sealed-run-ready-check` | `make release-sealed-run-ready`; its planner requires current passing run-ready and auto-promotion preseal evidence and reports the minimal next action |
| Auto-promotion evidence | `make release-auto-promotion-ready-check` | Run with `GOAL_RUN_ID=<goal-run-id>` when a run id is known or let `make release-auto-promotion-goal-run-id-guard` infer it from matching current verified `goal-run-status` and `goal-runtime-certificate` evidence; `make release-auto-promotion-preflight`, `make release-run-ready`, `make release-auto-promotion-preseal`, `make release-sealed-run-ready`, then `make release-auto-promotion-ready` when unattended promotion is the intended outcome; preflight/preseal keep missing verified runtime evidence as final promotion blockers instead of creating runtime-trial evidence, preseal includes `make release-auto-promotion-safe-cleanup`, and Stage 3 directly verifies the goal-runtime certificate while reusing the sealed operator summary generated by the sealed stage |
| Supply chain | `make supply-chain-check` | `make sbom-readiness-check` for SBOM readiness |

## Editing Discipline

- Prefer Make targets and `llm-wiki-*` console scripts in docs.
- Use canonical package paths such as `ops.scripts.release.release_smoke` when a module path is needed.
- Keep flat `ops.scripts.<name>` references as compatibility notes only.
- If a contract changes, update the related docs, tests, schema, and policy in the same patch.
