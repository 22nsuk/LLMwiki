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
`make dev-install` creates `.venv`, installs development requirements, and
installs the package in editable mode. `make bootstrap-preflight` records a
schema-backed environment report when dependency or interpreter drift needs to
be diagnosed.

`uv.lock` is the canonical dependency lockfile. When dependency inputs change,
refresh the lock intentionally; in review or check-only contexts, use
`uv lock --check` to verify the lockfile is current without rewriting it.

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
| Dependency input | `uv lock --check` | `make static` after any intentional lock refresh |
| Schema/report contract | `make report-contracts-core` | regenerate artifacts, then rerun the focused schema/report tests |
| Public export policy | `make sync-public-policy` | `make public-check` |
| Release evidence | `make release-run-ready-check` | `make release-run-ready` from the committed tree before release |
| Sealed release evidence | `make release-sealed-run-ready-check` | `make release-sealed-run-ready`; its planner requires current passing run-ready and auto-promotion preseal evidence and reports the minimal next action |
| Auto-promotion evidence | `make release-auto-promotion-ready-check` | Run with `GOAL_RUN_ID=<goal-run-id>` when a run id is known or let `make release-auto-promotion-goal-run-id-guard` infer it from matching current verified `goal-run-status` and `goal-runtime-certificate` evidence; `make release-auto-promotion-preflight`, `make release-run-ready`, `make release-auto-promotion-preseal`, `make release-sealed-run-ready`, then `make release-auto-promotion-ready` when unattended promotion is the intended outcome; preflight/preseal keep missing verified runtime evidence as final promotion blockers instead of creating runtime-trial evidence, preseal includes `make release-auto-promotion-safe-cleanup`, and Stage 3 directly verifies the goal-runtime certificate while reusing the sealed operator summary generated by the sealed stage |
| Supply chain | `make supply-chain-check` | `make sbom-readiness-check` for SBOM readiness |

## Editing Discipline

- Prefer Make targets and `llm-wiki-*` console scripts in docs.
- Use canonical package paths such as `ops.scripts.release.release_smoke` when a module path is needed.
- Keep flat `ops.scripts.<name>` references as compatibility notes only.
- If a contract changes, update the related docs, tests, schema, and policy in the same patch.
