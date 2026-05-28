OUTCOME_METRICS_OUT ?= ops/reports/outcome-metrics.json
PROMOTION_DECISION_TRENDS_OUT ?= ops/reports/promotion-decision-trends.json
PROMOTION_DECISION_TRENDS_RECENT_WINDOW ?= 20
OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json
OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json
MECHANISM_REVIEW_OUT ?= ops/reports/mechanism-review-candidates.json
MUTATION_PROPOSAL_OUT ?= ops/reports/mutation-proposals.json
MECHANISM_NAVIGATION_INDEX_OUT ?= tmp/mechanism-navigation-index.json
OBSERVATION_CLOSEOUT_LINT_OUT ?= tmp/observation-closeout-lint.json
OBSERVATION_CLOSEOUT_REGISTRY ?= ops/observation-closeout-registry.json
AUTO_IMPROVE_READINESS_OUT ?= ops/reports/auto-improve-readiness.json
AUTO_IMPROVE_READINESS_CANDIDATE_OUT ?= tmp/auto-improve-readiness.candidate.json
AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH ?= 0
CODEX_GOAL_CONTRACT_OUT ?= ops/reports/codex-goal-contract.json
CODEX_GOAL_CONTRACT_ID ?= auto-improve-goal
CODEX_GOAL_PROMPT_OUT ?= ops/reports/codex-goal-prompt.json
GOAL_RUN_ID ?= auto-improve-trial
GOAL_CONTRACT_RUN_ID ?= $(GOAL_RUN_ID)
GOAL_ACTIVE_STATE_DIR ?= runs/goal-$(GOAL_CONTRACT_RUN_ID)/state
CODEX_GOAL_ACTIVE_CONTRACT_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/codex-goal-contract.json
GOAL_WORKTREE_GUARD_OUT ?= ops/reports/goal-worktree-guard.json
GOAL_WORKTREE_MODE ?= git
GOAL_WORKTREE_STRICT ?=
GOAL_RUN_STATUS_OUT ?= ops/reports/goal-run-status.json
GOAL_RUNTIME_CERTIFICATE_OUT ?= ops/reports/goal-runtime-certificate.json
GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT ?= tmp/goal-runtime-certificate.candidate.json
GOAL_RUNTIME_CERTIFICATE_MODE ?=
GOAL_RUNTIME_CERTIFICATE_APPLY ?=
GOAL_RUNTIME_CLEAN_TRANSIENT_OUT ?= tmp/goal-runtime-clean-transient.json
GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY ?= 1
GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT ?= $(GOAL_RUN_STATUS_OUT)
GOAL_RUNTIME_QUARANTINE_PREFLIGHT_OUT ?= tmp/goal-runtime-quarantine-preflight.json
GOAL_RUNTIME_FIXED_POINT_CHECK_OUT ?= tmp/goal-runtime-fixed-point-check.json
GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_OUT ?= tmp/goal-runtime-local-evidence-refresh.json
GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_MAX_ITERATIONS ?= 6
GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_TIMEOUT_SECONDS ?= 300
GOAL_RUNTIME_RUN_ADMISSION_OUT ?= tmp/goal-runtime-run-admission.json
GOAL_RUNTIME_RUN_ADMISSION_RESUME ?=
GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN ?=
GOAL_MAINTENANCE_ACTION_PLAN_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/maintenance-action.json
GOAL_RUNTIME_CLOSEOUT_PLAN_OUT ?= tmp/goal-runtime-closeout-plan.json
GOAL_RUNTIME_CLOSEOUT_BUDGET ?= cheap
GOAL_RUNTIME_CLOSEOUT_STATE_DIR ?= $(GOAL_ACTIVE_STATE_DIR)/closeout
GOAL_RUNTIME_CLOSEOUT_SCRIPT_OUTPUT_SURFACES_OUT ?= $(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)/script-output-surfaces.json
GOAL_RUNTIME_CLOSEOUT_GENERATED_ARTIFACT_INDEX_OUT ?= $(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)/generated-artifact-index.json
GOAL_RUNTIME_CLOSEOUT_ARTIFACT_FRESHNESS_OUT ?= $(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)/artifact-freshness-report.json
GOAL_RUNTIME_LOCK_PATH ?= $(GOAL_RUN_LOG_DIR)/goal-runtime.lock.json
GOAL_RUNTIME_PYTHON_PREFLIGHT_OUT ?= tmp/goal-runtime-python-preflight.json
GOAL_SESSION_RESULT_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/auto-improve-goal-session-result.json
GOAL_ACTIVE_RUN_STATUS_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/goal-run-status.json
GOAL_RUN_STATUS_CANDIDATE_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/goal-run-status.candidate.json
GOAL_LOCAL_READINESS_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/auto-improve-readiness.json
GOAL_LOCAL_READINESS_CANDIDATE_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/auto-improve-readiness.candidate.json
GOAL_LOCAL_SESSION_SYNOPSIS_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/session-synopsis.json
GOAL_LOCAL_SESSION_SYNOPSIS_CANDIDATE_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/session-synopsis.candidate.json
GOAL_LOCAL_NEGATIVE_LESSONS_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/self-improvement-negative-lessons.json
GOAL_LOCAL_NEGATIVE_LESSONS_CANDIDATE_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/self-improvement-negative-lessons.candidate.json
GOAL_LOCAL_REMEDIATION_BACKLOG_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/remediation-backlog.json
GOAL_LOCAL_REMEDIATION_BACKLOG_CANDIDATE_OUT ?= $(GOAL_ACTIVE_STATE_DIR)/remediation-backlog.candidate.json
GOAL_RUN_STATUS ?= blocked
GOAL_RUNTIME_MODE ?= self_improvement_loop
GOAL_RUNTIME_SECONDS ?= 21600
GOAL_MAX_UNATTENDED_SECONDS ?= $(GOAL_RUNTIME_SECONDS)
GOAL_RUNNER_TIMEOUT_SECONDS ?= 28800
GOAL_MAX_MINUTES ?= 360
GOAL_MAX_PROPOSALS ?= 1
GOAL_MAX_CONSECUTIVE_FAILURES ?= 1
GOAL_HEARTBEAT_INTERVAL_SECONDS ?= 300
GOAL_CHECKPOINT_INTERVAL_SECONDS ?= 1800
GOAL_CHECKPOINT_COMMAND_TIMEOUT_SECONDS ?= 900
GOAL_MAINTAIN_UNTIL_BUDGET ?= 0
GOAL_MAINTENANCE_INTERVAL_SECONDS ?= 300
GOAL_POST_PROMOTE_MAINTENANCE_CYCLES ?= 1
GOAL_EXECUTOR ?= codex_exec
GOAL_ARTIFACT_CLASS ?= system_mechanism
GOAL_ALLOW_LEARNING_UNCERTAIN ?=
GOAL_RUN_COMMAND ?= $(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --session-id "$(GOAL_RUN_ID)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --max-minutes "$(GOAL_MAX_MINUTES)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --executor "$(GOAL_EXECUTOR)" --class "$(GOAL_ARTIFACT_CLASS)" $(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,) $(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,) --maintenance-interval-seconds "$(GOAL_MAINTENANCE_INTERVAL_SECONDS)" --post-promote-maintenance-cycles "$(GOAL_POST_PROMOTE_MAINTENANCE_CYCLES)"
GOAL_RESUME_COMMAND ?= $(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --resume-session "$(GOAL_RUN_ID)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --max-minutes "$(GOAL_MAX_MINUTES)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --executor "$(GOAL_EXECUTOR)" --class "$(GOAL_ARTIFACT_CLASS)" $(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,) $(if $(GOAL_MAINTAIN_UNTIL_BUDGET),--maintain-until-budget,) --maintenance-interval-seconds "$(GOAL_MAINTENANCE_INTERVAL_SECONDS)" --post-promote-maintenance-cycles "$(GOAL_POST_PROMOTE_MAINTENANCE_CYCLES)"
GOAL_MAINTENANCE_ACTION_NEXT_MAX_PROPOSALS ?= $(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --resume-session "$(GOAL_RUN_ID)" --print-maintenance-action-next-max-proposals --maintenance-action-plan-out "$(GOAL_MAINTENANCE_ACTION_PLAN_OUT)"
GOAL_FINAL_STATUS ?= stopped
GOAL_COMPLETED_AT ?=
GOAL_RUN_LOG_DIR ?= build/goal-runs
MECHANISM_RUN_ARGS ?=

.PHONY: auto-improve-readiness auto-improve-readiness-report auto-improve-readiness-report-body auto-improve-readiness-worktree-guard codex-goal-contract codex-goal-prompt codex-goal-client goal-prompt auto-improve-goal-contract goal-runtime-refresh goal-runtime-publish-snapshot goal-runtime-local-readiness goal-runtime-local-session-synopsis goal-runtime-local-negative-lessons goal-runtime-local-remediation-backlog goal-runtime-local-fixed-point-check goal-runtime-local-evidence-refresh goal-runtime-local-evidence-converge goal-runtime-publish-local-evidence goal-runtime-reconcile goal-runtime-pre-run-cleanup goal-runtime-between-run-settle goal-runtime-closeout-plan goal-runtime-closeout-candidate-script-output-surfaces goal-runtime-closeout-candidate-generated-artifact-index goal-runtime-closeout-candidate-artifact-freshness goal-runtime-closeout-candidate-converge goal-runtime-closeout-publish-script-output-surfaces goal-runtime-closeout-publish goal-runtime-closeout-finalize goal-runtime-closeout goal-runtime-closeout-full goal-runtime-clean-transient goal-runtime-quarantine-preflight goal-runtime-fixed-point-check goal-runtime-run-admission-converge goal-runtime-run-admission-local-refresh goal-runtime-run-admission goal-runtime-run-admission-resume goal-runtime-maintenance-action-plan goal-runtime-lock-check goal-runtime-lock-status goal-runtime-lock-stop goal-runtime-python-preflight long-run-preflight-clean auto-improve-goal-preflight auto-improve-goal-run auto-improve-goal-status auto-improve-goal-resume auto-improve-goal-maintenance-action auto-improve-goal-finalize auto-improve-goal-run-artifacts goal-runtime-certificate goal-worktree-guard mechanism-review mutation-proposal run-mechanism-experiment-linux-tmp outcome-metrics promotion-decision-trends routing-provenance-aggregate outcome-provenance-gate-policy
.PHONY: mechanism-navigation-index observation-closeout-lint

mechanism-navigation-index:
	$(PYTHON) -m ops.scripts.mechanism_navigation_index --vault "$(VAULT)" --out "$(MECHANISM_NAVIGATION_INDEX_OUT)"

observation-closeout-lint:
	$(PYTHON) -m ops.scripts.observation_closeout_lint --vault "$(VAULT)" --registry "$(OBSERVATION_CLOSEOUT_REGISTRY)" --out "$(OBSERVATION_CLOSEOUT_LINT_OUT)"

auto-improve-readiness: auto-improve-readiness-worktree-guard
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit $$status

auto-improve-readiness-report:
	$(MAKE) auto-improve-readiness-worktree-guard
	$(MAKE) refresh-generated-core
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=0
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=0
	$(MAKE) remediation-backlog
	$(MAKE) auto-improve-readiness-report-body AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH=0

auto-improve-readiness-report-body:
	@if [ "$(AUTO_IMPROVE_READINESS_WORKTREE_GUARD_REFRESH)" = "1" ]; then $(MAKE) auto-improve-readiness-worktree-guard; fi
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit 0

auto-improve-readiness-worktree-guard:
	-$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --requested-mode "$(GOAL_WORKTREE_MODE)" --out "$(GOAL_WORKTREE_GUARD_OUT)"

auto-improve-goal-contract:
	$(PYTHON) -m ops.scripts.codex_goal_client --vault "$(VAULT)" --out "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --contract-id "$(CODEX_GOAL_CONTRACT_ID)" --backend-type run_local_file --runtime-mode "$(GOAL_RUNTIME_MODE)" --max-unattended-seconds "$(GOAL_MAX_UNATTENDED_SECONDS)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --goal-status-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --readiness-report "$(GOAL_LOCAL_READINESS_OUT)" --worktree-guard-report "$(GOAL_WORKTREE_GUARD_OUT)"

codex-goal-contract:
	$(PYTHON) -m ops.scripts.codex_goal_client --vault "$(VAULT)" --out "$(CODEX_GOAL_CONTRACT_OUT)" --contract-id "$(CODEX_GOAL_CONTRACT_ID)" --backend-type file --runtime-mode "$(GOAL_RUNTIME_MODE)" --max-unattended-seconds "$(GOAL_MAX_UNATTENDED_SECONDS)" --max-proposals "$(GOAL_MAX_PROPOSALS)" --max-consecutive-failures "$(GOAL_MAX_CONSECUTIVE_FAILURES)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --goal-status-path "$(GOAL_RUN_STATUS_OUT)" --worktree-guard-report "$(GOAL_WORKTREE_GUARD_OUT)"

codex-goal-prompt: codex-goal-contract
	$(PYTHON) -m ops.scripts.codex_goal_prompt --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_CONTRACT_OUT)" --out "$(CODEX_GOAL_PROMPT_OUT)"

goal-runtime-refresh: auto-improve-goal-preflight auto-improve-goal-status

goal-runtime-publish-snapshot:
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --out "$(CODEX_GOAL_CONTRACT_OUT)" --schema ops/schemas/codex-goal-contract.schema.json
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status
	$(PYTHON) -m ops.scripts.codex_goal_prompt --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_CONTRACT_OUT)" --out "$(CODEX_GOAL_PROMPT_OUT)"

goal-runtime-local-readiness: auto-improve-readiness-worktree-guard
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(GOAL_LOCAL_READINESS_CANDIDATE_OUT)" --remediation-backlog "$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_READINESS_CANDIDATE_OUT)" --out "$(GOAL_LOCAL_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit 0

goal-runtime-local-session-synopsis:
	$(PYTHON) -m ops.scripts.session_synopsis --vault "$(VAULT)" --out "$(GOAL_LOCAL_SESSION_SYNOPSIS_CANDIDATE_OUT)" --auto-improve-readiness "$(GOAL_LOCAL_READINESS_OUT)" --goal-run-status "$(GOAL_ACTIVE_RUN_STATUS_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_SESSION_SYNOPSIS_CANDIDATE_OUT)" --out "$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)" --schema ops/schemas/session-synopsis.schema.json --expected-artifact-kind session_synopsis --expected-producer ops.scripts.session_synopsis

goal-runtime-local-negative-lessons:
	$(PYTHON) -m ops.scripts.self_improvement_negative_lessons --vault "$(VAULT)" --out "$(GOAL_LOCAL_NEGATIVE_LESSONS_CANDIDATE_OUT)" --session-synopsis "$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_NEGATIVE_LESSONS_CANDIDATE_OUT)" --out "$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)" --schema ops/schemas/self-improvement-negative-lessons.schema.json --expected-artifact-kind self_improvement_negative_lessons --expected-producer ops.scripts.self_improvement_negative_lessons

goal-runtime-local-remediation-backlog:
	$(PYTHON) -m ops.scripts.remediation_backlog --vault "$(VAULT)" --out "$(GOAL_LOCAL_REMEDIATION_BACKLOG_CANDIDATE_OUT)" --self-improvement-negative-lessons "$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)" --session-synopsis "$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_REMEDIATION_BACKLOG_CANDIDATE_OUT)" --out "$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)" --schema ops/schemas/remediation-backlog.schema.json --expected-artifact-kind remediation_backlog --expected-producer ops.scripts.remediation_backlog

goal-runtime-local-fixed-point-check:
	$(PYTHON) -m ops.scripts.goal_runtime_fixed_point_check --vault "$(VAULT)" --out "$(GOAL_RUNTIME_FIXED_POINT_CHECK_OUT)" --codex-goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --goal-run-status "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --auto-improve-readiness "$(GOAL_LOCAL_READINESS_OUT)" --session-synopsis "$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)" --remediation-backlog "$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)"

goal-runtime-local-evidence-refresh:
	$(PYTHON) -m ops.scripts.goal_runtime_local_evidence_refresh --vault "$(VAULT)" --out "$(GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_OUT)" --python $(PYTHON) --max-iterations "$(GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_MAX_ITERATIONS)" --timeout-seconds "$(GOAL_RUNTIME_LOCAL_EVIDENCE_REFRESH_TIMEOUT_SECONDS)" --codex-goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --goal-run-status "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --auto-improve-readiness "$(GOAL_LOCAL_READINESS_OUT)" --session-synopsis "$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)" --negative-lessons "$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)" --remediation-backlog "$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)"

goal-runtime-local-evidence-converge:
	$(MAKE) goal-runtime-local-evidence-refresh
	$(MAKE) goal-runtime-local-fixed-point-check

goal-runtime-publish-local-evidence:
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --out "$(CODEX_GOAL_CONTRACT_OUT)" --schema ops/schemas/codex-goal-contract.schema.json
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_READINESS_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_SESSION_SYNOPSIS_OUT)" --out "$(SESSION_SYNOPSIS_OUT)" --schema ops/schemas/session-synopsis.schema.json --expected-artifact-kind session_synopsis --expected-producer ops.scripts.session_synopsis
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_NEGATIVE_LESSONS_OUT)" --out "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT)" --schema ops/schemas/self-improvement-negative-lessons.schema.json --expected-artifact-kind self_improvement_negative_lessons --expected-producer ops.scripts.self_improvement_negative_lessons
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)" --out "$(REMEDIATION_BACKLOG_OUT)" --schema ops/schemas/remediation-backlog.schema.json --expected-artifact-kind remediation_backlog --expected-producer ops.scripts.remediation_backlog
	$(PYTHON) -m ops.scripts.codex_goal_prompt --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_CONTRACT_OUT)" --out "$(CODEX_GOAL_PROMPT_OUT)"

goal-runtime-reconcile:
	$(MAKE) goal-runtime-clean-transient
	$(MAKE) goal-runtime-local-evidence-converge
	$(MAKE) goal-runtime-publish-local-evidence
	$(MAKE) goal-runtime-fixed-point-check
	$(MAKE) generated-artifact-converge

goal-runtime-pre-run-cleanup:
	$(MAKE) tmp-json-clean
	$(MAKE) goal-runtime-clean-transient
	$(MAKE) goal-runtime-local-evidence-converge
	$(MAKE) artifact-freshness-refresh-check

goal-runtime-between-run-settle: goal-runtime-lock-check goal-runtime-python-preflight
	$(MAKE) refresh-generated-core
	$(MAKE) goal-runtime-pre-run-cleanup
	$(MAKE) goal-runtime-publish-local-evidence
	$(MAKE) goal-runtime-fixed-point-check

goal-runtime-closeout-plan:
	$(PYTHON) -m ops.scripts.goal_runtime_closeout --vault "$(VAULT)" --out "$(GOAL_RUNTIME_CLOSEOUT_PLAN_OUT)" --budget "$(GOAL_RUNTIME_CLOSEOUT_BUDGET)" --candidate-root "$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)"

goal-runtime-closeout-candidate-script-output-surfaces:
	$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" --out "$(GOAL_RUNTIME_CLOSEOUT_SCRIPT_OUTPUT_SURFACES_OUT)"

goal-runtime-closeout-candidate-generated-artifact-index:
	$(PYTHON) -m ops.scripts.generated_artifact_index --vault "$(VAULT)" --out "$(GOAL_RUNTIME_CLOSEOUT_GENERATED_ARTIFACT_INDEX_OUT)"

goal-runtime-closeout-candidate-artifact-freshness:
	$(PYTHON) -m ops.scripts.artifact_freshness_runtime --vault "$(VAULT)" --out "$(GOAL_RUNTIME_CLOSEOUT_ARTIFACT_FRESHNESS_OUT)" --mtime-source "$(ARTIFACT_FRESHNESS_MTIME_SOURCE)" $(if $(ARTIFACT_FRESHNESS_ZIP_METADATA),--zip-metadata "$(ARTIFACT_FRESHNESS_ZIP_METADATA)",)

goal-runtime-closeout-candidate-converge:
	$(MAKE) report-schema-samples-check
	$(MAKE) goal-runtime-clean-transient
	$(MAKE) goal-runtime-local-evidence-converge
	$(MAKE) goal-runtime-closeout-candidate-script-output-surfaces
	$(MAKE) goal-runtime-closeout-candidate-generated-artifact-index
	$(MAKE) goal-runtime-closeout-candidate-artifact-freshness

goal-runtime-closeout-publish-script-output-surfaces:
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_RUNTIME_CLOSEOUT_SCRIPT_OUTPUT_SURFACES_OUT)" --out "$(SCRIPT_OUTPUT_SURFACES_OUT)" --schema ops/schemas/script-output-surfaces.schema.json --expected-artifact-kind script_output_surfaces --expected-producer ops.scripts.script_output_surfaces --preserve-existing-on-semantic-match

goal-runtime-closeout-publish:
	$(MAKE) goal-runtime-closeout-publish-script-output-surfaces
	$(MAKE) goal-runtime-publish-local-evidence
	$(MAKE) goal-runtime-certificate
	$(MAKE) generated-artifact-converge

goal-runtime-closeout-finalize:
	$(MAKE) goal-runtime-fixed-point-check

goal-runtime-closeout:
	@set -e; \
	for target in $$($(PYTHON) -m ops.scripts.goal_runtime_closeout --vault "$(VAULT)" --budget cheap --candidate-root "$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)" --format targets); do \
		$(MAKE) $$target; \
	done
	$(MAKE) goal-runtime-closeout-plan GOAL_RUNTIME_CLOSEOUT_BUDGET=cheap

goal-runtime-closeout-full:
	@set -e; \
	for target in $$($(PYTHON) -m ops.scripts.goal_runtime_closeout --vault "$(VAULT)" --budget full --candidate-root "$(GOAL_RUNTIME_CLOSEOUT_STATE_DIR)" --format targets); do \
		$(MAKE) $$target; \
	done
	$(MAKE) goal-runtime-closeout-plan GOAL_RUNTIME_CLOSEOUT_BUDGET=full

goal-runtime-clean-transient:
	$(PYTHON) -m ops.scripts.goal_runtime_clean_transient --vault "$(VAULT)" --out "$(GOAL_RUNTIME_CLEAN_TRANSIENT_OUT)" --status-report "$(GOAL_RUNTIME_CLEAN_TRANSIENT_STATUS_REPORT)" $(if $(GOAL_RUNTIME_CLEAN_TRANSIENT_APPLY),--apply,)

goal-runtime-quarantine-preflight:
	$(PYTHON) -m ops.scripts.goal_runtime_quarantine_preflight --vault "$(VAULT)" --out "$(GOAL_RUNTIME_QUARANTINE_PREFLIGHT_OUT)" --mechanism-review-report "$(MECHANISM_REVIEW_OUT)" --strict

goal-runtime-fixed-point-check:
	$(PYTHON) -m ops.scripts.goal_runtime_fixed_point_check --vault "$(VAULT)" --out "$(GOAL_RUNTIME_FIXED_POINT_CHECK_OUT)"

goal-runtime-run-admission-converge: goal-runtime-lock-check goal-runtime-python-preflight
	$(MAKE) refresh-generated-core
	$(MAKE) release-smoke-fast-refresh-check
	$(MAKE) goal-runtime-pre-run-cleanup
	$(MAKE) goal-runtime-quarantine-preflight
	$(MAKE) goal-runtime-publish-local-evidence
	$(MAKE) goal-runtime-fixed-point-check

goal-runtime-run-admission-local-refresh: goal-runtime-lock-check goal-runtime-python-preflight
	$(MAKE) release-smoke-fast-refresh-check
	$(MAKE) goal-runtime-pre-run-cleanup
	$(MAKE) goal-runtime-quarantine-preflight

goal-runtime-run-admission: goal-runtime-run-admission-local-refresh
	$(PYTHON) -m ops.scripts.goal_runtime_run_admission --vault "$(VAULT)" --out "$(GOAL_RUNTIME_RUN_ADMISSION_OUT)" --cleanup-report "$(GOAL_RUNTIME_CLEAN_TRANSIENT_OUT)" --quarantine-preflight-report "$(GOAL_RUNTIME_QUARANTINE_PREFLIGHT_OUT)" --fixed-point-report "$(GOAL_RUNTIME_FIXED_POINT_CHECK_OUT)" --goal-worktree-guard-report "$(GOAL_WORKTREE_GUARD_OUT)" --mutation-proposals-report "$(MUTATION_PROPOSAL_OUT)" --readiness-report "$(GOAL_LOCAL_READINESS_OUT)" --remediation-backlog-report "$(GOAL_LOCAL_REMEDIATION_BACKLOG_OUT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --goal-run-status "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --runtime-certificate-report "$(GOAL_RUNTIME_CERTIFICATE_OUT)" $(if $(GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN),--maintenance-action-plan "$(GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN)",) $(if $(GOAL_RUNTIME_RUN_ADMISSION_RESUME),--resume-session "$(GOAL_RUN_ID)",) $(if $(GOAL_ALLOW_LEARNING_UNCERTAIN),--allow-learning-uncertain,) --strict

goal-runtime-run-admission-resume: goal-runtime-run-admission
goal-runtime-run-admission-resume: GOAL_RUNTIME_RUN_ADMISSION_RESUME=1

goal-runtime-maintenance-action-plan: goal-runtime-between-run-settle
	@$(GOAL_MAINTENANCE_ACTION_NEXT_MAX_PROPOSALS) > /dev/null

goal-runtime-lock-check:
	$(PYTHON) -m ops.scripts.goal_runtime_lock check --vault "$(VAULT)" --lock-path "$(GOAL_RUNTIME_LOCK_PATH)" --cleanup-stale

goal-runtime-lock-status:
	$(PYTHON) -m ops.scripts.goal_runtime_lock status --vault "$(VAULT)" --lock-path "$(GOAL_RUNTIME_LOCK_PATH)" --json

goal-runtime-lock-stop:
	$(PYTHON) -m ops.scripts.goal_runtime_lock stop --vault "$(VAULT)" --lock-path "$(GOAL_RUNTIME_LOCK_PATH)" --json

goal-runtime-python-preflight:
	$(PYTHON) -m ops.scripts.bootstrap_preflight --vault "$(VAULT)" --dev --environment-class goal-runtime --out "$(GOAL_RUNTIME_PYTHON_PREFLIGHT_OUT)"

long-run-preflight-clean: goal-runtime-run-admission-converge

codex-goal-client:
	$(PYTHON) -m pytest tests/test_codex_goal_contract.py tests/test_codex_goal_client.py tests/test_codex_goal_prompt.py $(PYTEST_SERIAL_FLAGS)

auto-improve-goal-preflight: goal-runtime-lock-check goal-runtime-python-preflight
	$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --requested-mode "$(GOAL_WORKTREE_MODE)" --out "$(GOAL_WORKTREE_GUARD_OUT)" $(if $(GOAL_WORKTREE_STRICT),--strict,)

goal-worktree-guard: auto-improve-goal-preflight

auto-improve-goal-run: goal-runtime-run-admission auto-improve-goal-contract
	$(PYTHON) -m ops.scripts.goal_runtime_runner --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --runtime-mode "$(GOAL_RUNTIME_MODE)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --result-out "$(GOAL_SESSION_RESULT_OUT)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --checkpoint-command-timeout-seconds "$(GOAL_CHECKPOINT_COMMAND_TIMEOUT_SECONDS)" --timeout-seconds "$(GOAL_RUNNER_TIMEOUT_SECONDS)" --workspace-lock-path "$(GOAL_RUNTIME_LOCK_PATH)" -- $(GOAL_RUN_COMMAND)

auto-improve-goal-status: auto-improve-goal-contract
	@status=0; $(PYTHON) -m ops.scripts.goal_run_status --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --status "$(GOAL_RUN_STATUS)" --runtime-mode "$(GOAL_RUNTIME_MODE)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --write-run-artifacts || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --out "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status; exit $$status

auto-improve-goal-resume: goal-runtime-run-admission-resume auto-improve-goal-contract
	$(PYTHON) -m ops.scripts.goal_runtime_runner --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --runtime-mode "$(GOAL_RUNTIME_MODE)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --result-out "$(GOAL_SESSION_RESULT_OUT)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --checkpoint-command-timeout-seconds "$(GOAL_CHECKPOINT_COMMAND_TIMEOUT_SECONDS)" --timeout-seconds "$(GOAL_RUNNER_TIMEOUT_SECONDS)" --workspace-lock-path "$(GOAL_RUNTIME_LOCK_PATH)" --resume-from-checkpoint -- $(GOAL_RESUME_COMMAND)

auto-improve-goal-maintenance-action: goal-runtime-maintenance-action-plan
	@next_max_proposals="$$( $(PYTHON) -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["next_max_proposals"])' "$(GOAL_MAINTENANCE_ACTION_PLAN_OUT)" )"; $(MAKE) auto-improve-goal-resume GOAL_MAX_PROPOSALS="$$next_max_proposals" GOAL_RUNTIME_RUN_ADMISSION_MAINTENANCE_ACTION_PLAN="$(GOAL_MAINTENANCE_ACTION_PLAN_OUT)"

auto-improve-goal-finalize: auto-improve-goal-contract
	@status=0; $(PYTHON) -m ops.scripts.goal_run_status --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --status "$(GOAL_FINAL_STATUS)" --runtime-mode "$(GOAL_RUNTIME_MODE)" --completed-at "$(GOAL_COMPLETED_AT)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --write-run-artifacts || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_RUN_STATUS_CANDIDATE_OUT)" --out "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --schema ops/schemas/goal-run-status.schema.json --expected-artifact-kind goal_run_status --expected-producer ops.scripts.goal_run_status; exit $$status

auto-improve-goal-run-artifacts: auto-improve-goal-status
	$(PYTHON) -m ops.scripts.goal_run_status --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --run-id "$(GOAL_RUN_ID)" --status "$(GOAL_RUN_STATUS)" --runtime-mode "$(GOAL_RUNTIME_MODE)" --heartbeat-interval-seconds "$(GOAL_HEARTBEAT_INTERVAL_SECONDS)" --checkpoint-interval-seconds "$(GOAL_CHECKPOINT_INTERVAL_SECONDS)" --status-report-path "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --write-run-artifacts

goal-runtime-certificate: auto-improve-goal-contract
	@status=0; $(PYTHON) -m ops.scripts.goal_runtime_certificate_report --vault "$(VAULT)" --goal-contract "$(CODEX_GOAL_ACTIVE_CONTRACT_OUT)" --status-report "$(GOAL_ACTIVE_RUN_STATUS_OUT)" --out "$(GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT)" $(if $(GOAL_RUNTIME_CERTIFICATE_MODE),--runtime-mode "$(GOAL_RUNTIME_CERTIFICATE_MODE)",) $(if $(GOAL_RUNTIME_CERTIFICATE_APPLY),--apply,) || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(GOAL_RUNTIME_CERTIFICATE_CANDIDATE_OUT)" --out "$(GOAL_RUNTIME_CERTIFICATE_OUT)" --schema ops/schemas/goal-runtime-certificate.schema.json --expected-artifact-kind goal_runtime_certificate --expected-producer ops.scripts.goal_runtime_certificate_report || status=$$?; exit $$status

goal-prompt: codex-goal-prompt

mechanism-review:
	$(PYTHON) -m ops.scripts.mechanism_review --vault "$(VAULT)"

mutation-proposal:
	$(PYTHON) -m ops.scripts.mutation_proposal --vault "$(VAULT)"

run-mechanism-experiment-linux-tmp:
	TMPDIR=/tmp TEMP=/tmp TMP=/tmp $(PYTHON) -m ops.scripts.run_mechanism_experiment --vault "$(VAULT)" $(MECHANISM_RUN_ARGS)

outcome-metrics:
	$(PYTHON) -m ops.scripts.outcome_metrics --vault "$(VAULT)"

promotion-decision-trends:
	$(PYTHON) -m ops.scripts.promotion_decision_trends --vault "$(VAULT)" --recent-window "$(PROMOTION_DECISION_TRENDS_RECENT_WINDOW)"

routing-provenance-aggregate:
	$(PYTHON) -m ops.scripts.observability_routing_provenance_runtime --vault "$(VAULT)"

outcome-provenance-gate-policy: outcome-metrics routing-provenance-aggregate
	$(PYTHON) -m ops.scripts.outcome_provenance_gate_policy --vault "$(VAULT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_OUT)" --schema ops/schemas/outcome-provenance-gate-policy.schema.json --expected-artifact-kind outcome_provenance_gate_policy --expected-producer ops.scripts.outcome_provenance_gate_policy
