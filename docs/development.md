# Development Workflow

This page is the public developer path for the code/ops mirror.

## Setup

```bash
make dev-install
make bootstrap-preflight
```

`make dev-install` creates `.venv`, installs development requirements, and
installs the package in editable mode. `make bootstrap-preflight` records a
schema-backed environment report when dependency or interpreter drift needs to
be diagnosed.

## Supported Test Entrypoints

공식 pytest 진입점은 `make test*`, `make check*`, `make public-check*` 또는 `.venv/bin/python -m pytest`다.
문서, CI, 재현 절차 예시도 bare `pytest`가 아니라 `python -m pytest` 또는 Make target을 사용한다.

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
- `make test-artifact-finalization`
- `make report-contract-finalization`
- `make test-release-sealing`
- `make test-release-sealing-core`
- `make test-release-sealing-all`
- `make test-subprocess`
- `make test-slow`
- `make test-integration`
- `make test-integration-heavy`
- `make test-public`
- `make public-check`
- `make test-source-package`
- `make release-source-package-check`
- `make release-closeout-regression-dry-run`
- `make test-execution-summary`
- `make test-execution-summary-report-contract`

## CI Tier Shape

`.github/workflows/ci.yml`은 test tier를 `fast`, `report-contract`, `release-closeout-regression`, `artifact-finalization`, `release-sealing`, `subprocess`, `slow`, `integration`, `integration-heavy`, `public`으로 나눠 병렬 job으로 실행하고, 별도 Windows/raw-registry/supply-chain job도 유지한다.

The lane contract lives in `ops/test-lane-registry.json`. CI and docs should
point to registry-backed Make targets rather than hand-maintained pytest marker
expressions.

## Change-Type Gates

| Change type | Minimum local check | Extra check |
| --- | --- | --- |
| Docs only | `make test-public` | `make sync-public-policy-check` if public boundaries changed |
| Python runtime | `make static` | focused `.venv/bin/python -m pytest ...` or `make test` |
| Make or CI lane | `make static` | `make report-contracts-core` |
| Schema/report contract | `make report-contracts-core` | regenerate artifacts, then `make test-artifact-finalization` |
| Public export policy | `make sync-public-policy` | `make public-check` |
| Release evidence | `make release-check` | `make release-check-all-surfaces` when export/public surfaces changed |
| Supply chain | `make supply-chain-check` | `make sbom-readiness-check` for SBOM readiness |

## Editing Discipline

- Prefer Make targets and `llm-wiki-*` console scripts in docs.
- Use canonical package paths such as `ops.scripts.release.release_smoke` when a module path is needed.
- Keep flat `ops.scripts.<name>` references as compatibility notes only.
- If a contract changes, update the related docs, tests, schema, and policy in the same patch.
