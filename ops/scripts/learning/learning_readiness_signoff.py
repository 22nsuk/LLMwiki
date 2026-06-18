#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
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
    LEARNING_READINESS_SIGNOFF_SCHEMA_PATH,
)

from .learning_readiness_vocabulary import LEARNING_REVIEW_REQUIRED_BLOCKER_ID

SIGNOFF_REPORT_REL_PATH = "ops/reports/learning-readiness-signoff.json"
SUPPORTED_BLOCKER_ID = LEARNING_REVIEW_REQUIRED_BLOCKER_ID
ARTIFACT_KIND = "learning_readiness_signoff"
PRODUCER = "ops.scripts.learning_readiness_signoff"
SOURCE_COMMAND = "python -m ops.scripts.learning_readiness_signoff --vault ."


@dataclass(frozen=True)
class LearningReadinessSignoffRequest:
    accepted_by: str
    risk_owner: str
    revalidation_condition: str
    rollback_trigger: str
    accepted_at: str | None = None
    expires_at: str | None = None
    expiry_days: int | None = None
    linked_blocker_id: str = SUPPORTED_BLOCKER_ID
    notes: str = ""


def _normalize_timestamp(value: str, *, field_name: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError(f"{field_name} must not be empty")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_plus_days(timestamp_z: str, days: int) -> str:
    if days <= 0:
        raise ValueError("expiry_days must be greater than zero")
    parsed = dt.datetime.fromisoformat(timestamp_z.replace("Z", "+00:00")).astimezone(dt.UTC)
    return (parsed + dt.timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def build_signoff_report(
    vault: Path,
    request: LearningReadinessSignoffRequest,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    if request.linked_blocker_id != SUPPORTED_BLOCKER_ID:
        raise ValueError(f"unsupported learning readiness blocker id: {request.linked_blocker_id}")
    if request.expires_at and request.expiry_days is not None:
        raise ValueError("provide either expires_at or expiry_days, not both")
    if not request.expires_at and request.expiry_days is None:
        raise ValueError("expires_at or expiry_days is required")

    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    normalized_accepted_at = (
        _normalize_timestamp(request.accepted_at, field_name="accepted_at")
        if request.accepted_at
        else generated_at
    )
    normalized_expires_at = (
        _normalize_timestamp(request.expires_at, field_name="expires_at")
        if request.expires_at
        else _timestamp_plus_days(normalized_accepted_at, int(request.expiry_days or 0))
    )
    accepted_by = _required_text(request.accepted_by, field_name="accepted_by")
    risk_owner = _required_text(request.risk_owner, field_name="risk_owner")
    revalidation_condition = _required_text(
        request.revalidation_condition,
        field_name="revalidation_condition",
    )
    rollback_trigger = _required_text(request.rollback_trigger, field_name="rollback_trigger")

    report = {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind=ARTIFACT_KIND,
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=LEARNING_READINESS_SIGNOFF_SCHEMA_PATH,
            source_paths=["ops/scripts/learning/learning_readiness_signoff.py"],
            text_inputs={
                "accepted_by": accepted_by,
                "linked_blocker_id": request.linked_blocker_id,
                "risk_owner": risk_owner,
                "revalidation_condition": revalidation_condition,
                "rollback_trigger": rollback_trigger,
                "accepted_at": normalized_accepted_at,
                "expires_at": normalized_expires_at,
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "linked_blocker_id": request.linked_blocker_id,
        "accepted_by": accepted_by,
        "accepted_at": normalized_accepted_at,
        "expires_at": normalized_expires_at,
        "risk_owner": risk_owner,
        "revalidation_condition": revalidation_condition,
        "rollback_trigger": rollback_trigger,
    }
    if request.notes.strip():
        report["notes"] = request.notes.strip()
    return report


def write_signoff_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=LEARNING_READINESS_SIGNOFF_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=SIGNOFF_REPORT_REL_PATH,
            context="learning readiness signoff schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the canonical learning readiness signoff report")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=SIGNOFF_REPORT_REL_PATH)
    parser.add_argument("--linked-blocker-id", default=SUPPORTED_BLOCKER_ID)
    parser.add_argument("--accepted-by", required=True)
    parser.add_argument("--accepted-at")
    expiry = parser.add_mutually_exclusive_group(required=True)
    expiry.add_argument("--expires-at")
    expiry.add_argument("--expiry-days", type=int)
    parser.add_argument("--risk-owner", required=True)
    parser.add_argument("--revalidation-condition", required=True)
    parser.add_argument("--rollback-trigger", required=True)
    parser.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_signoff_report(
        vault,
        LearningReadinessSignoffRequest(
            accepted_by=args.accepted_by,
            accepted_at=args.accepted_at,
            expires_at=args.expires_at,
            expiry_days=args.expiry_days,
            risk_owner=args.risk_owner,
            revalidation_condition=args.revalidation_condition,
            rollback_trigger=args.rollback_trigger,
            linked_blocker_id=args.linked_blocker_id,
            notes=args.notes,
        ),
        policy_path=args.policy_path,
    )
    destination = write_signoff_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
