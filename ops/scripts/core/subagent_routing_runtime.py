from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ops.scripts.mechanism.mechanism_assess import (
    MechanismAssessmentState,
    build_structural_metrics,
    complexity_dimension_evidence,
    complexity_dimensions,
    complexity_score,
    configured_high_risk_flags,
    detect_risk_flag_evidence,
    normalize_targets,
    target_structural_profiles,
)

from .artifact_envelope_runtime import build_canonical_report_envelope
from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    resolve_schema_backed_report_output_path,
    write_schema_backed_report,
)
from .output_runtime import display_path, resolve_vault_path
from .policy_runtime import (
    SUPPORTED_SUBAGENT_LADDER,
    load_policy,
    report_path,
    subagent_ladder_model_effort,
    subagent_score_band_names,
)
from .runtime_context import RuntimeContext
from .schema_constants_runtime import SUBAGENT_ROUTING_SCHEMA_PATH

SUBAGENT_ROUTING_SCHEMA = SUBAGENT_ROUTING_SCHEMA_PATH
PRODUCER = "ops.scripts.subagent_routing_runtime"
SOURCE_COMMAND = "python -m ops.scripts.core.select_subagent_rung"
ARTIFACT_KIND = "subagent_routing_report"
DEFAULT_SUBAGENT_ROUTING_REPORT_OUT = "tmp/subagent-routing-report.json"
CANONICAL_SUBAGENT_ROUTING_REPORT_OUT = "ops/reports/subagent-routing-report.json"


@dataclass(frozen=True)
class _SubagentRoutingReportPayload:
    vault: Path
    resolved_policy_path: Path
    policy: dict
    role: str
    profile_path_text: str
    generated_at: str
    primary_target_paths: list[str]
    supporting_target_paths: list[str]
    test_file_paths: list[str]
    validated_manual_risk_flags: list[str]
    validated_requested_rung: int | None
    structural_metrics: dict
    total_structural_metrics: dict
    diagnostics: dict
    dimensions: dict
    score: int
    risk_flags: list[str]
    detected_risk_flags: list[str]
    detected_risk_flag_evidence: list[dict]
    total_target_profiles: list[dict]
    dimension_evidence: dict
    routing_decision: dict


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def normalize_optional_targets(vault: Path, raw_targets: list[str]) -> list[tuple[str, Path]]:
    deduped = dedupe_preserve_order(raw_targets)
    if not deduped:
        return []
    return normalize_targets(vault, deduped)


def resolve_role_policy(policy: dict, role: str) -> dict:
    roles = policy["subagent_routing_policy"]["roles"]
    if role not in roles:
        raise ValueError(f"unknown subagent role: {role}")
    return roles[role]


def resolve_profile_path(vault: Path, role: str) -> Path:
    profile_path = resolve_vault_path(vault, f".codex/agents/{role}.toml")
    if not profile_path.exists():
        raise ValueError(f"missing subagent profile: {report_path(vault, profile_path)}")
    return profile_path


def validate_manual_risk_flags(policy: dict, manual_risk_flags: list[str]) -> list[str]:
    allowed_flags = set(configured_high_risk_flags(policy))
    ordered = dedupe_preserve_order(manual_risk_flags)
    for flag in ordered:
        if flag not in allowed_flags:
            raise ValueError(f"unsupported manual risk flag: {flag}")
    return ordered


def validate_requested_rung(requested_rung: int | None) -> int | None:
    if requested_rung is None:
        return None
    if requested_rung not in SUPPORTED_SUBAGENT_LADDER:
        raise ValueError(f"unsupported requested rung: {requested_rung}")
    return requested_rung


def score_band_name(policy: dict, score: int) -> str:
    score_bands = policy["subagent_routing_policy"]["score_bands"]
    for band_name in subagent_score_band_names(policy):
        if score <= score_bands[band_name]["max_score"]:
            return band_name
    raise ValueError(f"complexity score is outside configured score bands: {score}")


def allowed_rung_floor(allowed_rungs: list[int], requested_rung: int) -> int:
    for rung in allowed_rungs:
        if rung >= requested_rung:
            return rung
    return allowed_rungs[-1]


def effort_sufficiency_status(
    allowed_rungs: list[int],
    selected_rung: int,
    escalation_reasons: list[dict],
) -> dict[str, str]:
    max_role_rung = max(allowed_rungs)
    if len(allowed_rungs) == 1:
        return {
            "status": "fixed_role_floor",
            "why": (
                f"role is intentionally fixed to rung {selected_rung}; no lower "
                "reasoning effort is allowed by policy"
            ),
        }
    if selected_rung >= max_role_rung:
        if escalation_reasons:
            return {
                "status": "escalated_for_complexity",
                "why": (
                    f"selected rung {selected_rung} because score, pressure, or manual "
                    "request evidence reached the role's highest allowed rung"
                ),
            }
        return {
            "status": "default_highest_allowed",
            "why": (
                f"selected rung {selected_rung} because the role default is already "
                "the highest allowed rung"
            ),
        }
    return {
        "status": "sufficient_for_complexity",
        "why": (
            f"selected rung {selected_rung} is below the role maximum {max_role_rung} "
            "because no configured escalation evidence required the higher rung"
        ),
    }


def deescalation_reasons_for_policy(
    role_policy: dict,
    *,
    default_rung: int,
    band_rung: int,
    score_band: str,
    score: int,
    dimensions: dict[str, int],
    selected_rung: int,
) -> list[dict]:
    reasons: list[dict] = []
    if band_rung <= default_rung:
        reasons.append(
            {
                "type": "score_band_not_escalated",
                "detail": (
                    f"complexity score {score} fell in the {score_band} band; "
                    f"band rung {band_rung} did not exceed default rung {default_rung}"
                ),
            }
        )

    for dimension, override in role_policy["pressure_overrides"].items():
        value = dimensions[dimension]
        threshold = override["threshold"]
        if value >= threshold:
            continue
        reasons.append(
            {
                "type": "pressure_below_threshold",
                "detail": (
                    f"{dimension}={value} stayed below the role threshold {threshold}; "
                    f"no rung {override['min_rung']} pressure override applied"
                ),
                "dimension": dimension,
                "value": value,
                "threshold": threshold,
                "min_rung": override["min_rung"],
            }
        )

    max_role_rung = max(role_policy["allowed_rungs"])
    if selected_rung < max_role_rung:
        reasons.append(
            {
                "type": "higher_rung_not_required",
                "detail": (
                    f"selected rung {selected_rung}; role maximum rung {max_role_rung} "
                    "was not required by score band, pressure overrides, or manual request"
                ),
                "min_rung": max_role_rung,
            }
        )
    return reasons


def build_routing_decision(
    policy: dict,
    role: str,
    dimensions: dict[str, int],
    score: int,
    requested_rung: int | None = None,
) -> dict:
    role_policy = resolve_role_policy(policy, role)
    allowed_rungs = list(role_policy["allowed_rungs"])
    default_rung = role_policy["default_rung"]
    score_band = score_band_name(policy, score)
    band_rung = role_policy["score_band_rungs"][score_band]
    escalation_reasons: list[dict] = []

    derived_requested_rung = band_rung
    if band_rung > default_rung:
        escalation_reasons.append(
            {
                "type": "score_band",
                "detail": (
                    f"complexity score {score} fell in the {score_band} band and raised "
                    f"the rung floor to {band_rung}"
                ),
            }
        )

    for dimension, override in role_policy["pressure_overrides"].items():
        value = dimensions[dimension]
        threshold = override["threshold"]
        min_rung = override["min_rung"]
        if value < threshold:
            continue
        escalation_reasons.append(
            {
                "type": "pressure_override",
                "detail": (
                    f"{dimension}={value} met the role threshold {threshold} and "
                    f"requested at least rung {min_rung}"
                ),
                "dimension": dimension,
                "value": value,
                "threshold": threshold,
                "min_rung": min_rung,
            }
        )
        derived_requested_rung = max(derived_requested_rung, min_rung)

    if requested_rung is not None:
        escalation_reasons.append(
            {
                "type": "manual_request",
                "detail": f"caller requested at least rung {requested_rung}",
                "min_rung": requested_rung,
            }
        )
        derived_requested_rung = max(derived_requested_rung, requested_rung)

    selected_rung = allowed_rung_floor(allowed_rungs, derived_requested_rung)
    if selected_rung != derived_requested_rung:
        escalation_reasons.append(
            {
                "type": "allowed_rung_clamp",
                "detail": (
                    f"requested rung {derived_requested_rung} is outside the role ladder "
                    f"{allowed_rungs}; selected rung {selected_rung}"
                ),
                "min_rung": derived_requested_rung,
            }
        )

    model, reasoning_effort = subagent_ladder_model_effort(policy, selected_rung)
    return {
        "default_rung": default_rung,
        "allowed_rungs": allowed_rungs,
        "score_band": score_band,
        "band_rung": band_rung,
        "requested_rung": derived_requested_rung,
        "selected_rung": selected_rung,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox_mode": role_policy["sandbox_mode"],
        "escalation_reasons": escalation_reasons,
        "deescalation_reasons": deescalation_reasons_for_policy(
            role_policy,
            default_rung=default_rung,
            band_rung=band_rung,
            score_band=score_band,
            score=score,
            dimensions=dimensions,
            selected_rung=selected_rung,
        ),
        "effort_sufficiency": effort_sufficiency_status(
            allowed_rungs,
            selected_rung,
            escalation_reasons,
        ),
    }


def build_manual_dispatch_contract(
    *,
    role: str,
    profile_path: str,
    routing_decision: dict,
) -> dict:
    selected_model = routing_decision["model"]
    selected_reasoning_effort = routing_decision["reasoning_effort"]
    return {
        "contract": "manual_subagent_dispatch_v1",
        "source": "subagent_routing_selector",
        "role": role,
        "selected_rung": routing_decision["selected_rung"],
        "launch_parameters": {
            "profile_path": profile_path,
            "model": selected_model,
            "model_reasoning_effort": selected_reasoning_effort,
            "sandbox_mode": routing_decision["sandbox_mode"],
        },
        "fixed_reasoning_surface": {
            "compatibility_rule": "exact_model_and_reasoning_effort_match_required",
            "required_model": selected_model,
            "required_model_reasoning_effort": selected_reasoning_effort,
            "required_selected_rung": routing_decision["selected_rung"],
            "allowed_when": "fixed_values_match_required_model_and_reasoning_effort",
            "mismatch_action": "use_controllable_launch_parameters",
            "controllable_launch_surface": "controllable_launch_parameters",
        },
        "dispatch_surfaces": {
            "ladder_compliant_surface": "controllable_launch_parameters",
            "controllable_launch": (
                "Use repo-native codex_exec or a default/custom subagent surface that accepts "
                "model, model_reasoning_effort, sandbox_mode, and profile instructions."
            ),
            "platform_named_role": (
                "Treat platform named roles as fixed-reasoning surfaces; use them only when "
                "their fixed model/reasoning matches the selected rung, otherwise use a "
                "controllable launch surface."
            ),
        },
        "toml_fallback_role": "instruction_surface_only",
        "operator_action": (
            "Launch manual subagents through a controllable surface with these selected "
            "values; platform named roles may ignore model_reasoning_effort overrides. "
            "Use requested_rung only to request a higher floor within the role's allowed_rungs."
        ),
    }


def _build_subagent_routing_report_payload(payload: _SubagentRoutingReportPayload) -> dict:
    envelope = build_canonical_report_envelope(
        payload.vault,
        generated_at=payload.generated_at,
        artifact_kind=ARTIFACT_KIND,
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=payload.resolved_policy_path,
        schema_path=SUBAGENT_ROUTING_SCHEMA,
        source_paths=[
            "ops/scripts/core/select_subagent_rung.py",
            "ops/scripts/core/subagent_routing_runtime.py",
            "ops/scripts/mechanism/mechanism_assess.py",
        ],
        text_inputs={
            "role": payload.role,
            "primary_targets": "\n".join(payload.primary_target_paths),
            "supporting_targets": "\n".join(payload.supporting_target_paths),
            "test_files": "\n".join(payload.test_file_paths),
            "manual_risk_flags": "\n".join(payload.validated_manual_risk_flags),
            "requested_rung": (
                ""
                if payload.validated_requested_rung is None
                else str(payload.validated_requested_rung)
            ),
        },
    )
    return {
        **envelope,
        "$schema": SUBAGENT_ROUTING_SCHEMA,
        "vault": report_path(payload.vault, payload.vault),
        "generated_at": payload.generated_at,
        "policy": {
            "path": report_path(payload.vault, payload.resolved_policy_path),
            "version": payload.policy.get("version"),
        },
        "role": payload.role,
        "profile_path": payload.profile_path_text,
        "inputs": {
            "primary_targets": payload.primary_target_paths,
            "supporting_targets": payload.supporting_target_paths,
            "test_files": payload.test_file_paths,
            "manual_risk_flags": payload.validated_manual_risk_flags,
        },
        "structural_metrics": payload.structural_metrics,
        "total_structural_metrics": payload.total_structural_metrics,
        "diagnostics": payload.diagnostics,
        "complexity_profile": {
            "dimensions": payload.dimensions,
            "complexity_score": payload.score,
            "risk_flags": payload.risk_flags,
            "detected_risk_flags": payload.detected_risk_flags,
            "manual_risk_flags": payload.validated_manual_risk_flags,
            "risk_flag_evidence": payload.detected_risk_flag_evidence,
            "target_profiles": payload.total_target_profiles,
            "dimension_evidence": payload.dimension_evidence,
        },
        "routing_decision": payload.routing_decision,
        "manual_dispatch": build_manual_dispatch_contract(
            role=payload.role,
            profile_path=payload.profile_path_text,
            routing_decision=payload.routing_decision,
        ),
    }


def build_report(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    role: str,
    primary_targets: list[tuple[str, Path]],
    supporting_targets: list[tuple[str, Path]],
    test_files: list[tuple[str, Path]],
    manual_risk_flags: list[str],
    requested_rung: int | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    runtime_context = context or RuntimeContext.from_policy(policy)
    profile_path = resolve_profile_path(vault, role)
    validated_requested_rung = validate_requested_rung(requested_rung)
    validated_manual_risk_flags = validate_manual_risk_flags(policy, manual_risk_flags)

    state = MechanismAssessmentState()
    structural_metrics = build_structural_metrics(state, primary_targets, test_files)
    total_structural_metrics = build_structural_metrics(
        state,
        [*primary_targets, *supporting_targets],
        test_files,
    )
    total_target_profiles = target_structural_profiles(
        state,
        primary_targets + supporting_targets,
    )
    detected_risk_flag_evidence = detect_risk_flag_evidence(
        state,
        primary_targets + supporting_targets,
        configured_high_risk_flags(policy),
    )
    detected_risk_flags = sorted({entry["flag"] for entry in detected_risk_flag_evidence})
    risk_flags = sorted({*detected_risk_flags, *validated_manual_risk_flags})
    if not primary_targets and not supporting_targets and not risk_flags:
        dimensions = {
            "change_surface": 0,
            "dependency_impact": 0,
            "verification_cost": 0,
            "artifact_heterogeneity": 0,
            "environment_risk": 0,
        }
        dimension_evidence = complexity_dimension_evidence(
            total_structural_metrics,
            primary_targets,
            supporting_targets,
            risk_flags,
            total_target_profiles,
        )
        score = 0
    else:
        dimensions = complexity_dimensions(
            total_structural_metrics,
            primary_targets,
            supporting_targets,
            risk_flags,
            total_target_profiles,
        )
        dimension_evidence = complexity_dimension_evidence(
            total_structural_metrics,
            primary_targets,
            supporting_targets,
            risk_flags,
            total_target_profiles,
        )
        score = complexity_score(policy, dimensions)
    routing_decision = build_routing_decision(
        policy,
        role,
        dimensions,
        score,
        requested_rung=validated_requested_rung,
    )

    primary_target_paths = [rel_path for rel_path, _ in primary_targets]
    supporting_target_paths = [rel_path for rel_path, _ in supporting_targets]
    test_file_paths = [rel_path for rel_path, _ in test_files]

    profile_path_text = report_path(vault, profile_path)
    generated_at = runtime_context.isoformat_z()
    return _build_subagent_routing_report_payload(
        _SubagentRoutingReportPayload(
            vault=vault,
            resolved_policy_path=resolved_policy_path,
            policy=policy,
            role=role,
            profile_path_text=profile_path_text,
            generated_at=generated_at,
            primary_target_paths=primary_target_paths,
            supporting_target_paths=supporting_target_paths,
            test_file_paths=test_file_paths,
            validated_manual_risk_flags=validated_manual_risk_flags,
            validated_requested_rung=validated_requested_rung,
            structural_metrics=structural_metrics,
            total_structural_metrics=total_structural_metrics,
            diagnostics=state.report(),
            dimensions=dimensions,
            score=score,
            risk_flags=risk_flags,
            detected_risk_flags=detected_risk_flags,
            detected_risk_flag_evidence=detected_risk_flag_evidence,
            total_target_profiles=total_target_profiles,
            dimension_evidence=dimension_evidence,
            routing_decision=routing_decision,
        )
    )


def retention_policy_for_output(vault: Path, destination: Path) -> str:
    rel_path = report_path(vault, destination)
    if rel_path == CANONICAL_SUBAGENT_ROUTING_REPORT_OUT:
        return "canonical_report"
    if rel_path.startswith("runs/"):
        return "archive"
    return "ephemeral"


def write_report(vault: Path, report: dict, out_path: str | None) -> Path:
    destination = resolve_schema_backed_report_output_path(
        vault,
        out_path,
        default_relative_path=DEFAULT_SUBAGENT_ROUTING_REPORT_OUT,
    )
    report["retention_policy"] = retention_policy_for_output(vault, destination)
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SUBAGENT_ROUTING_SCHEMA,
            out_path=destination,
            default_relative_path=DEFAULT_SUBAGENT_ROUTING_REPORT_OUT,
            context="subagent routing schema validation failed",
            trailing_newline=False,
        )
    )


def run_selector(
    *,
    vault: Path,
    policy_path: str = "ops/policies/wiki-maintainer-policy.yaml",
    role: str,
    primary_targets: list[str] | None = None,
    supporting_targets: list[str] | None = None,
    test_files: list[str] | None = None,
    manual_risk_flags: list[str] | None = None,
    requested_rung: int | None = None,
    out_path: str | None = None,
    context: RuntimeContext | None = None,
) -> tuple[dict, Path]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    report = build_report(
        vault,
        policy,
        resolved_policy_path,
        role,
        normalize_optional_targets(vault, primary_targets or []),
        normalize_optional_targets(vault, supporting_targets or []),
        normalize_optional_targets(vault, test_files or []),
        manual_risk_flags or [],
        requested_rung=requested_rung,
        context=context,
    )
    destination = write_report(vault, report, out_path)
    return report, destination


def print_report(vault: Path, report: dict, destination: Path) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten_to={display_path(vault, destination)}")
