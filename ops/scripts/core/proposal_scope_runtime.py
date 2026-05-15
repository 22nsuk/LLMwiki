from __future__ import annotations

from pathlib import Path

from .artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from .filesystem_runtime import normalized_allowed_apply_roots
from ops.scripts.mechanism_assess import (
    MechanismAssessmentState,
    configured_high_risk_flags,
    detect_risk_flags,
    normalize_targets,
)
from .path_runtime import normalize_repo_path_text
from .policy_runtime import report_path
from .runtime_context import RuntimeContext
from .schema_constants_runtime import PROPOSAL_SCOPE_SCHEMA_PATH


PROPOSAL_SCOPE_SCHEMA = PROPOSAL_SCOPE_SCHEMA_PATH


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _target_test_patterns(target: str, patterns: list[str]) -> list[str]:
    stem = Path(target).stem
    target_stem = stem
    return [
        template.format(stem=stem, target_stem=target_stem)
        for template in patterns
    ]


def resolve_focus_tests(
    vault: Path,
    policy: dict,
    primary_targets: list[str],
    supporting_targets: list[str],
) -> list[str]:
    scope_policy = policy["auto_improve_policy"]["scope_resolution"]
    overrides = scope_policy["test_file_overrides"]
    resolved: list[str] = []

    for target in primary_targets:
        override_paths = overrides.get(target, [])
        for override in override_paths:
            normalized_override = normalize_repo_path_text(override)
            if normalized_override is None:
                continue
            candidate = (vault / normalized_override).resolve()
            if candidate.exists():
                resolved.append(normalized_override)

    for target in primary_targets:
        for pattern in _target_test_patterns(target, scope_policy["test_path_globs"]):
            for match in sorted(vault.glob(pattern)):
                if match.is_file():
                    resolved.append(match.relative_to(vault).as_posix())

    for target in supporting_targets:
        normalized = normalize_repo_path_text(target)
        if normalized is None:
            continue
        if normalized.startswith("tests/") and (vault / normalized).exists():
            resolved.append(normalized)
            continue
        for pattern in _target_test_patterns(target, scope_policy["test_path_globs"]):
            for match in sorted(vault.glob(pattern)):
                if match.is_file():
                    resolved.append(match.relative_to(vault).as_posix())

    return dedupe_preserve_order(resolved)


def _proposal_declared_focus_tests(vault: Path, proposal: dict) -> list[str]:
    resolved: list[str] = []
    for field in ("must_change_tests", "test_files"):
        values = proposal.get(field, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = normalize_repo_path_text(value)
            if normalized is None or not normalized.startswith("tests/"):
                continue
            if (vault / normalized).is_file():
                resolved.append(normalized)
    return dedupe_preserve_order(resolved)


def _resolve_manual_risk_flags(policy: dict, targets: list[str]) -> list[str]:
    overrides = policy["auto_improve_policy"]["scope_resolution"]["risk_flag_overrides"]
    flags: list[str] = []
    for target in targets:
        for prefix, flag in overrides.items():
            if target == prefix or target.startswith(prefix):
                flags.append(flag)
    return dedupe_preserve_order(flags)


def _resolve_auditors(policy: dict, risk_flags: list[str]) -> list[str]:
    role_map = policy["auto_improve_policy"]["scope_resolution"]["auditor_role_map"]
    roles: list[str] = []
    for flag in risk_flags:
        roles.extend(role_map.get(flag, []))
    return dedupe_preserve_order(roles)


def _reviewer_target_match(policy: dict, targets: list[str]) -> bool:
    prefixes = policy["auto_improve_policy"]["scope_resolution"]["reviewer_target_prefixes"]
    return any(
        target == prefix or target.startswith(prefix)
        for prefix in prefixes
        for target in targets
    )


def build_scope_freeze(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    *,
    run_id: str,
    proposal: dict,
    context: RuntimeContext,
) -> dict:
    primary_targets = list(proposal["primary_targets"])
    supporting_targets = list(proposal["supporting_targets"])
    focus_tests = dedupe_preserve_order(
        [
            *resolve_focus_tests(vault, policy, primary_targets, supporting_targets),
            *_proposal_declared_focus_tests(vault, proposal),
        ]
    )

    state = MechanismAssessmentState()
    target_pairs = normalize_targets(vault, dedupe_preserve_order([*primary_targets, *supporting_targets]))
    detected_risk_flags = detect_risk_flags(
        state,
        target_pairs,
        configured_high_risk_flags(policy),
    )
    manual_risk_flags = _resolve_manual_risk_flags(policy, [*primary_targets, *supporting_targets])
    risk_flags = dedupe_preserve_order([*detected_risk_flags, *manual_risk_flags])
    allowed_apply_roots = normalized_allowed_apply_roots(
        policy["auto_improve_policy"]["allowed_apply_roots"]
    )

    blocked_by: list[str] = []
    if not focus_tests and policy["auto_improve_policy"]["scope_resolution"]["fail_closed_on_missing_tests"]:
        blocked_by.append("missing_focused_tests")

    all_targets = [*primary_targets, *supporting_targets]
    return {
        "$schema": PROPOSAL_SCOPE_SCHEMA,
        "run_id": run_id,
        "proposal_id": proposal["proposal_id"],
        "source_candidate_id": str(proposal.get("source_candidate_id", "")).strip(),
        "generated_at": context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy["version"],
        },
        "status": "blocked" if blocked_by else "runnable",
        "inputs": {
            "primary_targets": primary_targets,
            "supporting_targets": supporting_targets,
        },
        "resolution": {
            "test_files": focus_tests,
            "risk_flags": risk_flags,
            "blocked_by": blocked_by,
        },
        "apply_guardrails": {
            "allowed_apply_roots": allowed_apply_roots,
        },
        "dispatch": {
            "worker": True,
            "validator": not blocked_by,
            "reviewer": _reviewer_target_match(policy, all_targets),
            "auditors": _resolve_auditors(policy, risk_flags),
        },
    }


def write_scope_freeze(vault: Path, report: dict, *, run_id: str) -> Path:
    relative_path = Path("runs") / run_id / "scope-freeze.json"
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=PROPOSAL_SCOPE_SCHEMA,
            out_path=relative_path,
            default_relative_path=relative_path.as_posix(),
            context="proposal scope schema validation failed",
            trailing_newline=False,
        )
    )
