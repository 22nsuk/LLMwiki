from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.mechanism.promotion_gate import main as promotion_gate_main
from tests.cli_test_runtime import CliInvocationResult, invoke_cli_main

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]
SCHEMA_PATHS = {
    "wiki-maintainer-policy.schema.json": REPO_ROOT / "ops" / "schemas" / "wiki-maintainer-policy.schema.json",
    "eval-report.schema.json": REPO_ROOT / "ops" / "schemas" / "eval-report.schema.json",
    "lint-report.schema.json": REPO_ROOT / "ops" / "schemas" / "lint-report.schema.json",
    "run-ledger.schema.json": REPO_ROOT / "ops" / "schemas" / "run-ledger.schema.json",
    "changed-files-manifest.schema.json": REPO_ROOT / "ops" / "schemas" / "changed-files-manifest.schema.json",
    "promotion-report.schema.json": REPO_ROOT / "ops" / "schemas" / "promotion-report.schema.json",
    "mechanism-assessment-report.schema.json": REPO_ROOT / "ops" / "schemas" / "mechanism-assessment-report.schema.json",
}


def seed_promotion_vault(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for name, source in SCHEMA_PATHS.items():
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
        "producer": "tests.test_promotion_gate_exit_codes",
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
        "producer": "tests.test_promotion_gate_exit_codes",
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


def mechanism_report(
    vault: Path,
    *,
    nonempty: int = 10,
    functions: int = 2,
    branches: int = 1,
    headings: int = 0,
    test_file_count: int = 1,
    test_case_count: int = 1,
    test_guardrail_count: int = 0,
    complexity_score: int = 25,
) -> dict:
    test_files = [f"tests/test_example_{idx}.py" for idx in range(test_file_count)]
    all_targets = ["ops/scripts/example.py", *test_files]
    return {
        "$schema": "ops/schemas/mechanism-assessment-report.schema.json",
        "vault": str(vault.resolve()),
        "generated_at": "2026-04-13T00:00:00Z",
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "primary_targets": ["ops/scripts/example.py"],
        "supporting_targets": [],
        "test_files": test_files,
        "structural_metrics": {
            "nonempty_line_count_total": nonempty,
            "python_function_count": functions,
            "python_branch_node_count": branches,
            "markdown_heading_count": headings,
            "test_file_count": test_file_count,
            "test_case_count": test_case_count,
            "test_guardrail_count": test_guardrail_count,
        },
        "total_structural_metrics": {
            "nonempty_line_count_total": nonempty,
            "python_function_count": functions,
            "python_branch_node_count": branches,
            "markdown_heading_count": headings,
            "test_file_count": test_file_count,
            "test_case_count": test_case_count,
            "test_guardrail_count": test_guardrail_count,
        },
        "complexity_profile": {
            "dimensions": {
                "change_surface": 2,
                "dependency_impact": 2,
                "verification_cost": 2,
                "artifact_heterogeneity": 1,
                "environment_risk": 0,
            },
            "complexity_score": complexity_score,
            "risk_flags": [],
            "primary_targets": ["ops/scripts/example.py"],
            "supporting_targets": [],
            "test_files": test_files,
            "risk_flag_evidence": [],
            "target_profiles": [
                {
                    "path": path,
                    "kind": "python",
                    "nonempty_line_count": nonempty,
                    "python_function_count": functions,
                    "python_branch_node_count": branches,
                    "markdown_heading_count": headings,
                    "python_semantic_complexity_points": functions + branches,
                    "whole_file_volume": nonempty,
                    "coarse_target": False,
                }
                for path in all_targets
            ],
            "dimension_evidence": {
                "change_surface": {
                    "target_count": len(all_targets),
                    "target_count_score": 2,
                    "whole_file_volume": nonempty,
                    "whole_file_volume_score": 2,
                    "per_target_capped_volume": nonempty,
                    "per_target_capped_volume_score": 2,
                    "semantic_volume": functions + branches,
                    "semantic_volume_score": 2,
                    "large_file_target_count": 0,
                    "coarse_target_bias_mitigated": False,
                    "selected_score": 2,
                },
                "verification_cost": {
                    "target_count": len(all_targets),
                    "test_file_count": test_file_count,
                    "test_case_count": test_case_count,
                    "test_guardrail_count": test_guardrail_count,
                    "verification_scope": "targeted_pytest",
                    "reasons": ["fixture"],
                    "selected_score": 2,
                },
            },
        },
        "diagnostics": {
            "unreadable_targets": [],
            "python_parse_failures": [],
        },
    }


def run_ledger() -> dict:
    return {
        "$schema": "ops/schemas/run-ledger.schema.json",
        "run_id": "run-exit-codes",
        "status": "ready",
        "events": [
            {
                "ts": "2026-04-13T00:00:00Z",
                "type": "created",
                "summary": "Initialized run artifacts.",
                "artifacts": ["runs/run-exit-codes/run-ledger.json"],
                "decision": "",
            },
            {
                "ts": "2026-04-13T00:01:00Z",
                "type": "promotion_evaluated",
                "summary": "Prepared candidate",
                "artifacts": ["ops/scripts/example.py"],
                "decision": "PROMOTE",
            }
        ],
    }


def changed_files_manifest() -> dict:
    return {
        "$schema": "ops/schemas/changed-files-manifest.schema.json",
        "run_id": "run-exit-codes",
        "generated_at": "2026-04-13T00:00:00Z",
        "declared_targets": {
            "primary_targets": ["ops/scripts/example.py"],
            "supporting_targets": [],
            "test_files": ["tests/test_example_0.py"],
        },
        "summary": {
            "total_changed_files": 1,
            "added": 0,
            "modified": 1,
            "deleted": 0,
        },
        "files": [{"path": "ops/scripts/example.py", "change_type": "modified"}],
    }


class PromotionGateExitCodeTest(unittest.TestCase):
    def run_module(self, vault: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) if not pythonpath else f"{REPO_ROOT}:{pythonpath}"
        return subprocess.run(
            [sys.executable, "-m", "ops.scripts.promotion_gate", *args],
            cwd=vault,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def run_main(self, vault: Path, *args: str) -> CliInvocationResult:
        return invoke_cli_main(promotion_gate_main, list(args), cwd=vault)

    def seed_valid_artifacts(self, vault: Path) -> None:
        artifacts_dir = vault / "artifacts"
        write_json(artifacts_dir / "baseline-eval.json", eval_report(vault, 10))
        write_json(artifacts_dir / "candidate-eval.json", eval_report(vault, 10))
        write_json(artifacts_dir / "baseline-lint.json", lint_report(vault))
        write_json(artifacts_dir / "candidate-lint.json", lint_report(vault))
        write_json(artifacts_dir / "baseline-mechanism.json", mechanism_report(vault))
        write_json(artifacts_dir / "candidate-mechanism.json", mechanism_report(vault))
        write_json(artifacts_dir / "changed-files-manifest.json", changed_files_manifest())
        write_json(vault / "runs" / "run-exit-codes" / "run-ledger.json", run_ledger())

    def base_args(self, vault: Path) -> list[str]:
        return [
            "--vault",
            str(vault),
            "--artifact-class",
            "system_mechanism",
            "--run-id",
            "run-exit-codes",
            "--primary-target",
            "ops/scripts/example.py",
            "--log-summary",
            "promotion gate exit code regression",
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

    def test_missing_mechanism_args_subprocess_smoke_returns_2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            completed = self.run_module(
                vault,
                "--vault",
                str(vault),
                "--artifact-class",
                "system_mechanism",
                "--run-id",
                "run-exit-codes",
                "--primary-target",
                "ops/scripts/example.py",
                "--log-summary",
                "missing args",
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("missing required arguments for system_mechanism", completed.stderr)

    def test_missing_policy_returns_3(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            completed = self.run_main(
                vault,
                "--vault",
                str(vault),
                "--policy",
                "ops/policies/missing.yaml",
                "--artifact-class",
                "wiki_source",
                "--run-id",
                "run-exit-codes",
                "--primary-target",
                "wiki/source--fake.md",
                "--log-summary",
                "missing policy",
            )
            self.assertEqual(completed.exit_code, 3)
            self.assertIn("missing policy", completed.stderr)

    def test_missing_artifact_returns_4(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_valid_artifacts(vault)
            (vault / "artifacts" / "baseline-eval.json").unlink()
            completed = self.run_main(vault, *self.base_args(vault))
            self.assertEqual(completed.exit_code, 4)
            self.assertIn("missing artifact", completed.stderr)

    def test_invalid_json_artifact_returns_5(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_valid_artifacts(vault)
            (vault / "artifacts" / "baseline-eval.json").write_text("{not-json", encoding="utf-8")
            completed = self.run_main(vault, *self.base_args(vault))
            self.assertEqual(completed.exit_code, 5)
            self.assertIn("failed to decode JSON artifact", completed.stderr)

    def test_schema_invalid_artifact_returns_6(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_valid_artifacts(vault)
            write_json(vault / "artifacts" / "baseline-eval.json", {"status": "pass"})
            completed = self.run_main(vault, *self.base_args(vault))
            self.assertEqual(completed.exit_code, 6)
            self.assertIn("schema validation failed", completed.stderr)

    def test_partial_mechanism_contract_eval_pair_returns_2(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_valid_artifacts(vault)

            completed = self.run_main(
                vault,
                *self.base_args(vault),
                "--baseline-mechanism-contract-eval-report",
                "artifacts/baseline-mechanism-contract-eval.json",
            )

            self.assertEqual(completed.exit_code, 2)
            self.assertIn(
                "mechanism contract eval requires both baseline and candidate reports",
                completed.stderr,
            )

    def test_invalid_output_schema_returns_7(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_valid_artifacts(vault)
            write_json(
                vault / "ops" / "schemas" / "promotion-report.schema.json",
                {
                    "type": "object",
                    "required": ["impossible"],
                    "additionalProperties": True,
                },
            )
            completed = self.run_main(vault, *self.base_args(vault))
            self.assertEqual(completed.exit_code, 7)
            self.assertIn("promotion report schema validation failed", completed.stderr)

    def test_discard_decision_still_returns_0(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            self.seed_valid_artifacts(vault)
            completed = self.run_main(vault, *self.base_args(vault))
            self.assertEqual(completed.exit_code, 0)
            report_path = vault / "runs" / "run-exit-codes" / "promotion-report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["decision"], "DISCARD")


if __name__ == "__main__":
    unittest.main()
