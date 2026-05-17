from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any


RESUME_METADATA_SCHEMA_PATH = "ops/schemas/goal-run-resume-metadata.schema.json"


def _canonical_json_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def resume_status(*, resume_from_checkpoint: bool, resume_command: str) -> str:
    if not resume_from_checkpoint:
        return "not_requested"
    if resume_command.strip():
        return "ready"
    return "missing_resume_command"


def mapping_field(report: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = report.get(field_name)
    return value if isinstance(value, Mapping) else {}


def resume_metadata_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    run = mapping_field(report, "run")
    goal = mapping_field(report, "goal")
    observability = mapping_field(report, "observability")
    generated_at = str(report.get("generated_at", "")).strip()
    input_fingerprints = dict(mapping_field(report, "input_fingerprints"))
    input_fingerprints["goal_run_status"] = _canonical_json_digest(report)
    return {
        "$schema": RESUME_METADATA_SCHEMA_PATH,
        "artifact_kind": "goal_run_resume_metadata",
        "generated_at": generated_at,
        "producer": str(report.get("producer", "")).strip() or "ops.scripts.goal_run_status",
        "source_command": str(report.get("source_command", "")).strip()
        or "python -m ops.scripts.goal_run_status --vault .",
        "source_revision": str(report.get("source_revision", "")).strip() or "unknown",
        "source_tree_fingerprint": str(report.get("source_tree_fingerprint", "")).strip()
        or "unknown",
        "input_fingerprints": input_fingerprints,
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "run_local_state",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": generated_at,
        },
        "run_id": run.get("run_id", ""),
        "contract_sha256": goal.get("contract_sha256", ""),
        "resume_from_checkpoint": observability.get("resume_from_checkpoint", False),
        "resume_command": observability.get("resume_command", ""),
    }
