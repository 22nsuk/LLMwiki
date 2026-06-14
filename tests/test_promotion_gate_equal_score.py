from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from ops.scripts.behavior_delta_runtime import (
    classify_surface,
    contract_touches_for_path,
)
from ops.scripts.policy_runtime import load_policy

from tests.minimal_vault_runtime import (
    POLICY_PATH,
    REPO_ROOT,
    SCHEMA_PATHS,
    set_policy_value,
)

LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]

PROMOTION_SCHEMA_NAMES = (
    "wiki-maintainer-policy.schema.json",
    "eval-report.schema.json",
    "lint-report.schema.json",
    "run-ledger.schema.json",
    "changed-files-manifest.schema.json",
    "behavior-delta.schema.json",
    "promotion-report.schema.json",
    "mechanism-assessment-report.schema.json",
)


def seed_promotion_vault(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for name in PROMOTION_SCHEMA_NAMES:
        source = SCHEMA_PATHS[name]
        (vault / "ops" / "schemas" / name).write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (vault / "ops" / "scripts" / "example.py").write_text(
        "def subject():\n    return 1\n",
        encoding="utf-8",
    )
    (vault / "tests" / "test_example.py").write_text(
        "def test_subject():\n    assert True\n",
        encoding="utf-8",
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def eval_report(vault: Path, score: int, max_score: int = 10, status: str = "pass") -> dict:
    return {
        "$schema": "ops/schemas/eval-report.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-13T00:00:00Z",
        "artifact_kind": "wiki_eval_report",
        "producer": "tests.test_promotion_gate_equal_score",
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
            "checked_at": "2026-04-13T00:00:00Z",
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": status,
        "max_score": max_score,
        "total_score": score,
        "pages": [],
    }


def lint_report(
    vault: Path,
    *,
    status: str = "pass",
    error_count: int = 0,
    warning_count: int = 0,
    review_candidate_count: int = 0,
) -> dict:
    return {
        "$schema": "ops/schemas/lint-report.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-13T00:00:00Z",
        "artifact_kind": "wiki_lint_report",
        "producer": "tests.test_promotion_gate_equal_score",
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
            "checked_at": "2026-04-13T00:00:00Z",
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": status,
        "errors": [{}] * error_count,
        "warnings": [{}] * warning_count,
        "review_candidates": [{}] * review_candidate_count,
        "stats": {
            "error_count": error_count,
            "warning_count": warning_count,
            "review_candidate_count": review_candidate_count,
        },
    }


@dataclass(frozen=True)
class MechanismReportOptions:
    primary_targets: list[str] = field(default_factory=list)
    nonempty: int = 0
    functions: int = 0
    branches: int = 0
    headings: int = 0
    test_file_count: int = 0
    test_case_count: int = 0
    complexity_score: int = 0
    risk_flags: list[str] | None = None
    test_files: list[str] | None = None
    supporting_targets: list[str] | None = None
    total_nonempty: int | None = None
    total_functions: int | None = None
    total_branches: int | None = None
    total_headings: int | None = None


def mechanism_report_options(**overrides: Any) -> MechanismReportOptions:
    return replace(MechanismReportOptions(), **overrides)


def mechanism_report(
    vault: Path,
    **overrides: Any,
) -> dict:
    options = mechanism_report_options(**overrides)
    test_files = options.test_files or [
        f"tests/test_example_{idx}.py" for idx in range(options.test_file_count)
    ]
    supporting_targets = options.supporting_targets or []
    all_targets = [*options.primary_targets, *supporting_targets, *test_files]
    total_nonempty = options.total_nonempty or options.nonempty
    total_functions = options.total_functions or options.functions
    total_branches = options.total_branches or options.branches
    total_headings = options.total_headings or options.headings
    return {
        "$schema": "ops/schemas/mechanism-assessment-report.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-13T00:00:00Z",
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "primary_targets": options.primary_targets,
        "supporting_targets": supporting_targets,
        "test_files": test_files,
        "structural_metrics": {
            "nonempty_line_count_total": options.nonempty,
            "python_function_count": options.functions,
            "python_branch_node_count": options.branches,
            "markdown_heading_count": options.headings,
            "test_file_count": options.test_file_count,
            "test_case_count": options.test_case_count,
        },
        "total_structural_metrics": {
            "nonempty_line_count_total": total_nonempty,
            "python_function_count": total_functions,
            "python_branch_node_count": total_branches,
            "markdown_heading_count": total_headings,
            "test_file_count": options.test_file_count,
            "test_case_count": options.test_case_count,
        },
        "complexity_profile": {
            "dimensions": {
                "change_surface": 2,
                "dependency_impact": 2,
                "verification_cost": 2,
                "artifact_heterogeneity": 1,
                "environment_risk": 5 if options.risk_flags else 0,
            },
            "complexity_score": options.complexity_score,
            "risk_flags": options.risk_flags or [],
            "primary_targets": options.primary_targets,
            "supporting_targets": supporting_targets,
            "test_files": test_files,
            "risk_flag_evidence": [
                {
                    "flag": flag,
                    "path": options.primary_targets[0],
                    "reason": "fixture",
                }
                for flag in (options.risk_flags or [])
            ],
            "target_profiles": [
                {
                    "path": path,
                    "kind": "python",
                    "nonempty_line_count": options.nonempty,
                    "python_function_count": options.functions,
                    "python_branch_node_count": options.branches,
                    "markdown_heading_count": options.headings,
                    "python_semantic_complexity_points": (
                        options.functions + options.branches
                    ),
                    "whole_file_volume": options.nonempty,
                    "coarse_target": False,
                }
                for path in all_targets
            ],
            "dimension_evidence": {
                "change_surface": {
                    "target_count": len(all_targets),
                    "target_count_score": 2,
                    "whole_file_volume": total_nonempty,
                    "whole_file_volume_score": 2,
                    "per_target_capped_volume": options.nonempty,
                    "per_target_capped_volume_score": 2,
                    "semantic_volume": total_functions + total_branches,
                    "semantic_volume_score": 2,
                    "large_file_target_count": 0,
                    "coarse_target_bias_mitigated": False,
                    "selected_score": 2,
                },
                "verification_cost": {
                    "target_count": len(all_targets),
                    "test_file_count": options.test_file_count,
                    "test_case_count": options.test_case_count,
                    "verification_scope": "targeted_pytest",
                    "reasons": ["fixture"],
                    "selected_score": 2,
                },
            },
        },
    }


def run_ledger(primary_target: str) -> dict:
    return {
        "$schema": "ops/schemas/run-ledger.schema.json",
        "run_id": "run-equal-score",
        "status": "ready",
        "events": [
            {
                "ts": "2026-04-13T00:00:00Z",
                "type": "created",
                "summary": "Initialized run artifacts.",
                "artifacts": ["runs/run-equal-score/run-ledger.json"],
                "decision": "",
            },
            {
                "ts": "2026-04-13T00:01:00Z",
                "type": "promotion_evaluated",
                "summary": "Prepared candidate",
                "artifacts": [primary_target],
                "decision": "PROMOTE",
            }
        ],
    }


def changed_files_manifest(
    primary_target: str,
    *,
    supporting_targets: list[str] | None = None,
    test_files: list[str] | None = None,
    changed_files: list[dict] | None = None,
) -> dict:
    supporting = supporting_targets or []
    tests = test_files or ["tests/test_example_0.py"]
    files = changed_files or [{"path": primary_target, "change_type": "modified"}]
    summary = {
        "total_changed_files": len(files),
        "added": sum(1 for item in files if item["change_type"] == "added"),
        "modified": sum(1 for item in files if item["change_type"] == "modified"),
        "deleted": sum(1 for item in files if item["change_type"] == "deleted"),
    }
    return {
        "$schema": "ops/schemas/changed-files-manifest.schema.json",
        "run_id": "run-equal-score",
        "generated_at": "2026-04-13T00:00:00Z",
        "declared_targets": {
            "primary_targets": [primary_target],
            "supporting_targets": supporting,
            "test_files": tests,
        },
        "summary": summary,
        "files": files,
    }


def _declared_targets_from_manifest(manifest: dict) -> tuple[list[str], list[str], list[str]]:
    declared = manifest.get("declared_targets", {})
    return (
        list(declared.get("primary_targets", [])),
        list(declared.get("supporting_targets", [])),
        list(declared.get("test_files", [])),
    )


def _path_is_declared(path: str, targets: list[str]) -> bool:
    normalized = path.rstrip("/")
    return any(
        normalized == target.rstrip("/") or normalized.startswith(f"{target.rstrip('/')}/")
        for target in targets
    )


def _semantic_class_for(change_type: str, touches: list[str]) -> str:
    if "promotion_gate" in touches:
        return "promotion_gate_changed"
    if "planning_gate" in touches:
        return "planning_gate_changed"
    if "runtime_execution" in touches:
        return "execution_flow_changed"
    if "policy_contract" in touches:
        return "policy_contract_changed"
    if "schema_contract" in touches or "artifact_contract" in touches:
        return "artifact_contract_changed"
    if change_type == "test_surface":
        return "test_expectation_changed"
    if change_type == "documentation_surface":
        return "documentation_only"
    if change_type in {"runtime_surface", "python_api_surface"}:
        return "implementation_changed"
    return "unknown"


def _expected_direction_for(change_type: str, touches: list[str]) -> str:
    if "test_surface" in touches:
        return "test_guardrail_change"
    if "documentation" in touches:
        return "documentation_change"
    if "promotion_gate" in touches or "planning_gate" in touches:
        return "gate_change"
    if "runtime_execution" in touches:
        return "execution_change"
    if change_type in {"artifact_contract", "policy_surface", "schema_surface"}:
        return "contract_change"
    return "unknown"


def behavior_delta_report(manifest: dict, *, run_id: str = "run-equal-score") -> dict:
    primary_targets, supporting_targets, test_files = _declared_targets_from_manifest(manifest)
    declared_scope = [*primary_targets, *supporting_targets, *test_files]
    deltas: list[dict] = []
    for index, item in enumerate(manifest["files"], start=1):
        path = item["path"]
        manifest_change_type = item["change_type"]
        change_type = classify_surface(path)
        touches = contract_touches_for_path(path, change_type)
        coverage_status = (
            "not_applicable"
            if change_type in {"documentation_surface", "test_surface"}
            else "covered"
            if test_files
            else "coverage_gap"
        )
        details = {
            "file_exists_in_baseline": manifest_change_type != "added",
            "file_exists_in_candidate": manifest_change_type != "deleted",
        }
        if Path(path).suffix == ".py":
            details.update(
                {
                    "added_symbols": [],
                    "removed_symbols": [],
                    "symbol_count_delta": 0,
                }
            )
        deltas.append(
            {
                "id": f"behavior-delta-{index:03d}",
                "target": path,
                "change_type": change_type,
                "manifest_change_type": manifest_change_type,
                "intent": "intended" if _path_is_declared(path, declared_scope) else "unexpected",
                "semantic_class": _semantic_class_for(change_type, touches),
                "expected_direction": _expected_direction_for(change_type, touches),
                "contract_touches": touches,
                "behavior": f"{manifest_change_type} {change_type} file; fixture delta",
                "evidence": ["artifacts/changed-files-manifest.json", *test_files],
                "coverage_status": coverage_status,
                "risk": "high" if manifest_change_type == "deleted" else "medium",
                "details": details,
            }
        )
    return {
        "$schema": "ops/schemas/behavior-delta.schema.json",
        "run_id": run_id,
        "generated_at": "2026-04-13T00:00:00Z",
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "primary_targets": primary_targets,
        "supporting_targets": supporting_targets,
        "test_files": test_files,
        "inputs": {
            "baseline_eval_report": "artifacts/baseline-eval.json",
            "candidate_eval_report": "artifacts/candidate-eval.json",
            "baseline_lint_report": "artifacts/baseline-lint.json",
            "candidate_lint_report": "artifacts/candidate-lint.json",
            "baseline_mechanism_report": "artifacts/baseline-mechanism.json",
            "candidate_mechanism_report": "artifacts/candidate-mechanism.json",
            "changed_files_manifest": "artifacts/changed-files-manifest.json",
        },
        "summary": {
            "behavior_changed": bool(deltas),
            "changed_file_count": len(manifest["files"]),
            "delta_count": len(deltas),
            "intended_change_count": sum(1 for delta in deltas if delta["intent"] == "intended"),
            "unexpected_change_count": sum(1 for delta in deltas if delta["intent"] == "unexpected"),
            "unknown_intent_count": 0,
            "coverage_gap_count": sum(
                1 for delta in deltas if delta["coverage_status"] == "coverage_gap"
            ),
            "contract_touch_count": sum(
                1
                for delta in deltas
                if any(
                    touch not in {"documentation", "test_surface", "unknown"}
                    for touch in delta["contract_touches"]
                )
            ),
            "high_risk_delta_count": sum(1 for delta in deltas if delta["risk"] == "high"),
            "regression_count": 0,
            "risk_level": "medium" if deltas else "none",
        },
        "deltas": deltas,
        "diagnostics": {
            "notes": ["fixture behavior-delta for promotion gate tests"],
            "skipped_files": [],
        },
    }


class PromotionGateEqualScoreTest(unittest.TestCase):
    def run_module(self, vault: Path, *args: str) -> dict:
        env = os.environ.copy()
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) if not pythonpath else f"{REPO_ROOT}:{pythonpath}"
        subprocess.run(
            [sys.executable, "-m", "ops.scripts.promotion_gate", *args],
            cwd=vault,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        report_path = vault / "runs" / "run-equal-score" / "promotion-report.json"
        return json.loads(report_path.read_text(encoding="utf-8"))

    def seed_reports(
        self,
        vault: Path,
        *,
        baseline_eval: dict,
        candidate_eval: dict,
        baseline_lint: dict,
        candidate_lint: dict,
        baseline_mechanism: dict,
        candidate_mechanism: dict,
        changed_manifest: dict | None = None,
        include_behavior_delta: bool = False,
    ) -> None:
        artifacts_dir = vault / "artifacts"
        write_json(artifacts_dir / "baseline-eval.json", baseline_eval)
        write_json(artifacts_dir / "candidate-eval.json", candidate_eval)
        write_json(artifacts_dir / "baseline-lint.json", baseline_lint)
        write_json(artifacts_dir / "candidate-lint.json", candidate_lint)
        write_json(artifacts_dir / "baseline-mechanism.json", baseline_mechanism)
        write_json(artifacts_dir / "candidate-mechanism.json", candidate_mechanism)
        candidate_primary_targets = candidate_mechanism.get("primary_targets", ["ops/scripts/example.py"])
        candidate_supporting_targets = candidate_mechanism.get("supporting_targets", [])
        candidate_test_files = candidate_mechanism.get("test_files", ["tests/test_example_0.py"])
        manifest = changed_manifest or changed_files_manifest(
            candidate_primary_targets[0],
            supporting_targets=candidate_supporting_targets,
            test_files=candidate_test_files,
        )
        write_json(artifacts_dir / "changed-files-manifest.json", manifest)
        if include_behavior_delta:
            write_json(artifacts_dir / "behavior-delta.json", behavior_delta_report(manifest))
        write_json(vault / "runs" / "run-equal-score" / "run-ledger.json", run_ledger("ops/scripts/example.py"))

    def base_args(
        self,
        vault: Path,
        *,
        behavior_delta: bool = False,
        auto_improve_run: bool = False,
    ) -> list[str]:
        args = [
            "--vault",
            str(vault),
            "--artifact-class",
            "system_mechanism",
            "--run-id",
            "run-equal-score",
            "--primary-target",
            "ops/scripts/example.py",
            "--log-summary",
            "equal score promotion regression",
            "--signoff-status",
            "approved",
            "--baseline-eval-report",
            "artifacts/baseline-eval.json",
            "--candidate-eval-report",
            "artifacts/candidate-eval.json",
            "--baseline-lint-report",
            "artifacts/baseline-lint.json",
            "--candidate-lint-report",
            "artifacts/candidate-lint.json",
            "--baseline-mechanism-report",
            "artifacts/baseline-mechanism.json",
            "--candidate-mechanism-report",
            "artifacts/candidate-mechanism.json",
            "--changed-files-manifest",
            "artifacts/changed-files-manifest.json",
        ]
        if behavior_delta:
            args.extend(["--behavior-delta", "artifacts/behavior-delta.json"])
        if auto_improve_run:
            args.append("--auto-improve-run")
        return args

    def test_same_eval_with_lint_improvement_promotes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault, review_candidate_count=2),
                candidate_lint=lint_report(vault, review_candidate_count=1),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))
            self.assertEqual(report["decision"], "PROMOTE")
            self.assertEqual(report["outcome"], "promoted")
            self.assertEqual(report["decision_record"]["decision"], "PROMOTE")
            self.assertEqual(report["decision_record"]["source_rule"], "default_promote")
            self.assertEqual(
                report["decision_reduction"]["selected_decision_id"],
                report["decision_record"]["decision_id"],
            )

    def test_same_eval_missing_behavior_delta_discards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault, review_candidate_count=2),
                candidate_lint=lint_report(vault, review_candidate_count=1),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
            )

            report = self.run_module(vault, *self.base_args(vault))

            self.assertEqual(report["decision"], "DISCARD")
            self.assertEqual(report["outcome"], "discarded")
            self.assertEqual(report["decision_record"]["decision"], "DISCARD")
            self.assertEqual(report["decision_record"]["source_rule"], "behavior_delta_presence")
            presence_check = next(
                check for check in report["checks"] if check["id"] == "behavior_delta_presence"
            )
            self.assertEqual(presence_check["status"], "FAIL")
            self.assertIn("equal_score_promotion", presence_check["detail"])

    def test_score_improvement_promotes_without_secondary_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10, max_score=11, status="fail"),
                candidate_eval=eval_report(vault, 11),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=12,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=30,
                ),
            )

            report = self.run_module(vault, *self.base_args(vault))
            self.assertEqual(report["decision"], "PROMOTE")
            presence_check = next(
                check for check in report["checks"] if check["id"] == "behavior_delta_presence"
            )
            self.assertEqual(presence_check["status"], "WARN")

    def test_auto_improve_requires_behavior_delta_even_with_score_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10, max_score=11, status="fail"),
                candidate_eval=eval_report(vault, 11),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=12,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=30,
                ),
            )

            report = self.run_module(vault, *self.base_args(vault, auto_improve_run=True))

            self.assertEqual(report["decision"], "DISCARD")
            presence_check = next(
                check for check in report["checks"] if check["id"] == "behavior_delta_presence"
            )
            self.assertEqual(presence_check["status"], "FAIL")
            self.assertIn("auto_improve_run", presence_check["detail"])

    def test_same_eval_with_structural_regression_discards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=12,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=2,
                    test_case_count=2,
                    complexity_score=28,
                    test_files=["tests/test_example.py", "tests/test_extra.py"],
                ),
            )

            report = self.run_module(vault, *self.base_args(vault))
            self.assertEqual(report["decision"], "DISCARD")

    def test_changed_files_outside_allowed_apply_roots_discards_even_when_declared_in_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 11),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=["README.md"],
                    test_files=["tests/test_example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=["README.md"],
                    test_files=["tests/test_example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                changed_manifest=changed_files_manifest(
                    "ops/scripts/example.py",
                    supporting_targets=["README.md"],
                    test_files=["tests/test_example.py"],
                    changed_files=[
                        {"path": "README.md", "change_type": "modified"},
                        {"path": "ops/scripts/example.py", "change_type": "modified"},
                    ],
                ),
            )

            report = self.run_module(
                vault,
                *self.base_args(vault),
                "--supporting-target",
                "README.md",
            )

            self.assertEqual(report["decision"], "DISCARD")
            apply_root_check = next(
                check for check in report["checks"] if check["id"] == "changed_files_manifest_allowed_apply_roots"
            )
            self.assertEqual(apply_root_check["status"], "FAIL")
            self.assertIn("README.md", apply_root_check["detail"])
            self.assertIn("ops/", apply_root_check["detail"])

    def test_test_only_changed_files_discard_without_primary_target_touch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 11),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    test_files=["tests/test_example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    test_files=["tests/test_example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                changed_manifest=changed_files_manifest(
                    "ops/scripts/example.py",
                    test_files=["tests/test_example.py"],
                    changed_files=[
                        {"path": "tests/test_example.py", "change_type": "modified"},
                    ],
                ),
            )

            report = self.run_module(vault, *self.base_args(vault))

            self.assertEqual(report["decision"], "DISCARD")
            primary_touch_check = next(
                check for check in report["checks"] if check["id"] == "changed_files_manifest_primary_targets_touched"
            )
            self.assertEqual(primary_touch_check["status"], "FAIL")
            self.assertIn("do not touch any primary target", primary_touch_check["detail"])

    def test_same_eval_discards_when_primary_slims_but_total_complexity_regresses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    supporting_targets=["ops/scripts/helper_runtime.py"],
                    nonempty=5,
                    functions=1,
                    branches=0,
                    headings=0,
                    total_nonempty=18,
                    total_functions=3,
                    total_branches=4,
                    total_headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
            )

            report = self.run_module(vault, *self.base_args(vault))
            self.assertEqual(report["decision"], "DISCARD")
            complexity_check = next(
                item for item in report["checks"] if item["id"] == "structural_complexity_non_regression"
            )
            self.assertEqual(complexity_check["status"], "FAIL")
            self.assertIn("baseline_total=", complexity_check["detail"])

    def test_same_eval_allows_test_backed_nonempty_growth_within_policy_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=3052,
                    functions=27,
                    branches=22,
                    headings=0,
                    test_file_count=1,
                    test_case_count=5,
                    complexity_score=57,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=3065,
                    functions=27,
                    branches=22,
                    headings=0,
                    test_file_count=1,
                    test_case_count=6,
                    complexity_score=57,
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))

            self.assertEqual(report["decision"], "PROMOTE")
            complexity_check = next(
                item for item in report["checks"] if item["id"] == "structural_complexity_non_regression"
            )
            self.assertEqual(complexity_check["status"], "PASS")

    def test_same_eval_discards_when_test_backed_nonempty_growth_exceeds_policy_budget(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=3052,
                    functions=27,
                    branches=22,
                    headings=0,
                    test_file_count=1,
                    test_case_count=5,
                    complexity_score=57,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=3073,
                    functions=27,
                    branches=22,
                    headings=0,
                    test_file_count=1,
                    test_case_count=6,
                    complexity_score=57,
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))

            self.assertEqual(report["decision"], "DISCARD")
            complexity_check = next(
                item for item in report["checks"] if item["id"] == "structural_complexity_non_regression"
            )
            self.assertEqual(complexity_check["status"], "FAIL")

    def test_same_eval_discards_when_semantic_complexity_grows_with_tests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=3052,
                    functions=27,
                    branches=22,
                    headings=0,
                    test_file_count=1,
                    test_case_count=5,
                    complexity_score=57,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=3124,
                    functions=30,
                    branches=33,
                    headings=0,
                    test_file_count=1,
                    test_case_count=6,
                    complexity_score=61,
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))

            self.assertEqual(report["decision"], "DISCARD")
            complexity_check = next(
                item for item in report["checks"] if item["id"] == "structural_complexity_non_regression"
            )
            self.assertEqual(complexity_check["status"], "FAIL")

    def test_same_eval_without_secondary_improvement_discards(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            mechanism = mechanism_report(
                vault,
                primary_targets=["ops/scripts/example.py"],
                nonempty=10,
                functions=2,
                branches=1,
                headings=0,
                test_file_count=1,
                test_case_count=1,
                complexity_score=25,
            )
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism,
                candidate_mechanism=mechanism,
            )

            report = self.run_module(vault, *self.base_args(vault))
            self.assertEqual(report["decision"], "DISCARD")

    def test_same_eval_with_high_risk_flag_and_tests_increase_still_promotes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault),
                candidate_lint=lint_report(vault),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=2,
                    test_case_count=3,
                    complexity_score=35,
                    risk_flags=["schema_change"],
                    test_files=["tests/test_example.py", "tests/test_extra.py"],
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))
            self.assertEqual(report["decision"], "PROMOTE")
            risk_check = next(check for check in report["checks"] if check["id"] == "risk_flags")
            self.assertEqual(risk_check["status"], "WARN")

    def test_require_log_entry_false_marks_log_not_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            set_policy_value(
                vault,
                ("mutation_policy", "require_log_entry"),
                False,
            )
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault, review_candidate_count=2),
                candidate_lint=lint_report(vault, review_candidate_count=1),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))
            self.assertEqual(report["decision"], "PROMOTE")
            self.assertFalse(report["log"]["required"])
            self.assertEqual(report["log"]["status"], "not_required")
            self.assertIn("no system/system-log.md append is required", report["next_action"])

    def test_same_eval_honors_policy_selected_secondary_axes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            set_policy_value(
                vault,
                ("equal_score_promotion", "secondary_axes"),
                ["lint"],
            )
            self.seed_reports(
                vault,
                baseline_eval=eval_report(vault, 10),
                candidate_eval=eval_report(vault, 10),
                baseline_lint=lint_report(vault, review_candidate_count=2),
                candidate_lint=lint_report(vault, review_candidate_count=1),
                baseline_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=10,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=25,
                ),
                candidate_mechanism=mechanism_report(
                    vault,
                    primary_targets=["ops/scripts/example.py"],
                    nonempty=12,
                    functions=2,
                    branches=1,
                    headings=0,
                    test_file_count=1,
                    test_case_count=1,
                    complexity_score=28,
                ),
                include_behavior_delta=True,
            )

            report = self.run_module(vault, *self.base_args(vault, behavior_delta=True))
            self.assertEqual(report["decision"], "PROMOTE")
            eligibility_check = next(
                check
                for check in report["checks"]
                if check["id"] == "equal_score_secondary_eligibility"
            )
            self.assertIn("selected_axes=['lint']", eligibility_check["detail"])


if __name__ == "__main__":
    unittest.main()
