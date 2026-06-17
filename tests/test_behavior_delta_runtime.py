from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.artifact_freshness_runtime import (
    EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY,
)
from ops.scripts.core.behavior_delta_runtime import (
    BehaviorDeltaRequest,
    build_behavior_delta_report,
    write_behavior_delta_report,
)
from tests.minimal_vault_runtime import seed_minimal_vault


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_behavior_delta_request(root: Path) -> BehaviorDeltaRequest:
    run_id = "run-behavior-request"
    input_artifacts = {
        "baseline_eval_report": f"runs/{run_id}/baseline-eval.json",
        "candidate_eval_report": f"runs/{run_id}/candidate-eval.json",
        "baseline_lint_report": f"runs/{run_id}/baseline-lint.json",
        "candidate_lint_report": f"runs/{run_id}/candidate-lint.json",
        "baseline_mechanism_report": f"runs/{run_id}/baseline-mechanism-assessment.json",
        "candidate_mechanism_report": f"runs/{run_id}/candidate-mechanism-assessment.json",
        "changed_files_manifest": f"runs/{run_id}/changed-files-manifest.json",
    }
    return BehaviorDeltaRequest(
        baseline_root=root / "vault",
        candidate_root=root / "workspace",
        run_id=run_id,
        generated_at="2026-04-16T00:00:00Z",
        policy_path="ops/policies/wiki-maintainer-policy.yaml",
        policy={"version": 1},
        primary_targets=[],
        supporting_targets=[],
        test_files=[],
        input_artifacts=input_artifacts,
        changed_files_manifest={
            "$schema": "ops/schemas/changed-files-manifest.schema.json",
            "run_id": run_id,
            "generated_at": "2026-04-16T00:00:00Z",
            "declared_targets": {
                "primary_targets": [],
                "supporting_targets": [],
                "test_files": [],
            },
            "summary": {
                "total_changed_files": 0,
                "added": 0,
                "modified": 0,
                "deleted": 0,
            },
            "files": [],
        },
    )


class BehaviorDeltaRuntimeTest(unittest.TestCase):
    def test_build_behavior_delta_report_accepts_request_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _minimal_behavior_delta_request(Path(tmp))

            report = build_behavior_delta_report(request)

            self.assertEqual(report["run_id"], "run-behavior-request")
            self.assertEqual(report["summary"]["changed_file_count"], 0)

    def test_build_behavior_delta_report_rejects_mixed_request_and_legacy_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = _minimal_behavior_delta_request(Path(tmp))

            with self.assertRaisesRegex(
                TypeError,
                "request cannot be combined with legacy keyword arguments: run_id",
            ):
                build_behavior_delta_report(request, run_id="override")

    def test_builds_deterministic_symbol_delta_and_writes_schema_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            workspace = root / "workspace"
            vault.mkdir()
            workspace.mkdir()
            seed_minimal_vault(vault)
            seed_minimal_vault(workspace)

            _write(
                vault / "ops" / "scripts" / "example.py",
                "def keep():\n    return 1\n",
            )
            _write(
                workspace / "ops" / "scripts" / "example.py",
                "def keep():\n    return 1\n\n\ndef helper():\n    return 2\n",
            )
            _write(
                workspace / "tests" / "test_example.py",
                "def test_helper():\n    assert True\n",
            )

            manifest = {
                "$schema": "ops/schemas/changed-files-manifest.schema.json",
                "run_id": "run-behavior",
                "generated_at": "2026-04-16T00:00:00Z",
                "declared_targets": {
                    "primary_targets": ["ops/scripts/example.py"],
                    "supporting_targets": [],
                    "test_files": ["tests/test_example.py"],
                },
                "summary": {
                    "total_changed_files": 2,
                    "added": 1,
                    "modified": 1,
                    "deleted": 0,
                },
                "files": [
                    {"path": "ops/scripts/example.py", "change_type": "modified"},
                    {"path": "tests/test_example.py", "change_type": "added"},
                ],
            }
            input_artifacts = {
                "baseline_eval_report": "runs/run-behavior/baseline-eval.json",
                "candidate_eval_report": "runs/run-behavior/candidate-eval.json",
                "baseline_lint_report": "runs/run-behavior/baseline-lint.json",
                "candidate_lint_report": "runs/run-behavior/candidate-lint.json",
                "baseline_mechanism_report": "runs/run-behavior/baseline-mechanism-assessment.json",
                "candidate_mechanism_report": "runs/run-behavior/candidate-mechanism-assessment.json",
                "changed_files_manifest": "runs/run-behavior/changed-files-manifest.json",
            }

            report = build_behavior_delta_report(
                baseline_root=vault,
                candidate_root=workspace,
                run_id="run-behavior",
                generated_at="2026-04-16T00:00:00Z",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                policy={"version": 1},
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                test_files=["tests/test_example.py"],
                input_artifacts=input_artifacts,
                changed_files_manifest=manifest,
            )

            self.assertEqual(report["summary"]["changed_file_count"], 2)
            self.assertEqual(report["summary"]["delta_count"], 2)
            self.assertEqual(report["summary"]["intended_change_count"], 2)
            self.assertEqual(report["summary"]["unexpected_change_count"], 0)
            self.assertEqual(report["summary"]["unknown_intent_count"], 0)
            self.assertEqual(report["summary"]["contract_touch_count"], 1)
            runtime_delta = report["deltas"][0]
            self.assertEqual(runtime_delta["change_type"], "runtime_surface")
            self.assertEqual(runtime_delta["intent"], "intended")
            self.assertEqual(runtime_delta["semantic_class"], "api_surface_changed")
            self.assertEqual(runtime_delta["expected_direction"], "unknown")
            self.assertEqual(runtime_delta["contract_touches"], ["runtime_logic"])
            self.assertEqual(runtime_delta["coverage_status"], "covered")
            self.assertEqual(runtime_delta["details"]["added_symbols"], ["helper"])
            self.assertIn("added Python symbols: helper", runtime_delta["behavior"])
            test_delta = report["deltas"][1]
            self.assertEqual(test_delta["coverage_status"], "not_applicable")
            self.assertEqual(test_delta["semantic_class"], "test_expectation_changed")
            self.assertEqual(test_delta["expected_direction"], "test_guardrail_change")
            self.assertEqual(test_delta["contract_touches"], ["test_surface"])

            rel_path = write_behavior_delta_report(
                vault=vault,
                report_path="runs/run-behavior/behavior-delta.json",
                report=report,
            )
            self.assertEqual(rel_path, "runs/run-behavior/behavior-delta.json")
            written = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            metadata = written.pop("metadata")
            self.assertEqual(written, report)
            embedded_envelope = next(
                item["value"]
                for item in metadata["properties"]
                if item["name"] == EMBEDDED_ARTIFACT_ENVELOPE_PROPERTY
            )
            envelope = json.loads(embedded_envelope)
            self.assertEqual(envelope["artifact_kind"], "behavior_delta")
            self.assertEqual(envelope["artifact_status"], "archived")
            self.assertEqual(envelope["retention_policy"], "archive")
            self.assertEqual(envelope["currentness"]["status"], "current")

    def test_build_behavior_delta_report_records_parse_errors_and_skipped_manifest_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            workspace = root / "workspace"
            vault.mkdir()
            workspace.mkdir()
            seed_minimal_vault(vault)
            seed_minimal_vault(workspace)

            _write(
                vault / "ops" / "scripts" / "broken_example.py",
                "def keep():\n    return 1\n",
            )
            _write(
                workspace / "ops" / "scripts" / "broken_example.py",
                "def keep(:\n    return 2\n",
            )

            manifest = {
                "$schema": "ops/schemas/changed-files-manifest.schema.json",
                "run_id": "run-behavior-fault",
                "generated_at": "2026-04-16T00:00:00Z",
                "declared_targets": {
                    "primary_targets": [],
                    "supporting_targets": [],
                    "test_files": [],
                },
                "summary": {
                    "total_changed_files": 2,
                    "added": 0,
                    "modified": 2,
                    "deleted": 0,
                },
                "files": [
                    {"path": "", "change_type": "modified"},
                    {"path": "ops/scripts/broken_example.py", "change_type": "renamed"},
                ],
            }
            input_artifacts = {
                "baseline_eval_report": "runs/run-behavior-fault/baseline-eval.json",
                "candidate_eval_report": "runs/run-behavior-fault/candidate-eval.json",
                "baseline_lint_report": "runs/run-behavior-fault/baseline-lint.json",
                "candidate_lint_report": "runs/run-behavior-fault/candidate-lint.json",
                "baseline_mechanism_report": "runs/run-behavior-fault/baseline-mechanism-assessment.json",
                "candidate_mechanism_report": "runs/run-behavior-fault/candidate-mechanism-assessment.json",
                "changed_files_manifest": "runs/run-behavior-fault/changed-files-manifest.json",
            }

            report = build_behavior_delta_report(
                baseline_root=vault,
                candidate_root=workspace,
                run_id="run-behavior-fault",
                generated_at="2026-04-16T00:00:00Z",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                policy={"version": 1},
                primary_targets=[],
                supporting_targets=[],
                test_files=[],
                input_artifacts=input_artifacts,
                changed_files_manifest=manifest,
            )

            self.assertEqual(report["summary"]["changed_file_count"], 2)
            self.assertEqual(report["summary"]["delta_count"], 1)
            self.assertEqual(report["summary"]["unexpected_change_count"], 1)
            self.assertEqual(report["summary"]["coverage_gap_count"], 1)
            self.assertEqual(report["summary"]["risk_level"], "medium")
            delta = report["deltas"][0]
            self.assertEqual(delta["manifest_change_type"], "modified")
            self.assertEqual(delta["coverage_status"], "coverage_gap")
            self.assertEqual(delta["intent"], "unexpected")
            self.assertIn("parse_error", delta["details"])
            self.assertIn("could not be parsed deterministically", delta["behavior"])
            skipped_files = report["diagnostics"]["skipped_files"]
            self.assertEqual(skipped_files[0], {"path": "<missing>", "reason": "missing path"})
            self.assertEqual(skipped_files[1]["path"], "ops/scripts/broken_example.py")
            self.assertEqual(skipped_files[1]["reason"], "unknown manifest change_type")
            self.assertEqual(skipped_files[1]["detail"], "renamed")


if __name__ == "__main__":
    unittest.main()
