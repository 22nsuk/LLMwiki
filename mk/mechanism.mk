OUTCOME_METRICS_OUT ?= ops/reports/outcome-metrics.json
OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json
OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json
POLICY ?= ops/policies/wiki-maintainer-policy.yaml
AUTO_IMPROVE_READINESS_OUT ?= ops/reports/auto-improve-readiness.json
AUTO_IMPROVE_READINESS_CANDIDATE_OUT ?= tmp/auto-improve-readiness.candidate.json
GOAL_REPO_URL ?=
GOAL_REPO_VISIBILITY ?= UNKNOWN
GOAL_BASELINE_COMMIT ?=
GOAL_BRANCH ?= goal/5day-auto-improve-runtime
GOAL_WORKTREE_PATH ?= ../LLMwiki-worktrees/goal-5day-auto-improve-runtime
GOAL_ACTIVE_PROFILE ?= 5-day-sustained
GOAL_CONTRACT ?= ops/reports/codex-goal-contract.json
GOAL_STATUS_OUT ?= ops/reports/goal-run-status.json
GOAL_AUDIT_JSONL ?= ops/reports/goal-audit-log.jsonl
GOAL_PROMPT_OUT ?= ops/reports/goal-prompt.md
GOAL_HEARTBEAT_REASON ?= heartbeat
GOAL_CHECKPOINT_REASON ?= checkpoint
GOAL_HEARTBEAT_INTERVAL ?= 5
GOAL_CHECKPOINT_INTERVAL ?= 30
GOAL_EXECUTOR ?= codex_exec
GOAL_SESSION_ID ?=
GOAL_RESUME_SESSION ?=
GOAL_RESUME_FROM_CHECKPOINT ?=
GOAL_RUN_EXTRA_ARGS ?=
REMEDIATION_BACKLOG_OUT ?= ops/reports/remediation-backlog.json
SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT ?= ops/reports/self-improvement-negative-lessons.json
MECHANISM_RUN_ARGS ?=
GOAL_SESSION_ARG = $(if $(GOAL_SESSION_ID),--session-id "$(GOAL_SESSION_ID)",)
GOAL_RESUME_SESSION_ARG = $(if $(GOAL_RESUME_SESSION),--resume-session "$(GOAL_RESUME_SESSION)",)
GOAL_RESUME_CHECKPOINT_ARG = $(if $(GOAL_RESUME_FROM_CHECKPOINT),--resume-from-checkpoint "$(GOAL_RESUME_FROM_CHECKPOINT)",)

.PHONY: auto-improve-goal-finalize auto-improve-goal-preflight auto-improve-goal-resume auto-improve-goal-run auto-improve-goal-status auto-improve-readiness auto-improve-readiness-report auto-improve-readiness-report-body codex-goal-contract goal-prompt goal-run-status-checkpoint goal-run-status-heartbeat goal-run-status-init goal-worktree-guard mechanism-review mutation-proposal remediation-backlog run-mechanism-experiment-linux-tmp outcome-metrics routing-provenance-aggregate outcome-provenance-gate-policy self-improvement-negative-lessons

auto-improve-readiness: refresh-generated-core
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit $$status

auto-improve-readiness-report: refresh-generated-core auto-improve-readiness-report-body

auto-improve-readiness-report-body:
	@status=0; $(PYTHON) -m ops.scripts.auto_improve_readiness --vault "$(VAULT)" --out "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" || status=$$?; $(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(AUTO_IMPROVE_READINESS_CANDIDATE_OUT)" --out "$(AUTO_IMPROVE_READINESS_OUT)" --schema ops/schemas/auto-improve-readiness-report.schema.json --expected-artifact-kind auto_improve_readiness_report --expected-producer ops.scripts.auto_improve_readiness_runtime; exit 0

goal-worktree-guard:
	$(PYTHON) -m ops.scripts.goal_worktree_guard --vault "$(VAULT)" --expected-branch "$(GOAL_BRANCH)"

auto-improve-goal-preflight: goal-worktree-guard

goal-run-status-init: goal-worktree-guard
	$(PYTHON) -m ops.scripts.goal_run_status init --vault "$(VAULT)" --repo-url "$(GOAL_REPO_URL)" --visibility "$(GOAL_REPO_VISIBILITY)" --baseline-commit "$(GOAL_BASELINE_COMMIT)" --branch "$(GOAL_BRANCH)" --worktree-path "$(GOAL_WORKTREE_PATH)" --active-profile "$(GOAL_ACTIVE_PROFILE)"

codex-goal-contract: goal-run-status-init

auto-improve-goal-status: goal-run-status-init

goal-run-status-heartbeat:
	$(PYTHON) -m ops.scripts.goal_run_status heartbeat --vault "$(VAULT)" --reason "$(GOAL_HEARTBEAT_REASON)"

goal-run-status-checkpoint:
	$(PYTHON) -m ops.scripts.goal_run_status checkpoint --vault "$(VAULT)" --reason "$(GOAL_CHECKPOINT_REASON)"

auto-improve-goal-run: auto-improve-goal-preflight
	$(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --policy "$(POLICY)" --goal-contract "$(GOAL_CONTRACT)" --goal-profile "$(GOAL_ACTIVE_PROFILE)" --status-out "$(GOAL_STATUS_OUT)" --audit-jsonl "$(GOAL_AUDIT_JSONL)" --heartbeat-interval "$(GOAL_HEARTBEAT_INTERVAL)" --checkpoint-interval "$(GOAL_CHECKPOINT_INTERVAL)" --executor "$(GOAL_EXECUTOR)" $(GOAL_SESSION_ARG) $(GOAL_RUN_EXTRA_ARGS)

auto-improve-goal-resume: auto-improve-goal-preflight
	$(PYTHON) -m ops.scripts.auto_improve_loop --vault "$(VAULT)" --policy "$(POLICY)" --goal-contract "$(GOAL_CONTRACT)" --goal-profile "$(GOAL_ACTIVE_PROFILE)" --status-out "$(GOAL_STATUS_OUT)" --audit-jsonl "$(GOAL_AUDIT_JSONL)" --heartbeat-interval "$(GOAL_HEARTBEAT_INTERVAL)" --checkpoint-interval "$(GOAL_CHECKPOINT_INTERVAL)" --executor "$(GOAL_EXECUTOR)" $(GOAL_RESUME_CHECKPOINT_ARG) $(GOAL_RESUME_SESSION_ARG) $(GOAL_RUN_EXTRA_ARGS)

auto-improve-goal-finalize:
	$(PYTHON) -m ops.scripts.goal_run_status checkpoint --vault "$(VAULT)" --reason "profile closeout checkpoint; goal remains active until sustained profile completion is verified"
	$(MAKE) auto-improve-readiness-report-body session-synopsis artifact-freshness-check

goal-prompt:
	$(PYTHON) -m ops.scripts.goal_prompt --contract ops/reports/codex-goal-contract.json --out "$(GOAL_PROMPT_OUT)"

remediation-backlog:
	$(PYTHON) -m ops.scripts.remediation_backlog --vault "$(VAULT)" --out "$(REMEDIATION_BACKLOG_OUT)"

self-improvement-negative-lessons:
	$(PYTHON) -m ops.scripts.self_improvement_negative_lessons --vault "$(VAULT)" --out "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT)"

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
