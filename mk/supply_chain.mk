SUPPLY_CHAIN_PROVENANCE_OUT ?= ops/reports/supply-chain-provenance.json
SUPPLY_CHAIN_GATE_OUT ?= ops/reports/supply-chain-gate-report.json
SECURITY_ADVISORIES_OUT ?= ops/reports/security-advisories.json
SBOM_EXPORT_MAPPING_OUT ?= ops/reports/sbom-export-mapping.json
SBOM_READINESS_GATE_OUT ?= ops/reports/sbom-readiness-gate-report.json
SUPPLY_CHAIN_ARTIFACT_MODEL_OUT ?= ops/reports/supply-chain-artifact-model.json
CYCLONEDX_SBOM_OUT ?= ops/reports/cyclonedx-bom.json
SPDX_SBOM_OUT ?= ops/reports/spdx-sbom.json
OPENVEX_DRAFT_OUT ?= ops/reports/openvex-draft.json
IN_TOTO_STATEMENT_OUT ?= ops/reports/in-toto-statement.json
SIGSTORE_BUNDLE_OUT ?= ops/reports/sigstore-bundle-verification.json
SIGSTORE_BUNDLE_REF ?=
SUPPLY_CHAIN_BENCHMARK_OUT ?= ops/reports/supply-chain-benchmark.json
ALLOW_FINALITY_INVALIDATION ?=

.PHONY: supply-chain-provenance sbom-export-mapping supply-chain-check security-advisories sbom-readiness-check supply-chain-artifact-model cyclonedx-sbom spdx-sbom openvex-draft in-toto-statement sigstore-bundle supply-chain-benchmark supply-chain-finality-writer-guard supply-chain-artifacts-cached openvex-draft-cached provenance-check

supply-chain-provenance:
	$(PYTHON) -m ops.scripts.supply_chain_provenance --vault "$(VAULT)" --out "$(SUPPLY_CHAIN_PROVENANCE_OUT)"

sbom-export-mapping:
	$(PYTHON) -m ops.scripts.sbom_export_mapping --vault "$(VAULT)" --out "$(SBOM_EXPORT_MAPPING_OUT)"

supply-chain-check: uv-lock-check supply-chain-provenance
	$(PYTHON) -m ops.scripts.supply_chain_gate_runtime --vault "$(VAULT)"

security-advisories:
	$(PYTHON) -m ops.scripts.security_advisories --vault "$(VAULT)" --out "$(SECURITY_ADVISORIES_OUT)"

sbom-readiness-check: sbom-export-mapping
	$(PYTHON) -m ops.scripts.sbom_readiness_gate_runtime --vault "$(VAULT)"

supply-chain-artifact-model: security-advisories sbom-export-mapping
	$(PYTHON) -m ops.scripts.supply_chain_artifact_model --vault "$(VAULT)" --out "$(SUPPLY_CHAIN_ARTIFACT_MODEL_OUT)"

cyclonedx-sbom: sbom-readiness-check
	$(PYTHON) -m ops.scripts.cyclonedx_sbom --vault "$(VAULT)" --out "$(CYCLONEDX_SBOM_OUT)"

spdx-sbom: supply-chain-artifact-model
	$(PYTHON) -m ops.scripts.spdx_sbom --vault "$(VAULT)" --out "$(SPDX_SBOM_OUT)"

openvex-draft: cyclonedx-sbom
	$(PYTHON) -m ops.scripts.openvex_draft --vault "$(VAULT)" --out "$(OPENVEX_DRAFT_OUT)"

in-toto-statement: spdx-sbom openvex-draft
	$(PYTHON) -m ops.scripts.in_toto_statement --vault "$(VAULT)" --out "$(IN_TOTO_STATEMENT_OUT)"

sigstore-bundle: in-toto-statement
	$(PYTHON) -m ops.scripts.sigstore_bundle --vault "$(VAULT)" --out "$(SIGSTORE_BUNDLE_OUT)" $(if $(SIGSTORE_BUNDLE_REF),--bundle-ref "$(SIGSTORE_BUNDLE_REF)",)

supply-chain-benchmark:
	$(PYTHON) -m ops.scripts.supply_chain_benchmark --vault "$(VAULT)" --out "$(SUPPLY_CHAIN_BENCHMARK_OUT)"

supply-chain-finality-writer-guard:
	@if [ "$(ALLOW_FINALITY_INVALIDATION)" = "1" ]; then \
		echo "supply-chain finality writer guard bypassed; finish with make release-finality-resettle-current-or-refresh"; \
	elif $(MAKE) --no-print-directory release-closeout-finality-verify >/dev/null 2>&1; then \
		echo "supply-chain artifacts are finality-tracked writers; run them before finality or set ALLOW_FINALITY_INVALIDATION=1 and finish with make release-finality-resettle-current-or-refresh"; \
		exit 1; \
	fi

supply-chain-artifacts-cached: supply-chain-finality-writer-guard
	$(PYTHON) -m ops.scripts.supply_chain_artifacts --vault "$(VAULT)" --provenance-out "$(SUPPLY_CHAIN_PROVENANCE_OUT)" --gate-out "$(SUPPLY_CHAIN_GATE_OUT)" --security-advisories-out "$(SECURITY_ADVISORIES_OUT)" --mapping-out "$(SBOM_EXPORT_MAPPING_OUT)" --readiness-out "$(SBOM_READINESS_GATE_OUT)" --model-out "$(SUPPLY_CHAIN_ARTIFACT_MODEL_OUT)" --cyclonedx-out "$(CYCLONEDX_SBOM_OUT)" --spdx-out "$(SPDX_SBOM_OUT)" --openvex-out "$(OPENVEX_DRAFT_OUT)" --in-toto-out "$(IN_TOTO_STATEMENT_OUT)" --sigstore-out "$(SIGSTORE_BUNDLE_OUT)" $(if $(SIGSTORE_BUNDLE_REF),--sigstore-bundle-ref "$(SIGSTORE_BUNDLE_REF)",)

openvex-draft-cached: supply-chain-artifacts-cached

provenance-check: supply-chain-check
