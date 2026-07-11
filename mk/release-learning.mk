.PHONY: learning-claim-activation-report learning-claim-evidence-bundle learning-claim-unlock-review learning-confirmed-evidence-cohort learning-confirmed-legacy-reconstruction learning-delta-scoreboard learning-readiness-signoff learning-readiness-signoff-check learning-readiness-signoff-refresh learning-readiness-signoff-revalidation learning-readiness-signoff-revalidation-check learning-readiness-signoff-template remediation-backlog self-improvement-negative-lessons session-synopsis

learning-readiness-signoff:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff --vault "$(VAULT)" --out "$(LEARNING_READINESS_SIGNOFF_OUT)" --accepted-by "$(LEARNING_READINESS_SIGNOFF_ACCEPTED_BY)" --expiry-days "$(LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS)" --risk-owner "$(LEARNING_READINESS_SIGNOFF_RISK_OWNER)" --revalidation-condition "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CONDITION)" --rollback-trigger "$(LEARNING_READINESS_SIGNOFF_ROLLBACK_TRIGGER)" $(if $(LEARNING_READINESS_SIGNOFF_NOTES),--notes "$(LEARNING_READINESS_SIGNOFF_NOTES)",)

learning-readiness-signoff-refresh:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff_refresh --vault "$(VAULT)" --reuse-from "$(LEARNING_READINESS_SIGNOFF_REUSE_FROM)" --out "$(LEARNING_READINESS_SIGNOFF_OUT)"

learning-readiness-signoff-check:
	$(PYTHON) -m ops.scripts.release_closeout_summary --vault "$(VAULT)" --out tmp/learning-readiness-signoff-check-release-closeout-summary.json --profile "$(RELEASE_CLOSEOUT_PROFILE)" --no-fail

learning-readiness-signoff-revalidation:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff_revalidation --vault "$(VAULT)" --out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT)" --window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)" --required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)" --required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)"

learning-readiness-signoff-revalidation-check:
	$(PYTHON) -m ops.scripts.learning_readiness_signoff_revalidation --vault "$(VAULT)" --out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT)" --window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)" --required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)" --required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)" --fail-on-due

learning-readiness-signoff-template:
	$(PYTHON) -m json.tool ops/templates/learning-readiness-signoff.json

learning-confirmed-legacy-reconstruction:
	$(PYTHON) -m ops.scripts.learning_confirmed_legacy_reconstruction --vault "$(VAULT)" --out "$(LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_CANDIDATE_OUT)" --out "$(LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_OUT)" --schema ops/schemas/learning-confirmed-legacy-reconstruction.schema.json --expected-artifact-kind learning_confirmed_legacy_reconstruction --expected-producer ops.scripts.learning_confirmed_legacy_reconstruction

learning-claim-evidence-bundle: learning-confirmed-legacy-reconstruction
	$(PYTHON) -m ops.scripts.learning_claim_evidence_bundle --vault "$(VAULT)" --out "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" --schema ops/schemas/learning-claim-evidence-bundle.schema.json --expected-artifact-kind learning_claim_evidence_bundle --expected-producer ops.scripts.learning_claim_evidence_bundle

learning-confirmed-evidence-cohort: learning-claim-evidence-bundle
	$(PYTHON) -m ops.scripts.learning_confirmed_evidence_cohort --vault "$(VAULT)" --out "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT)" --evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" --confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_CANDIDATE_OUT)" --out "$(LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT)" --schema ops/schemas/learning-confirmed-evidence-cohort.schema.json --expected-artifact-kind learning_confirmed_evidence_cohort --expected-producer ops.scripts.learning_confirmed_evidence_cohort

learning-claim-unlock-review: learning-confirmed-evidence-cohort
	$(PYTHON) -m ops.scripts.learning_claim_unlock_review --vault "$(VAULT)" --out "$(LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT)" $(if $(LEARNING_CLAIM_AUTO_UNLOCK_POLICY),--auto-policy "$(LEARNING_CLAIM_AUTO_UNLOCK_POLICY)",) --evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)" $(if $(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY),--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)",) $(if $(LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY),--approved-by "$(LEARNING_CLAIM_UNLOCK_REVIEW_APPROVED_BY)",) $(if $(LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT),--reviewed-at "$(LEARNING_CLAIM_UNLOCK_REVIEW_REVIEWED_AT)",)
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_UNLOCK_REVIEW_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_UNLOCK_REVIEW_OUT)" --schema ops/schemas/learning-claim-unlock-review.schema.json --expected-artifact-kind learning_claim_unlock_review --expected-producer ops.scripts.learning_claim_unlock_review

learning-delta-scoreboard: learning-claim-unlock-review
	$(PYTHON) -m ops.scripts.learning_delta_scoreboard --vault "$(VAULT)" --out "$(LEARNING_DELTA_SCOREBOARD_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_DELTA_SCOREBOARD_CANDIDATE_OUT)" --out "$(LEARNING_DELTA_SCOREBOARD_OUT)" --schema ops/schemas/learning-delta-scoreboard.schema.json --expected-artifact-kind learning_delta_scoreboard --expected-producer ops.scripts.learning_delta_scoreboard

learning-claim-activation-report: learning-delta-scoreboard
	$(PYTHON) -m ops.scripts.learning_claim_activation_report --vault "$(VAULT)" --out "$(LEARNING_CLAIM_ACTIVATION_REPORT_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(LEARNING_CLAIM_ACTIVATION_REPORT_CANDIDATE_OUT)" --out "$(LEARNING_CLAIM_ACTIVATION_REPORT_OUT)" --schema ops/schemas/learning-claim-activation-report.schema.json --expected-artifact-kind learning_claim_activation_report --expected-producer ops.scripts.learning_claim_activation_report

session-synopsis: learning-claim-activation-report
	$(PYTHON) -m ops.scripts.session_synopsis --vault "$(VAULT)" --out "$(SESSION_SYNOPSIS_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(SESSION_SYNOPSIS_CANDIDATE_OUT)" --out "$(SESSION_SYNOPSIS_OUT)" --schema ops/schemas/session-synopsis.schema.json --expected-artifact-kind session_synopsis --expected-producer ops.scripts.session_synopsis

self-improvement-negative-lessons: session-synopsis
	$(PYTHON) -m ops.scripts.self_improvement_negative_lessons --vault "$(VAULT)" --out "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_CANDIDATE_OUT)" --out "$(SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT)" --schema ops/schemas/self-improvement-negative-lessons.schema.json --expected-artifact-kind self_improvement_negative_lessons --expected-producer ops.scripts.self_improvement_negative_lessons

remediation-backlog: self-improvement-negative-lessons session-synopsis
	$(PYTHON) -m ops.scripts.remediation_backlog --vault "$(VAULT)" --out "$(REMEDIATION_BACKLOG_CANDIDATE_OUT)"
	$(PYTHON) -m ops.scripts.canonical_artifact_promote --vault "$(VAULT)" --candidate "$(REMEDIATION_BACKLOG_CANDIDATE_OUT)" --out "$(REMEDIATION_BACKLOG_OUT)" --schema ops/schemas/remediation-backlog.schema.json --expected-artifact-kind remediation_backlog --expected-producer ops.scripts.remediation_backlog --binding-mode revision
