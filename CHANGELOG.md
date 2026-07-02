# Changelog

## 2026-07 — Source-derived sync convergence

- Added `make sync-derived` and `make sync-derived-check` as the single operator
  entrypoints for tracked source-derived projections, and moved CI's fast-tier
  stale projection check to the new aggregate.
- Added registry-derived pytest marker registration and converted the
  `schema_static_smoke` selector pack to a non-persistent marker-owned pack.
- Added a non-writing `make-target-inventory-check` lane and wired it into
  `sync-derived-check` for write/check parity on Make inventory diagnostics.
- Converted the `release_closeout_regression` selector pack to a function-marker
  owned pack, removing another hand-maintained selector list.
- Converted the curated `fast_smoke` precheck to a marker-owned pack and removed
  stale compatibility-alias deselects so the generated selector stays pure `-m`.
- Converted the default `make test` boundary pack to the
  `default_test_boundary` marker so the boundary chain no longer carries a
  duplicated explicit selector list.
- Converted the remaining projected explicit selector packs
  `runtime_hotspot_smoke`, `report_contract_core`, and `release_sealing_core`
  to marker-owned packs, preserving nodeid parity with their prior selector
  lists, and keeping the `release_sealing_core` node IDs co-marked with
  `release_sealing` for compatibility.
- Removed the obsolete explicit-selector fallback from the generated selector
  projection path, so `PACK_VARIABLES` can only expose marker-owned pytest
  packs; the remaining explicit packs are release/source-package wrapper lanes.
- Reduced script lifecycle policy drift by deriving module paths from
  `canonical_module`, keeping legacy `path` schema-compatible but no longer
  storing it in the policy registry.
- Added `make script-module-surfaces` and `make script-module-surfaces-check`
  to derive stable import exports and direct-entrypoint flags from source while
  keeping module `role` as the manually curated contract field.
- Removed the low-use optional codebase-memory-mcp sidecar targets, export
  helper, template, and docs while retaining local `.codebase-memory` public
  leak protection.
- Wired CLI surface inventory coverage into anti-slop admission so
  `make-target-inventory-check` and `sync-derived-check` fail when pyproject,
  Make, or direct fallback script surfaces are missing lifecycle policy entries.

## 2026-06 — Runtime decomposition, release evidence, and public mirror hygiene

- Continued the runtime-codehealth-hardening sprint: extracted readiness remediation,
  dashboard status, closeout render/envelope, and mutation proposal helpers while
  keeping façade contracts and golden digests stable.
- Hardened artifact freshness stale routing, source-identity ownership, and Sigstore
  verification paths; tightened release CI evidence and supply-chain closeout gates.
- Decoupled external-report action matrix finality binding and stabilized release
  readiness status lanes, auto-improve maintenance empty-queue handling, and
  envelope maintenance action plans.
- Added compatibility alias deprecation tracking extensions and refreshed related
  schema fixtures and tests.
- Included `CHANGELOG.md` in the public export allowlist so public mirror history
  stays aligned with doc-graph `ROOT_DOCS`.

## CycloneDX / OpenVEX SBOM draft surface

- Added `uv.lock` dependency edge parsing to the repo-native supply-chain provenance report.
- Added CycloneDX 1.6 JSON SBOM generation with `make cyclonedx-sbom` and `ops/reports/cyclonedx-bom.json`.
- Added SBOM readiness gate reporting with `make sbom-readiness-check` and `ops/reports/sbom-readiness-gate-report.json`.
- Added OpenVEX draft shell generation with `make openvex-draft` and `ops/reports/openvex-draft.json`.
- Documented the SPDX parallel emitter decision as deferred until CycloneDX graph and OpenVEX applicability semantics stabilize.
- Kept in-toto/SLSA provenance, Sigstore bundle, PyPI Trusted Publishing attestations, and default release hard-gate promotion as follow-up hardening.

## SBOM/export mapping audit surface

- Added `ops/scripts/sbom_export_mapping.py` and `ops/schemas/sbom-export-mapping.schema.json`.
- Added `make sbom-export-mapping` to generate `ops/reports/sbom-export-mapping.json`.
- Added `uv.lock` to the public export surface and generated public `.gitignore` contract.
- Hardened release manifest and public export file enumeration so symlinked files are excluded.
- Excluded the local `review/` patch workspace from release manifest inventory.
- Added focused tests for SBOM/export mapping and manifest/export symlink safety.

## Docs update: provenance gate / repo-native provenance

- README에 `make supply-chain-check`, `make provenance-check`, `make release-provenance-clean` 사용 경로를 추가했습니다.
- README에 `run-artifact-fingerprint.json`의 `repo_provenance_snapshot` 설명을 추가했습니다.
- README와 `ops/README.md`에 `ci_install_proof` / `lock_evidence` 경계, gate report 경로, optional strict target 운영 계약을 반영했습니다.
- `ops/README.md`에 generator(`supply_chain_provenance.py`)와 evaluator(`supply_chain_gate_runtime.py`) 분리 구조를 문서화했습니다.

# Supply-chain / Provenance patch bundle

Included changes:

- Added structured `ci_install_proof` and `lock_evidence` to repo-level supply-chain provenance.
- Added strict evaluator `ops/scripts/supply_chain_gate_runtime.py` and its schema.
- Added Make targets `supply-chain-check`, `provenance-check`, and `release-provenance-clean`.
- Added a dedicated CI job for the supply-chain gate on Python 3.12.
- Extended run artifact fingerprint with `repo_provenance_snapshot`.
- Updated schema fixtures and tests to keep generator/gate/fingerprint contracts aligned.

Important corrections relative to the candidate patch:

- Fixed the gate to inspect `exists` and `parser_status.status` instead of a non-existent `inputs[*].status` field.
- Normalized CI install command capture so the proof records the actual pip command text rather than YAML prefixes.
- Added dependency installation to the new CI job before invoking `make supply-chain-check`.
- Kept `release-clean` unchanged and introduced `release-provenance-clean` separately to preserve existing release-smoke contracts.
