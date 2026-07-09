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
FINGERPRINT_VALUE_FIELD_NAMES = frozenset({"input_digest", "input_fingerprint", "sha256"})
FINGERPRINT_VALUE_FIELD_SUFFIXES = ("_fingerprint", "_sha256")
ARTIFACT_ENVELOPE_PROPERTY_NAME = "urn:openai:artifact-envelope"

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
    "release_closeout_summary": "0cf9f6fcd926a9c75a41e1457fb8c6c26f42dc6749042468108d62294df3ac97",
    "auto_improve_session_bundle": "0937b3fc5b4bfb176332efecb0eccccb04e2c85ff87792f61c1ede9a7cd78af0",
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


def _fingerprint_value_sentinel(key: str, item: object) -> str | None:
    if not isinstance(item, str):
        return None
    if key in VOLATILE_FIELD_VALUE_SENTINELS:
        return VOLATILE_FIELD_VALUE_SENTINELS[key]
    if key in FINGERPRINT_VALUE_FIELD_NAMES or key.endswith(FINGERPRINT_VALUE_FIELD_SUFFIXES):
        return f"<{key}>"
    return None


def _strip_artifact_envelope_property_value(value: str) -> str:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    return json.dumps(
        strip_volatile_fields(parsed),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _strip_metadata_properties(properties: list[object]) -> list[object]:
    stripped_properties: list[object] = []
    for property_payload in properties:
        if not isinstance(property_payload, dict):
            stripped_properties.append(strip_volatile_fields(property_payload))
            continue
        stripped_property: dict[str, object] = {}
        is_artifact_envelope = property_payload.get("name") == ARTIFACT_ENVELOPE_PROPERTY_NAME
        for key, item in property_payload.items():
            if key == "value" and is_artifact_envelope and isinstance(item, str):
                stripped_property[key] = _strip_artifact_envelope_property_value(item)
                continue
            stripped_property[key] = strip_volatile_fields(item)
        stripped_properties.append(stripped_property)
    return stripped_properties


def strip_volatile_fields(value: object) -> object:
    if isinstance(value, dict):
        stripped: dict[str, object] = {}
        for key, item in value.items():
            if key in VOLATILE_FIELD_NAMES:
                continue
            if key == "properties" and isinstance(item, list):
                stripped[key] = _strip_metadata_properties(item)
                continue
            if key in FINGERPRINT_MAP_FIELD_NAMES and isinstance(item, dict):
                stripped[key] = dict.fromkeys(sorted(item), "<fingerprint>")
                continue
            fingerprint_sentinel = _fingerprint_value_sentinel(key, item)
            if fingerprint_sentinel is not None:
                stripped[key] = fingerprint_sentinel
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
