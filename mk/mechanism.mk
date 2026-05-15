OUTCOME_METRICS_OUT ?= ops/reports/outcome-metrics.json
OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json
OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json
AUTO_IMPROVE_READINESS_OUT ?= ops/reports/auto-improve-readiness.json
AUTO_IMPROVE_READINESS_CANDIDATE_OUT ?= tmp/auto-improve-readiness.candidate.json
MECHANISM_RUN_ARGS ?=

.PHONY: auto-improve-readiness auto-improve-readiness-report auto-improve-readiness-report-body mechanism-review mutation-proposal run-mechanism-experiment-linux-tmp outcome-metrics routing-provenance-aggregate outcome-provenance-gate-policy 

auto-improve-readiness: refresh-generated-core
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit $$status

auto-improve-readiness-report: refresh-generated-core auto-improve-readiness-report-body

auto-improve-readiness-report-body:
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit 0

mechanism-review:
	$(PYTHON) -m ops.scripts.mechanism_review --vault "$(VAULT)"

mutation-proposal:
	$(PYTHON) -m ops.scripts.mutation_proposal --vault "$(VAULT)"

run-mechanism-experiment-linux-tmp:
	TMPDIR=/tmp TEMP=/tmp TMP=/tmp $(PYTHON) -m ops.scripts.run_mechanism_experiment --vault "$(VAULT)" $(MECHANISM_RUN_ARGS)

outcome-metrics:
	$(PYTHON) -m ops.scripts.outcome_metrics --vault "$(VAULT)"

routing-provenance-aggregate:
	$(PYTHON) -m ops.scripts.observability_routing_provenance_runtime --vault "$(VAULT)"

outcome-provenance-gate-policy: outcome-metrics routing-provenance-aggregate
	$(PYTHON) -m ops.scripts.outcome_provenance_gate_policy --vault "$(VAULT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_OUT)" --schema ops/schemas/outcome-provenance-gate-policy.schema.json --expected-artifact-kind outcome_provenance_gate_policy --expected-producer ops.scripts.outcome_provenance_gate_policy
