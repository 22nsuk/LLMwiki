#!/usr/bin/env python3
"""Build a release lane summary from closeout reports.

This module provides the canonical unified vocabulary entry point for
release authority state.  Consumers that need a single, consistent view of
lane statuses (cohort, clean, conditional, machine, operator) and accepted
risk counts should read the artifact produced by this script rather than
parsing individual closeout / cohort / dashboard reports directly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.release.release_authority_vocabulary import (
        REASON_MACHINE_RELEASE_NOT_ALLOWED,
    )
    from ops.scripts.release.release_status_v2 import (
        release_status_v2_view_with_readiness_fallback,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        RELEASE_LANE_SUMMARY_SCHEMA_PATH,
    )
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object_with_diagnostics,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.release.release_authority_vocabulary import (
        REASON_MACHINE_RELEASE_NOT_ALLOWED,
    )
    from ops.scripts.release.release_status_v2 import (
        release_status_v2_view_with_readiness_fallback,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import RELEASE_LANE_SUMMARY_SCHEMA_PATH
    from ops.scripts.source_tree_fingerprint_runtime import (
        release_source_tree_fingerprint,
    )


DEFAULT_OUT = "ops/reports/release-lane-summary.json"
PRODUCER = "ops.scripts.release_lane_summary"
CLOSEOUT_PATH = "ops/reports/release-closeout-summary.json"
COHORT_PATH = "ops/reports/release-evidence-cohort.json"
DASHBOARD_PATH = "ops/reports/release-evidence-dashboard.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"


def _load(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    return payload, str(diagnostics.get("status", "unknown")).strip() or "unknown"


def _cohort_status(cohort: dict[str, Any]) -> str:
    return str(cohort.get("status", "unknown")).strip() or "unknown"


def _clean_lane_status(cohort: dict[str, Any]) -> str:
    contract = cohort.get("clean_lane_contract", {})
    if isinstance(contract, dict):
        return str(contract.get("status", "fail")).strip() or "fail"
    return "fail"


def _closeout_status_view(closeout: dict[str, Any]) -> dict[str, Any]:
    return release_status_v2_view_with_readiness_fallback(closeout)


def _conditional_lane_status(closeout: dict[str, Any]) -> str:
    state = str(_closeout_status_view(closeout)["release_authority_status"])
    if state in {"conditional_pass", "clean_pass"}:
        return "pass"
    return "fail"


def _machine_release_status(closeout: dict[str, Any]) -> str:
    view = _closeout_status_view(closeout)
    authority_status = str(view["release_authority_status"])
    blocker_reason_ids = {str(reason) for reason in view["blocker_reason_ids"]}
    if authority_status == "clean_pass" and REASON_MACHINE_RELEASE_NOT_ALLOWED not in blocker_reason_ids:
        return "allowed"
    return "blocked"


def _operator_release_status(closeout: dict[str, Any]) -> str:
    authority_status = str(_closeout_status_view(closeout)["release_authority_status"])
    return "allowed" if authority_status in {"clean_pass", "conditional_pass"} else "blocked"


def _release_authority_status(closeout: dict[str, Any]) -> str:
    return str(_closeout_status_view(closeout)["release_authority_status"])


def _sealed_release_status(closeout: dict[str, Any]) -> str:
    return str(_closeout_status_view(closeout)["sealed_release_status"])


def _active_blockers(closeout: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = closeout.get("blockers", [])
    if not isinstance(blockers, list):
        return []
    return [item for item in blockers if isinstance(item, dict)]


def _auto_improve_lane_status(closeout: dict[str, Any]) -> str:
    if not closeout:
        return "unknown"
    for blocker in _active_blockers(closeout):
        if str(blocker.get("source", "")).strip() == "auto_improve_readiness":
            return "blocked"
    return "pass"


def _active_learning_claim_blocker_count(closeout: dict[str, Any]) -> int:
    return len(
        {
            f"{str(blocker.get('source', '')).strip()}:{str(blocker.get('code', '')).strip()}"
            for blocker in _active_blockers(closeout)
            if str(blocker.get("learning_lane_effect", "")).strip() == "blocks_learning_claim"
        }
    )


def _accepted_risk_family_count(closeout: dict[str, Any]) -> int:
    summary = closeout.get("summary", {})
    if isinstance(summary, dict):
        return int(summary.get("accepted_risk_family_count", 0) or 0)
    return 0


def _accepted_risk_instance_count(closeout: dict[str, Any]) -> int:
    summary = closeout.get("summary", {})
    if isinstance(summary, dict):
        return int(summary.get("accepted_risk_instance_count", 0) or 0)
    return 0


def _dashboard_summary_count(dashboard: dict[str, Any], key: str) -> int:
    summary = dashboard.get("summary", {})
    if isinstance(summary, dict):
        return int(summary.get(key, 0) or 0)
    return 0


def _gate_attention_count(dashboard: dict[str, Any]) -> int:
    return _dashboard_summary_count(dashboard, "gate_attention_count")


def _clean_lane_blocking_family_count(cohort: dict[str, Any]) -> int:
    contract = cohort.get("clean_lane_contract", {})
    if isinstance(contract, dict):
        return int(contract.get("clean_lane_blocking_family_count", 0) or 0)
    return 0


def _accepted_risk_scope_count(closeout: dict[str, Any], key: str) -> int:
    counts = closeout.get("accepted_risk_count_by_scope", {})
    if isinstance(counts, dict):
        return int(counts.get(key, 0) or 0)
    return 0


def _learning_claim_context(
    scoreboard: dict[str, Any],
    load_status: str,
    *,
    active_learning_claim_blocker_count: int,
) -> dict[str, Any]:
    if load_status != "ok":
        return {
            "learning_lane_status": "blocked" if active_learning_claim_blocker_count else "unknown",
            "learning_claim_allowed": False,
            "learning_claim_guard_status": "unknown",
            "claims_learning_improved": False,
        }
    summary = scoreboard.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    guard = scoreboard.get("learning_claim_guard")
    if not isinstance(guard, dict):
        guard = {}
    claims_learning_improved = bool(summary.get("claims_learning_improved"))
    learning_claim_allowed = bool(summary.get("learning_claim_allowed"))
    guard_status = str(guard.get("status", scoreboard.get("status", "unknown"))).strip() or "unknown"
    learning_lane_status = (
        "blocked"
        if active_learning_claim_blocker_count or (claims_learning_improved and not learning_claim_allowed)
        else "pass"
    )
    if guard_status == "unknown":
        learning_lane_status = "blocked" if active_learning_claim_blocker_count else "unknown"
    return {
        "learning_lane_status": learning_lane_status,
        "learning_claim_allowed": learning_claim_allowed,
        "learning_claim_guard_status": guard_status,
        "claims_learning_improved": claims_learning_improved,
    }


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    current_fingerprint = release_source_tree_fingerprint(vault)

    closeout, _ = _load(vault, CLOSEOUT_PATH)
    cohort, _ = _load(vault, COHORT_PATH)
    dashboard, _ = _load(vault, DASHBOARD_PATH)
    learning_scoreboard, learning_scoreboard_load_status = _load(vault, LEARNING_DELTA_SCOREBOARD_PATH)
    active_learning_claim_blocker_count = _active_learning_claim_blocker_count(closeout)
    learning_context = _learning_claim_context(
        learning_scoreboard,
        learning_scoreboard_load_status,
        active_learning_claim_blocker_count=active_learning_claim_blocker_count,
    )

    lane_summary = {
        "cohort_status": _cohort_status(cohort),
        "clean_lane_status": _clean_lane_status(cohort),
        "conditional_lane_status": _conditional_lane_status(closeout),
        "auto_improve_lane_status": _auto_improve_lane_status(closeout),
        "learning_lane_status": learning_context["learning_lane_status"],
        "machine_release_status": _machine_release_status(closeout),
        "operator_release_status": _operator_release_status(closeout),
        "release_authority_status": _release_authority_status(closeout),
        "sealed_release_status": _sealed_release_status(closeout),
        "learning_claim_guard_status": learning_context["learning_claim_guard_status"],
        "learning_claim_allowed": learning_context["learning_claim_allowed"],
        "claims_learning_improved": learning_context["claims_learning_improved"],
        "accepted_risk_family_count": _accepted_risk_family_count(closeout),
        "accepted_risk_instance_count": _accepted_risk_instance_count(closeout),
        "accepted_risk_count": _dashboard_summary_count(dashboard, "accepted_risk_count"),
        "gate_attention_count": _gate_attention_count(dashboard),
        "clean_lane_blocking_family_count": _clean_lane_blocking_family_count(cohort),
        "learning_claim_blocking_family_count": (
            _accepted_risk_scope_count(closeout, "learning_claim_blocking_family_count")
            + active_learning_claim_blocker_count
        ),
        "advisory_lifecycle_family_count": _accepted_risk_scope_count(
            closeout,
            "advisory_lifecycle_family_count",
        ),
    }

    # Overall status: fail if any lane fails, attention if cohort attention, else pass
    status = "pass"
    if lane_summary["clean_lane_status"] == "fail" or lane_summary["machine_release_status"] == "blocked":
        status = "attention"
    if lane_summary["learning_lane_status"] == "blocked":
        status = "attention"
    if lane_summary["cohort_status"] == "fail":
        status = "fail"

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_lane_summary",
            producer=PRODUCER,
            source_command="python -m ops.scripts.release_lane_summary --vault . --out ops/reports/release-lane-summary.json",
            resolved_policy_path=resolved_policy_path,
            schema_path=RELEASE_LANE_SUMMARY_SCHEMA_PATH,
            source_paths=["ops/scripts/release/release_lane_summary.py"],
            file_inputs={
                "release_closeout_summary": CLOSEOUT_PATH,
                "release_evidence_cohort": COHORT_PATH,
                "release_evidence_dashboard": DASHBOARD_PATH,
                "learning_delta_scoreboard": LEARNING_DELTA_SCOREBOARD_PATH,
            },
            text_inputs={"current_source_tree_fingerprint": current_fingerprint},
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "lane_summary": lane_summary,
        "provenance": {
            "cohort_source": COHORT_PATH,
            "closeout_source": CLOSEOUT_PATH,
            "dashboard_source": DASHBOARD_PATH,
            "learning_delta_scoreboard_source": LEARNING_DELTA_SCOREBOARD_PATH,
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_LANE_SUMMARY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release lane summary schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a release lane summary from closeout reports")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
