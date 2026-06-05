#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext


DEFAULT_CLOSEOUT_SUMMARY = "ops/reports/release-closeout-summary.json"
DEFAULT_OUT = "tmp/release-clean-lane-evidence-review.json"
PRODUCER = "ops.scripts.release_clean_lane_evidence_review"
SCHEMA_PATH = "ops/schemas/release-clean-lane-evidence-review.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.release_clean_lane_evidence_review"


def _resolved_input_path(vault: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return (vault / resolved).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fingerprint_groups(source_tree_coherence: dict[str, Any]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    components = source_tree_coherence.get("components")
    if not isinstance(components, list):
        return groups
    for component in components:
        if not isinstance(component, dict):
            continue
        fingerprint = str(component.get("source_tree_fingerprint", "")).strip() or "missing"
        groups.setdefault(fingerprint, []).append(str(component.get("name", "")).strip())
    return {key: sorted(value) for key, value in sorted(groups.items())}


def _evidence_unit(
    risk: dict[str, Any],
    *,
    source_tree_status: str,
    fingerprint_group_count: int,
) -> dict[str, Any]:
    code = str(risk.get("code", "")).strip()
    clean_effect = str(risk.get("clean_lane_effect", "")).strip()
    required_evidence = risk.get("required_evidence")
    if not isinstance(required_evidence, list):
        required_evidence = []

    if clean_effect == "does_not_block_clean_lane":
        demotion_status = "already_clean_non_blocking"
        clean_pass_candidate = True
    elif code == "source_tree_coherence_attention" and source_tree_status == "pass":
        demotion_status = "clean_pass_ready"
        clean_pass_candidate = True
    elif code == "source_tree_coherence_attention":
        demotion_status = "requires_same_chain_refresh"
        clean_pass_candidate = False
    else:
        demotion_status = "requires_policy_review"
        clean_pass_candidate = False

    return {
        "code": code,
        "source": str(risk.get("source", "")).strip(),
        "source_path": str(risk.get("source_path", "")).strip(),
        "clean_lane_effect": clean_effect,
        "conditional_lane_effect": str(risk.get("conditional_lane_effect", "")).strip(),
        "advisory_lifecycle_effect": str(
            risk.get("advisory_lifecycle_effect", "")
        ).strip(),
        "demotion_status": demotion_status,
        "clean_pass_candidate": clean_pass_candidate,
        "required_evidence": [str(item) for item in required_evidence],
        "source_tree_status": source_tree_status,
        "source_tree_fingerprint_group_count": fingerprint_group_count,
    }


def build_report(
    vault: Path,
    *,
    closeout_summary_path: str | Path = DEFAULT_CLOSEOUT_SUMMARY,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    resolved_summary_path = _resolved_input_path(vault, closeout_summary_path)
    closeout = _load_json(resolved_summary_path)
    source_tree = closeout.get("source_tree_coherence")
    if not isinstance(source_tree, dict):
        source_tree = {}
    source_tree_status = str(source_tree.get("status", "")).strip()
    fingerprint_groups = _fingerprint_groups(source_tree)
    risks = closeout.get("accepted_risks")
    if not isinstance(risks, list):
        risks = []
    units = [
        _evidence_unit(
            risk,
            source_tree_status=source_tree_status,
            fingerprint_group_count=len(fingerprint_groups),
        )
        for risk in risks
        if isinstance(risk, dict)
    ]
    demotion_counts = Counter(unit["demotion_status"] for unit in units)
    evidence_required_count = sum(
        1
        for unit in units
        if unit["demotion_status"]
        in {"requires_same_chain_refresh", "requires_policy_review"}
    )
    status = "attention" if evidence_required_count else "pass"
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="release_clean_lane_evidence_review",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/release_clean_lane_evidence_review.py"],
            file_inputs={"release_closeout_summary": resolved_summary_path},
        ),
        "vault": report_path(vault, vault),
        "status": status,
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "release_closeout_summary": {
            "path": report_path(vault, resolved_summary_path),
            "status": str(closeout.get("status", "")).strip(),
            "release_readiness_state": str(
                closeout.get("release_readiness_state", "")
            ).strip(),
            "machine_release_allowed": bool(closeout.get("machine_release_allowed", False)),
        },
        "source_tree_coherence": {
            "status": source_tree_status,
            "component_count": int(source_tree.get("component_count", 0) or 0),
            "fingerprint_group_count": len(fingerprint_groups),
            "fingerprint_groups": fingerprint_groups,
        },
        "summary": {
            "accepted_risk_count": len(units),
            "clean_pass_candidate_count": sum(
                1 for unit in units if unit["clean_pass_candidate"]
            ),
            "evidence_required_count": evidence_required_count,
            "already_clean_non_blocking_count": int(
                demotion_counts.get("already_clean_non_blocking", 0)
            ),
            "same_chain_refresh_required_count": int(
                demotion_counts.get("requires_same_chain_refresh", 0)
            ),
            "policy_review_required_count": int(
                demotion_counts.get("requires_policy_review", 0)
            ),
        },
        "evidence_units": units,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release clean lane evidence review schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Separate clean-lane accepted-risk demotion evidence from release closeout status.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--closeout-summary", default=DEFAULT_CLOSEOUT_SUMMARY)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--fail-on-attention", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, closeout_summary_path=args.closeout_summary)
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.fail_on_attention and report["status"] == "attention":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
