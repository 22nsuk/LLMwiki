# Orchestration Decomposition (P1) + Artifact Governance Simplification (P2) — Execution Plan

**Date**: 2026-05-13
**Scope**: Public mirror (`ops/`, `tests/`, `tools/`, `.codex/agents/`, `.github/`, root docs)
**Decision**: P1 first, then P2. Option A (re-export) for script subpackaging. `ops/operator/` for operator-only artifacts.
**Review amendment**: P1 re-export must use a proxy alias that preserves module identity, not eager module-copying. P2 must audit path dependencies before moving any schema-backed `ops/reports/` artifact.

---

## 0. Execution Order

```
P1-A: Makefile domain decomposition (mk/*.mk)
P1-B: ops/scripts/ subpackaging (Option A: re-export)
P1-C: Test / schema / contract file updates
P1-D: Verification (make static → test-fast → check)
       ↓ Transition Gate: all P1 AC pass
P2-A: Artifact 4-class taxonomy + ops/operator/ creation
P2-B: Makefile variable / recipe path migration
P2-C: Refresh chain DAGification + deduplication
P2-D: Verification (make static → test-fast → check)
```

---

## P1. Orchestration Decomposition

### P1-A. Makefile Domain Decomposition

**Principle**: Root `Makefile` keeps only shared interpreter/vault variables, entrypoint aliases, and `include mk/*.mk`. Domain variables and all domain target definitions move to `mk/*.mk`.

| File | Domain | Targets / Variables |
|------|--------|-------------------|
| `mk/core.mk` | Dev env, common variables | `dev-install`, `bootstrap-preflight`, common vars (lines 1–100) |
| `mk/static.mk` | Static analysis | `static`, `ruff`, `typecheck`, `ruff-strict-preview`, `mypy-strict-preview` |
| `mk/test.mk` | Test wrappers | `test-*`, `unit-tests-*`, `fast-smoke`, `test-execution-summary-*` |
| `mk/eval.mk` | Eval / gating | `lint`, `eval`, `stage2-eval`, `planning-gate`, `warning-budget`, `complexity-budget`, `function-budget-refactor-proposals` |
| `mk/artifact.mk` | Artifact management | `artifact-freshness`, `generated-artifact-index`, `archive-execution-manifest`, `tmp-clean`, `refresh-generated-*` |
| `mk/registry.mk` | Registry / raw intake | `registry-preflight`, `raw-registry-*`, `raw-intake-*`, `manifest` |
| `mk/mechanism.mk` | Mechanism / experiments | `mechanism-review`, `mutation-proposal`, `auto-improve-*`, `outcome-metrics`, `routing-provenance-aggregate`, `run-mechanism-experiment` |
| `mk/release.mk` | Release / closeout | `release-*`, `learning-*`, `operator-release-summary`, `external-report-*` |
| `mk/public.mk` | Public mirror | `public-export`, `public-check-*`, `sync-public-policy` |
| `mk/supply_chain.mk` | Supply chain / SBOM | `supply-chain-*`, `sbom-*`, `cyclonedx-*`, `spdx-*`, `openvex-*`, `in-toto-*`, `sigstore-*` |

**Root Makefile residue**:
```makefile
VENV_DIR ?= .venv
VENV_PYTHON ?= $(VENV_DIR)/bin/python
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)
BOOTSTRAP_PYTHON ?= python3
VAULT ?= .

include mk/core.mk
include mk/static.mk
include mk/test.mk
include mk/eval.mk
include mk/artifact.mk
include mk/registry.mk
include mk/mechanism.mk
include mk/release.mk
include mk/public.mk
include mk/supply_chain.mk

export PYTEST_DISABLE_PLUGIN_AUTOLOAD

# Aggregate entrypoints (100% backward-compatible aliases)
.PHONY: check check-finalized check-clean check-serial check-all check-strict
check: static artifact-freshness-check registry-preflight lint eval stage2-eval planning-gate unit-tests
# ... (existing aliases preserved)
```

The `export PYTEST_DISABLE_PLUGIN_AUTOLOAD` line stays after the includes so `mk/test.mk` can assign `PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1` before Make exports it.

### P1-B. ops/scripts/ Subpackaging (Option A: re-export)

**Principle**: Physical move to subdirectories, but preserve `ops.scripts.xxx` and `python -m ops.scripts.xxx` via a lazy proxy re-export in `ops/scripts/__init__.py`.

```
ops/scripts/
├── __init__.py              # backward-compatible re-export hub
├── core/                    # artifact_io, output, policy, schema, runtime_context, filesystem, path, command, yaml
├── test/
├── eval/
├── release/
├── public/
├── supply_chain/
├── registry/
├── mechanism/
└── learning/
```

**Re-export implementation** (lazy proxy, module-identity preserving):
```python
# ops/scripts/__init__.py (P1 Phase 1)
from pathlib import Path
import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_loader

_SUBPACKAGES = ["core", "test", "eval", "release", "public", "supply_chain", "registry", "mechanism", "learning"]

class _ProxyLoader(Loader):
    def __init__(self, target_name: str) -> None:
        self._target_name = target_name

    def exec_module(self, module) -> None:
        target = __import__(self._target_name, fromlist=["__name__"])
        sys.modules[module.__name__] = target
        module.__dict__.update(target.__dict__)

    def get_code(self, fullname):
        target = __import__(self._target_name, fromlist=["__name__"])
        source = Path(target.__file__).read_text(encoding="utf-8")
        return compile(source, target.__file__, "exec")

class _ReexportFinder(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        # Map ops.scripts.<name> to the unique ops.scripts.<subpackage>.<name>.
        ...

sys.meta_path.insert(0, _ReexportFinder())
```

Do not use eager imports with `except Exception: continue`: that hides real import failures and can leave `import ops.scripts.xxx` as a copied module dict instead of the same object as `ops.scripts.<subpackage>.xxx`. The acceptance test must assert alias identity and monkeypatch behavior, not only import success.

**Files to update**:
1. `ops/scripts/` → create 9 subdirectories and move script modules with `git mv` when this is a Git worktree
2. `ops/scripts/__init__.py` → add re-export logic
3. `ops/script-module-surfaces.json` → update all `path` fields to subpackage paths
4. `ops/script-output-surfaces.json` → regenerate via `python -m ops.scripts.script_output_surfaces` (flat compatibility) or the canonical physical module path
5. `tests/test_script_module_surface_contract.py` → verify traversal still works
6. `tests/test_writer_output_paths.py` → verify regenerated registry matches AST
7. `tests/test_import_fallback_contract.py` → verify flat alias identity, `python -m ops.scripts.xxx`, and unique script stems across subpackages

### P1-C. Test / Schema / Contract Updates

| File | Change |
|------|--------|
| `ops/script-module-surfaces.json` | all `path` fields → `ops/scripts/{subpkg}/` paths |
| `ops/schemas/script-module-surfaces.schema.json` | Allow subpackage depth in `path` pattern (optional) |
| `tests/test_script_module_surface_contract.py` | Verify `__all__` sync across subpackages |
| `tests/test_writer_output_paths.py` | Verify regenerated `script-output-surfaces.json` |
| `.github/workflows/ci.yml` | Verify no hardcoded flat-path references to moved scripts |
| `.github/workflows/release.yml` | Use canonical nested module paths for release artifact attestation commands |
| `tests/test_import_fallback_contract.py` | Verify flat re-export alias identity and `python -m ops.scripts.xxx` compatibility |
| `tests/test_makefile_static_gates.py` | Verify root `Makefile` keeps only common variables and exports pytest plugin policy after includes |
| `tests/test_source_trace_runtime.py` | Verify historical `ops/scripts/<module>.py` source traces resolve to the unique subpackage relocation |
| `ops/scripts/public/public_surface_policy.py` | Include `mk/` in the exported public surface, because root `Makefile` now depends on `mk/*.mk` |
| `AGENTS.md` / `README.md` | Document `mk/` as public-safe runtime surface |

**Source trace compatibility**: Full-vault history includes append-only pages and reports that may still cite flat `ops/scripts/<module>.py` paths. Do not bulk-edit those historical traces. `source_trace_runtime` must resolve a flat script path to the unique moved file under `ops/scripts/<subpackage>/<module>.py`; ambiguous or missing relocations should still report a missing target.

### P1-D. Verification Order

```bash
make static
make test-fast
make test-public
make test-artifact-finalization
make check
```

**P1 Completion Criteria**:
- [ ] `make static` passes (ruff, mypy)
- [ ] `make test-fast` passes (fast lane 100%)
- [ ] `make test-public` passes (public mirror contract)
- [ ] `make test-artifact-finalization` passes (script-output-surfaces.json freshness)
- [ ] `make check` passes (full gate)
- [ ] Root Makefile only includes `mk/*.mk` and defines entrypoint aliases
- [ ] Public export includes `mk/*.mk`; exported public mirror passes `make public-check`
- [ ] `ops/scripts/` is reorganized into 9 subpackages
- [ ] Existing `python -m ops.scripts.xxx` and `import ops.scripts.xxx` paths remain functional
- [ ] Flat alias imports return the same module object as the canonical subpackage import, so monkeypatching and `patch("ops.scripts.xxx...")` keep working
- [ ] Historical flat `ops/scripts/<module>.py` source traces resolve to the unique moved subpackage file
- [ ] `script-module-surfaces.json` paths updated to subpackage paths
- [ ] `script-output-surfaces.json` regenerated and matches live AST inventory

---

## P2. Generated Artifact Governance Simplification

### P2-A. Artifact 4-Class Taxonomy + ops/operator/ Creation

| Class | Definition | Long-term location | Checked-in? | P2 Phase 1 action |
|-------|-----------|-------------------|-------------|-------------------|
| **source contract** | Directly imported/verified by tests/scripts | `ops/` root | ✅ Required | Keep as-is |
| **release authority** | Required for release gate; signing/attestation target | `ops/authority/` (P2 Phase 2) | ✅ Required | Keep in `ops/reports/` for P2 Phase 1 |
| **operator-only** | Operational reference; read by CI/tests but not release-critical | `ops/operator/` (P2 Phase 1) | ✅ Optional | Move only after path-dependency audit |
| **tmp/advisory** | Regeneratable; draft/snapshot/diagnostic | `tmp/` or `ops/advisory/` (P2 Phase 2) | ❌ .gitignore | Move to `tmp/` or keep in `ops/reports/` for P2 Phase 1 |

**P2 Phase 1 amendment: do not blanket-move the old list.**

The current repository binds several generated reports to release closeout policies, fixed-point plans, schema samples, docs, and tests. These are release-authority or source-contract artifacts until the dependent paths are migrated in the same change:
- `artifact-freshness-report.json`
- `generated-artifact-index.json`
- `release-risk-taxonomy-matrix.json`
- `release-risk-taxonomy-matrix.md`
- `manual-mutate-defect-registry.json`
- `defect-escape-closures.json`
- `rework-closures.json`
- any report named by `ops/policies/release-closeout-*.json`, release evidence/cohort scripts, or report-contract tests

P2 Phase 1 should therefore start with a path-dependency audit:

```bash
rg -n "ops/reports/<artifact-name>" ops tests mk .github README.md ARCHITECTURE.md
```

Only artifacts with no release gate, fixed-point, schema-sample, or report-contract dependency can move directly to `ops/operator/`. Reports that still serve as release evidence may move only as an explicit contract migration that updates Make variables, policies, tests, schema samples, docs, artifact freshness/index scans, and release closeout readers together.

### P2-B. Makefile Variable / Recipe Path Migration

**Key change**: `*_OUT` variables in `mk/*.mk`, but only for artifacts that passed the P2-A path-dependency audit.

```makefile
# mk/artifact.mk
# Keep release-authority reports in ops/reports/ during P2 Phase 1.
ARTIFACT_FRESHNESS_OUT ?= ops/reports/artifact-freshness-report.json
GENERATED_ARTIFACT_INDEX_OUT ?= ops/reports/generated-artifact-index.json

# Example audited operator-only output.
OPERATOR_RELEASE_SUMMARY_OUT ?= ops/operator/operator-release-summary.json

# mk/public.mk
# Keep public-check-summary in its current location unless its release/report-contract
# consumers are migrated in the same patch.
PUBLIC_CHECK_SUMMARY_OUT ?= ops/reports/public-check-summary.json
```

**Scripts requiring scan-path updates**:
- `ops/scripts/artifact_freshness_runtime.py` → add `ops/operator/` to scan targets while preserving existing `ops/reports/` coverage
- `ops/scripts/generated_artifact_index.py` → add `ops/operator/` to scan targets while preserving existing `ops/reports/` coverage

### P2-C. Refresh Chain DAGification

**Problem**: `release-evidence-closeout` calls `generated-artifact-index` 4×, `artifact-freshness` 3×, `tmp-json-clean` 4×.

**Solution**: Decompose into 3 phases with explicit dependencies. Each phase calls index/freshness exactly once at the end.

```makefile
# mk/release.mk
release-evidence-closeout: release-evidence-closeout-phase-3

release-evidence-closeout-phase-1: refresh-generated-core bootstrap-preflight registry-preflight static report-schema-samples-check external-report-reference-manifest-release-check auto-improve-readiness-report-body release-smoke-full release-source-package-check test-execution-summary-report-contract-refresh tmp-json-clean

release-evidence-closeout-phase-2: release-evidence-closeout-phase-1 generated-artifact-index artifact-freshness test-execution-summary-full-refresh public-check-summary learning-claim-evidence-bundle learning-confirmed-evidence-cohort learning-claim-unlock-review learning-delta-scoreboard release-closeout-summary learning-readiness-signoff-revalidation release-evidence-cohort auto-improve-readiness-report-body release-evidence-dashboard release-lane-summary release-clean-blocker-ledger tmp-json-clean

release-evidence-closeout-phase-3: release-evidence-closeout-phase-2 generated-artifact-index artifact-freshness test-artifact-finalization release-closeout-post-check-finalizer-dry-run release-closeout-fixed-point tmp-json-clean release-closeout-finality-verify
```

### P2-D. Verification Order

```bash
make static
make test-fast
make artifact-freshness          # verify ops/operator/ is scanned
make generated-artifact-index    # verify ops/operator/ is indexed
make test-artifact-finalization
make public-check
make release-smoke-fast
make check
```

**P2 Completion Criteria**:
- [ ] `ops/operator/` created and populated with operator-only artifacts
- [ ] Path-dependency audit proves no moved artifact is still consumed as release authority or source contract
- [ ] `make static` passes
- [ ] `make test-fast` passes
- [ ] `make artifact-freshness` scans `ops/operator/` correctly
- [ ] `make generated-artifact-index` indexes `ops/operator/` correctly
- [ ] `make test-artifact-finalization` passes with new paths
- [ ] `release-evidence-closeout` deduplicates index/freshness to ≤3 calls each
- [ ] `tmp-json-clean` reduced to ≤2 calls
- [ ] Canonical and operator-only artifacts are physically separated

---

## Risk Matrix

| Risk | Severity | Mitigation |
|------|----------|------------|
| `ops/scripts/` re-export failure breaks imports | High | Lazy proxy re-export in `__init__.py`. Prioritize `test_import_fallback_contract.py` and `test_script_module_surface_contract.py`. |
| Flat alias module copies break monkeypatching | High | Assert `import ops.scripts.xxx` is the same object as `ops.scripts.<subpackage>.xxx`, and verify `patch("ops.scripts.xxx...")` mutates the canonical module. |
| Historical source traces point at moved flat script paths | High | Resolve unique `ops/scripts/<module>.py` relocations in `source_trace_runtime`; preserve missing-target errors for ambiguous relocations. |
| Public export omits `mk/*.mk` after Makefile decomposition | High | Add `mk/` to public surface policy and root `.gitignore`; verify with `make public-check`. |
| `script-module-surfaces.json` path omissions | Medium | Batch-convert all `path` fields. Tests detect omissions. |
| P2 misclassifies release authority as operator-only | High | Run path-dependency audit before moving; keep artifacts referenced by release closeout policies, fixed-point plans, schema samples, or report-contract tests in `ops/reports/` until a full contract migration. |
| `artifact_freshness_runtime.py` misses `ops/operator/` | High | Update scan target list inside script. Verify with `make artifact-freshness`. |
| `generated_artifact_index.py` misses `ops/operator/` | High | Update scan target list. Verify with `make generated-artifact-index`. |
| `release-evidence-closeout` DAG misses dependency | Medium | Compare dry-run target invocation order with original sequential log. |
| CI artifact upload hardcoded paths | Medium | Search `.github/workflows/*.yml` for `ops/reports/` references, update to `ops/operator/` where needed. |
| Git history lost during file moves | Low | Use `git mv` for all file relocations when this is a Git worktree; in a non-Git mirror, document the filesystem move and rely on path contracts/tests. |

---

## Step-by-Step Checklist (For Actual Execution)

### P1 Steps
1. Create `mk/` directory and `mk/*.mk` files
2. Reduce root `Makefile` to common variables + includes + aliases
3. `make static` → `make test-fast`
4. Create 9 subdirectories under `ops/scripts/`
5. Move script modules into subpackages, using `git mv` when this is a Git worktree
6. Add lazy proxy re-export logic to `ops/scripts/__init__.py`
7. Update `ops/script-module-surfaces.json` paths
8. Regenerate `ops/script-output-surfaces.json`
9. Add tests for alias identity, `python -m ops.scripts.xxx`, unambiguous script stems, root Makefile residue, and historical source-trace relocation
10. Add `mk/` to public surface policy and run `make sync-public-policy`
11. Run `make static` → `make test-fast` → `make test-public` → `make test-artifact-finalization`
12. Run `make public-check`
13. Run `make check`

### P2 Steps
1. Create `ops/operator/`
2. Audit each candidate with `rg -n "ops/reports/<artifact-name>" ops tests mk .github README.md ARCHITECTURE.md`
3. Move only audited operator-only artifacts from `ops/reports/` to `ops/operator/`
4. Update `*_OUT` variables in `mk/*.mk` for moved artifacts only
5. Update scan targets in `artifact_freshness_runtime.py` and `generated_artifact_index.py`
6. DAGify `release-evidence-closeout` in `mk/release.mk`
7. Update CI workflow artifact upload paths if needed
8. Run `make static` → `make test-fast` → `make artifact-freshness` → `make generated-artifact-index`
9. Run `make test-artifact-finalization` → `make public-check` → `make release-smoke-fast`
10. Run `make check`
11. Run `make sync-public-policy`
