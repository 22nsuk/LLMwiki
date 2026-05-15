from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import load_policy
from ops.scripts.promotion_decision_registry_runtime import attach_decision_contract
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault


LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]
FIXTURE_GENERATED_AT = "2026-04-15T00:00:00Z"
FIXTURE_REPORT_PRODUCER = "tests.run_mechanism_experiment_test_utils"


@dataclass(frozen=True)
class PromotionReportCallExpectation:
    run_id: str
    primary_targets: tuple[str, ...]
    supporting_targets: tuple[str, ...]
    log_summary: str
    require_signoff: bool
    signoff_status: str | None
    signoff_by: str | None
    signoff_ts: str | None
    changed_files_manifest_path: str
    behavior_delta_path: str


@dataclass(frozen=True)
class ForcedPromotionReportPatch:
    decision: str
    signoff_required: bool | None = None
    signoff_status: str | None = None
    signoff_by: str | None = None
    signoff_ts: str | None = None
    log_status: str | None = "pending"
    log_entry_ref: str | None = ""
    checks: tuple[dict[str, str], ...] | None = None
    decision_contract_entries: tuple[dict[str, Any], ...] = ()


PENDING_SIGNOFF_DECISION_CONTRACT: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "signoff_status",
        "decision": "HOLD",
        "reason_code": "signoff_status",
        "reason_detail": "fixture forces pending signoff hold",
        "evidence_refs": ["signoff_status"],
    },
)


def _write_json(vault: Path, rel_path: str, payload: dict[str, Any]) -> str:
    (vault / rel_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rel_path


def _canonical_report_fields(vault: Path, *, artifact_kind: str) -> dict[str, Any]:
    return {
        "$schema": f"ops/schemas/{artifact_kind.removeprefix('wiki_').replace('_', '-')}.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": FIXTURE_GENERATED_AT,
        "artifact_kind": artifact_kind,
        "producer": FIXTURE_REPORT_PRODUCER,
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture",
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": FIXTURE_GENERATED_AT,
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
    }


def _eval_report_payload(vault: Path) -> dict[str, Any]:
    return {
        **_canonical_report_fields(vault, artifact_kind="wiki_eval_report"),
        "$schema": "ops/schemas/eval-report.schema.json",
        "status": "pass",
        "max_score": 10,
        "total_score": 10,
        "pages": [],
    }


def _lint_report_payload(vault: Path) -> dict[str, Any]:
    return {
        **_canonical_report_fields(vault, artifact_kind="wiki_lint_report"),
        "$schema": "ops/schemas/lint-report.schema.json",
        "status": "pass",
        "errors": [],
        "warnings": [],
        "review_candidates": [],
        "stats": {
            "error_count": 0,
            "warning_count": 0,
            "review_candidate_count": 0,
        },
    }


def _mechanism_target_profiles(paths: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "path": path,
            "kind": "python",
            "nonempty_line_count": 10,
            "python_function_count": 2,
            "python_branch_node_count": 1,
            "markdown_heading_count": 0,
            "python_semantic_complexity_points": 3,
            "whole_file_volume": 10,
            "coarse_target": False,
        }
        for path in paths
    ]


def _mechanism_complexity_profile(
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
) -> dict[str, Any]:
    target_count = len(primary_targets) + len(supporting_targets) + len(test_files)
    return {
        "dimensions": {
            "change_surface": 2,
            "dependency_impact": 2,
            "verification_cost": 2,
            "artifact_heterogeneity": 1,
            "environment_risk": 0,
        },
        "complexity_score": 25,
        "risk_flags": [],
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "test_files": test_files,
        "risk_flag_evidence": [],
        "target_profiles": _mechanism_target_profiles([*primary_targets, *supporting_targets, *test_files]),
        "dimension_evidence": {
            "change_surface": {
                "target_count": target_count,
                "target_count_score": 2,
                "whole_file_volume": 10,
                "whole_file_volume_score": 2,
                "per_target_capped_volume": 10,
                "per_target_capped_volume_score": 2,
                "semantic_volume": 3,
                "semantic_volume_score": 2,
                "large_file_target_count": 0,
                "coarse_target_bias_mitigated": False,
                "selected_score": 2,
            },
            "verification_cost": {
                "target_count": target_count,
                "test_file_count": len(test_files),
                "test_case_count": len(test_files),
                "verification_scope": "targeted_pytest",
                "reasons": ["fixture"],
                "selected_score": 2,
            },
        },
    }


def _mechanism_report_payload(
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
) -> dict[str, Any]:
    structural_metrics = {
        "nonempty_line_count_total": 10,
        "python_function_count": 2,
        "python_branch_node_count": 1,
        "markdown_heading_count": 0,
        "test_file_count": len(test_files),
        "test_case_count": len(test_files),
    }
    return {
        "$schema": "ops/schemas/mechanism-assessment-report.schema.json",
        "vault": "",
        "generated_at": FIXTURE_GENERATED_AT,
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "test_files": test_files,
        "structural_metrics": structural_metrics,
        "total_structural_metrics": dict(structural_metrics),
        "complexity_profile": _mechanism_complexity_profile(
            primary_targets,
            supporting_targets,
            test_files,
        ),
        "diagnostics": {
            "unreadable_targets": [],
            "python_parse_failures": [],
        },
    }


def write_stubbed_capture_artifacts(
    vault: Path,
    *,
    run_id: str,
    phase: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
) -> dict:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    eval_rel = _write_json(
        vault,
        f"runs/{run_id}/{phase}-eval.json",
        _eval_report_payload(vault),
    )
    lint_rel = _write_json(
        vault,
        f"runs/{run_id}/{phase}-lint.json",
        _lint_report_payload(vault),
    )
    mechanism_payload = _mechanism_report_payload(primary_targets, supporting_targets, test_files)
    mechanism_payload["vault"] = str(vault.resolve())
    mechanism_rel = _write_json(
        vault,
        f"runs/{run_id}/{phase}-mechanism-assessment.json",
        mechanism_payload,
    )
    return {
        "lint": lint_rel,
        "eval": eval_rel,
        "mechanism": mechanism_rel,
    }


def _assert_promotion_report_call(
    expectation: PromotionReportCallExpectation,
    *,
    run_id: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    log_summary: str,
    require_signoff: bool,
    signoff_status: str | None,
    signoff_by: str | None,
    signoff_ts: str | None,
    changed_files_manifest_path: str,
    behavior_delta_path: str | None,
) -> None:
    actual = {
        "run_id": run_id,
        "primary_targets": tuple(primary_targets),
        "supporting_targets": tuple(supporting_targets),
        "log_summary": log_summary,
        "require_signoff": require_signoff,
        "signoff_status": signoff_status,
        "signoff_by": signoff_by,
        "signoff_ts": signoff_ts,
        "changed_files_manifest_path": changed_files_manifest_path,
        "behavior_delta_path": behavior_delta_path,
    }
    expected = {
        "run_id": expectation.run_id,
        "primary_targets": expectation.primary_targets,
        "supporting_targets": expectation.supporting_targets,
        "log_summary": expectation.log_summary,
        "require_signoff": expectation.require_signoff,
        "signoff_status": expectation.signoff_status,
        "signoff_by": expectation.signoff_by,
        "signoff_ts": expectation.signoff_ts,
        "changed_files_manifest_path": expectation.changed_files_manifest_path,
        "behavior_delta_path": expectation.behavior_delta_path,
    }
    if actual != expected:
        raise AssertionError(f"unexpected promotion report call: {actual!r} != {expected!r}")


def _apply_forced_promotion_patch(
    promotion_report: dict[str, Any],
    patch: ForcedPromotionReportPatch,
) -> None:
    promotion_report["decision"] = patch.decision
    if patch.signoff_required is not None:
        promotion_report["signoff"]["required"] = patch.signoff_required
    if patch.signoff_status is not None:
        promotion_report["signoff"]["status"] = patch.signoff_status
    if patch.signoff_by is not None:
        promotion_report["signoff"]["by"] = patch.signoff_by
    if patch.signoff_ts is not None:
        promotion_report["signoff"]["ts"] = patch.signoff_ts
    if patch.log_status is not None:
        promotion_report["log"]["status"] = patch.log_status
    if patch.log_entry_ref is not None:
        promotion_report["log"]["entry_ref"] = patch.log_entry_ref
    if patch.checks is not None:
        promotion_report["checks"] = [dict(check) for check in patch.checks]


def forced_promotion_report_builder(
    expectation: PromotionReportCallExpectation,
    patch: ForcedPromotionReportPatch,
) -> Callable[..., Path]:
    def fake_build_promotion_report(_vault: Path, **kwargs: Any) -> Path:
        policy = kwargs["policy"]
        resolved_policy_path = kwargs["resolved_policy_path"]
        run_id = str(kwargs["run_id"])
        _assert_promotion_report_call(
            expectation,
            run_id=run_id,
            primary_targets=list(kwargs["primary_targets"]),
            supporting_targets=list(kwargs["supporting_targets"]),
            log_summary=str(kwargs["log_summary"]),
            require_signoff=bool(kwargs["require_signoff"]),
            signoff_status=kwargs["signoff_status"],
            signoff_by=kwargs["signoff_by"],
            signoff_ts=kwargs["signoff_ts"],
            changed_files_manifest_path=str(kwargs["changed_files_manifest_path"]),
            behavior_delta_path=kwargs.get("behavior_delta_path"),
        )
        if not policy:
            raise AssertionError("expected non-empty policy")
        if not resolved_policy_path:
            raise AssertionError("expected resolved policy path")

        promotion_path = _vault / "runs" / run_id / "promotion-report.json"
        promotion_report = json.loads(promotion_path.read_text(encoding="utf-8"))
        _apply_forced_promotion_patch(promotion_report, patch)
        promotion_report = attach_decision_contract(
            promotion_report,
            [dict(entry) for entry in patch.decision_contract_entries],
            subject_id=run_id,
            subject_kind="system_mechanism",
            policy_version=policy.get("version"),
            source_pass="system_mechanism",
            signoff=promotion_report["signoff"],
        )
        promotion_path.write_text(
            json.dumps(promotion_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return promotion_path

    return fake_build_promotion_report


def seed_wrapper_vault(vault: Path) -> None:
    seed_minimal_vault(vault)
    (vault / "ops" / "schemas" / "eval-report.schema.json").write_text(
        (REPO_ROOT / "ops" / "schemas" / "eval-report.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "schemas" / "lint-report.schema.json").write_text(
        (REPO_ROOT / "ops" / "schemas" / "lint-report.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "schemas" / "mutation-proposals.schema.json").write_text(
        (REPO_ROOT / "ops" / "schemas" / "mutation-proposals.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "schemas" / "changed-files-manifest.schema.json").write_text(
        (REPO_ROOT / "ops" / "schemas" / "changed-files-manifest.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "templates" / "mechanism-run").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    (vault / "tools").mkdir(parents=True, exist_ok=True)

    (vault / "ops" / "scripts" / "example.py").write_text(
        "def subject(value):\n"
        "    if value > 0:\n"
        "        return 1\n"
        "    if value == 0:\n"
        "        return 0\n"
        "    return -1\n",
        encoding="utf-8",
    )
    (vault / "tests" / "test_example.py").write_text(
        "def test_subject_positive():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    (vault / "tools" / "mutate_success.py").write_text(
        "from pathlib import Path\n"
        "root = Path(__file__).resolve().parents[1]\n"
        "(root / 'ops' / 'scripts' / 'example.py').write_text(\n"
        "    \"def subject(value):\\n\"\n"
        "    \"    if value == 0:\\n\"\n"
        "    \"        return 0\\n\"\n"
        "    \"    return 1 if value > 0 else -1\\n\",\n"
        "    encoding='utf-8',\n"
        ")\n"
        "test_path = root / 'tests' / 'test_example.py'\n"
        "test_path.write_text(\n"
        "    test_path.read_text(encoding='utf-8') +\n"
        "    \"\\n\\ndef test_subject_zero():\\n    assert True\\n\",\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    (vault / "tools" / "mutate_out_of_scope.py").write_text(
        "from pathlib import Path\n"
        "root = Path(__file__).resolve().parents[1]\n"
        "(root / 'README.md').write_text('workspace-only out of scope change\\n', encoding='utf-8')\n"
        "(root / 'ops' / 'scripts' / 'example.py').write_text(\n"
        "    \"def subject(value):\\n\"\n"
        "    \"    return 2 if value > 0 else 0\\n\",\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    (vault / "tools" / "mutate_success_with_ephemeral_noise.py").write_text(
        "from pathlib import Path\n"
        "root = Path(__file__).resolve().parents[1]\n"
        "(root / 'ops' / 'scripts' / 'example.py').write_text(\n"
        "    \"def subject(value):\\n\"\n"
        "    \"    if value == 0:\\n\"\n"
        "    \"        return 0\\n\"\n"
        "    \"    return 1 if value > 0 else -1\\n\",\n"
        "    encoding='utf-8',\n"
        ")\n"
        "test_path = root / 'tests' / 'test_example.py'\n"
        "test_path.write_text(\n"
        "    test_path.read_text(encoding='utf-8') +\n"
        "    \"\\n\\ndef test_subject_zero():\\n    assert True\\n\",\n"
        "    encoding='utf-8',\n"
        ")\n"
        "(root / '.obsidian').mkdir(parents=True, exist_ok=True)\n"
        "(root / '.obsidian' / 'workspace.json').write_text('{\"workspace\": \"noise\"}\\n', encoding='utf-8')\n"
        "(root / '.venv' / 'lib64' / 'python3.12' / 'site-packages').mkdir(parents=True, exist_ok=True)\n"
        "(root / '.venv' / 'lib64' / 'python3.12' / 'site-packages' / 'noise.py').write_text('sentinel = 1\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )


def mutation_proposal_report(primary_target: str) -> dict:
    current_policy, _ = load_policy(REPO_ROOT)
    return {
        "$schema": "ops/schemas/mutation-proposals.schema.json",
        "vault": ".",
        "generated_at": "2026-04-14T00:00:00Z",
        "artifact_kind": "mutation_proposals_report",
        "producer": "tests.run_mechanism_experiment_test_utils",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture",
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": "2026-04-14T00:00:00Z",
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": current_policy["version"],
        },
        "status": "pass",
        "summary": {
            "source_candidates_read": 1,
            "log_entries_scanned": 0,
            "proposals_emitted": 1,
            "blocked_proposals": 0,
            "queue_pressure_summary": "session unavailable | contract_regression_signals 1 proposal",
        },
        "diagnostics": {
            "source_mechanism_review_report": "ops/reports/mechanism-review-candidates.json",
            "skipped_candidates": [],
            "evidence_gaps": [],
            "empty_queue_blockers": [],
            "family_session_calibration": {
                "enabled": True,
                "status": "no_session_context",
                "proposal_count": 1,
                "blocked_proposal_count": 0,
                "by_family": [
                    {
                        "family": "contract_regression_signals",
                        "proposal_count": 1,
                        "blocked_proposal_count": 0,
                        "session_priority_delta": 0,
                        "boosted_candidates": 0,
                        "lowered_candidates": 0,
                        "unchanged_candidates": 1,
                        "validation_blocked_sessions": 0,
                        "review_blocked_sessions": 0,
                        "mutation_failed_sessions": 0,
                        "validator_dispatch_sessions": 0,
                        "reviewer_dispatch_sessions": 0,
                        "high_risk_routing_sessions": 0,
                    }
                ],
            },
            "queue_selection": {
                "available_proposal_count": 1,
                "selected_proposal_count": 1,
                "runnable_available_count": 1,
                "blocked_available_count": 0,
                "selected_runnable_count": 1,
                "selected_blocked_count": 0,
                "blocked_reason_counts": [],
            },
            "recent_log_overlap": {
                "dedupe_window": 5,
                "section_ordering": "timestamp",
                "scanned_log_headings": [],
                "matches": [],
            },
        },
        "proposals": [
            {
                "proposal_id": "repeated_same_eval_or_discard__example",
                "source_candidate_id": "mechanism_eval_stagnation_candidate__example",
                "source_candidate_type": "mechanism_eval_stagnation_candidate",
                "family": "contract_regression_signals",
                "tier": "supporting",
                "priority": 80,
                "primary_targets": [primary_target],
                "supporting_targets": [],
                "metrics_triggered": ["stage1_same_eval_rate"],
                "run_ids": ["run-a"],
                "failure_mode": "repeated_same_eval_or_discard",
                "single_mechanism_scope": f"narrow the next mechanism experiment on {primary_target} to one failure mode",
                "change_hypothesis": (
                    f"If the next experiment around {primary_target} isolates one failure mode instead of mutating multiple surfaces, "
                    "candidate_eval improvement or equal-score secondary improvement becomes more likely."
                ),
                "expected_binary_signal": "candidate_eval > baseline_eval or equal-score promotion with one strict secondary improvement",
                "blast_radius_score": 15,
                "must_change_tests": ["tests/test_example.py"],
                "must_change_budget_signal": {
                    "signal": "candidate_eval.total_score",
                    "expected_change": "increase_or_equal_score_secondary",
                },
                "must_not_expand_apply_roots": True,
                "must_not_increase_untyped_surface": True,
                "required_artifacts": [
                    "runs/<run-id>/promotion-report.json",
                    "runs/<run-id>/baseline-mechanism-assessment.json",
                    "runs/<run-id>/candidate-mechanism-assessment.json",
                ],
                "blocked_by": [],
                "priority_breakdown": {
                    "base_priority": 80,
                    "historical_calibration_delta": 0,
                    "session_calibration_delta": 0,
                    "review_candidate_priority": 80,
                    "recent_log_overlap_penalty": 0,
                    "final_priority": 80,
                },
                "why_now": "contract_regression_signals family에서 non-improvement signal이 누적돼 지금 한 번의 단일 mechanism 실험으로 좁힐 가치가 있다.",
            }
        ],
    }


def successful_command_result(command: str, stdout: str = "") -> dict:
    return {
        "command": command,
        "argv": [command],
        "returncode": 0,
        "stdout": stdout,
        "stderr": "",
    }
