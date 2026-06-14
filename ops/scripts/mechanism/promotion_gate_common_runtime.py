from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ops.scripts.output_runtime import resolve_vault_path
from ops.scripts.policy_runtime import report_path
from ops.scripts.promotion_decision_registry_runtime import (
    PromotionDecisionRegistryError,
    decision_outcome,
)
from ops.scripts.schema_constants_runtime import (
    BEHAVIOR_DELTA_SCHEMA_PATH,
    CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    EVAL_REPORT_SCHEMA_PATH,
    LINT_REPORT_SCHEMA_PATH,
    MECHANISM_ASSESSMENT_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
    RUN_LEDGER_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_or_raise

PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
LINT_REPORT_SCHEMA = LINT_REPORT_SCHEMA_PATH
EVAL_REPORT_SCHEMA = EVAL_REPORT_SCHEMA_PATH
MECHANISM_REPORT_SCHEMA = MECHANISM_ASSESSMENT_SCHEMA_PATH
RUN_LEDGER_SCHEMA = RUN_LEDGER_SCHEMA_PATH
CHANGED_FILES_MANIFEST_SCHEMA = CHANGED_FILES_MANIFEST_SCHEMA_PATH
BEHAVIOR_DELTA_SCHEMA = BEHAVIOR_DELTA_SCHEMA_PATH


class PromotionGateError(Exception):
    exit_code = 8


class PromotionGateUsageError(PromotionGateError):
    exit_code = 2


class PromotionGatePolicyError(PromotionGateError):
    exit_code = 3


class PromotionGateArtifactMissingError(PromotionGateError):
    exit_code = 4


class PromotionGateArtifactDecodeError(PromotionGateError):
    exit_code = 5


class PromotionGateArtifactSchemaError(PromotionGateError):
    exit_code = 6


class PromotionGateReportWriteError(PromotionGateError):
    exit_code = 7


class PromotionGateInternalError(PromotionGateError):
    exit_code = 8


def resolve_repo_path(vault: Path, raw_path: str) -> Path:
    return resolve_vault_path(vault, raw_path)


def repo_relative_path(vault: Path, raw_path: str) -> str:
    return report_path(vault, resolve_repo_path(vault, raw_path))


def normalize_reported_page(vault: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return report_path(vault, path)
    return path.as_posix()


def extract_policy_identity(report: dict) -> tuple[str | None, int | None]:
    policy = report.get("policy")
    if not isinstance(policy, dict):
        return None, None
    return policy.get("path"), policy.get("version")


def normalize_report_vault(vault: Path, raw_vault: str | None) -> str | None:
    if not raw_vault:
        return None
    return str(resolve_repo_path(vault, raw_vault))


def ledger_artifact_targets(run_ledger: dict) -> set[str]:
    targets: set[str] = set()
    for event in run_ledger.get("events", []):
        for artifact in event.get("artifacts", []):
            if isinstance(artifact, str) and artifact:
                targets.add(artifact)
    return targets


def validate_json_artifact(vault: Path, raw_path: str, schema_rel_path: str) -> tuple[dict, str]:
    path = resolve_repo_path(vault, raw_path)
    if not path.exists():
        raise PromotionGateArtifactMissingError(f"missing artifact: {report_path(vault, path)}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PromotionGateArtifactDecodeError(
            f"failed to decode JSON artifact {report_path(vault, path)}: {exc}"
        ) from exc
    except OSError as exc:
        raise PromotionGateArtifactDecodeError(
            f"failed to read JSON artifact {report_path(vault, path)}: {exc}"
        ) from exc

    try:
        schema = load_schema(vault / schema_rel_path)
        validate_or_raise(
            data,
            schema,
            context=f"schema validation failed for {report_path(vault, path)}",
        )
    except FileNotFoundError as exc:
        raise PromotionGateArtifactSchemaError(
            f"missing schema for artifact validation: {schema_rel_path}"
        ) from exc
    except ValueError as exc:
        raise PromotionGateArtifactSchemaError(str(exc)) from exc
    return data, report_path(vault, path)


def ensure_log_args_consistent(args: Any) -> None:
    if args.log_recorded and not args.log_entry_ref:
        raise PromotionGateUsageError("--log-recorded requires --log-entry-ref")
    if args.log_entry_ref and not args.log_recorded:
        raise PromotionGateUsageError("--log-entry-ref requires --log-recorded")


def build_signoff(policy: dict, artifact_class: str, args: Any) -> dict:
    default_signoff = policy["promotion_policy"]["signoff_defaults"][artifact_class]
    required = default_signoff == "required" or args.require_signoff
    status = args.signoff_status or ("pending" if required else "not_required")
    if required and status == "not_required":
        raise PromotionGateUsageError("required signoff cannot use status 'not_required'")
    return {
        "required": required,
        "status": status,
        "by": args.signoff_by or "",
        "ts": args.signoff_ts or "",
    }


def build_log(policy: dict, args: Any) -> dict:
    log_defaults = policy["promotion_policy"]["log_defaults"]
    required = policy["mutation_policy"]["require_log_entry"]
    if not required:
        status = "not_required"
    else:
        status = "recorded" if args.log_recorded and args.log_entry_ref else "pending"
    return {
        "required": required,
        "page": log_defaults["page"],
        "summary": args.log_summary,
        "status": status,
        "entry_ref": args.log_entry_ref or "",
    }


def build_history_status(*, status: str = "active", reason: str = "", by: str = "", ts: str = "") -> dict:
    return {
        "status": status,
        "reason": reason,
        "by": by,
        "ts": ts,
    }


def decision_to_outcome(decision: str) -> str:
    try:
        return decision_outcome(decision)
    except PromotionDecisionRegistryError:
        return ""


def decision_to_next_action(decision: str, signoff_required: bool, log_required: bool) -> str:
    outcome = decision_to_outcome(decision)
    if outcome == "promoted":
        if log_required:
            return "Append the matching entry to system/system-log.md if not yet recorded, then persist the report."
        return "Persist the report; no system/system-log.md append is required by current policy."
    if outcome == "hold":
        if signoff_required:
            if log_required:
                return "Collect required signoff, then rerun promotion_gate.py and append the log entry."
            return "Collect required signoff, then rerun promotion_gate.py."
        return "Address the remaining warning condition, then rerun promotion_gate.py."
    return "Do not promote this candidate; fix the failing checks or discard the change."


def page_target_matches(target_rel: str, spec: dict) -> bool:
    path = Path(target_rel)
    if len(path.parts) < 2:
        return False
    if path.parts[0] != spec["root"]:
        return False
    return any(path.stem.startswith(prefix) for prefix in spec["prefixes"])


def mechanism_target_matches(target_rel: str, spec: dict) -> bool:
    for allowed in spec["allowed_targets"]:
        if allowed.endswith("/"):
            if target_rel.startswith(allowed):
                return True
            continue
        if target_rel == allowed:
            return True
    return False


def page_record_map(vault: Path, eval_report: dict) -> dict[str, dict]:
    return {
        normalize_reported_page(vault, page["page"]): page
        for page in eval_report["pages"]
    }


def lint_input_summary(report: dict) -> dict:
    stats = report.get("stats", {})
    return {
        "status": report["status"],
        "error_count": stats.get("error_count", len(report.get("errors", []))),
        "warning_count": stats.get("warning_count", len(report.get("warnings", []))),
        "review_candidate_count": stats.get(
            "review_candidate_count",
            len(report.get("review_candidates", [])),
        ),
    }


def eval_input_summary(report: dict) -> dict:
    return {
        "status": report["status"],
        "total_score": report["total_score"],
        "max_score": report["max_score"],
    }


def lint_status_rank(status: str) -> int:
    ranks = {
        "pass": 0,
        "warn": 1,
        "fail": 2,
    }
    return ranks[status]


def lint_comparison_tuple(report: dict) -> tuple[int, int, int, int]:
    summary = lint_input_summary(report)
    return (
        lint_status_rank(summary["status"]),
        summary["error_count"],
        summary["warning_count"],
        summary["review_candidate_count"],
    )


def structural_metrics(report: dict) -> dict:
    return report["structural_metrics"]


def structural_metric_tuple(report: dict) -> tuple[int, int, int, int]:
    metrics = structural_metrics(report)
    return (
        metrics["nonempty_line_count_total"],
        metrics["python_function_count"],
        metrics["python_branch_node_count"],
        metrics["markdown_heading_count"],
    )


def total_structural_metrics(report: dict) -> dict:
    return report.get("total_structural_metrics", report["structural_metrics"])


def total_structural_metric_tuple(report: dict) -> tuple[int, int, int, int]:
    metrics = total_structural_metrics(report)
    return (
        metrics["nonempty_line_count_total"],
        metrics["python_function_count"],
        metrics["python_branch_node_count"],
        metrics["markdown_heading_count"],
    )


def configured_secondary_axes(policy: dict) -> list[str]:
    supported = {"lint", "complexity", "tests"}
    configured = policy["equal_score_promotion"]["secondary_axes"]
    ordered: list[str] = []
    seen: set[str] = set()
    for axis in configured:
        if axis not in supported:
            raise PromotionGatePolicyError(f"unsupported equal-score secondary axis: {axis}")
        if axis in seen:
            continue
        seen.add(axis)
        ordered.append(axis)
    return ordered


def report_target_list(report: dict, field: str) -> list[str]:
    values = report.get(field, [])
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]
