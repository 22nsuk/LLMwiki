# SBOM / OpenVEX / provenance hardening review

Date: 2026-04-20
Review basis: uploaded repository snapshot + `improvement-observations.json`

## Executive summary

The latest observation was valid: the existing `make openvex-draft` chain repeatedly re-traversed the same provenance and manifest surfaces before producing the final OpenVEX artifact. The repository already had the right *logical* layering (provenance -> mapping -> readiness -> CycloneDX -> OpenVEX), but it did not yet have an efficient *execution* path that reused intermediate artifacts in-process.

The most important near-term risk was therefore not schema correctness but operational cost and drift risk:

1. repeated traversal in local/CI runs,
2. weak practical reuse of already-generated CycloneDX output,
3. CI continuing to call the strict path even after a faster path existed,
4. future hardening work having no clean orchestration point to attach to.

I addressed the highest-value items directly in code.

## Confirmed latest observation

The uploaded observation identified that `openvex-draft` indirectly reran `sbom-export-mapping` and `cyclonedx-sbom`, causing repeated traversal of release/public/dependency inputs before the final OpenVEX draft was emitted. That observation is accurate and should be treated as a real pipeline inefficiency, not merely a cosmetic Makefile issue.

## What I changed

### 1) Added a shared in-process artifact pipeline

New script:

- `ops/scripts/supply_chain_artifacts.py`

This script generates the following outputs in one process while reusing already-built in-memory structures:

- `ops/reports/supply-chain-provenance.json`
- `ops/reports/supply-chain-gate-report.json`
- `ops/reports/sbom-export-mapping.json`
- `ops/reports/sbom-readiness-gate-report.json`
- `ops/reports/cyclonedx-bom.json`
- `ops/reports/openvex-draft.json`

This is the most robust way to reduce repeated scans without weakening correctness.

### 2) Kept the strict path intact and added an explicit fast path

Updated `Makefile`:

- existing strict chain remains:
  - `sbom-export-mapping`
  - `sbom-readiness-check`
  - `cyclonedx-sbom`
  - `openvex-draft`
- new fast path added:
  - `supply-chain-artifacts-cached`
  - `openvex-draft-cached`

This preserves the original correctness-first contract while making the optimized path explicit.

### 3) Wired the CI workflow to the fast path

Updated `.github/workflows/ci.yml` so the artifact generation step now calls:

- `make openvex-draft-cached`

Without this change, the performance fix would have existed in the repository but not in the default operational path.

### 4) Refactored generators to accept reusable in-memory intermediates

Updated:

- `ops/scripts/supply_chain_gate_runtime.py`
- `ops/scripts/sbom_export_mapping.py`
- `ops/scripts/sbom_readiness_gate_runtime.py`
- `ops/scripts/cyclonedx_sbom.py`
- `ops/scripts/openvex_draft.py`

These now accept optional in-memory reports/BOM objects so the new orchestration layer can avoid redundant recomputation.

### 5) Hardened OpenVEX reuse behavior

`openvex_draft.py` now validates a reusable on-disk CycloneDX BOM against the CycloneDX schema before trusting it.

Why this matters:

- before this, a stale or malformed preexisting BOM could be silently reused;
- after this, reuse is explicit and schema-backed.

This is a real hardening improvement, but it also means tests or callers that relied on underspecified BOM stubs must now provide valid CycloneDX-shaped input.

### 6) Fixed and extended tests

Added/updated:

- `tests/test_supply_chain_artifacts.py`
- `tests/test_makefile_static_gates.py`
- `tests/test_openvex_draft.py`
- `ops/mypy-allowlist.txt`

## Validation performed

### Test runs

Validated successfully:

- `python3 -m unittest tests.test_supply_chain_provenance tests.test_sbom_export_mapping tests.test_cyclonedx_sbom tests.test_openvex_draft tests.test_sbom_readiness_gate_runtime tests.test_supply_chain_gate_runtime tests.test_supply_chain_artifacts`
- `python3 -m pytest tests/test_makefile_static_gates.py -q -o addopts=''`
- `python3 -m py_compile` on the modified Python modules

Observed warning:

- `tests/test_makefile_static_gates.py` emits `PytestUnknownMarkWarning` for `pytest.mark.public` because the mark is not registered. This does not currently fail the test run, but it is worth cleaning up separately.

### Runtime smoke check

Ran:

- `python3 -m ops.scripts.supply_chain_artifacts --vault /mnt/data/reviewrepo`

The command emitted all six expected report paths.

## Review of the deferred / future work items

### SPDX parallel emitter

Current decision: keep deferred until CycloneDX graph + OpenVEX applicability stabilize.

Assessment: **correct to defer for now**.

Reasoning:

- the repository’s canonical graph/applicability path is still consolidating;
- adding SPDX in parallel before the canonical graph/applicability semantics settle would increase maintenance surface and test burden;
- the better next step is to stabilize the orchestration and artifact contracts first, then add SPDX as a second emitter over a settled intermediate model.

What should be true before enabling SPDX:

- a single canonical internal dependency graph model,
- explicit product identity rules,
- stable statement/justification semantics for applicability,
- compatibility tests that compare CycloneDX and SPDX projections from the same internal model.

### in-toto / SLSA

Assessment: **good hardening follow-up, but should attach to the new orchestrator rather than bypass it**.

Recommended shape:

- reuse the existing provenance report as the source of truth for build inputs and dependency evidence;
- emit an in-toto Statement envelope and SLSA provenance predicate from the same canonical pipeline stage;
- do not fork separate provenance collection logic.

### Sigstore bundle

Assessment: **worth doing after in-toto/SLSA emission exists**.

Recommended rule:

- sign the final distribution artifacts and/or attestation envelopes,
- persist the verification bundle alongside each attestation output,
- keep the bundle as an attached verification artifact rather than inventing a parallel verification format.

### PyPI Trusted Publishing / attestations

Assessment: **appropriate later hardening step**, but it should be modeled as a release/distribution concern, not as a repository-scan concern.

Recommended sequence:

1. stabilize repo-native provenance/SBOM/VEX artifacts,
2. emit in-toto/SLSA provenance from the same canonical model,
3. integrate Trusted Publishing,
4. publish PyPI attestations for actual release files.

## Priority order from this review

### P0 — done now

- introduce reusable in-process supply-chain artifact pipeline,
- add explicit fast-path Make targets,
- route CI to the fast path,
- schema-validate reusable CycloneDX BOM input,
- add regression coverage.

### P1 — should be next

- define a canonical internal artifact model that future SPDX / in-toto / SLSA / Sigstore / PyPI attestation emitters all consume,
- register the custom pytest mark to remove warning noise,
- add a small benchmark or timing assertion so the cached path improvement remains observable over time.

### P2 — after applicability semantics harden

- add advisory ingestion and actual OpenVEX statement authoring rules,
- implement SPDX as a parallel emitter from the shared model,
- add BOM-linking / cross-artifact reference strategy where appropriate.

### P3 — release hardening

- in-toto Statement + SLSA provenance emission,
- Sigstore bundle persistence and verification checks,
- PyPI Trusted Publishing + attestations for built artifacts.

## Problems that would likely appear if execution started without these changes

1. CI and local runs would keep paying repeated scan/traversal cost.
2. Developers could believe OpenVEX was “reusing” CycloneDX when Make still forced a full strict chain first.
3. Later attestation work would likely grow as multiple partially overlapping generators rather than a single canonical pipeline.
4. Reusing a malformed existing BOM could silently pollute OpenVEX output.
5. Documentation and CI could drift away from the intended operational path.

## Remaining recommendations not yet implemented

1. Register the `public` pytest mark in project pytest configuration.
2. Add a lightweight timing benchmark comparing strict vs cached path.
3. Design a canonical cross-artifact identity strategy before SPDX / in-toto expansion.
4. When OpenVEX statements become non-empty, enforce justification/action field rules as first-class validation, not just schema shape.
5. Consider future BOM-Link style references once multiple artifact families are emitted from one release event.

## Files changed

- `.github/workflows/ci.yml`
- `Makefile`
- `README.md`
- `ops/README.md`
- `ops/mypy-allowlist.txt`
- `ops/scripts/supply_chain_gate_runtime.py`
- `ops/scripts/sbom_export_mapping.py`
- `ops/scripts/sbom_readiness_gate_runtime.py`
- `ops/scripts/cyclonedx_sbom.py`
- `ops/scripts/openvex_draft.py`
- `ops/scripts/supply_chain_artifacts.py`
- `tests/test_makefile_static_gates.py`
- `tests/test_openvex_draft.py`
- `tests/test_supply_chain_artifacts.py`

## Bottom line

The repository direction is sound. The deferment of SPDX is still the right call, but the operational gap around repeated traversal and missing orchestration needed to be fixed before pushing further into self-improvement and later attestation hardening. That gap is now materially reduced.
