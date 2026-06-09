#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass, replace
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
)
from ops.scripts.release.release_sealed_run_manifest import (
    DEFAULT_OUT as DEFAULT_SEALED_RUN_MANIFEST,
    _json_identity,
    _unique_failures,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_revision_runtime import resolve_source_revision
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
DEFAULT_GOAL_RUN_STATUS = "ops/reports/goal-run-status.json"
DEFAULT_GOAL_RUNTIME_CERTIFICATE = "ops/reports/goal-runtime-certificate.json"

STAGES = {"sealed-run-ready", "auto-promotion-ready"}


@dataclass(frozen=True)
class NodeSpec:
    name: str
    path: str
    expected_artifact_kind: str
    authority_stage: str
    cost_class: str
    check_target: str
    refresh_target: str
    require_pass: bool
    expected_phase: str = ""


@dataclass(frozen=True)
class ReleaseEvidencePlanRequest:
    vault: Path
    stage: str
    run_manifest: str = DEFAULT_RUN_MANIFEST
    sealed_run_manifest: str = DEFAULT_SEALED_RUN_MANIFEST
    operator_summary: str = DEFAULT_OPERATOR_SUMMARY
    auto_improve_readiness: str = DEFAULT_AUTO_IMPROVE_READINESS
    auto_promotion_preflight: str = DEFAULT_AUTO_PROMOTION_PREFLIGHT
    auto_promotion_preseal: str = DEFAULT_AUTO_PROMOTION_PRESEAL
    goal_run_status: str = DEFAULT_GOAL_RUN_STATUS
    goal_runtime_certificate: str = DEFAULT_GOAL_RUNTIME_CERTIFICATE
    context: RuntimeContext | None = None

    def paths(self) -> dict[str, str]:
        return {
            "run_manifest": self.run_manifest,
            "sealed_run_manifest": self.sealed_run_manifest,
            "operator_summary": self.operator_summary,
            "auto_improve_readiness": self.auto_improve_readiness,
            "auto_promotion_preflight": self.auto_promotion_preflight,
            "auto_promotion_preseal": self.auto_promotion_preseal,
            "goal_run_status": self.goal_run_status,
            "goal_runtime_certificate": self.goal_runtime_certificate,
        }


def _node(
    vault: Path,
    *,
    spec: NodeSpec,
    current_fingerprint: str,
    current_revision: str,
) -> dict[str, Any]:
    identity = _json_identity(vault, spec.path)
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, spec.path))
    if diagnostics.get("status") != "ok":
        payload = {}
    source_revision = str(payload.get("source_revision", "")).strip()
    issues: list[str] = []
    if identity["load_status"] != "ok":
        issues.append("not_loadable")
    if identity["artifact_kind"] != spec.expected_artifact_kind:
        issues.append("artifact_kind_mismatch")
    if (
        identity["source_tree_fingerprint"] != current_fingerprint
        or source_revision != current_revision
    ):
        issues.append("stale")
    if spec.require_pass and identity["status"] != "pass":
        issues.append("not_pass")
    phase = str(payload.get("phase", "")).strip()
    if spec.expected_phase and phase != spec.expected_phase:
        issues.append("phase_mismatch")
    return {
        "name": spec.name,
        "path": identity["path"],
        "authority_stage": spec.authority_stage,
        "cost_class": spec.cost_class,
        "check_target": spec.check_target,
        "refresh_target": spec.refresh_target,
        "expected_artifact_kind": spec.expected_artifact_kind,
        "expected_phase": spec.expected_phase,
        "load_status": identity["load_status"],
        "artifact_kind": identity["artifact_kind"],
        "phase": phase,
        "status": identity["status"],
        "source_revision": source_revision,
        "source_tree_fingerprint": identity["source_tree_fingerprint"],
        "input_fingerprint": identity["sha256"],
        "dependency_fingerprint": producer_input_fingerprint(payload),
        "verification_status": "",
        "currentness_status": "current"
        if (
            identity["source_tree_fingerprint"] == current_fingerprint
            and source_revision == current_revision
        )
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
            f"source_revision={node['source_revision']}; "
            f"currentness={node['currentness_status']}; "
            f"issues={','.join(node['issues']) or 'none'}"
        ),
        "expected": (
            f"artifact_kind={node['expected_artifact_kind']}; status=pass; "
            "source_revision=current; source_tree_fingerprint=current"
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


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def _operator_attention_counts(vault: Path, path: str) -> dict[str, int]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path))
    if diagnostics.get("status") != "ok" or not isinstance(payload, dict):
        return {}
    accepted_risk = payload.get("accepted_risk")
    if not isinstance(accepted_risk, dict):
        return {}
    fields = (
        "accepted_risk_count",
        "release_accepted_risk_count",
        "gate_attention_count",
    )
    return {field: _int_value(accepted_risk.get(field)) for field in fields}


def _operator_attention_blocker(
    *,
    node: dict[str, Any],
    counts: dict[str, int],
) -> dict[str, str]:
    observed = "; ".join(f"{name}={value}" for name, value in counts.items())
    return {
        "id": "operator_summary_release_attention_not_clean",
        "node": str(node["name"]),
        "observed": observed,
        "expected": (
            "accepted_risk_count=0; release_accepted_risk_count=0; gate_attention_count=0"
        ),
        "summary": (
            "Sealed operator diagnostics still report accepted risk or gate attention, so "
            "unattended promotion would fail at Stage 3."
        ),
        "recommended_next_step": (
            "Run make release-auto-promotion-preseal to refresh source cleanup evidence, "
            "then make release-sealed-run-ready to regenerate the sealed operator summary."
        ),
    }


def _goal_run_status_node(
    vault: Path,
    path: str,
    *,
    current_fingerprint: str,
    current_revision: str,
) -> dict[str, Any]:
    node = _node(
        vault,
        spec=NodeSpec(
            "goal_run_status",
            path,
            "goal_run_status",
            "release-auto-promotion-ready",
            "cheap",
            "release-auto-promotion-ready-check",
            "auto-improve-goal-status",
            False,
        ),
        current_fingerprint=current_fingerprint,
        current_revision=current_revision,
    )
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path))
    if diagnostics.get("status") != "ok":
        payload = {}
    run = payload.get("run")
    run = run if isinstance(run, dict) else {}
    node["verification_status"] = str(run.get("status", "")).strip()
    if node["verification_status"] != "completed":
        node["can_reuse"] = False
        if "not_verified" not in node["issues"]:
            node["issues"].append("not_verified")
    return node


def _goal_runtime_certificate_node(
    vault: Path,
    path: str,
    *,
    current_fingerprint: str,
    current_revision: str,
) -> dict[str, Any]:
    node = _node(
        vault,
        spec=NodeSpec(
            "goal_runtime_certificate",
            path,
            "goal_runtime_certificate",
            "release-auto-promotion-ready",
            "cheap",
            "release-auto-promotion-ready-check",
            "goal-runtime-certificate",
            True,
        ),
        current_fingerprint=current_fingerprint,
        current_revision=current_revision,
    )
    payload, diagnostics = load_optional_json_object_with_diagnostics(_resolve(vault, path))
    if diagnostics.get("status") != "ok":
        payload = {}
    certificate = payload.get("certificate")
    certificate = certificate if isinstance(certificate, dict) else {}
    eligible = certificate.get("eligible", False)
    node["verification_status"] = str(certificate.get("verification_status", "")).strip()
    if not (node["verification_status"] in {"eligible", "already_verified"} and eligible is True):
        node["can_reuse"] = False
        if "not_verified" not in node["issues"]:
            node["issues"].append("not_verified")
    return node


def _plan_nodes(
    vault: Path,
    paths: dict[str, str],
    *,
    fingerprint: str,
    revision: str,
) -> dict[str, dict[str, Any]]:
    specs = [
        NodeSpec(
            "run_manifest",
            paths["run_manifest"],
            "release_run_manifest",
            "release-run-ready",
            "expensive",
            "release-run-ready-check",
            "release-run-ready",
            True,
        ),
        NodeSpec(
            "auto_promotion_preflight",
            paths["auto_promotion_preflight"],
            "release_auto_promotion_preflight",
            "release-auto-promotion-preflight",
            "cheap",
            "release-auto-promotion-preflight-check",
            "release-auto-promotion-preflight",
            True,
            "preflight",
        ),
        NodeSpec(
            "auto_promotion_preseal",
            paths["auto_promotion_preseal"],
            "release_auto_promotion_preflight",
            "release-auto-promotion-preseal",
            "cheap",
            "release-auto-promotion-preseal-check",
            "release-auto-promotion-preseal",
            True,
            "preseal",
        ),
        NodeSpec(
            "sealed_run_manifest",
            paths["sealed_run_manifest"],
            "release_sealed_run_manifest",
            "release-sealed-run-ready",
            "medium",
            "release-sealed-run-ready-check",
            "release-sealed-run-ready",
            True,
        ),
        NodeSpec(
            "operator_summary",
            paths["operator_summary"],
            "operator_release_summary",
            "release-auto-promotion-ready",
            "cheap",
            "release-auto-promotion-ready-check",
            "release-auto-promotion-operator-summary",
            False,
        ),
        NodeSpec(
            "auto_improve_readiness",
            paths["auto_improve_readiness"],
            "auto_improve_readiness_report",
            "release-auto-promotion-ready",
            "cheap",
            "release-auto-promotion-ready-check",
            "auto-improve-readiness-report-body",
            False,
        ),
    ]
    nodes = {
        spec.name: _node(
            vault,
            spec=spec,
            current_fingerprint=fingerprint,
            current_revision=revision,
        )
        for spec in specs
    }
    nodes["goal_run_status"] = _goal_run_status_node(
        vault,
        paths["goal_run_status"],
        current_fingerprint=fingerprint,
        current_revision=revision,
    )
    nodes["goal_runtime_certificate"] = _goal_runtime_certificate_node(
        vault,
        paths["goal_runtime_certificate"],
        current_fingerprint=fingerprint,
        current_revision=revision,
    )
    return nodes


def _sealed_run_ready_findings(
    nodes: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    blockers: list[dict[str, Any]] = []
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
    if blockers:
        return blockers, []
    return blockers, [
        _action(
            target="release-evidence-closeout-sealed-sidecars",
            action_type="refresh_sealed_sidecars",
            cost_class="medium",
            reason=(
                "run-ready and preseal authorities are reusable; sealed sidecars "
                "and the sealed operator diagnostic may be refreshed."
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


def _auto_promotion_ready_findings(
    vault: Path,
    nodes: dict[str, dict[str, Any]],
    *,
    operator_summary: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    blockers = _auto_promotion_ready_blockers(vault, nodes, operator_summary=operator_summary)
    actions: list[dict[str, str]] = []
    if not blockers and not nodes["auto_improve_readiness"]["can_reuse"]:
        actions.append(
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
    return blockers, actions


def _auto_promotion_ready_blockers(
    vault: Path,
    nodes: dict[str, dict[str, Any]],
    *,
    operator_summary: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    blocker_specs = [
        (
            "auto_promotion_preflight",
            "auto_promotion_preflight_not_reusable",
            "Auto-promotion preflight is missing, stale, invalid, or not passing.",
            "Run make release-auto-promotion-preflight before release-run-ready, then rerun the planner.",
        ),
        (
            "run_manifest",
            "run_manifest_not_reusable",
            "Runnable release authority is missing, stale, invalid, or not passing.",
            "Run make release-run-ready, then rerun the planner.",
        ),
        (
            "auto_promotion_preseal",
            "auto_promotion_preseal_not_reusable",
            "Auto-promotion preseal is missing, stale, invalid, or not passing.",
            "Run make release-auto-promotion-preseal before release-sealed-run-ready, then rerun the planner.",
        ),
        (
            "sealed_run_manifest",
            "sealed_run_manifest_not_reusable",
            "Sealed release authority is missing, stale, invalid, or not passing.",
            "Run make release-sealed-run-ready, then rerun the planner.",
        ),
        (
            "operator_summary",
            "operator_summary_not_reusable",
            "Sealed operator diagnostics are missing, stale, invalid, or not reusable.",
            (
                "Run make release-sealed-run-ready to refresh sealed operator diagnostics, "
                "or make release-auto-promotion-operator-summary if sealed sidecars are already current."
            ),
        ),
        (
            "goal_run_status",
            "goal_run_status_not_reusable",
            "Completed goal-run status evidence is missing, stale, invalid, or not completed.",
            (
                "Publish current completed goal-run status evidence for the selected run id, "
                "then rerun the planner."
            ),
        ),
        (
            "goal_runtime_certificate",
            "goal_runtime_certificate_not_reusable",
            "Verified goal-runtime certificate evidence is missing, stale, invalid, or not verified.",
            (
                "Run make goal-runtime-certificate for the selected completed run, "
                "then rerun the planner."
            ),
        ),
    ]
    for node_key, blocker_id, summary, next_step in blocker_specs:
        if not nodes[node_key]["can_reuse"]:
            blockers.append(
                _blocker(
                    blocker_id=blocker_id,
                    node=nodes[node_key],
                    summary=summary,
                    recommended_next_step=next_step,
                )
            )
    if nodes["operator_summary"]["can_reuse"]:
        counts = _operator_attention_counts(vault, operator_summary)
        if any(value != 0 for value in counts.values()):
            blockers.append(_operator_attention_blocker(node=nodes["operator_summary"], counts=counts))
    return blockers


def _plan_payload(
    metadata: dict[str, Any],
    *,
    stage: str,
    nodes: dict[str, dict[str, Any]],
    planned_actions: list[dict[str, str]],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    plan_status = "ready" if not blockers else "blocked"
    return {
        "$schema": SCHEMA_PATH,
        "artifact_kind": "release_evidence_plan",
        "generated_at": metadata["generated_at"],
        "producer": PRODUCER,
        "source_command": SOURCE_COMMAND,
        "source_revision": metadata["commit"],
        "source_tree_fingerprint": metadata["fingerprint"],
        "input_fingerprints": {name: str(node["input_fingerprint"]) for name, node in nodes.items()},
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "release_sidecar_authority",
        "encoding": "utf-8",
        "currentness": {"status": "current", "checked_at": metadata["generated_at"]},
        "stage": stage,
        "plan_status": plan_status,
        "execution_mode": "cost_aware_minimal",
        "nodes": nodes,
        "planned_actions": planned_actions,
        "blockers": blockers,
        "failures": _unique_failures([str(blocker["id"]) for blocker in blockers]),
    }


def _build_plan_from_request(request: ReleaseEvidencePlanRequest) -> dict[str, Any]:
    if request.stage not in STAGES:
        raise ValueError(f"unsupported release evidence planning stage: {request.stage}")
    runtime_context = request.context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    fingerprint = release_source_tree_fingerprint(request.vault)
    commit = resolve_source_revision(request.vault).revision
    nodes = _plan_nodes(
        request.vault,
        request.paths(),
        fingerprint=fingerprint,
        revision=commit,
    )
    if request.stage == "sealed-run-ready":
        blockers, planned_actions = _sealed_run_ready_findings(nodes)
    else:
        blockers, planned_actions = _auto_promotion_ready_findings(
            request.vault,
            nodes,
            operator_summary=request.operator_summary,
        )
    metadata = {
        "generated_at": generated_at,
        "commit": commit,
        "fingerprint": fingerprint,
    }
    return _plan_payload(
        metadata,
        stage=request.stage,
        nodes=nodes,
        planned_actions=planned_actions,
        blockers=blockers,
    )


def _legacy_build_plan_request(
    vault: Path | str,
    *,
    stage: str | None,
    context: RuntimeContext | None,
    path_overrides: dict[str, str],
) -> ReleaseEvidencePlanRequest:
    if stage is None:
        raise TypeError("build_plan() missing required keyword-only argument: 'stage'")
    request = ReleaseEvidencePlanRequest(vault=Path(vault), stage=stage, context=context)
    unsupported = sorted(set(path_overrides) - set(request.paths()))
    if unsupported:
        fields = ", ".join(unsupported)
        raise TypeError(f"unsupported release evidence path override(s): {fields}")
    replacement_fields: dict[str, Any] = dict(path_overrides)
    return replace(request, **replacement_fields)


def build_plan(
    request_or_vault: ReleaseEvidencePlanRequest | Path | str,
    *,
    stage: str | None = None,
    context: RuntimeContext | None = None,
    **path_overrides: str,
) -> dict[str, Any]:
    if isinstance(request_or_vault, ReleaseEvidencePlanRequest):
        if stage is not None or context is not None or path_overrides:
            raise TypeError(
                "ReleaseEvidencePlanRequest cannot be combined with legacy build_plan keywords"
            )
        return _build_plan_from_request(request_or_vault)
    request = _legacy_build_plan_request(
        request_or_vault,
        stage=stage,
        context=context,
        path_overrides=path_overrides,
    )
    return _build_plan_from_request(request)


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
    parser.add_argument("--goal-run-status", default=DEFAULT_GOAL_RUN_STATUS)
    parser.add_argument("--goal-runtime-certificate", default=DEFAULT_GOAL_RUNTIME_CERTIFICATE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    plan = build_plan(
        ReleaseEvidencePlanRequest(
            vault=vault,
            stage=args.stage,
            run_manifest=args.run_manifest,
            sealed_run_manifest=args.sealed_run_manifest,
            operator_summary=args.operator_summary,
            auto_improve_readiness=args.auto_improve_readiness,
            auto_promotion_preflight=args.auto_promotion_preflight,
            auto_promotion_preseal=args.auto_promotion_preseal,
            goal_run_status=args.goal_run_status,
            goal_runtime_certificate=args.goal_runtime_certificate,
        )
    )
    path = write_plan(vault, plan, args.out)
    print(display_path(vault, path))
    print(f"release_evidence_plan_status={plan['plan_status']}")
    return 1 if args.require_ready and plan["plan_status"] != "ready" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
