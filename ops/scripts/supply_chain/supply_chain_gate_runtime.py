from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.core.output_runtime import display_path
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    SUPPLY_CHAIN_GATE_REPORT_SCHEMA_PATH,
)
from ops.scripts.supply_chain.ci_install_proof_runtime import (
    CANONICAL_UV_LOCK_CHECK_COMMAND,
    UV_LOCK_CHECK_COMMAND,
    ci_install_evidence_content,
    collect_ci_install_contract,
)

GATE_REPORT_SCHEMA_PATH = SUPPLY_CHAIN_GATE_REPORT_SCHEMA_PATH
PROVENANCE_REPORT_REL_PATH = "ops/reports/supply-chain-provenance.json"
GATE_REPORT_REL_PATH = "ops/reports/supply-chain-gate-report.json"
PRODUCER = "ops.scripts.supply_chain_gate_runtime"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain_gate_runtime --vault ."


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _check_inputs_exist(provenance: dict[str, Any]) -> dict[str, Any]:
    inputs = provenance.get("inputs", [])
    missing = [
        str(item.get("path", ""))
        for item in inputs
        if isinstance(item, dict)
        and str(item.get("authority_role", "canonical")).strip() != "compatibility"
        and not bool(item.get("exists"))
    ]
    if missing:
        return {"rule": "all_required_inputs_exist", "pass": False, "details": f"Missing: {', '.join(missing)}"}
    return {"rule": "all_required_inputs_exist", "pass": True}


def _check_parser_errors(provenance: dict[str, Any]) -> dict[str, Any]:
    inputs = provenance.get("inputs", [])
    errors = [
        str(item.get("path", ""))
        for item in inputs
        if isinstance(item, dict)
        and isinstance(item.get("parser_status"), dict)
        and item["parser_status"].get("status") == "error"
    ]
    lock_evidence = provenance.get("lock_evidence", {})
    if (
        isinstance(lock_evidence, dict)
        and isinstance(lock_evidence.get("parser_status"), dict)
        and lock_evidence["parser_status"].get("status") == "error"
    ):
        path = str(lock_evidence.get("path", "uv.lock"))
        if path not in errors:
            errors.append(path)

    if errors:
        return {"rule": "no_parser_errors", "pass": False, "details": f"Parser errors in: {', '.join(errors)}"}
    return {"rule": "no_parser_errors", "pass": True}


def _check_ci_install_drift(vault: Path, provenance: dict[str, Any]) -> dict[str, Any]:
    proof = provenance.get("ci_install_proof", {})
    if not isinstance(proof, dict):
        return {"rule": "ci_install_note_drift", "pass": False, "details": "Missing ci_install_proof block"}

    workflow_rel = str(proof.get("workflow_path", ".github/workflows/ci.yml"))
    workflow_path = vault / workflow_rel
    if not bool(proof.get("workflow_exists")) or not workflow_path.exists():
        return {"rule": "ci_install_note_drift", "pass": False, "details": f"Missing workflow: {workflow_rel}"}

    _workflow_exists, content = ci_install_evidence_content(vault, workflow_rel)
    current_contract = collect_ci_install_contract(content)
    if not bool(proof.get("checks_uv_lock_freshness")):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI proof does not show uv.lock freshness check",
        }
    if not bool(proof.get("exports_frozen_uv_lock")):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI proof does not show frozen uv.lock export",
        }
    if not bool(proof.get("installs_locked_requirements")):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI proof does not show locked requirements install",
        }
    if str(proof.get("install_resolution_mode", "")) != "canonical_lock_export":
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI proof does not identify canonical lock export install mode",
        }
    if not bool(current_contract["checks_uv_lock_freshness"]):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI evidence sources do not contain canonical uv-lock-check command",
        }
    if not bool(current_contract["exports_frozen_uv_lock"]):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI evidence sources do not contain frozen uv.lock export command",
        }
    if not bool(current_contract["installs_locked_requirements"]):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "CI evidence sources do not contain locked requirements install command",
        }
    if (
        bool(current_contract["installs_requirements_dev"])
        and not bool(current_contract["editable_install"])
    ):
        return {
            "rule": "ci_install_note_drift",
            "pass": False,
            "details": "Workflow contains legacy range install without direct editable install",
        }
    return {"rule": "ci_install_note_drift", "pass": True}


def _check_uv_lock_freshness(provenance: dict[str, Any]) -> dict[str, Any]:
    lock_evidence = provenance.get("lock_evidence", {})
    proof = provenance.get("ci_install_proof", {})
    if not isinstance(lock_evidence, dict) or not isinstance(proof, dict):
        return {
            "rule": "uv_lock_freshness_enforced",
            "pass": False,
            "details": "Missing lock evidence or CI proof block",
        }
    if str(lock_evidence.get("lock_check_status", "")) != "enforced":
        return {
            "rule": "uv_lock_freshness_enforced",
            "pass": False,
            "details": "uv.lock freshness check is not recorded as enforced",
        }
    if str(lock_evidence.get("canonical_lock_policy_status", "")) != "enforced":
        return {
            "rule": "uv_lock_freshness_enforced",
            "pass": False,
            "details": "canonical uv.lock freshness policy is not recorded as enforced",
        }
    if str(lock_evidence.get("lock_check_command", "")) != UV_LOCK_CHECK_COMMAND:
        return {
            "rule": "uv_lock_freshness_enforced",
            "pass": False,
            "details": "uv.lock freshness evidence does not bind uv lock --check",
        }
    if str(lock_evidence.get("canonical_lock_check_command", "")) != CANONICAL_UV_LOCK_CHECK_COMMAND:
        return {
            "rule": "uv_lock_freshness_enforced",
            "pass": False,
            "details": "uv.lock freshness evidence does not bind canonical index check",
        }
    if not bool(proof.get("checks_uv_lock_freshness")):
        return {
            "rule": "uv_lock_freshness_enforced",
            "pass": False,
            "details": "CI proof does not bind canonical uv-lock-check",
        }
    return {"rule": "uv_lock_freshness_enforced", "pass": True}


def build_gate_report(
    vault: Path,
    context: RuntimeContext,
    provenance_report: dict[str, Any] | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, policy_path)
    provenance = provenance_report
    provenance_path = vault / PROVENANCE_REPORT_REL_PATH
    generated_at = context.isoformat_z()
    if provenance is None:
        if not provenance_path.exists():
            return {
                **build_canonical_report_envelope(
                    vault,
                    generated_at=generated_at,
                    artifact_kind="supply_chain_gate_report",
                    producer=PRODUCER,
                    source_command=SOURCE_COMMAND,
                    resolved_policy_path=resolved_policy_path,
                    schema_path=GATE_REPORT_SCHEMA_PATH,
                    source_paths=[
                        "ops/scripts/supply_chain/supply_chain_gate_runtime.py",
                        "ops/scripts/supply_chain/ci_install_proof_runtime.py",
                    ],
                    file_inputs={"provenance_report": PROVENANCE_REPORT_REL_PATH},
                ),
                "$schema": GATE_REPORT_SCHEMA_PATH,
                "vault": report_path(vault, vault),
                "generated_at": generated_at,
                "provenance_report_ref": PROVENANCE_REPORT_REL_PATH,
                "status": "fail",
                "checks": [{"rule": "provenance_report_exists", "pass": False, "details": "Run generator first"}],
            }

        provenance = _load_json(provenance_path)
    checks = [
        _check_inputs_exist(provenance),
        _check_parser_errors(provenance),
        _check_uv_lock_freshness(provenance),
        _check_ci_install_drift(vault, provenance),
    ]
    status = "pass" if all(check["pass"] for check in checks) else "fail"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="supply_chain_gate_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=GATE_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/supply_chain/supply_chain_gate_runtime.py",
                "ops/scripts/supply_chain/ci_install_proof_runtime.py",
            ],
            file_inputs={"provenance_report": PROVENANCE_REPORT_REL_PATH},
        ),
        "$schema": GATE_REPORT_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": generated_at,
        "provenance_report_ref": PROVENANCE_REPORT_REL_PATH,
        "status": status,
        "checks": checks,
    }


def write_gate_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=GATE_REPORT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=GATE_REPORT_REL_PATH,
            context="Supply-chain gate schema validation failed",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strict supply-chain provenance gate")
    parser.add_argument("--vault", default=".", help="Path to the vault root")
    parser.add_argument("--policy-path")
    args = parser.parse_args(argv)

    vault = Path(args.vault).resolve()
    policy, _ = load_policy(vault, args.policy_path)
    context = RuntimeContext.from_policy(policy)
    report = build_gate_report(vault, context, policy_path=args.policy_path)
    destination = write_gate_report(vault, report, GATE_REPORT_REL_PATH)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
