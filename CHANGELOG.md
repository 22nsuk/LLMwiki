# Changelog

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
