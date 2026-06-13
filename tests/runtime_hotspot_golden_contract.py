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
    "mutation_proposal": "b9ea5b2efb4434d72e6f0668fd911bcb8f7788f67405113c0f70044994e50e05",
    "release_evidence_dashboard": "a680cf53ae5264f3c7fca2ddefe386d30efaa567d93a85a5dde5fe03272968e9",
    "release_closeout_summary": "1cbc5be38b1a80449fd4390d3b6a8a24f2907bc6846f9d77e5788608a04a046c",
    "auto_improve_session_bundle": "7251f54bf1438f405b2ed3a9f8f41945edcbade1ffe5d59cf863772d079932ac",
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
