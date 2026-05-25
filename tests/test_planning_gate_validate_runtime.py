from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import ops.scripts.planning_gate_validate_runtime as planning_gate_validate_runtime
from ops.scripts.finalize_run_runtime import finalize_run
from ops.scripts.planning_gate_artifact_runtime import (
    ArtifactLoadError,
    load_artifact,
    validate_artifact,
)
from ops.scripts.planning_gate_phase_checks_runtime import finalized_only_phase_checks
from ops.scripts.planning_gate_phase_state_runtime import (
    MechanismPhaseState,
    classify_mechanism_phase,
    load_completed_mechanism_inputs,
)
from ops.scripts.planning_gate_report_runtime import (
    artifact_dir_report_path,
    validate_run_dir,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    PLANNING_GATE_VALIDATION_REPORT_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.starter_bundle_runtime import (
    DEFAULT_STARTER_BUNDLE,
    StarterBundleDefinition,
    starter_bundle_path,
)

from tests.minimal_vault_runtime import seed_minimal_vault, seed_planning_artifacts
from tests.test_planning_gate_validate import seed_mechanism_run_artifacts


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
    )


class PlanningGateValidateRuntimeTest(unittest.TestCase):
    def test_runtime_facade_does_not_reexport_owner_helpers(self) -> None:
        for name in (
            "_classify_mechanism_phase",
            "_mechanism_phase_state",
            "_mechanism_phase",
            "_placeholder_mechanism_bundle",
            "_load_completed_mechanism_inputs",
            "_slugify_heading",
            "_system_log_contains_entry_ref",
            "_completed_mechanism_phase_checks",
            "_finalized_only_phase_checks",
            "_mechanism_phase_checks",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(planning_gate_validate_runtime, name))

    def test_classify_mechanism_phase_prefers_bundle_phase_then_run_status(self) -> None:
        starter_bundle = StarterBundleDefinition(
            name="planning_default",
            path="ops/templates",
            phase="starter",
            promotion_report_input_placeholders={},
        )

        self.assertEqual(
            classify_mechanism_phase(
                starter_bundle=starter_bundle,
                promotion_report={},
                run_ledger={},
            ),
            "starter",
        )
        self.assertEqual(
            classify_mechanism_phase(
                starter_bundle=None,
                promotion_report={"artifact_class": "system_mechanism"},
                run_ledger={"status": "ready"},
            ),
            "mechanism_evaluated",
        )
        self.assertEqual(
            classify_mechanism_phase(
                starter_bundle=None,
                promotion_report={"artifact_class": "system_mechanism"},
                run_ledger={"status": "complete"},
            ),
            "mechanism_finalized",
        )

    def test_load_completed_mechanism_inputs_reports_missing_candidate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-runtime-missing-input"
            run_dir = seed_mechanism_run_artifacts(vault, run_id)
            (run_dir / "candidate-mechanism-assessment.json").unlink()

            phase_state = MechanismPhaseState(
                artifact_dir_report=f"runs/{run_id}",
                phase="mechanism_evaluated",
                promotion_report=load_artifact(run_dir / "promotion-report.json"),
                run_ledger=load_artifact(run_dir / "run-ledger.json"),
                planning_validation=load_artifact(run_dir / "planning-validation.json"),
            )

            completed_inputs = load_completed_mechanism_inputs(vault, phase_state)

            self.assertFalse(completed_inputs.ready)
            self.assertIn(
                "candidate-mechanism-assessment.json",
                " ".join(completed_inputs.input_validation_failures),
            )

    def test_finalized_only_phase_checks_pass_after_finalize_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_id = "run-runtime-finalized"
            run_dir = seed_mechanism_run_artifacts(vault, run_id)

            finalize_run(vault, run_id)

            phase_state = MechanismPhaseState(
                artifact_dir_report=f"runs/{run_id}",
                phase="mechanism_finalized",
                promotion_report=load_artifact(run_dir / "promotion-report.json"),
                run_ledger=load_artifact(run_dir / "run-ledger.json"),
                planning_validation=load_artifact(run_dir / "planning-validation.json"),
            )

            checks = finalized_only_phase_checks(vault, phase_state)

            self.assertTrue(all(item["pass"] for item in checks))

    def test_validate_run_dir_uses_injected_runtime_context_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-runtime-timestamp")

            report = validate_run_dir(vault, run_dir, context=fixed_context())

            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(
                validate_with_schema(
                    report,
                    load_schema(vault / PLANNING_GATE_VALIDATION_REPORT_SCHEMA_PATH),
                ),
                [],
            )
            event_log = vault / "runs" / "run-runtime-timestamp" / "runtime-events.jsonl"
            events = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["component"], "planning_gate_validate")
            self.assertEqual(events[0]["phase"], "mechanism_evaluated")
            self.assertEqual(events[0]["decision"], "pass")
            self.assertEqual(events[0]["policy_version"], 4)

    def test_validate_starter_bundle_does_not_append_placeholder_runtime_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            artifact_dir = starter_bundle_path(vault, policy, DEFAULT_STARTER_BUNDLE)
            seed_planning_artifacts(vault, "run-YYYYMMDD-slug", artifact_dir=artifact_dir)

            report = validate_run_dir(vault, artifact_dir, policy=policy, context=fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                sorted(path.relative_to(vault).as_posix() for path in vault.rglob("*.jsonl")),
                [],
            )

    def test_artifact_dir_report_path_normalizes_windows_separator_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            self.assertEqual(
                artifact_dir_report_path(vault, Path("runs\\run-temp\\artifacts")),
                "runs/run-temp/artifacts",
            )

    def test_load_artifact_raises_domain_error_for_non_object_json_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            payload_path = Path(temp_dir) / "bad.json"
            payload_path.write_text('["not", "an", "object"]', encoding="utf-8")

            with self.assertRaises(ArtifactLoadError):
                load_artifact(payload_path)

    def test_validate_artifact_reports_domain_load_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            artifact_dir = vault / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            (artifact_dir / "seed.yaml").write_text("- invalid-root\n", encoding="utf-8")

            result = validate_artifact(
                vault,
                artifact_dir,
                "seed.yaml",
                "ops/schemas/seed.schema.json",
            )

            self.assertFalse(result["pass"])
            self.assertTrue(any("failed to load artifact" in error for error in result["errors"]))
            self.assertTrue(any("yaml root must be a mapping" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
