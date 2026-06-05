#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.learning.learning_readiness_signoff import (
        ARTIFACT_KIND,
        SIGNOFF_REPORT_REL_PATH,
        SUPPORTED_BLOCKER_ID,
        LearningReadinessSignoffRequest,
        build_signoff_report,
        write_signoff_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext
else:
    from ops.scripts.output_runtime import display_path
    from ops.scripts.runtime_context import RuntimeContext

    from .learning_readiness_signoff import (
        ARTIFACT_KIND,
        SIGNOFF_REPORT_REL_PATH,
        SUPPORTED_BLOCKER_ID,
        LearningReadinessSignoffRequest,
        build_signoff_report,
        write_signoff_report,
    )

REFRESH_SOURCE_COMMAND = "python -m ops.scripts.learning_readiness_signoff_refresh --vault ."


def _resolve_input_path(vault: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return vault / path


def _require_text(payload: dict[str, Any], field_name: str) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ValueError(
            f"{field_name} must not be empty in the reused learning readiness signoff"
        )
    return value


def load_reused_signoff_payload(vault: Path, reuse_from: str) -> dict[str, Any]:
    source_path = _resolve_input_path(vault, reuse_from)
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"reused learning readiness signoff not found: {source_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"reused learning readiness signoff is not valid JSON: {source_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("reused learning readiness signoff must be a JSON object")
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if artifact_kind != ARTIFACT_KIND:
        raise ValueError(
            "reused learning readiness signoff must declare "
            f"artifact_kind={ARTIFACT_KIND}, got {artifact_kind or 'missing'}"
        )
    return payload


def build_refreshed_signoff_report(
    vault: Path,
    *,
    reuse_from: str = SIGNOFF_REPORT_REL_PATH,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    payload = load_reused_signoff_payload(vault, reuse_from)
    request = LearningReadinessSignoffRequest(
        accepted_by=_require_text(payload, "accepted_by"),
        accepted_at=_require_text(payload, "accepted_at"),
        expires_at=_require_text(payload, "expires_at"),
        risk_owner=_require_text(payload, "risk_owner"),
        revalidation_condition=_require_text(payload, "revalidation_condition"),
        rollback_trigger=_require_text(payload, "rollback_trigger"),
        linked_blocker_id=(
            str(payload.get("linked_blocker_id", SUPPORTED_BLOCKER_ID)).strip()
            or SUPPORTED_BLOCKER_ID
        ),
        notes=str(payload.get("notes", "")).strip(),
    )
    report = build_signoff_report(
        vault,
        request,
        policy_path=policy_path,
        context=context,
    )
    report["source_command"] = REFRESH_SOURCE_COMMAND
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the canonical learning readiness signoff report by reusing "
            "the acceptance metadata from an existing signoff artifact"
        )
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--reuse-from", default=SIGNOFF_REPORT_REL_PATH)
    parser.add_argument("--out", default=SIGNOFF_REPORT_REL_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_refreshed_signoff_report(
        vault,
        reuse_from=args.reuse_from,
        policy_path=args.policy_path,
    )
    destination = write_signoff_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
