RAW_REGISTRY_OUT ?= ops/raw-registry.json
MANIFEST_OUT ?= ops/manifest.json
RAW_REGISTRY_PREFLIGHT_OUT ?= ops/reports/raw-registry-preflight-report.json
RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT ?= ops/reports/raw-registry-preflight-reproducibility.json
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT ?= ops/reports/raw-registry-cross-environment-matrix.json
RAW_REGISTRY_PREFLIGHT_CHECK_OUT ?= tmp/raw-registry-preflight-report-check.json
RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_CHECK_OUT ?= tmp/raw-registry-preflight-reproducibility-check.json
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_CHECK_OUT ?= tmp/raw-registry-cross-environment-matrix-check.json
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_LINUX_OUT ?= ops/reports/raw-registry-cross-environment-matrix-linux-c-utf8.json
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_WINDOWS_OUT ?= ops/reports/raw-registry-cross-environment-matrix-windows-utf8.json
RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_MACOS_OUT ?= ops/reports/raw-registry-cross-environment-matrix-macos-utf8.json
RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_OUT ?= ops/reports/raw-registry-cross-environment-evidence-bundle.json
RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_STAGING_OUT ?= tmp/raw-registry-cross-environment-evidence-bundle.candidate.json
RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_DIAGNOSTIC_OUT ?= tmp/raw-registry-cross-environment-evidence-bundle-check.json
RAW_INTAKE_ABSORPTION_MATRIX ?= runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json
RAW_INTAKE_ROUTE_PROPOSAL_OUT ?= tmp/raw-intake-route-proposal-report.json
RAW_INTAKE_SOURCE_QUALITY_OUT ?= tmp/raw-intake-source-quality-report.json
RAW_INTAKE_ABSORPTION_CLOSEOUT_OUT ?= tmp/raw-intake-absorption-closeout-report.json

.PHONY: registry-preflight registry-preflight-check raw-registry-cross-environment-matrix raw-registry-cross-environment-profile-matrices raw-registry-cross-environment-evidence-bundle raw-registry-cross-environment-evidence-bundle-check raw-intake-route-proposal raw-intake-source-quality raw-intake-absorption-closeout raw-registry-export manifest sanitize-runs 

registry-preflight:
	$(PYTHON) -m ops.scripts.raw_registry_preflight --vault "$(VAULT)" --out "$(RAW_REGISTRY_PREFLIGHT_OUT)" --reproducibility-out "$(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_OUT)"
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT)" --require-live

registry-preflight-check:
	$(PYTHON) -m ops.scripts.raw_registry_preflight --vault "$(VAULT)" --out "$(RAW_REGISTRY_PREFLIGHT_CHECK_OUT)" --reproducibility-out "$(RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_CHECK_OUT)"
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_CHECK_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_CHECK_OUT)" --require-live

raw-registry-cross-environment-matrix:
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_OUT)"

raw-registry-cross-environment-profile-matrices:
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --profile linux-c-utf8 --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_LINUX_OUT)"
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --profile windows-utf8 --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_WINDOWS_OUT)"
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_matrix --vault "$(VAULT)" --stored-report "$(RAW_REGISTRY_PREFLIGHT_OUT)" --profile macos-utf8 --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_MATRIX_MACOS_OUT)"

raw-registry-cross-environment-evidence-bundle: raw-registry-cross-environment-profile-matrices
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_evidence_bundle --vault "$(VAULT)" --reports-dir "ops/reports" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_STAGING_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_STAGING_OUT)" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_OUT)" --schema ops/schemas/raw-registry-cross-environment-evidence-bundle.schema.json --expected-artifact-kind raw_registry_cross_environment_evidence_bundle --expected-producer ops.scripts.raw_registry_cross_environment_evidence_bundle

raw-registry-cross-environment-evidence-bundle-check:
	$(PYTHON) -m ops.scripts.raw_registry_cross_environment_evidence_bundle --vault "$(VAULT)" --reports-dir "ops/reports" --out "$(RAW_REGISTRY_CROSS_ENVIRONMENT_EVIDENCE_BUNDLE_DIAGNOSTIC_OUT)"

raw-intake-route-proposal:
	$(PYTHON) -m ops.scripts.raw_intake_route_proposal --vault "$(VAULT)" --matrix "$(RAW_INTAKE_ABSORPTION_MATRIX)" --out "$(RAW_INTAKE_ROUTE_PROPOSAL_OUT)"

raw-intake-source-quality:
	$(PYTHON) -m ops.scripts.raw_intake_source_quality --vault "$(VAULT)" --matrix "$(RAW_INTAKE_ABSORPTION_MATRIX)" --out "$(RAW_INTAKE_SOURCE_QUALITY_OUT)" --fail-on-fail

raw-intake-absorption-closeout:
	$(PYTHON) -m ops.scripts.raw_intake_route_proposal --vault "$(VAULT)" --matrix "$(RAW_INTAKE_ABSORPTION_MATRIX)" --out "$(RAW_INTAKE_ABSORPTION_CLOSEOUT_OUT)" --mode absorption_closeout --fail-on-fail
raw-registry-export:
	$(PYTHON) -m ops.scripts.raw_registry_export --vault "$(VAULT)" --out "$(RAW_REGISTRY_OUT)"

manifest:
	$(PYTHON) -m ops.scripts.wiki_manifest --vault "$(VAULT)" --out "$(MANIFEST_OUT)"

sanitize-runs:
	$(PYTHON) -m ops.scripts.sanitize_run_artifacts --vault "$(VAULT)"
