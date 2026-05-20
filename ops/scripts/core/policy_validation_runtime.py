from __future__ import annotations

from collections.abc import Callable
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from .filesystem_runtime import normalized_allowed_apply_roots
from .path_runtime import normalize_repo_path_text
from .promotion_decision_registry_runtime import promotion_decision_values


SUPPORTED_COMPLEXITY_FORMULA = "complexity_score = round(sum(weight_i * dimension_i) / 5)"
SUPPORTED_COMPLEXITY_OUTPUT_RANGE = "0-100"
SUPPORTED_SUBAGENT_LADDER = {
    1: ("gpt-5.5", "medium"),
    2: ("gpt-5.5", "high"),
    3: ("gpt-5.5", "xhigh"),
}
SUPPORTED_SUBAGENT_SANDBOX_MODES = set("read-only workspace-write danger-full-access".split())
SUPPORTED_WORKSPACE_PREPARATION_MODES = set("full_copy sparse_manifest".split())
SUPPORTED_SUBAGENT_PRESSURE_DIMENSIONS = {
    "change_surface",
    "dependency_impact",
    "verification_cost",
    "artifact_heterogeneity",
    "environment_risk",
}
SUPPORTED_PROMOTION_DECISION_VALUES = set(promotion_decision_values())
SUPPORTED_LOG_STATUS_VALUES = set("pending recorded not_required".split())
SUPPORTED_WARNING_BUDGET_SOURCES = set("raw_registry_preflight wiki_lint".split())
SUPPORTED_PROMOTION_RULE_REDUCERS = set(
    "none status_fail_discard candidate_lint_status candidate_eval_status "
    "equal_score_secondary signoff_status page_repo_lint_status "
    "page_primary_eval_status page_signoff_status".split()
)
SUPPORTED_PROMOTION_RULE_SEVERITIES = set("info advisory warning blocker".split())
SUPPORTED_PROMOTION_RULE_ARTIFACT_DEPENDENCIES = {
    "baseline_eval_report",
    "candidate_eval_report",
    "baseline_lint_report",
    "candidate_lint_report",
    "baseline_mechanism_report",
    "candidate_mechanism_report",
    "changed_files_manifest",
    "run_ledger",
    "behavior_delta",
    "policy",
    "signoff",
    "current_lint",
    "current_eval",
    "current_stage2",
}
SUPPORTED_PAGE_CLASS_PROMOTION_RULES = {
    "primary_target_scope",
    "primary_target_exists",
    "repo_lint_status",
    "current_policy_consistency",
    "primary_target_eval_full_pass",
    "primary_target_stage2_full_pass",
    "signoff_status",
}
SUPPORTED_SYSTEM_MECHANISM_PROMOTION_RULES = {
    "primary_target_scope",
    "primary_target_exists",
    "report_consistency",
    "run_ledger_target_coverage",
    "mechanism_report_primary_targets",
    "changed_files_manifest_declared_targets",
    "changed_files_manifest_scope",
    "changed_files_manifest_allowed_apply_roots",
    "changed_files_manifest_nonempty",
    "changed_files_manifest_primary_targets_touched",
    "behavior_delta_presence",
    "candidate_lint_pass",
    "candidate_eval_pass",
    "eval_score_improves",
    "lint_non_regression",
    "lint_improves",
    "structural_complexity_non_regression",
    "structural_complexity_improves",
    "tests_non_regression",
    "tests_increase",
    "complexity_profile_score",
    "risk_flags",
    "equal_score_secondary_eligibility",
    "signoff_status",
}
SUPPORTED_PROMOTION_RULES_BY_REGISTRY = {
    "page_class": SUPPORTED_PAGE_CLASS_PROMOTION_RULES,
    "system_mechanism": SUPPORTED_SYSTEM_MECHANISM_PROMOTION_RULES,
}
POLICY_RUNTIME_REQUIRED_PATHS = (
    (("page_shape", "special_page_required_sections"), dict),
    (("page_shape", "source_required_sections"), list),
    (("page_shape", "concept_required_sections"), list),
    (("page_shape", "synthesis_required_sections"), list),
    (("page_shape", "lint_required_sections"), list),
    (("content_promotion_review", "research_anchor_min_inbound_links"), int),
    (("content_promotion_review", "research_anchor_required_sections"), list),
    (("starter_bundles", "planning_default", "path"), str),
    (("starter_bundles", "planning_default", "phase"), str),
    (("starter_bundles", "system_mechanism", "path"), str),
    (("starter_bundles", "system_mechanism", "phase"), str),
    (("runtime_defaults", "display_timezone", "label"), str),
    (("runtime_defaults", "display_timezone", "utc_offset"), str),
    (("release_packaging", "archive_root_name"), str),
    (("release_packaging", "zip_normalization", "timestamp_utc"), str),
    (("release_packaging", "zip_normalization", "file_mode_octal"), str),
    (("strict_warning_budget", "default_profile"), str),
    (("strict_warning_budget", "profiles"), dict),
    (("behavior_delta", "required_for_system_mechanism"), bool),
    (("behavior_delta", "required_for_auto_improve"), bool),
    (("behavior_delta", "required_for_equal_score_promotion"), bool),
    (("equal_score_promotion", "nonempty_line_growth_budget_per_added_test_case"), int),
    (("auto_improve_policy", "artifact_class"), str),
    (("auto_improve_policy", "session_reports_dir"), str),
    (("auto_improve_policy", "defaults", "executor_timeout_seconds"), int),
    (("auto_improve_policy", "defaults", "wrapper_command_timeout_seconds"), int),
)
UTC_OFFSET_RE = re.compile(r"^[+-](?:0\d|1\d|2[0-3]):[0-5]\d$")
FILE_MODE_OCTAL_RE = re.compile(r"^[0-7]{3,4}$")
ARCHIVE_ROOT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class _SubagentRegistryContext:
    score_band_names: list[str]
    score_band_name_set: set[str]
    ladder_rungs: set[int]
    role_names: set[str]
    pressure_dimensions: set[str]


@dataclass(frozen=True)
class PolicyInvariantRule:
    rule_id: str
    summary: str
    evaluate: Callable[[dict], object]


def _policy_value(policy: dict, path: tuple[str, ...]) -> Any:
    value: Any = policy
    walked: list[str] = []
    for key in path:
        walked.append(key)
        if not isinstance(value, dict) or key not in value:
            joined = ".".join(walked)
            raise ValueError(f"missing required policy path: {joined}")
        value = value[key]
    return value


def _registry_keys(registry: dict, path: str) -> list[str]:
    if not isinstance(registry, dict) or not registry:
        raise ValueError(f"{path} must be a non-empty registry")
    ordered: list[str] = []
    seen: set[str] = set()
    for key in registry:
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{path} contains an invalid registry key")
        if key in seen:
            raise ValueError(f"{path} must not contain duplicate keys: {key}")
        seen.add(key)
        ordered.append(key)
    return ordered


def _string_registry(values: list[str], path: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{path} must be a non-empty list")
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path} contains an invalid registry value")
        if value in seen:
            raise ValueError(f"{path} must not contain duplicate values: {value}")
        seen.add(value)
        ordered.append(value)
    return ordered


def _require_registry_subset(
    values: list[str],
    allowed: set[str],
    *,
    path: str,
    registry_path: str,
) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"{path} references values outside {registry_path}: {unknown}")


def _require_registry_contains(
    values: list[str],
    required: set[str],
    *,
    path: str,
) -> None:
    missing = sorted(required - set(values))
    if missing:
        raise ValueError(f"unsupported {path}: missing required values {missing}")


def _require_registry_exact(
    values: list[str],
    expected: set[str],
    *,
    path: str,
) -> None:
    actual = set(values)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(
            f"unsupported {path}: expected exactly {sorted(expected)}; missing={missing} extra={extra}"
        )


def _validate_promotion_rule_metadata_registry(
    promotion_policy: dict,
    registry_name: str,
    supported_rules: set[str],
) -> None:
    rule_ids = _string_registry(
        promotion_policy["rule_registry"][registry_name],
        f"promotion_policy.rule_registry.{registry_name}",
    )
    _require_registry_exact(
        rule_ids,
        supported_rules,
        path=f"promotion_policy.rule_registry.{registry_name}",
    )
    metadata = promotion_policy["rule_metadata"][registry_name]
    metadata_ids = _registry_keys(
        metadata,
        f"promotion_policy.rule_metadata.{registry_name}",
    )
    missing = sorted(set(rule_ids) - set(metadata_ids))
    extra = sorted(set(metadata_ids) - set(rule_ids))
    if missing or extra:
        raise ValueError(
            f"promotion_policy.rule_metadata.{registry_name} must match "
            f"promotion_policy.rule_registry.{registry_name}; missing={missing} extra={extra}"
        )

    for rule_id, rule_metadata in metadata.items():
        reducer = str(rule_metadata["reducer"])
        if reducer not in SUPPORTED_PROMOTION_RULE_REDUCERS:
            raise ValueError(
                "unsupported promotion rule reducer: "
                f"promotion_policy.rule_metadata.{registry_name}.{rule_id}.reducer={reducer}"
            )
        severity = str(rule_metadata["severity"])
        if severity not in SUPPORTED_PROMOTION_RULE_SEVERITIES:
            raise ValueError(
                "unsupported promotion rule severity: "
                f"promotion_policy.rule_metadata.{registry_name}.{rule_id}.severity={severity}"
            )
        dependencies = (
            _string_registry(
                rule_metadata["artifact_dependencies"],
                (
                    f"promotion_policy.rule_metadata.{registry_name}."
                    f"{rule_id}.artifact_dependencies"
                ),
            )
            if rule_metadata["artifact_dependencies"]
            else []
        )
        _require_registry_subset(
            dependencies,
            SUPPORTED_PROMOTION_RULE_ARTIFACT_DEPENDENCIES,
            path=(
                f"promotion_policy.rule_metadata.{registry_name}."
                f"{rule_id}.artifact_dependencies"
            ),
            registry_path="supported promotion rule artifact dependencies",
        )


def _validate_promotion_rule_metadata(policy: dict) -> None:
    promotion_policy = policy["promotion_policy"]
    for registry_name, supported_rules in SUPPORTED_PROMOTION_RULES_BY_REGISTRY.items():
        _validate_promotion_rule_metadata_registry(
            promotion_policy,
            registry_name,
            supported_rules,
        )


def display_timezone_from_policy(policy: dict) -> dt.timezone:
    config = _policy_value(policy, ("runtime_defaults", "display_timezone"))
    label = str(config["label"]).strip()
    utc_offset = str(config["utc_offset"]).strip()
    if not label:
        raise ValueError("runtime_defaults.display_timezone.label must not be empty")
    if not UTC_OFFSET_RE.fullmatch(utc_offset):
        raise ValueError(
            "unsupported runtime_defaults.display_timezone.utc_offset: "
            f"{utc_offset}"
        )
    sign = 1 if utc_offset[0] == "+" else -1
    hours = int(utc_offset[1:3])
    minutes = int(utc_offset[4:6])
    offset = sign * dt.timedelta(hours=hours, minutes=minutes)
    return dt.timezone(offset, name=label)


def zip_normalization_from_policy(policy: dict) -> dict[str, Any]:
    config = _policy_value(policy, ("release_packaging", "zip_normalization"))
    timestamp_text = str(config["timestamp_utc"]).strip()
    try:
        timestamp = dt.datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "unsupported release_packaging.zip_normalization.timestamp_utc: "
            f"{timestamp_text}"
        ) from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != dt.timedelta(0):
        raise ValueError(
            "release_packaging.zip_normalization.timestamp_utc must be an explicit UTC timestamp"
        )
    if timestamp.year < 1980:
        raise ValueError(
            "release_packaging.zip_normalization.timestamp_utc must be >= 1980-01-01T00:00:00Z"
        )

    file_mode_text = str(config["file_mode_octal"]).strip()
    if not FILE_MODE_OCTAL_RE.fullmatch(file_mode_text):
        raise ValueError(
            "unsupported release_packaging.zip_normalization.file_mode_octal: "
            f"{file_mode_text}"
        )

    return {
        "timestamp_utc": timestamp,
        "file_mode": int(file_mode_text, 8),
    }


def release_archive_root_name_from_policy(policy: dict) -> str:
    release_packaging = _policy_value(policy, ("release_packaging",))
    archive_root_name = str(release_packaging.get("archive_root_name", "LLMwiki")).strip()
    if not ARCHIVE_ROOT_NAME_RE.fullmatch(archive_root_name):
        raise ValueError(
            "unsupported release_packaging.archive_root_name: "
            f"{archive_root_name}"
        )
    return archive_root_name


def workspace_preparation_mode_from_policy(policy: dict) -> str:
    config = policy["auto_improve_policy"].get("workspace_preparation", {})
    if not isinstance(config, dict):
        raise ValueError("auto_improve_policy.workspace_preparation must be an object")
    mode = str(config.get("mode", "full_copy")).strip()
    if mode not in SUPPORTED_WORKSPACE_PREPARATION_MODES:
        raise ValueError(
            "unsupported auto_improve_policy.workspace_preparation.mode: "
            f"{mode}"
        )
    return mode


def _normalize_declared_dependency_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "auto_improve_policy.workspace_preparation.declared_dependencies entries must be strings"
        )
    raw = value.strip().replace("\\", "/").rstrip("/")
    normalized = normalize_repo_path_text(raw)
    if (
        normalized is None
        or normalized in {".", ".."}
        or normalized.startswith("../")
        or normalized.startswith("/")
    ):
        raise ValueError(
            "invalid auto_improve_policy.workspace_preparation.declared_dependencies entry: "
            f"{value}"
        )
    return normalized


def workspace_preparation_declared_dependencies_from_policy(policy: dict) -> list[str]:
    config = policy["auto_improve_policy"].get("workspace_preparation", {})
    if not isinstance(config, dict):
        raise ValueError("auto_improve_policy.workspace_preparation must be an object")
    dependencies = config.get("declared_dependencies", [])
    if not isinstance(dependencies, list):
        raise ValueError(
            "auto_improve_policy.workspace_preparation.declared_dependencies must be an array"
        )

    normalized_dependencies: list[str] = []
    seen: set[str] = set()
    for dependency in dependencies:
        normalized = _normalize_declared_dependency_path(dependency)
        if normalized in seen:
            continue
        seen.add(normalized)
        normalized_dependencies.append(normalized)
    return normalized_dependencies


def _validate_required_runtime_paths(policy: dict) -> None:
    for path, expected_type in POLICY_RUNTIME_REQUIRED_PATHS:
        value = _policy_value(policy, path)
        if not isinstance(value, expected_type):
            joined = ".".join(path)
            raise ValueError(
                f"invalid policy type at {joined}: expected {expected_type.__name__}"
            )


def _validate_complexity_policy(policy: dict) -> None:
    complexity_scoring = policy["complexity_policy"]["scoring"]
    if complexity_scoring["formula"] != SUPPORTED_COMPLEXITY_FORMULA:
        raise ValueError(
            "unsupported complexity_policy.scoring.formula: "
            f"{complexity_scoring['formula']}"
        )
    if complexity_scoring["output_range"] != SUPPORTED_COMPLEXITY_OUTPUT_RANGE:
        raise ValueError(
            "unsupported complexity_policy.scoring.output_range: "
            f"{complexity_scoring['output_range']}"
        )
    complexity_dimensions = set(
        _registry_keys(
            policy["complexity_policy"]["dimensions"],
            "complexity_policy.dimensions",
        )
    )
    if complexity_dimensions != SUPPORTED_SUBAGENT_PRESSURE_DIMENSIONS:
        raise ValueError(
            "unsupported complexity_policy.dimensions: "
            f"{sorted(complexity_dimensions)}"
        )


def _validate_subagent_safety_policy(policy: dict) -> None:
    subagent_policy = policy["subagent_routing_policy"]
    ladder = subagent_policy["ladder"]
    expected_rungs = list(SUPPORTED_SUBAGENT_LADDER.keys())
    actual_rungs = [entry["rung"] for entry in ladder]
    if actual_rungs != expected_rungs:
        raise ValueError(
            "unsupported subagent_routing_policy.ladder rung ordering: "
            f"{actual_rungs}"
        )
    for entry in ladder:
        expected_model, expected_effort = SUPPORTED_SUBAGENT_LADDER[entry["rung"]]
        if entry["model"] != expected_model or entry["reasoning_effort"] != expected_effort:
            raise ValueError(
                "unsupported subagent_routing_policy.ladder entry: "
                f"rung={entry['rung']} model={entry['model']} effort={entry['reasoning_effort']}"
            )

    for role, role_policy in subagent_policy["roles"].items():
        sandbox_mode = role_policy["sandbox_mode"]
        if sandbox_mode not in SUPPORTED_SUBAGENT_SANDBOX_MODES:
            raise ValueError(
                "unsupported subagent_routing_policy.roles sandbox_mode: "
                f"{role} -> {sandbox_mode}"
            )


def _validate_auto_improve_safety_policy(policy: dict) -> None:
    auto_improve_policy = policy["auto_improve_policy"]
    if (
        auto_improve_policy["defaults"]["wrapper_command_timeout_seconds"]
        < auto_improve_policy["defaults"]["executor_timeout_seconds"]
    ):
        raise ValueError(
            "auto_improve_policy.defaults.wrapper_command_timeout_seconds must be "
            "greater than or equal to executor_timeout_seconds"
        )
    normalized_apply_roots = normalized_allowed_apply_roots(
        auto_improve_policy["allowed_apply_roots"]
    )
    if normalized_apply_roots != auto_improve_policy["allowed_apply_roots"]:
        raise ValueError(
            "auto_improve_policy.allowed_apply_roots must be unique normalized "
            "repo-relative paths and preserve trailing '/' only for directory prefixes"
        )
    if auto_improve_policy["artifact_class"] != "system_mechanism":
        raise ValueError(
            "auto_improve_policy.artifact_class must stay fixed at system_mechanism"
        )
    workspace_preparation_mode_from_policy(policy)
    workspace_preparation_declared_dependencies_from_policy(policy)


def _validate_strict_warning_budget_policy(policy: dict) -> None:
    warning_budget_policy = policy["strict_warning_budget"]
    default_profile = warning_budget_policy["default_profile"]
    profiles = warning_budget_policy["profiles"]
    if default_profile not in profiles:
        raise ValueError(
            "strict_warning_budget.default_profile must reference a configured profile"
        )
    lint_warning_types = set(policy["lint_thresholds"])
    lint_warning_types.discard("python_function_review")
    for profile_name, profile in profiles.items():
        sources = _registry_keys(
            profile["sources"],
            f"strict_warning_budget.profiles.{profile_name}.sources",
        )
        _require_registry_subset(
            sources,
            SUPPORTED_WARNING_BUDGET_SOURCES,
            path=f"strict_warning_budget.profiles.{profile_name}.sources",
            registry_path="supported warning budget sources",
        )
        for source_name, source_policy in profile["sources"].items():
            warning_types = _registry_keys(
                source_policy["warning_type_budgets"],
                (
                    "strict_warning_budget.profiles."
                    f"{profile_name}.sources.{source_name}.warning_type_budgets"
                ),
            )
            _require_registry_subset(
                warning_types,
                lint_warning_types,
                path=(
                    "strict_warning_budget.profiles."
                    f"{profile_name}.sources.{source_name}.warning_type_budgets"
                ),
                registry_path="lint_thresholds",
            )


POLICY_SAFETY_INVARIANT_RULES: tuple[PolicyInvariantRule, ...] = (
    PolicyInvariantRule("required_runtime_paths", "Required runtime policy paths have expected types.", _validate_required_runtime_paths),
    PolicyInvariantRule("complexity_policy_contract", "Complexity scoring and dimensions stay supported.", _validate_complexity_policy),
    PolicyInvariantRule("subagent_safety_contract", "Subagent ladder and sandboxes stay supported.", _validate_subagent_safety_policy),
    PolicyInvariantRule("auto_improve_safety_contract", "Auto-improve timeout, roots, class, and workspace policy stay safe.", _validate_auto_improve_safety_policy),
    PolicyInvariantRule("strict_warning_budget_contract", "Strict warning-budget profiles reference supported sources and warning types.", _validate_strict_warning_budget_policy),
    PolicyInvariantRule(
        "runtime_defaults_contract",
        "Runtime timezone, archive root, and zip normalization stay deterministic.",
        lambda policy: (
            display_timezone_from_policy(policy),
            release_archive_root_name_from_policy(policy),
            zip_normalization_from_policy(policy),
        ),
    ),
)


def validate_policy_safety_invariants(policy: dict) -> None:
    for rule in POLICY_SAFETY_INVARIANT_RULES:
        rule.evaluate(policy)


def validate_policy_registry_references(policy: dict) -> None:
    context = _build_subagent_registry_context(policy)
    _validate_subagent_role_registry(policy, context)
    _validate_auto_improve_registry_references(policy, context)
    _validate_promotion_registry_references(policy)


def _build_subagent_registry_context(policy: dict) -> _SubagentRegistryContext:
    subagent_policy = policy["subagent_routing_policy"]
    score_bands = subagent_policy["score_bands"]
    score_band_names = list(
        _registry_keys(
            score_bands,
            "subagent_routing_policy.score_bands",
        )
    )
    score_band_name_set = set(score_band_names)
    band_max_scores = [score_bands[name]["max_score"] for name in score_band_names]
    if band_max_scores != sorted(band_max_scores):
        raise ValueError(
            "subagent_routing_policy.score_bands must have ascending max_score values"
        )
    if band_max_scores[-1] != 100:
        raise ValueError(
            "subagent_routing_policy.score_bands final max_score must be 100"
        )

    ladder_rungs = {entry["rung"] for entry in subagent_policy["ladder"]}
    role_names = set(_registry_keys(subagent_policy["roles"], "subagent_routing_policy.roles"))
    pressure_dimensions = set(
        _registry_keys(
            policy["complexity_policy"]["dimensions"],
            "complexity_policy.dimensions",
        )
    )
    _string_registry(
        policy["complexity_policy"]["risk_overrides"]["high_risk_flags"],
        "complexity_policy.risk_overrides.high_risk_flags",
    )
    return _SubagentRegistryContext(
        score_band_names=score_band_names,
        score_band_name_set=score_band_name_set,
        ladder_rungs=ladder_rungs,
        role_names=role_names,
        pressure_dimensions=pressure_dimensions,
    )


def _validate_subagent_role_registry(
    policy: dict,
    context: _SubagentRegistryContext,
) -> None:
    subagent_policy = policy["subagent_routing_policy"]
    for role, role_policy in subagent_policy["roles"].items():
        allowed_rungs = role_policy["allowed_rungs"]
        if not allowed_rungs:
            raise ValueError(
                f"subagent_routing_policy.roles.{role}.allowed_rungs must not be empty"
            )
        if sorted(allowed_rungs) != allowed_rungs:
            raise ValueError(
                f"subagent_routing_policy.roles.{role}.allowed_rungs must be sorted"
            )
        if len(set(allowed_rungs)) != len(allowed_rungs):
            raise ValueError(
                f"subagent_routing_policy.roles.{role}.allowed_rungs must be unique"
            )
        if not set(allowed_rungs).issubset(context.ladder_rungs):
            raise ValueError(
                f"subagent_routing_policy.roles.{role}.allowed_rungs must stay within the approved ladder"
            )

        default_rung = role_policy["default_rung"]
        if default_rung not in allowed_rungs:
            raise ValueError(
                f"subagent_routing_policy.roles.{role}.default_rung must be one of allowed_rungs"
            )

        score_band_rungs = role_policy["score_band_rungs"]
        role_score_bands = set(
            _registry_keys(
                score_band_rungs,
                f"subagent_routing_policy.roles.{role}.score_band_rungs",
            )
        )
        if role_score_bands != context.score_band_name_set:
            missing = sorted(context.score_band_name_set - role_score_bands)
            extra = sorted(role_score_bands - context.score_band_name_set)
            raise ValueError(
                f"subagent_routing_policy.roles.{role}.score_band_rungs must match "
                f"subagent_routing_policy.score_bands; missing={missing} extra={extra}"
            )
        for band_name in context.score_band_names:
            rung = score_band_rungs[band_name]
            if rung not in allowed_rungs:
                raise ValueError(
                    f"subagent_routing_policy.roles.{role}.score_band_rungs.{band_name} must be one of allowed_rungs"
                )

        for dimension, override in role_policy["pressure_overrides"].items():
            if dimension not in context.pressure_dimensions:
                raise ValueError(
                    "unsupported subagent_routing_policy pressure override dimension: "
                    f"{role} -> {dimension}"
                )
            if override["min_rung"] not in allowed_rungs:
                raise ValueError(
                    f"subagent_routing_policy.roles.{role}.pressure_overrides.{dimension}.min_rung must be one of allowed_rungs"
                )


def _validate_auto_improve_registry_references(
    policy: dict,
    context: _SubagentRegistryContext,
) -> None:
    auto_improve_policy = policy["auto_improve_policy"]
    allowed_executors = _string_registry(
        auto_improve_policy["allowed_executors"],
        "auto_improve_policy.allowed_executors",
    )
    if auto_improve_policy["defaults"]["executor"] not in allowed_executors:
        raise ValueError(
            "auto_improve_policy.defaults.executor must be one of allowed_executors"
        )

    reviewer_score_bands = _string_registry(
        auto_improve_policy["scope_resolution"]["reviewer_score_bands"],
        "auto_improve_policy.scope_resolution.reviewer_score_bands",
    )
    _require_registry_subset(
        reviewer_score_bands,
        context.score_band_name_set,
        path="auto_improve_policy.scope_resolution.reviewer_score_bands",
        registry_path="subagent_routing_policy.score_bands",
    )

    always_roles = _string_registry(
        auto_improve_policy["dispatch"]["always_roles"],
        "auto_improve_policy.dispatch.always_roles",
    )
    _require_registry_subset(
        always_roles,
        context.role_names,
        path="auto_improve_policy.dispatch.always_roles",
        registry_path="subagent_routing_policy.roles",
    )

    auditor_role_map = auto_improve_policy["scope_resolution"]["auditor_role_map"]
    for mapped_roles in auditor_role_map.values():
        _require_registry_subset(
            mapped_roles,
            context.role_names,
            path="auto_improve_policy.scope_resolution.auditor_role_map",
            registry_path="subagent_routing_policy.roles",
        )


def _validate_promotion_registry_references(policy: dict) -> None:
    decision_values = _string_registry(
        policy["promotion_policy"]["decision_values"],
        "promotion_policy.decision_values",
    )
    _require_registry_exact(
        decision_values,
        SUPPORTED_PROMOTION_DECISION_VALUES,
        path="promotion_policy.decision_values",
    )

    log_status_values = _string_registry(
        policy["promotion_policy"]["log_defaults"]["status_values"],
        "promotion_policy.log_defaults.status_values",
    )
    _require_registry_contains(
        log_status_values,
        SUPPORTED_LOG_STATUS_VALUES,
        path="promotion_policy.log_defaults.status_values",
    )
    _validate_promotion_rule_metadata(policy)
