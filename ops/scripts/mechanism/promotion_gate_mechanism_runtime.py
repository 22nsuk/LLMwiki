from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .promotion_gate_mechanism_finalize_runtime import (
    finalize_mechanism_promotion_report,
)
from .promotion_gate_mechanism_report_runtime import (
    MechanismPromotionReportAssemblyRequest,
    assemble_mechanism_promotion_report as _assemble_mechanism_promotion_report,
)
from .promotion_gate_mechanism_rule_registry_runtime import (
    build_mechanism_rule_registry as _build_mechanism_rule_registry,
)
from .promotion_gate_mechanism_state_runtime import (
    MechanismGateInputRequest,
    MechanismGateInputs,
    MechanismPromotionState,
    build_mechanism_promotion_state as _build_mechanism_promotion_state,
    collect_mechanism_gate_inputs as _collect_mechanism_gate_inputs,
)


@dataclass(frozen=True)
class MechanismPromotionReportRequest:
    vault: Path
    run_id: str
    policy: dict
    resolved_policy_path: Path
    artifact_class: str
    primary_targets: list[str]
    supporting_targets: list[str]
    signoff: dict
    log: dict
    inputs: MechanismGateInputs
    auto_improve_run: bool = False


def collect_mechanism_gate_inputs(
    vault_or_request: Path | MechanismGateInputRequest,
    *legacy_args: Any,
    **legacy_fields: Any,
) -> MechanismGateInputs:
    return _collect_mechanism_gate_inputs(
        vault_or_request,
        *legacy_args,
        **legacy_fields,
    )


def build_mechanism_promotion_state(
    vault: Path,
    *,
    policy: dict,
    resolved_policy_path: Path,
    artifact_class: str,
    primary_targets: list[str],
    signoff: dict,
    inputs: MechanismGateInputs,
) -> MechanismPromotionState:
    return _build_mechanism_promotion_state(
        vault,
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        artifact_class=artifact_class,
        primary_targets=primary_targets,
        signoff=signoff,
        inputs=inputs,
    )


def build_mechanism_rule_registry(
    vault: Path,
    *,
    run_id: str,
    policy: dict,
    primary_targets: list[str],
    supporting_targets: list[str],
    signoff: dict,
    inputs: MechanismGateInputs,
    state: MechanismPromotionState,
    auto_improve_run: bool,
) -> dict:
    return _build_mechanism_rule_registry(
        vault=vault,
        run_id=run_id,
        policy=policy,
        primary_targets=primary_targets,
        supporting_targets=supporting_targets,
        signoff=signoff,
        inputs=inputs,
        state=state,
        auto_improve_run=auto_improve_run,
    )


def assemble_mechanism_promotion_report(
    *args: Any,
    request: MechanismPromotionReportAssemblyRequest | None = None,
    **kwargs: Any,
) -> dict:
    return _assemble_mechanism_promotion_report(*args, request=request, **kwargs)


def mechanism_class_report(
    *args: Any,
    request: MechanismPromotionReportRequest | None = None,
    auto_improve_run: bool | None = None,
    **kwargs: Any,
) -> dict:
    request = _coerce_mechanism_promotion_report_request(
        request=request,
        args=args,
        kwargs=kwargs,
        auto_improve_run=auto_improve_run,
    )
    state = build_mechanism_promotion_state(
        request.vault,
        policy=request.policy,
        resolved_policy_path=request.resolved_policy_path,
        artifact_class=request.artifact_class,
        primary_targets=request.primary_targets,
        signoff=request.signoff,
        inputs=request.inputs,
    )
    available_rules = build_mechanism_rule_registry(
        request.vault,
        run_id=request.run_id,
        policy=request.policy,
        primary_targets=request.primary_targets,
        supporting_targets=request.supporting_targets,
        signoff=request.signoff,
        inputs=request.inputs,
        state=state,
        auto_improve_run=request.auto_improve_run,
    )
    return finalize_mechanism_promotion_report(
        run_id=request.run_id,
        artifact_class=request.artifact_class,
        policy=request.policy,
        primary_targets=request.primary_targets,
        supporting_targets=request.supporting_targets,
        signoff=request.signoff,
        log=request.log,
        inputs=request.inputs,
        available_rules=available_rules,
    )


def _coerce_mechanism_promotion_report_request(
    *,
    request: MechanismPromotionReportRequest | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    auto_improve_run: bool | None,
) -> MechanismPromotionReportRequest:
    if request is not None:
        if args or kwargs:
            raise TypeError("request cannot be combined with positional or keyword report fields")
        if auto_improve_run is not None:
            return replace(request, auto_improve_run=auto_improve_run)
        return request

    field_names = [
        "vault",
        "run_id",
        "policy",
        "resolved_policy_path",
        "artifact_class",
        "primary_targets",
        "supporting_targets",
        "signoff",
        "log",
        "inputs",
    ]
    if len(args) > len(field_names):
        raise TypeError(f"expected at most {len(field_names)} positional arguments")
    values = dict(zip(field_names, args, strict=False))
    values.update(kwargs)
    values["auto_improve_run"] = bool(auto_improve_run) if auto_improve_run is not None else bool(
        values.get("auto_improve_run", False)
    )
    missing = [name for name in field_names if name not in values]
    if missing:
        raise TypeError(f"missing mechanism promotion report fields: {', '.join(missing)}")
    return MechanismPromotionReportRequest(**values)
