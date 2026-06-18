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

FINGERPRINT_MAP_FIELD_NAMES = frozenset({"input_fingerprints"})

VOLATILE_FIELD_VALUE_SENTINELS = {
    "current_source_revision": "<current_source_revision>",
    "current_source_tree_fingerprint": "<current_source_tree_fingerprint>",
    "observed_source_revision": "<observed_source_revision>",
    "observed_source_tree_fingerprint": "<observed_source_tree_fingerprint>",
    "producer_input_fingerprint": "<producer_input_fingerprint>",
    "source_revision": "<source_revision>",
    "source_tree_fingerprint": "<source_tree_fingerprint>",
    "source_tree_fingerprint_current": "<source_tree_fingerprint_current>",
}

STRUCTURAL_GOLDEN_DIGESTS = {
    "mutation_proposal": "99536d57a2fc8f1a5ceb2fe658cec2f7e75bd4cb3d63b83dc6121c68ea426366",
    "release_evidence_dashboard": "3cdc62c1128d5fad032aa4cc2fda5931805d12964f76b2acdbf0dcd8e6d90d32",
    "release_closeout_summary": "6b2a8f1a26d6ee8eb149653cc0e8d6e2108b2627f9997aa8367adb21e2746152",
    "auto_improve_session_bundle": "4f8f612077c773f77e425f9ea3ba5759514b1f77f58d96203e4dbc24175c3a4f",
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
        stripped: dict[str, object] = {}
        for key, item in value.items():
            if key in VOLATILE_FIELD_NAMES:
                continue
            if key in FINGERPRINT_MAP_FIELD_NAMES and isinstance(item, dict):
                stripped[key] = dict.fromkeys(sorted(item), "<fingerprint>")
                continue
            if key in VOLATILE_FIELD_VALUE_SENTINELS:
                stripped[key] = VOLATILE_FIELD_VALUE_SENTINELS[key]
                continue
            stripped[key] = strip_volatile_fields(item)
        return stripped
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
