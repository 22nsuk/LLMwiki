OUTCOME_METRICS_OUT ?= ops/reports/outcome-metrics.json
OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json
OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json
AUTO_IMPROVE_READINESS_OUT ?= ops/reports/auto-improve-readiness.json
AUTO_IMPROVE_READINESS_CANDIDATE_OUT ?= tmp/auto-improve-readiness.candidate.json
CODEX_GOAL_CONTRACT_OUT ?= ops/reports/codex-goal-contract.json
CODEX_GOAL_CONTRACT_ID ?= auto-improve-goal
CODEX_GOAL_PROMPT_OUT ?= ops/reports/codex-goal-prompt.json
GOAL_RUN_ID ?= auto-improve-trial
GOAL_CONTRACT_RUN_ID ?= $(GOAL_RUN_ID)
GOAL_ACTIVE_STATE_DIR ?= runs/goal-$(GOAL_CONTRACT_RUN_ID)/state
CODEX_GOAL_ACTIVE_CONTRACT_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/codex-goal-contract.json
GOAL_WORKTREE_GUARD_OUT ?= tmp/goal-worktree-guard.json
GOAL_WORKTREE_MODE ?= git
GOAL_WORKTREE_ALLOW_DIRTY ?=
GOAL_WORKTREE_STRICT ?=
GOAL_RUN_STATUS_OUT ?= ops/reports/goal-run-status.json
GOAL_PROFILE_VERIFICATION_OUT ?= ops/reports/goal-profile-verification.json
GOAL_PROFILE_VERIFICATION_CANDIDATE_OUT ?= tmp/goal-profile-verification.candidate.json
GOAL_PROFILE_VERIFICATION_PROFILE ?=
GOAL_PROFILE_VERIFICATION_APPLY ?=
GOAL_RUNTIME_CLEAN_TRANSIENT_OUT ?= tmp/goal-runtime-clean-transient.json
GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY ?= 1
GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT ?= $(GOAL_RUN_STATUS_OUT)
GOAL_RUNTIME_FIXED_POINT_CHECK_OUT ?= tmp/goal-runtime-fixed-point-check.json
GOAL_SESSION_RESULT_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/auto-improve-goal-session-result.json
GOAL_ACTIVE_RUN_STATUS_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/goal-run-status.json
GOAL_RUN_STATUS_CANDIDATE_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/goal-run-status.candidate.json
GOAL_RUN_STATUS ?= blocked
GOAL_RUN_PROFILE ?= 30m_trial
GOAL_MAX_UNATTENDED_SECONDS ?= 1800
GOAL_RUNNER_TIMEOUT_SECONDS ?= 9000
GOAL_RUNNER_TIMEOUT_GRACE_SECONDS ?= 7200
GOAL_MAX_MINUTES ?= 30
GOAL_MAX_PROPOSALS ?= 1
GOAL_MAX_CONSECUTIVE_FAILURES ?= 1
GOAL_HEARTBEAT_INTERVAL_SECONDS ?= 300
GOAL_CHECKPOINT_INTERVAL_SECONDS ?= 1800
GOAL_CHECKPOINT_COMMAND_TIMEOUT_SECONDS ?= 900
GOAL_MAINTAIN_UNTIL_BUDGET ?= 1
GOAL_MAINTENANCE_INTERVAL_SECONDS ?= 300
GOAL_EXECUTOR ?= codex_exec
GOAL_ARTIFACT_CLASS ?= system_mechanism
GOAL_ALLOW_LEARNING_UNCERTAIN ?=
GOAL_RUN_COMMAND ?= $(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --session-id "$(GOAL_RUN_ID)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --max-minutes "$(GOAL_MAX_MINUTES)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --executor "$(GOAL_EXECUTOR)" --class "$(GOAL_ARTIFACT_CLASS)" $(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,) $(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,) --maintenance-interval-seconds "$(GOAL_MAINTENANCE_INTERVAL_SECONDS)"
GOAL_RESUME_COMMAND ?= $(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --resume-session "$(GOAL_RUN_ID)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --max-minutes "$(GOAL_MAX_MINUTES)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --executor "$(GOAL_EXECUTOR)" --class "$(GOAL_ARTIFACT_CLASS)" $(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,) $(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,) --maintenance-interval-seconds "$(GOAL_MAINTENANCE_INTERVAL_SECONDS)"
GOAL_FINAL_STATUS ?= stopped
GOAL_COMPLETED_AT ?=
GOAL_LADDER_PROFILES ?= 30m_trial 6h_ramp 2d_candidate 5d_sustained
GOAL_RUN_LOG_DIR ?= build/goal-runs
GOAL_LADDER_RUN_ID ?= goal-ladder-$(shell date -u +%Y%m%dT%H%M%SZ)
GOAL_LADDER_CONTRACT_RUN_ID ?= $(GOAL_LADDER_RUN_ID)
GOAL_LADDER_LOG ?= $(GOAL_RUN_LOG_DIR)/$(GOAL_LADDER_RUN_ID).log
GOAL_LADDER_PID ?= $(GOAL_RUN_LOG_DIR)/$(GOAL_LADDER_RUN_ID).pid
MECHANISM_RUN_ARGS ?=

.PHONY: auto-improve-readiness auto-improve-readiness-report auto-improve-readiness-report-body auto-improve-readiness-worktree-guard codex-goal-contract codex-goal-prompt codex-goal-client goal-prompt auto-improve-goal-contract goal-runtime-refresh goal-runtime-publish-snapshot goal-runtime-reconcile goal-runtime-clean-transient goal-runtime-fixed-point-check long-run-preflight-clean auto-improve-goal-preflight auto-improve-goal-run auto-improve-goal-status auto-improve-goal-resume auto-improve-goal-finalize auto-improve-goal-run-artifacts auto-improve-goal-ladder-run auto-improve-goal-ladder-start goal-profile-verification goal-worktree-guard mechanism-review mutation-proposal run-mechanism-experiment-linux-tmp outcome-metrics routing-provenance-aggregate outcome-provenance-gate-policy

auto-improve-readiness: refresh-generated-core auto-improve-readiness-worktree-guard
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit $$status

auto-improve-readiness-report: refresh-generated-core auto-improve-readiness-report-body

auto-improve-readiness-report-body: auto-improve-readiness-worktree-guard
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit 0

auto-improve-readiness-worktree-guard:
	-$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --requested-mode "$(GOAL_WORKTREE_MODE)" --out "$(GOAL_WORKTREE_GUARD_OUT)" $(if $(GOAL_WORKTREE_ALLOW_DIRTY),--allow-dirty,)

auto-improve-goal-contract:
	$(PYTHON) -m ops.scripts.codex_goal_client --vault "$(VAULT)" --out "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --contract-id "$(CODEX_GOAL_CONTRACT_ID)" --backend-type run_local_file --current-profile "$(GOAL_RUN_PROFILE)" --max-unattended-seconds "$(GOAL_MAX_UNATTENDED_SECONDS)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --goal-status-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --worktree-guard-report "$(GOAL_WORKTREE_GUARD_OUT)"

codex-goal-contract:
	$(PYTHON) -m ops.scripts.codex_goal_client --vault "$(VAULT)" --out "$(CODEX_GOAL_CONTRACT_OUT)" --contract-id "$(CODEX_GOAL_CONTRACT_ID)" --backend-type file --current-profile "$(GOAL_RUN_PROFILE)" --max-unattended-seconds "$(GOAL_MAX_UNATTENDED_SECONDS)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --goal-status-path "$(GOAL_RUN_STATUS_OUT)" --worktree-guard-report "$(GOAL_WORKTREE_GUARD_OUT)"

codex-goal-prompt: codex-goal-contract
	$(PYTHON) -m ops.scripts.codex_goal_prompt --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_CONTRACT_OUT)" --out "$(CODEX_GOAL_PROMPT_OUT)"

goal-runtime-refresh: auto-improve-goal-preflight auto-improve-goal-status

goal-runtime-publish-snapshot:
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --out "$(CODEX_GOAL_CONTRACT_OUT)" --schema ops/schemas/codex-goal-contract.schema.json
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status
	$(PYTHON) -m ops.scripts.codex_goal_prompt --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_CONTRACT_OUT)" --out "$(CODEX_GOAL_PROMPT_OUT)"

goal-runtime-reconcile:
	$(MAKE) goal-runtime-clean-transient
	$(MAKE) goal-runtime-refresh
	$(MAKE) goal-runtime-publish-snapshot
	$(MAKE) session-synopsis
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) goal-runtime-refresh
	$(MAKE) goal-runtime-publish-snapshot
	$(MAKE) session-synopsis
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body
	$(MAKE) session-synopsis
	$(MAKE) remediation-backlog
	$(MAKE) goal-runtime-fixed-point-check
	$(MAKE) external-report-action-matrix
	$(MAKE) generated-artifact-index
	$(MAKE) artifact-freshness

goal-runtime-clean-transient:
	$(PYTHON) -m ops.scripts.goal_runtime_clean_transient --vault "$(VAULT)" --out "$(GOAL_RUNTIME_CLEAN_TRANSIENT_OUT)" --status-report "$(GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT)" $(if $(GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY),--apply,)

goal-runtime-fixed-point-check:
	$(PYTHON) -m ops.scripts.goal_runtime_fixed_point_check --vault "$(VAULT)" --out "$(GOAL_RUNTIME_FIXED_POINT_CHECK_OUT)"

long-run-preflight-clean: goal-runtime-clean-transient goal-runtime-fixed-point-check auto-improve-goal-preflight

codex-goal-client:
	$(PYTHON) -m pytest tests/test_codex_goal_contract.py tests/test_codex_goal_client.py tests/test_codex_goal_prompt.py $(PYTEST_SERIAL_FLAGS)

auto-improve-goal-preflight:
	$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --requested-mode "$(GOAL_WORKTREE_MODE)" --out "$(GOAL_WORKTREE_GUARD_OUT)" $(if $(GOAL_WORKTREE_ALLOW_DIRTY),--allow-dirty,) $(if $(GOAL_WORKTREE_STRICT),--strict,)

goal-worktree-guard: auto-improve-goal-preflight

auto-improve-goal-run: auto-improve-goal-preflight auto-improve-goal-contract
	$(PYTHON) -m ops.scripts.goal_runtime_runner --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --profile "$(GOAL_RUN_PROFILE)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --result-out "$(GOAL_SESSION_RESULT_OUT)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --checkpoint-command-timeout-seconds "$(GOAL_CHECKPOINT_COMMAND_TIMEOUT_SECONDS)" --timeout-seconds "$(GOAL_RUNNER_TIMEOUT_SECONDS)" -- $(GOAL_RUN_COMMAND)

auto-improve-goal-status: auto-improve-goal-contract
	@status=0; $(PYTHON) -m ops.scripts.goal_run_status --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --status "$(GOAL_RUN_STATUS)" --profile "$(GOAL_RUN_PROFILE)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --write-run-artifacts || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --out "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status; exit $$status

auto-improve-goal-resume: auto-improve-goal-preflight auto-improve-goal-contract
	$(PYTHON) -m ops.scripts.goal_runtime_runner --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --profile "$(GOAL_RUN_PROFILE)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --result-out "$(GOAL_SESSION_RESULT_OUT)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --checkpoint-command-timeout-seconds "$(GOAL_CHECKPOINT_COMMAND_TIMEOUT_SECONDS)" --timeout-seconds "$(GOAL_RUNNER_TIMEOUT_SECONDS)" --resume-from-checkpoint -- $(GOAL_RESUME_COMMAND)

auto-improve-goal-finalize: auto-improve-goal-contract
	@status=0; $(PYTHON) -m ops.scripts.goal_run_status --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --status "$(GOAL_FINAL_STATUS)" --profile "$(GOAL_RUN_PROFILE)" --completed-at "$(GOAL_COMPLETED_AT)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --write-run-artifacts || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --out "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status; exit $$status

auto-improve-goal-run-artifacts: auto-improve-goal-status
	$(PYTHON) -m ops.scripts.goal_run_status --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --status "$(GOAL_RUN_STATUS)" --profile "$(GOAL_RUN_PROFILE)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --write-run-artifacts

goal-profile-verification: auto-improve-goal-contract
	@status=0; $(PYTHON) -m ops.scripts.goal_profile_verification --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --status-report "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_PROFILE_VERIFICATION_CANDIDATE_OUT)" $(if $(GOAL_PROFILE_VERIFICATION_PROFILE),--profile "$(GOAL_PROFILE_VERIFICATION_PROFILE)",) $(if $(GOAL_PROFILE_VERIFICATION_APPLY),--apply,) || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_PROFILE_VERIFICATION_CANDIDATE_OUT)" --out "$(GOAL_PROFILE_VERIFICATION_OUT)" --schema ops/schemas/goal-profile-verification.schema.json --expected-artifact-kind goal_profile_verification --expected-producer ops.scripts.goal_profile_verification || status=$$?; exit $$status

auto-improve-goal-ladder-run: auto-improve-goal-preflight
	@set -e; runner_timeout_grace="$(GOAL_RUNNER_TIMEOUT_GRACE_SECONDS)"; for profile in $(GOAL_LADDER_PROFILES); do \
		case "$$profile" in \
			30m_trial) profile_seconds=1800; profile_minutes=30; profile_proposals=1; profile_failures=1 ;; \
			6h_ramp) profile_seconds=21600; profile_minutes=360; profile_proposals=6; profile_failures=2 ;; \
			2d_candidate) profile_seconds=172800; profile_minutes=2880; profile_proposals=24; profile_failures=3 ;; \
			5d_sustained) profile_seconds=432000; profile_minutes=7200; profile_proposals=60; profile_failures=3 ;; \
			*) echo "unsupported goal profile: $$profile" >&2; exit 2 ;; \
		esac; \
		runner_timeout=$$((profile_seconds + runner_timeout_grace)); \
		if [ "$$profile" != "30m_trial" ]; then \
			$(MAKE) goal-runtime-reconcile \
				GOAL_CONTRACT_RUN_ID="$(GOAL_CONTRACT_RUN_ID)" \
				GOAL_RUN_ID="$(GOAL_RUN_ID)-$$profile" \
				GOAL_RUN_PROFILE="$$profile" \
				GOAL_MAX_UNATTENDED_SECONDS="$$profile_seconds" \
				GOAL_MAX_PROPOSALS="$$profile_proposals" \
				GOAL_MAX_CONSECUTIVE_FAILURES="$$profile_failures"; \
		fi; \
		echo "Starting goal auto-improve profile: $$profile"; \
		$(MAKE) auto-improve-goal-run \
			GOAL_CONTRACT_RUN_ID="$(GOAL_CONTRACT_RUN_ID)" \
			GOAL_RUN_PROFILE="$$profile" \
			GOAL_RUN_ID="$(GOAL_RUN_ID)-$$profile" \
			GOAL_MAX_UNATTENDED_SECONDS="$$profile_seconds" \
			GOAL_MAX_MINUTES="$$profile_minutes" \
			GOAL_RUNNER_TIMEOUT_SECONDS="$$runner_timeout" \
			GOAL_MAX_PROPOSALS="$$profile_proposals" \
			GOAL_MAX_CONSECUTIVE_FAILURES="$$profile_failures"; \
		$(MAKE) goal-profile-verification \
			GOAL_CONTRACT_RUN_ID="$(GOAL_CONTRACT_RUN_ID)" \
			GOAL_RUN_ID="$(GOAL_RUN_ID)-$$profile" \
			GOAL_RUN_PROFILE="$$profile" \
			GOAL_MAX_UNATTENDED_SECONDS="$$profile_seconds" \
			GOAL_MAX_PROPOSALS="$$profile_proposals" \
			GOAL_MAX_CONSECUTIVE_FAILURES="$$profile_failures" \
			GOAL_PROFILE_VERIFICATION_PROFILE="$$profile" \
			GOAL_PROFILE_VERIFICATION_APPLY=1; \
		$(PYTHON) -c 'import json, sys; report = json.load(open("$(GOAL_PROFILE_VERIFICATION_OUT)", encoding="utf-8")); profile = sys.argv[1]; verification = report.get("profile", {}); update = report.get("contract_update", {}); status = verification.get("verification_status", ""); applied = update.get("applied"); ok = report.get("status") == "pass" and verification.get("target_profile") == profile and (applied is True or status in {"already_verified", "already_complete"}); sys.stderr.write("" if ok else "goal ladder profile verification failed: profile=%s status=%s applied=%s\n" % (profile, status, applied)); raise SystemExit(0 if ok else 1)' "$$profile"; \
	done

auto-improve-goal-ladder-start: auto-improve-goal-preflight
	@mkdir -p "$(GOAL_RUN_LOG_DIR)"
	@setsid $(MAKE) auto-improve-goal-ladder-run PYTHON=$(PYTHON) VAULT="$(VAULT)" GOAL_LADDER_PROFILES="$(GOAL_LADDER_PROFILES)" GOAL_RUN_ID="$(GOAL_LADDER_RUN_ID)" GOAL_CONTRACT_RUN_ID="$(GOAL_LADDER_CONTRACT_RUN_ID)" CODEX_GOAL_CONTRACT_ID="$(CODEX_GOAL_CONTRACT_ID)" GOAL_ALLOW_LEARNING_UNCERTAIN="$(GOAL_ALLOW_LEARNING_UNCERTAIN)" > "$(GOAL_LADDER_LOG)" 2>&1 < /dev/null & echo $$! > "$(GOAL_LADDER_PID)"
	@printf 'started goal ladder pid=%s log=%s\n' "$$(cat "$(GOAL_LADDER_PID)")" "$(GOAL_LADDER_LOG)"

goal-prompt: codex-goal-prompt

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
