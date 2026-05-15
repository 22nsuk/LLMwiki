from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.finalize_run_runtime import finalize_run
from ops.scripts.planning_gate_validate import validate_run_dir
from ops.scripts.promotion_decision_registry_runtime import (
    attach_decision_contract,
    decision_event_from_record,
)

from tests.minimal_vault_runtime import seed_minimal_vault, seed_planning_artifacts
from tests.test_promotion_gate_exit_codes import (
    changed_files_manifest,
    eval_report,
    lint_report,
    mechanism_report,
    write_json,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _copy_mechanism_run_schemas(vault: Path) -> None:
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    for schema_name in ("eval-report.schema.json", "lint-report.schema.json"):
        (vault / "ops" / "schemas" / schema_name).write_text(
            (REPO_ROOT / "ops" / "schemas" / schema_name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )


def _write_mechanism_run_subject_files(vault: Path) -> None:
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "scripts" / "example.py").write_text(
        "def subject(flag):\n    if flag:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    (vault / "tests" / "test_example.py").write_text(
        "def test_subject_true():\n    assert True\n",
        encoding="utf-8",
    )


def _write_mechanism_seed(run_dir: Path, run_id: str) -> None:
    (run_dir / "seed.yaml").write_text(
        f"""$schema: "ops/schemas/seed.schema.json"
run_id: {run_id}
mode: planning
request:
  summary: "Mechanism run"
  requester: human
  source_pages:
    - "system/system-log.md"
state:
  current: SEED_FROZEN
  allowed_next:
    - PLAN_DRAFT
goals:
  primary:
    - "Finalize a mechanism run"
  non_goals:
    - "None"
constraints:
  hard:
    - "No raw edits"
  soft:
    - "Keep it narrow"
success_criteria:
  - id: SC-001
    text: "Artifacts stay inside the run directory"
    trace:
      - "ops/scripts/example.py"
assumptions:
  open:
    - "None"
  frozen:
    - "Mechanism scope is fixed"
evidence:
  wiki_pages:
    - "system/system-log.md"
  raw_sources:
    - "raw/fake.pdf"
signoff:
  status: pending
  by: ""
  ts: ""
notes: ""
""",
        encoding="utf-8",
    )


def _write_mechanism_planning_validation(run_dir: Path, run_id: str) -> None:
    write_json(
        run_dir / "planning-validation.json",
        {
            "$schema": "ops/schemas/planning-validation.schema.json",
            "run_id": run_id,
            "status": "WARN",
            "summary": "Mechanism run is prepared but not finalized.",
            "checks": [
                {
                    "id": "run_seeded",
                    "status": "PASS",
                    "detail": "starter artifacts exist",
                    "required_artifacts": ["seed.yaml", "run-ledger.json", "promotion-report.json"],
                }
            ],
            "open_questions": [],
            "signoff": {
                "required": True,
                "status": "approved",
                "by": "human",
                "ts": "2026-04-14T00:00:00Z",
            },
            "next_action": "Finalize after promotion gate result is recorded.",
        },
    )


def _mechanism_promotion_report_payload(run_id: str) -> dict:
    return attach_decision_contract(
        {
            "$schema": "ops/schemas/promotion-report.schema.json",
            "run_id": run_id,
            "mode": "report_only",
            "artifact_class": "system_mechanism",
            "decision": "PROMOTE",
            "summary": "Finalize mechanism run validation coverage.",
            "primary_targets": ["ops/scripts/example.py"],
            "supporting_targets": ["tests/test_example.py"],
            "checks": [
                {
                    "id": "mechanism_scope_frozen",
                    "status": "PASS",
                    "detail": "single primary target is fixed",
                }
            ],
            "signoff": {
                "required": True,
                "status": "approved",
                "by": "human",
                "ts": "2026-04-14T00:00:00Z",
            },
            "log": {
                "required": True,
                "page": "system/system-log.md",
                "summary": "Finalize mechanism run validation coverage.",
                "status": "pending",
                "entry_ref": "",
            },
            "history": {
                "status": "active",
                "reason": "",
                "by": "",
                "ts": "",
            },
            "next_action": "Append the matching entry to system/system-log.md if not yet recorded, then persist the report.",
            "inputs": {
                "baseline_eval_report": f"runs/{run_id}/baseline-eval.json",
                "candidate_eval_report": f"runs/{run_id}/candidate-eval.json",
                "baseline_lint_report": f"runs/{run_id}/baseline-lint.json",
                "candidate_lint_report": f"runs/{run_id}/candidate-lint.json",
                "baseline_mechanism_report": f"runs/{run_id}/baseline-mechanism-assessment.json",
                "candidate_mechanism_report": f"runs/{run_id}/candidate-mechanism-assessment.json",
                "changed_files_manifest": f"runs/{run_id}/changed-files-manifest.json",
                "run_ledger": f"runs/{run_id}/run-ledger.json",
            },
        },
        [],
        subject_id=run_id,
        subject_kind="system_mechanism",
        policy_version=1,
        source_pass="system_mechanism",
        signoff={
            "required": True,
            "status": "approved",
            "by": "human",
            "ts": "2026-04-14T00:00:00Z",
        },
    )


def _base_mechanism_ledger_events(run_id: str) -> list[dict]:
    return [
        {
            "ts": "2026-04-14T00:00:00Z",
            "type": "created",
            "summary": "Initialized mechanism run artifacts.",
            "artifacts": [
                f"runs/{run_id}/seed.yaml",
                f"runs/{run_id}/planning-validation.json",
                f"runs/{run_id}/run-ledger.json",
                f"runs/{run_id}/promotion-report.json",
            ],
            "decision": "",
        },
        {
            "ts": "2026-04-14T00:01:00Z",
            "type": "seed_frozen",
            "summary": "Frozen mechanism scope for validation fixture.",
            "artifacts": [f"runs/{run_id}/seed.yaml", f"runs/{run_id}/plan.md"],
            "decision": "ready_for_baseline_capture",
        },
        {
            "ts": "2026-04-14T00:02:00Z",
            "type": "baseline_captured",
            "summary": "Captured baseline artifacts for validation fixture.",
            "artifacts": [
                "ops/scripts/example.py",
                "tests/test_example.py",
                f"runs/{run_id}/baseline-lint.json",
                f"runs/{run_id}/baseline-eval.json",
                f"runs/{run_id}/baseline-mechanism-assessment.json",
            ],
            "decision": "baseline_ready",
        },
        {
            "ts": "2026-04-14T00:03:00Z",
            "type": "mutation_applied",
            "summary": "Applied fixture mutation.",
            "artifacts": ["ops/scripts/example.py", "tests/test_example.py"],
            "decision": "candidate_ready_for_capture",
        },
        {
            "ts": "2026-04-14T00:04:00Z",
            "type": "candidate_captured",
            "summary": "Captured candidate artifacts for validation fixture.",
            "artifacts": [
                "ops/scripts/example.py",
                "tests/test_example.py",
                f"runs/{run_id}/candidate-lint.json",
                f"runs/{run_id}/candidate-eval.json",
                f"runs/{run_id}/candidate-mechanism-assessment.json",
            ],
            "decision": "ready_for_repo_health_gate",
        },
        {
            "ts": "2026-04-14T00:05:00Z",
            "type": "repo_health_checked",
            "summary": "Repo health passed for validation fixture.",
            "artifacts": [
                f"runs/{run_id}/candidate-lint.json",
                f"runs/{run_id}/candidate-eval.json",
                f"runs/{run_id}/changed-files-manifest.json",
            ],
            "decision": "repo_health_pass",
        },
    ]


def _append_promotion_evaluated_event(events: list[dict], run_id: str, promotion_report: dict) -> None:
    promotion_decision_event = decision_event_from_record(
        promotion_report["decision_record"],
        ledger_event_type="promotion_evaluated",
        effective_at="2026-04-14T00:06:00Z",
    )
    events.append(
        {
            "ts": "2026-04-14T00:06:00Z",
            "type": "promotion_evaluated",
            "summary": "Promotion gate evaluated the validation fixture.",
            "artifacts": [
                "ops/scripts/example.py",
                "tests/test_example.py",
                f"runs/{run_id}/baseline-lint.json",
                f"runs/{run_id}/candidate-lint.json",
                f"runs/{run_id}/baseline-eval.json",
                f"runs/{run_id}/candidate-eval.json",
                f"runs/{run_id}/baseline-mechanism-assessment.json",
                f"runs/{run_id}/candidate-mechanism-assessment.json",
                f"runs/{run_id}/changed-files-manifest.json",
                f"runs/{run_id}/promotion-report.json",
            ],
            "decision": "PROMOTE",
            "decision_event": promotion_decision_event,
        }
    )


def _append_finalized_event(events: list[dict], run_id: str, promotion_report: dict) -> None:
    events.append(
        {
            "ts": "2026-04-14T00:07:00Z",
            "type": "finalized",
            "summary": "Finalized validation fixture.",
            "artifacts": [
                f"runs/{run_id}/promotion-report.json",
                f"runs/{run_id}/run-ledger.json",
                "system/system-log.md",
            ],
            "decision": "complete",
            "decision_event": decision_event_from_record(
                promotion_report["decision_record"],
                ledger_event_type="finalized",
                effective_at="2026-04-14T00:07:00Z",
            ),
        }
    )


def _write_mechanism_run_ledger(
    run_dir: Path,
    run_id: str,
    *,
    ledger_status: str,
    promotion_report: dict,
) -> None:
    events = _base_mechanism_ledger_events(run_id)
    if ledger_status in {"ready", "complete"}:
        _append_promotion_evaluated_event(events, run_id, promotion_report)
    if ledger_status == "complete":
        _append_finalized_event(events, run_id, promotion_report)
    write_json(
        run_dir / "run-ledger.json",
        {
            "$schema": "ops/schemas/run-ledger.schema.json",
            "run_id": run_id,
            "status": ledger_status,
            "events": events,
        },
    )


def _write_mechanism_run_evidence(vault: Path, run_dir: Path, run_id: str, promotion_report: dict) -> None:
    write_json(run_dir / "baseline-eval.json", eval_report(vault, 10))
    write_json(run_dir / "candidate-eval.json", eval_report(vault, 10))
    write_json(run_dir / "baseline-lint.json", lint_report(vault))
    write_json(run_dir / "candidate-lint.json", lint_report(vault))
    write_json(run_dir / "baseline-mechanism-assessment.json", mechanism_report(vault))
    write_json(run_dir / "candidate-mechanism-assessment.json", mechanism_report(vault))
    manifest = changed_files_manifest()
    manifest["run_id"] = run_id
    write_json(run_dir / "changed-files-manifest.json", manifest)
    write_json(run_dir / "promotion-report.json", promotion_report)


def seed_mechanism_run_artifacts(vault: Path, run_id: str, *, ledger_status: str = "ready") -> Path:
    run_dir = vault / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _copy_mechanism_run_schemas(vault)
    _write_mechanism_run_subject_files(vault)
    _write_mechanism_seed(run_dir, run_id)
    _write_mechanism_planning_validation(run_dir, run_id)
    promotion_report = _mechanism_promotion_report_payload(run_id)
    _write_mechanism_run_ledger(
        run_dir,
        run_id,
        ledger_status=ledger_status,
        promotion_report=promotion_report,
    )
    _write_mechanism_run_evidence(vault, run_dir, run_id, promotion_report)
    return run_dir


class PlanningGateValidateTests(unittest.TestCase):
    def test_optional_promotion_report_is_validated_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_planning_artifacts(vault, "run-opt")
            artifact_dir = vault / "artifacts"
            (artifact_dir / "promotion-report.json").write_text("{", encoding="utf-8")

            report = validate_run_dir(vault, artifact_dir)

            self.assertEqual(report["status"], "fail")
            promotion_result = next(
                item for item in report["artifacts"] if item["artifact"] == "promotion-report.json"
            )
            self.assertFalse(promotion_result["pass"])
            self.assertTrue(any("failed to load artifact" in error for error in promotion_result["errors"]))

    def test_promotion_report_run_id_must_align_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_planning_artifacts(vault, "run-opt")
            artifact_dir = vault / "artifacts"
            (artifact_dir / "promotion-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/promotion-report.schema.json",
                        "run_id": "run-other",
                        "mode": "report_only",
                        "artifact_class": "wiki_source",
                        "decision": "HOLD",
                        "summary": "placeholder",
                        "primary_targets": ["wiki/source--fake.md"],
                        "supporting_targets": [],
                        "checks": [{"id": "scope", "status": "WARN", "detail": "placeholder"}],
                        "signoff": {
                            "required": False,
                            "status": "not_required",
                            "by": "",
                            "ts": "",
                        },
                        "log": {
                            "required": True,
                            "page": "system/system-log.md",
                            "summary": "placeholder",
                            "status": "pending",
                            "entry_ref": "",
                        },
                        "history": {
                            "status": "active",
                            "reason": "",
                            "by": "",
                            "ts": "",
                        },
                        "next_action": "placeholder",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = validate_run_dir(vault, artifact_dir)

            self.assertEqual(report["status"], "fail")
            run_id_check = next(item for item in report["cross_checks"] if item["check"] == "run_id_alignment")
            self.assertFalse(run_id_check["pass"])

    def test_system_mechanism_promotion_report_requires_run_ledger_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_planning_artifacts(vault, "run-opt")
            artifact_dir = vault / "artifacts"
            (artifact_dir / "promotion-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/promotion-report.schema.json",
                        "run_id": "run-opt",
                        "mode": "report_only",
                        "artifact_class": "system_mechanism",
                        "decision": "HOLD",
                        "summary": "placeholder",
                        "primary_targets": ["ops/scripts/planning_gate_validate.py"],
                        "supporting_targets": [],
                        "checks": [{"id": "scope", "status": "WARN", "detail": "placeholder"}],
                        "signoff": {
                            "required": True,
                            "status": "pending",
                            "by": "",
                            "ts": "",
                        },
                        "log": {
                            "required": True,
                            "page": "system/system-log.md",
                            "summary": "placeholder",
                            "status": "pending",
                            "entry_ref": "",
                        },
                        "history": {
                            "status": "active",
                            "reason": "",
                            "by": "",
                            "ts": "",
                        },
                        "next_action": "placeholder",
                        "inputs": {
                            "run_ledger": "runs/run-opt/run-ledger.json",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = validate_run_dir(vault, artifact_dir)

            self.assertEqual(report["status"], "fail")
            ledger_check = next(
                item
                for item in report["cross_checks"]
                if item["check"] == "mechanism_promotion_run_ledger_alignment"
            )
            self.assertFalse(ledger_check["pass"])
            self.assertEqual(ledger_check["detail"]["expected"], "artifacts/run-ledger.json")
            self.assertEqual(ledger_check["detail"]["actual"], "runs/run-opt/run-ledger.json")

    def test_system_mechanism_promotion_report_requires_changed_files_manifest_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_planning_artifacts(vault, "run-opt")
            artifact_dir = vault / "artifacts"
            (artifact_dir / "promotion-report.json").write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/promotion-report.schema.json",
                        "run_id": "run-opt",
                        "mode": "report_only",
                        "artifact_class": "system_mechanism",
                        "decision": "HOLD",
                        "summary": "placeholder",
                        "primary_targets": ["ops/scripts/planning_gate_validate.py"],
                        "supporting_targets": [],
                        "checks": [{"id": "scope", "status": "WARN", "detail": "placeholder"}],
                        "signoff": {
                            "required": True,
                            "status": "pending",
                            "by": "",
                            "ts": "",
                        },
                        "log": {
                            "required": True,
                            "page": "system/system-log.md",
                            "summary": "placeholder",
                            "status": "pending",
                            "entry_ref": "",
                        },
                        "history": {
                            "status": "active",
                            "reason": "",
                            "by": "",
                            "ts": "",
                        },
                        "next_action": "placeholder",
                        "inputs": {
                            "run_ledger": "artifacts/run-ledger.json",
                            "changed_files_manifest": "runs/run-opt/changed-files-manifest.json",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            report = validate_run_dir(vault, artifact_dir)

            self.assertEqual(report["status"], "fail")
            manifest_check = next(
                item
                for item in report["cross_checks"]
                if item["check"] == "mechanism_promotion_changed_files_manifest_alignment"
            )
            self.assertFalse(manifest_check["pass"])
            self.assertEqual(manifest_check["detail"]["expected"], "artifacts/changed-files-manifest.json")
            self.assertEqual(
                manifest_check["detail"]["actual"],
                "runs/run-opt/changed-files-manifest.json",
            )

    def test_mechanism_evaluated_phase_fails_when_required_run_artifact_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-mechanism-missing")
            (run_dir / "candidate-mechanism-assessment.json").unlink()

            report = validate_run_dir(vault, run_dir)

            self.assertEqual(report["phase"], "mechanism_evaluated")
            self.assertEqual(report["status"], "fail")
            phase_check = next(
                item for item in report["phase_checks"] if item["check"] == "mechanism_run_inputs_complete"
            )
            self.assertFalse(phase_check["pass"])
            self.assertIn("candidate-mechanism-assessment.json", phase_check["detail"])

    def test_mechanism_evaluated_phase_fails_when_test_surface_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-mechanism-no-tests")
            write_json(run_dir / "baseline-mechanism-assessment.json", mechanism_report(vault, test_file_count=0))
            write_json(run_dir / "candidate-mechanism-assessment.json", mechanism_report(vault, test_file_count=0))

            report = validate_run_dir(vault, run_dir)

            self.assertEqual(report["phase"], "mechanism_evaluated")
            self.assertEqual(report["status"], "fail")
            phase_check = next(
                item for item in report["phase_checks"] if item["check"] == "mechanism_run_test_surface_present"
            )
            self.assertFalse(phase_check["pass"])

    def test_mechanism_finalized_phase_passes_after_finalize_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-mechanism-finalized")

            finalize_run(vault, "run-mechanism-finalized")

            report = validate_run_dir(vault, run_dir)

            self.assertEqual(report["phase"], "mechanism_finalized")
            self.assertEqual(report["status"], "pass")
            self.assertTrue(all(item["pass"] for item in report["phase_checks"]))

    def test_mechanism_evaluated_phase_fails_when_required_event_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-mechanism-missing-event")
            ledger_path = run_dir / "run-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["events"] = [
                event for event in ledger["events"] if event["type"] != "promotion_evaluated"
            ]
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

            report = validate_run_dir(vault, run_dir)

            self.assertEqual(report["phase"], "starter")
            self.assertEqual(report["status"], "fail")
            ledger_result = next(
                item for item in report["artifacts"] if item["artifact"] == "run-ledger.json"
            )
            self.assertFalse(ledger_result["pass"])
            self.assertTrue(ledger_result["errors"])

    def test_mechanism_evaluated_phase_fails_when_event_order_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            run_dir = seed_mechanism_run_artifacts(vault, "run-mechanism-bad-order")
            ledger_path = run_dir / "run-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            events = ledger["events"]
            events[1], events[2] = events[2], events[1]
            ledger["events"] = events
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

            report = validate_run_dir(vault, run_dir)

            self.assertEqual(report["phase"], "mechanism_evaluated")
            self.assertEqual(report["status"], "fail")
            order_check = next(
                item for item in report["phase_checks"] if item["check"] == "mechanism_run_event_order"
            )
            self.assertFalse(order_check["pass"])


if __name__ == "__main__":
    unittest.main()
