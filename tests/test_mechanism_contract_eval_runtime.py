from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism.mechanism_contract_eval_runtime import (
    ARTIFACT_KIND,
    MechanismContractEvalRequest,
    write_mechanism_contract_eval_pair,
)
from tests.test_promotion_gate_equal_score import (
    behavior_delta_report,
    changed_files_manifest,
    eval_report,
    lint_report,
    mechanism_report,
    seed_promotion_vault,
    write_json,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_ledger(run_id: str) -> dict:
    events = [
        "created",
        "seed_frozen",
        "baseline_captured",
        "mutation_applied",
        "candidate_captured",
        "repo_health_checked",
    ]
    return {
        "$schema": "ops/schemas/run-ledger.schema.json",
        "run_id": run_id,
        "status": "running",
        "events": [
            {
                "ts": f"2026-04-15T03:{index:02d}:00Z",
                "type": event_type,
                "summary": f"{event_type} fixture",
                "artifacts": [f"runs/{run_id}/{event_type}.json"],
                "decision": "ready",
            }
            for index, event_type in enumerate(events)
        ],
    }


def _seed_contract_eval_run(vault: Path, run_id: str, *, test_files: list[str] | None = None) -> None:
    primary_targets = ["ops/scripts/example.py"]
    resolved_test_files = test_files if test_files is not None else ["tests/test_example.py"]
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "baseline-eval.json", eval_report(vault, 8, status="fail"))
    write_json(run_dir / "candidate-eval.json", eval_report(vault, 8, status="fail"))
    write_json(run_dir / "baseline-lint.json", lint_report(vault))
    write_json(run_dir / "candidate-lint.json", lint_report(vault))
    write_json(
        run_dir / "baseline-mechanism-assessment.json",
        mechanism_report(vault, primary_targets=primary_targets, test_files=resolved_test_files),
    )
    write_json(
        run_dir / "candidate-mechanism-assessment.json",
        mechanism_report(vault, primary_targets=primary_targets, test_files=resolved_test_files),
    )
    manifest = changed_files_manifest(primary_targets[0], test_files=resolved_test_files)
    manifest["run_id"] = run_id
    manifest["declared_targets"]["test_files"] = resolved_test_files
    write_json(run_dir / "changed-files-manifest.json", manifest)
    behavior = behavior_delta_report(manifest, run_id=run_id)
    behavior["inputs"]["baseline_eval_report"] = f"runs/{run_id}/baseline-eval.json"
    behavior["inputs"]["candidate_eval_report"] = f"runs/{run_id}/candidate-eval.json"
    behavior["inputs"]["baseline_lint_report"] = f"runs/{run_id}/baseline-lint.json"
    behavior["inputs"]["candidate_lint_report"] = f"runs/{run_id}/candidate-lint.json"
    behavior["inputs"]["baseline_mechanism_report"] = (
        f"runs/{run_id}/baseline-mechanism-assessment.json"
    )
    behavior["inputs"]["candidate_mechanism_report"] = (
        f"runs/{run_id}/candidate-mechanism-assessment.json"
    )
    behavior["inputs"]["changed_files_manifest"] = f"runs/{run_id}/changed-files-manifest.json"
    write_json(run_dir / "behavior-delta.json", behavior)
    write_json(run_dir / "run-ledger.json", _run_ledger(run_id))


class MechanismContractEvalRuntimeTests(unittest.TestCase):
    def test_write_pair_scores_candidate_contract_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            run_id = "run-contract-eval"
            _seed_contract_eval_run(vault, run_id)
            policy, policy_path = load_policy(vault)

            artifacts = write_mechanism_contract_eval_pair(
                MechanismContractEvalRequest(
                    vault=vault,
                    run_id=run_id,
                    policy=policy,
                    resolved_policy_path=policy_path,
                    policy_path_text="ops/policies/wiki-maintainer-policy.yaml",
                    context=fixed_context(),
                )
            )

            baseline = _read_json(vault / artifacts["baseline"])
            candidate = _read_json(vault / artifacts["candidate"])
            self.assertEqual(
                artifacts,
                {
                    "baseline": f"runs/{run_id}/baseline-mechanism-contract-eval.json",
                    "candidate": f"runs/{run_id}/candidate-mechanism-contract-eval.json",
                },
            )
            self.assertEqual(baseline["artifact_kind"], ARTIFACT_KIND)
            self.assertEqual(candidate["artifact_kind"], ARTIFACT_KIND)
            self.assertEqual((baseline["total_score"], baseline["max_score"], baseline["status"]), (2, 4, "fail"))
            self.assertEqual((candidate["total_score"], candidate["max_score"], candidate["status"]), (4, 4, "pass"))
            candidate_results = {
                result["eval"]: result
                for result in candidate["pages"][0]["results"]
            }
            self.assertTrue(candidate_results["changed_targets_contract"]["pass"])
            self.assertTrue(candidate_results["behavior_delta_contract"]["pass"])
            self.assertEqual(
                candidate_results["behavior_delta_contract"]["detail"]["coverage_gap_count"],
                0,
            )
            baseline_results = {
                result["eval"]: result
                for result in baseline["pages"][0]["results"]
            }
            self.assertFalse(baseline_results["changed_targets_contract"]["pass"])
            self.assertFalse(baseline_results["behavior_delta_contract"]["pass"])

    def test_candidate_contract_eval_reports_coverage_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            run_id = "run-contract-eval-gap"
            _seed_contract_eval_run(vault, run_id, test_files=[])
            policy, policy_path = load_policy(vault)

            artifacts = write_mechanism_contract_eval_pair(
                MechanismContractEvalRequest(
                    vault=vault,
                    run_id=run_id,
                    policy=policy,
                    resolved_policy_path=policy_path,
                    policy_path_text="ops/policies/wiki-maintainer-policy.yaml",
                    context=fixed_context(),
                )
            )

            candidate = _read_json(vault / artifacts["candidate"])
            behavior_result = next(
                result
                for result in candidate["pages"][0]["results"]
                if result["eval"] == "behavior_delta_contract"
            )
            self.assertEqual(candidate["status"], "fail")
            self.assertFalse(behavior_result["pass"])
            self.assertEqual(behavior_result["detail"]["coverage_gap_count"], 1)

    def test_candidate_contract_eval_validates_input_artifact_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            run_id = "run-contract-eval-invalid-input"
            _seed_contract_eval_run(vault, run_id)
            write_json(
                vault / "runs" / run_id / "candidate-lint.json",
                {"$schema": "ops/schemas/lint-report.schema.json"},
            )
            policy, policy_path = load_policy(vault)

            artifacts = write_mechanism_contract_eval_pair(
                MechanismContractEvalRequest(
                    vault=vault,
                    run_id=run_id,
                    policy=policy,
                    resolved_policy_path=policy_path,
                    policy_path_text="ops/policies/wiki-maintainer-policy.yaml",
                    context=fixed_context(),
                )
            )

            candidate = _read_json(vault / artifacts["candidate"])
            promotion_result = next(
                result
                for result in candidate["pages"][0]["results"]
                if result["eval"] == "promotion_gate_contract"
            )
            self.assertEqual(candidate["status"], "fail")
            self.assertFalse(promotion_result["pass"])
            self.assertIn(
                "candidate_lint_report",
                promotion_result["detail"]["missing_or_invalid_inputs"],
            )

    def test_cli_writes_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_promotion_vault(vault)
            run_id = "run-contract-eval-cli"
            _seed_contract_eval_run(vault, run_id)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ops.scripts.mechanism.mechanism_contract_eval",
                    "--vault",
                    str(vault),
                    "--run-id",
                    run_id,
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn(f"runs/{run_id}/baseline-mechanism-contract-eval.json", completed.stdout)
            self.assertTrue((vault / "runs" / run_id / "candidate-mechanism-contract-eval.json").is_file())
