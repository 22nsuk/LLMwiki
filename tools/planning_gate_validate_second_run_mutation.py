#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "ops" / "scripts" / "planning_gate_validate_runtime.py"
TEST_PATH = ROOT / "tests" / "test_planning_gate_validate.py"

RUNTIME_OLD = """    promotion_report = loaded_data.get("promotion-report.json")
    if isinstance(promotion_report, dict):
        promotion_class = promotion_report.get("artifact_class")
        if promotion_class == "system_mechanism":
            inputs = promotion_report.get("inputs")
            expected_run_ledger = f"{artifact_dir_report}/run-ledger.json"
            actual_run_ledger = ""
            if isinstance(inputs, dict):
                candidate = inputs.get("run_ledger")
                if isinstance(candidate, str):
                    actual_run_ledger = candidate
            allowed_run_ledger_values = set(
                starter_bundle_allowed_promotion_input_paths(
                    starter_bundle,
                    "run_ledger",
                    expected_path=expected_run_ledger,
                )
            )
            cross_checks.append(
                {
                    "check": "mechanism_promotion_run_ledger_alignment",
                    "pass": actual_run_ledger in allowed_run_ledger_values,
                    "detail": {
                        "expected": expected_run_ledger,
                        "actual": actual_run_ledger,
                        "allowed": sorted(allowed_run_ledger_values),
                    },
                }
            )
            expected_manifest = f"{artifact_dir_report}/changed-files-manifest.json"
            actual_manifest = ""
            if isinstance(inputs, dict):
                candidate = inputs.get("changed_files_manifest")
                if isinstance(candidate, str):
                    actual_manifest = candidate
            allowed_manifest_values = set(
                starter_bundle_allowed_promotion_input_paths(
                    starter_bundle,
                    "changed_files_manifest",
                    expected_path=expected_manifest,
                )
            )
            cross_checks.append(
                {
                    "check": "mechanism_promotion_changed_files_manifest_alignment",
                    "pass": actual_manifest in allowed_manifest_values,
                    "detail": {
                        "expected": expected_manifest,
                        "actual": actual_manifest,
                        "allowed": sorted(allowed_manifest_values),
                    },
                }
            )
"""

RUNTIME_NEW = """    promotion_report = loaded_data.get("promotion-report.json")
    if isinstance(promotion_report, dict) and promotion_report.get("artifact_class") == "system_mechanism":
        inputs = promotion_report.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {}
        alignment_specs = (
            ("run_ledger", "mechanism_promotion_run_ledger_alignment", "run-ledger.json"),
            (
                "changed_files_manifest",
                "mechanism_promotion_changed_files_manifest_alignment",
                "changed-files-manifest.json",
            ),
        )
        for input_key, check_name, artifact_name in alignment_specs:
            expected_path = f"{artifact_dir_report}/{artifact_name}"
            actual_path = inputs.get(input_key, "")
            if not isinstance(actual_path, str):
                actual_path = ""
            allowed_paths = set(
                starter_bundle_allowed_promotion_input_paths(
                    starter_bundle,
                    input_key,
                    expected_path=expected_path,
                )
            )
            cross_checks.append(
                {
                    "check": check_name,
                    "pass": actual_path in allowed_paths,
                    "detail": {
                        "expected": expected_path,
                        "actual": actual_path,
                        "allowed": sorted(allowed_paths),
                    },
                }
            )
"""

TEST_ANCHOR = """            self.assertFalse(ledger_check["pass"])
            self.assertEqual(ledger_check["detail"]["expected"], "artifacts/run-ledger.json")
            self.assertEqual(ledger_check["detail"]["actual"], "runs/run-opt/run-ledger.json")

"""

TEST_INSERT = """    def test_system_mechanism_promotion_report_requires_changed_files_manifest_alignment(self) -> None:
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

"""


def _replace_once(text: str, old: str, new: str, *, label: str) -> tuple[str, bool]:
    if new in text:
        return text, False
    if old not in text:
        raise SystemExit(f"expected {label} snippet not found")
    return text.replace(old, new, 1), True


def _insert_once(text: str, anchor: str, addition: str, *, label: str) -> tuple[str, bool]:
    if addition in text:
        return text, False
    if anchor not in text:
        raise SystemExit(f"expected {label} anchor not found")
    return text.replace(anchor, anchor + addition, 1), True


def main() -> None:
    runtime_text = RUNTIME_PATH.read_text(encoding="utf-8")
    test_text = TEST_PATH.read_text(encoding="utf-8")

    runtime_text, runtime_changed = _replace_once(
        runtime_text,
        RUNTIME_OLD,
        RUNTIME_NEW,
        label="planning_gate runtime alignment block",
    )
    test_text, test_changed = _insert_once(
        test_text,
        TEST_ANCHOR,
        TEST_INSERT,
        label="planning_gate regression test insertion point",
    )

    if not runtime_changed and not test_changed:
        print("planning_gate_validate second-run mutation already applied")
        return

    RUNTIME_PATH.write_text(runtime_text, encoding="utf-8")
    TEST_PATH.write_text(test_text, encoding="utf-8")
    print("applied planning_gate_validate second-run mutation")


if __name__ == "__main__":
    main()
