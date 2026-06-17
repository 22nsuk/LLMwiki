from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

VOLATILE_FIELD_NAMES = frozenset(
    {
        "artifact_path",
        "created_at",
        "generated_at",
        "input_path",
        "last_modified",
        "mtime",
        "mtime_iso",
        "output_path",
        "path",
        "paths",
        "policy_path",
        "refreshed_at",
        "report_path",
        "source_path",
        "source_paths",
        "timestamp",
        "updated_at",
        "vault_path",
        "written_at",
    }
)

STRUCTURAL_GOLDEN_DIGESTS = {
    "mutation_proposal": "e1d159a76895dc1c075b2629c64478131c8c8a534dfe4702d7d2571fd214fe63",
    "release_evidence_dashboard": "a20e22a6e65cd029e9ecdb7df40851a647b9c031f524d02b9a6cdba534c4e653",
    "release_closeout_summary": "aec02eedf846eaf2f14fc28022fc11b6ce3f97db69116a4f6cb3d081e09a9a99",
    "auto_improve_session_bundle": "ea3e17dffc82840a0d1f8cff8ef67459e52829817b8d466c6a9fc2616cf4a54b",
}

STRUCTURAL_CONTRACTS: dict[str, dict[str, object]] = {
    "mutation_proposal": {
        "required_top_level_keys": (
            "diagnostics",
            "proposals",
            "schema_version",
            "status",
            "summary",
        ),
        "status": "pass",
    },
    "release_evidence_dashboard": {
        "required_top_level_keys": (
            "gates",
            "inputs",
            "schema_version",
            "status",
            "summary",
        ),
        "status": "pass",
    },
    "release_closeout_summary": {
        "required_top_level_keys": (
            "components",
            "schema_version",
            "status",
            "summary",
        ),
        "status": "pass",
    },
    "auto_improve_session_bundle": {
        "required_top_level_keys": (
            "promotion_decision_trends",
            "result",
            "routing_provenance_aggregate",
            "routing_reports",
            "run_artifact_fingerprint",
            "run_telemetry",
            "runtime_events",
            "session",
        ),
        "result_completion_class": "bounded_success_after_promotion",
    },
}


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def strip_volatile_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: strip_volatile_fields(item)
            for key, item in value.items()
            if key not in VOLATILE_FIELD_NAMES
        }
    if isinstance(value, list):
        return [strip_volatile_fields(item) for item in value]
    return value


def structural_digest(payload: object) -> str:
    return hashlib.sha256(canonical_bytes(strip_volatile_fields(payload))).hexdigest()


def assert_structural_contract(facade_name: str, payload: Mapping[str, Any]) -> None:
    contract = STRUCTURAL_CONTRACTS[facade_name]
    required_keys = contract["required_top_level_keys"]
    missing = [key for key in required_keys if key not in payload]
    assert not missing, f"{facade_name} missing structural keys: {missing}"

    if "status" in contract:
        assert payload.get("status") == contract["status"], (
            f"{facade_name} status drift: expected {contract['status']!r}, got {payload.get('status')!r}"
        )
    if "result_status" in contract:
        result = payload.get("result")
        assert isinstance(result, dict), f"{facade_name} result payload must be a mapping"
        assert result.get("status") == contract["result_status"], (
            f"{facade_name} result status drift: expected {contract['result_status']!r}, "
            f"got {result.get('status')!r}"
        )
    if "result_completion_class" in contract:
        result = payload.get("result")
        assert isinstance(result, dict), f"{facade_name} result payload must be a mapping"
        assert result.get("completion_class") == contract["result_completion_class"], (
            f"{facade_name} result completion_class drift: expected "
            f"{contract['result_completion_class']!r}, got {result.get('completion_class')!r}"
        )
