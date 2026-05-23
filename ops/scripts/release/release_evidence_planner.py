#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object_with_diagnostics,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.release.release_run_manifest import (
    DEFAULT_OUT as DEFAULT_RUN_MANIFEST,
    _resolve,
    git_commit,
)
from ops.scripts.release.release_sealed_run_manifest import (
    DEFAULT_OUT as DEFAULT_SEALED_RUN_MANIFEST,
    _json_identity,
    _unique_failures,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import (
    producer_input_fingerprint,
    release_source_tree_fingerprint,
)


DEFAULT_OUT = "build/release/release-evidence-plan.json"
SCHEMA_PATH = "ops/schemas/release-evidence-plan.schema.json"
PRODUCER = "ops.scripts.release_evidence_planner"
SOURCE_COMMAND = "python -m ops.scripts.release_evidence_planner --vault ."
DEFAULT_OPERATOR_SUMMARY = "build/release/operator-release-summary.json"
DEFAULT_AUTO_IMPROVE_READINESS = "ops/reports/auto-improve-readiness.json"
DEFAULT_AUTO_PROMOTION_PREFLIGHT = "build/release/release-auto-promotion-preflight.json"
DEFAULT_AUTO_PROMOTION_PRESEAL = "build/release/release-auto-promotion-preseal.json"

STAGES = {"sealed-run-ready", "auto-promotion-ready"}


def _node(
    vault: Path,
    *,
    name: str,
    path: str,
    expected_artifact_kind: str,
    authority_stage: str,
    cost_class: str,
    check_target: str,
    refresh_target: str,
    current_fingerprint: str,
    require_pass: bool,
    expected_phase: str = "",
) -> dict[str, Any]:
    identity = _json_identity(vault, path)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path))
    if diagnostics.get("status") != "ok":
        payload = {}
    issues: list[str] = []
    if identity["load_status"] != "ok":
        issues.append("not_loadable")
    if identity["artifact_kind"] != expected_artifact_kind:
        issues.append("artifact_kind_mismatch")
    if identity["source_tree_fingerprint"] != current_fingerprint:
        issues.append("stale")
    if require_pass and identity["status"] != "pass":
        issues.append("not_pass")
    phase = str(payload.get("phase", "")).strip()
    if expected_phase and phase != expected_phase:
        issues.append("phase_mismatch")
    return {
        "name": name,
        "path": identity["path"],
        "authority_stage": authority_stage,
        "cost_class": cost_class,
        "check_target": check_target,
        "refresh_target": refresh_target,
        "expected_artifact_kind": expected_artifact_kind,
        "expected_phase": expected_phase,
        "load_status": identity["load_status"],
        "artifact_kind": identity["artifact_kind"],
        "phase": phase,
        "status": identity["status"],
        "source_tree_fingerprint": identity["source_tree_fingerprint"],
        "input_fingerprint": identity["sha256"],
        "dependency_fingerprint": producer_input_fingerprint(payload),
        "currentness_status": "current"
        if identity["source_tree_fingerprint"] == current_fingerprint
        else "stale",
        "can_reuse": not issues,
        "issues": issues,
    }


def _blocker(
    *,
    blocker_id: str,
    node: dict[str, Any],
    summary: str,
    recommended_next_step: str,
) -> dict[str, Any]:
    return {
        "id": blocker_id,
        "node": str(node["name"]),
        "observed": (
            f"load_status={node['load_status']}; artifact_kind={node['artifact_kind']}; "
            f"phase={node['phase']}; status={node['status']}; "
            f"currentness={node['currentness_status']}; "
            f"issues={','.join(node['issues']) or 'none'}"
        ),
        "expected": (
            f"artifact_kind={node['expected_artifact_kind']}; status=pass; "
            "source_tree_fingerprint=current"
        ),
        "summary": summary,
        "recommended_next_step": recommended_next_step,
    }


def _action(
    *,
    target: str,
    action_type: str,
    cost_class: str,
    reason: str,
) -> dict[str, str]:
    return {
        "target": target,
        "action_type": action_type,
        "cost_class": cost_class,
        "reason": reason,
    }


def build_plan(
    vault: Path,
    *,
    stage: str,
    run_manifest: str = DEFAULT_RUN_MANIFEST,
    sealed_run_manifest: str = DEFAULT_SEALED_RUN_MANIFEST,
    operator_summary: str = DEFAULT_OPERATOR_SUMMARY,
    auto_improve_readiness: str = DEFAULT_AUTO_IMPROVE_READINESS,
    auto_promotion_preflight: str = DEFAULT_AUTO_PROMOTION_PREFLIGHT,
    auto_promotion_preseal: str = DEFAULT_AUTO_PROMOTION_PRESEAL,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"unsupported release evidence planning stage: {stage}")
    runtime_context = context or RuntimeContext(display_timezone=dt.timezone.utc)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(vault)
    nodes = {
        "run_manifest": _node(
            vault,
            name="run_manifest",
            path=run_manifest,
            expected_artifact_kind="release_run_manifest",
            authority_stage="release-run-ready",
            cost_class="expensive",
            check_target="release-run-ready-check",
            refresh_target="release-run-ready",
            current_fingerprint=fingerprint,
            require_pass=True,
        ),
        "auto_promotion_preflight": _node(
            vault,
            name="auto_promotion_preflight",
            path=auto_promotion_preflight,
            expected_artifact_kind="release_auto_promotion_preflight",
            authority_stage="release-auto-promotion-preflight",
            cost_class="cheap",
            check_target="release-auto-promotion-preflight-check",
            refresh_target="release-auto-promotion-preflight",
            current_fingerprint=fingerprint,
            require_pass=True,
            expected_phase="preflight",
        ),
        "auto_promotion_preseal": _node(
            vault,
            name="auto_promotion_preseal",
            path=auto_promotion_preseal,
            expected_artifact_kind="release_auto_promotion_preflight",
            authority_stage="release-auto-promotion-preseal",
            cost_class="cheap",
            check_target="release-auto-promotion-preseal-check",
            refresh_target="release-auto-promotion-preseal",
            current_fingerprint=fingerprint,
            require_pass=True,
            expected_phase="preseal",
        ),
        "sealed_run_manifest": _node(
            vault,
            name="sealed_run_manifest",
            path=sealed_run_manifest,
            expected_artifact_kind="release_sealed_run_manifest",
            authority_stage="release-sealed-run-ready",
            cost_class="medium",
            check_target="release-sealed-run-ready-check",
            refresh_target="release-sealed-run-ready",
            current_fingerprint=fingerprint,
            require_pass=True,
        ),
        "operator_summary": _node(
            vault,
            name="operator_summary",
            path=operator_summary,
            expected_artifact_kind="operator_release_summary",
            authority_stage="release-auto-promotion-ready",
            cost_class="cheap",
            check_target="release-auto-promotion-ready-check",
            refresh_target="release-auto-promotion-operator-summary",
            current_fingerprint=fingerprint,
            require_pass=False,
        ),
        "auto_improve_readiness": _node(
            vault,
            name="auto_improve_readiness",
            path=auto_improve_readiness,
            expected_artifact_kind="auto_improve_readiness_report",
            authority_stage="release-auto-promotion-ready",
            cost_class="cheap",
            check_target="release-auto-promotion-ready-check",
            refresh_target="auto-improve-readiness-report-body",
            current_fingerprint=fingerprint,
            require_pass=False,
        ),
    }

    blockers: list[dict[str, Any]] = []
    planned_actions: list[dict[str, str]] = []

    if stage == "sealed-run-ready":
        if not nodes["run_manifest"]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id="run_manifest_not_reusable",
                    node=nodes["run_manifest"],
                    summary="Runnable release authority is missing, stale, invalid, or not passing.",
                    recommended_next_step="Run make release-run-ready, then rerun the planner.",
                )
            )
        if not blockers:
            planned_actions.extend(
                [
                    _action(
                        target="release-evidence-closeout-sealed-sidecars",
                        action_type="refresh_sealed_sidecars",
                        cost_class="medium",
                        reason=(
                            "run-ready authority is reusable; sealed sidecars and the sealed "
                            "operator diagnostic may be refreshed."
                        ),
                    ),
                    _action(
                        target="release-sealed-post-seal-attestation",
                        action_type="refresh_post_seal_attestation",
                        cost_class="medium",
                        reason="sealed sidecars must be bound after source zip materialization.",
                    ),
                    _action(
                        target="release-evidence-closeout-sealed-check",
                        action_type="verify_sealed_rehearsal",
                        cost_class="medium",
                        reason="sealed package authority requires the rehearsal check.",
                    ),
                ]
            )
    elif stage == "auto-promotion-ready":
        if not nodes["auto_promotion_preflight"]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id="auto_promotion_preflight_not_reusable",
                    node=nodes["auto_promotion_preflight"],
                    summary=(
                        "Auto-promotion preflight is missing, stale, invalid, or not passing."
                    ),
                    recommended_next_step=(
                        "Run make release-auto-promotion-preflight before release-run-ready, "
                        "then rerun the planner."
                    ),
                )
            )
        if not nodes["run_manifest"]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id="run_manifest_not_reusable",
                    node=nodes["run_manifest"],
                    summary="Runnable release authority is missing, stale, invalid, or not passing.",
                    recommended_next_step="Run make release-run-ready, then rerun the planner.",
                )
            )
        if not nodes["auto_promotion_preseal"]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id="auto_promotion_preseal_not_reusable",
                    node=nodes["auto_promotion_preseal"],
                    summary="Auto-promotion preseal is missing, stale, invalid, or not passing.",
                    recommended_next_step=(
                        "Run make release-auto-promotion-preseal before release-sealed-run-ready, "
                        "then rerun the planner."
                    ),
                )
            )
        if not nodes["sealed_run_manifest"]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id="sealed_run_manifest_not_reusable",
                    node=nodes["sealed_run_manifest"],
                    summary="Sealed release authority is missing, stale, invalid, or not passing.",
                    recommended_next_step="Run make release-sealed-run-ready, then rerun the planner.",
                )
            )
        if not nodes["operator_summary"]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id="operator_summary_not_reusable",
                    node=nodes["operator_summary"],
                    summary=(
                        "Sealed operator diagnostics are missing, stale, invalid, or not reusable."
                    ),
                    recommended_next_step=(
                        "Run make release-sealed-run-ready to refresh sealed operator diagnostics, "
                        "or make release-auto-promotion-operator-summary if sealed sidecars are "
                        "already current."
                    ),
                )
            )
        if not blockers:
            if not nodes["auto_improve_readiness"]["can_reuse"]:
                planned_actions.append(
                    _action(
                        target="auto-improve-readiness-report-body",
                        action_type="pre_seal_diagnostic_refresh_required",
                        cost_class="cheap",
                        reason=(
                            "auto-improve readiness is not reusable for the current source tree; "
                            "refresh it before resealing evidence, not during stage 3 readback."
                        ),
                    )
                )

    plan_status = "ready" if not blockers else "blocked"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_evidence_plan",
        "generated_at": generated_at,
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": git_commit(vault),
        "source_tree_fingerprint": fingerprint,
        "input_fingerprints": {name: str(node["input_fingerprint"]) for name, node in nodes.items()},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": generated_at},
        "stage": stage,
        "plan_status": plan_status,
        "execution_mode": "cost_aware_minimal",
        "nodes": nodes,
        "planned_actions": planned_actions,
        "blockers": blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


def write_plan(vault: Path, plan: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=plan,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release evidence plan schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan cost-aware release evidence actions.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--stage", choices=sorted(STAGES), default="auto-promotion-ready")
    parser.add_argument("--require-ready", action="store_true")
    parser.add_argument("--run-manifest", default=DEFAULT_RUN_MANIFEST)
    parser.add_argument("--sealed-run-manifest", default=DEFAULT_SEALED_RUN_MANIFEST)
    parser.add_argument("--operator-summary", default=DEFAULT_OPERATOR_SUMMARY)
    parser.add_argument("--auto-improve-readiness", default=DEFAULT_AUTO_IMPROVE_READINESS)
    parser.add_argument("--auto-promotion-preflight", default=DEFAULT_AUTO_PROMOTION_PREFLIGHT)
    parser.add_argument("--auto-promotion-preseal", default=DEFAULT_AUTO_PROMOTION_PRESEAL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    plan = build_plan(
        vault,
        stage=args.stage,
        run_manifest=args.run_manifest,
        sealed_run_manifest=args.sealed_run_manifest,
        operator_summary=args.operator_summary,
        auto_improve_readiness=args.auto_improve_readiness,
        auto_promotion_preflight=args.auto_promotion_preflight,
        auto_promotion_preseal=args.auto_promotion_preseal,
    )
    path = write_plan(vault, plan, args.out)
    print(display_path(vault, path))
    print(f"release_evidence_plan_status={plan['plan_status']}")
    return 1 if args.require_ready and plan["plan_status"] != "ready" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
