#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        GITHUB_GOVERNANCE_LIVE_DRIFT_SCHEMA_PATH,
    )
    from ops.scripts.yaml_runtime import parse_simple_yaml
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        GITHUB_GOVERNANCE_LIVE_DRIFT_SCHEMA_PATH,
    )
    from ops.scripts.yaml_runtime import parse_simple_yaml


DEFAULT_OUT = "ops/reports/github-governance-live-drift.json"
DEFAULT_LIVE_INPUT = "tmp/github-governance-live-input.json"
GOVERNANCE_CONTRACT_PATH = ".github/release-governance.yml"
ARTIFACT_KIND = "github_governance_live_drift_verification"
PRODUCER = "ops.scripts.github_governance_live_drift"
SOURCE_COMMAND = (
    "python -m ops.scripts.release.github_governance_live_drift --vault . "
    "--live-input tmp/github-governance-live-input.json "
    "--out ops/reports/github-governance-live-drift.json"
)
BRANCH_PROTECTION_FIELDS = (
    "require_pull_request",
    "require_review_before_merge",
    "require_required_status_checks",
    "require_branches_up_to_date",
    "require_linear_history",
    "allow_force_pushes",
    "allow_deletions",
    "main_direct_push",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _normalized_string(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalized_strings(values: Iterable[Any]) -> list[str]:
    normalized: dict[str, None] = {}
    for value in values:
        text = _normalized_string(value)
        if text:
            normalized[text] = None
    return sorted(normalized)


def _string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        for key in ("context", "name", "check", "required_check"):
            text = _normalized_string(value.get(key))
            if text:
                return [text]
        return []
    if isinstance(value, list):
        strings: list[str] = []
        for item in value:
            strings.extend(_string_items(item))
        return strings
    return []


def _ci_matrix_check_name(tier: str, version: str) -> str:
    return f"{tier} / py{version.removeprefix('py')}"


def _ci_matrix_excluded_checks(matrix: Mapping[str, Any]) -> set[str]:
    excluded: set[str] = set()
    for item in _as_list(matrix.get("exclude")):
        item_mapping = _as_mapping(item)
        tier = _normalized_string(item_mapping.get("tier"))
        version = _normalized_string(
            item_mapping.get("python-version", item_mapping.get("python_version"))
        )
        if tier and version:
            excluded.add(_ci_matrix_check_name(tier, version))
    return excluded


def _expected_required_checks(governance: Mapping[str, Any]) -> list[str]:
    required = _as_mapping(governance.get("required_status_checks"))
    singleton_checks = _string_items(required.get("singleton_checks"))
    matrix = _as_mapping(required.get("ci_matrix"))
    versions = _string_items(matrix.get("python_versions"))
    tiers = _string_items(matrix.get("tiers"))
    excluded_checks = _ci_matrix_excluded_checks(matrix)
    matrix_checks: list[str] = []
    for version in versions:
        for tier in tiers:
            check_name = _ci_matrix_check_name(tier, version)
            if check_name not in excluded_checks:
                matrix_checks.append(check_name)
    return _normalized_strings([*singleton_checks, *matrix_checks])


def _expected_protected_branches(governance: Mapping[str, Any]) -> list[str]:
    publication_target = _as_mapping(governance.get("publication_target"))
    return _normalized_strings(_string_items(publication_target.get("protected_branches")))


def _expected_branch_contract(governance: Mapping[str, Any]) -> dict[str, Any]:
    protection = _as_mapping(governance.get("branch_protection"))
    return {
        field: protection[field]
        for field in BRANCH_PROTECTION_FIELDS
        if field in protection
    }


def _read_live_input(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, ["live_input_missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, ["live_input_invalid_json"]
    if not isinstance(payload, dict):
        return {}, ["live_input_not_object"]
    return payload, []


def _observed_required_checks(live: Mapping[str, Any]) -> list[str]:
    direct = _string_items(live.get("required_status_checks"))
    if direct:
        return _normalized_strings(direct)
    checks = _string_items(live.get("required_checks"))
    if checks:
        return _normalized_strings(checks)
    required_status_checks = _as_mapping(live.get("required_status_checks"))
    for key in ("contexts", "checks", "required_checks"):
        checks = _string_items(required_status_checks.get(key))
        if checks:
            return _normalized_strings(checks)
    branch_protection = _as_mapping(live.get("branch_protection"))
    nested_required = _as_mapping(branch_protection.get("required_status_checks"))
    for key in ("contexts", "checks", "required_checks"):
        checks = _string_items(nested_required.get(key))
        if checks:
            return _normalized_strings(checks)
    return []


def _branch_name_from_item(item: Mapping[str, Any]) -> str:
    for key in ("name", "branch", "pattern"):
        text = _normalized_string(item.get(key))
        if text:
            return text
    return ""


def _branch_protection_from_item(item: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("protection", "branch_protection", "rules"):
        nested = _as_mapping(item.get(key))
        if nested:
            return _filtered_branch_protection(nested)
    return _filtered_branch_protection(item)


def _filtered_branch_protection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        field: value[field]
        for field in BRANCH_PROTECTION_FIELDS
        if field in value
    }


def _observed_branch_protection(live: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    branch_protection = _as_mapping(live.get("branch_protection"))
    branch_specific = {
        _normalized_string(branch): _branch_protection_from_item(_as_mapping(value))
        for branch, value in branch_protection.items()
        if _normalized_string(branch) and isinstance(value, Mapping)
    }
    if branch_specific:
        observed.update(branch_specific)
    elif branch_protection:
        branches = _normalized_strings(_string_items(live.get("protected_branches"))) or [
            "main"
        ]
        for branch in branches:
            observed[branch] = _filtered_branch_protection(branch_protection)

    branches_payload = live.get("branches")
    branch_items: list[Any]
    if isinstance(branches_payload, Mapping):
        branch_items = [
            {"name": name, **_as_mapping(value)}
            for name, value in branches_payload.items()
        ]
    else:
        branch_items = _as_list(branches_payload)
    for item in branch_items:
        item_mapping = _as_mapping(item)
        name = _branch_name_from_item(item_mapping)
        if name:
            observed[name] = _branch_protection_from_item(item_mapping)
    return observed


def _observed_protected_branches(live: Mapping[str, Any]) -> list[str]:
    direct = _string_items(live.get("protected_branches"))
    if direct:
        return _normalized_strings(direct)
    observed = _observed_branch_protection(live)
    if observed:
        return sorted(observed)
    return []


def _branch_drift(
    *,
    branch: str,
    expected: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    missing_fields = [
        field for field in expected if field not in observed or observed.get(field) is None
    ]
    mismatched_fields = [
        field
        for field in expected
        if field not in missing_fields and observed.get(field) != expected.get(field)
    ]
    status = "pass" if not missing_fields and not mismatched_fields else "fail"
    return {
        "branch": branch,
        "status": status,
        "expected": {field: expected[field] for field in expected},
        "observed": {field: observed[field] for field in expected if field in observed},
        "missing_fields": missing_fields,
        "mismatched_fields": mismatched_fields,
    }


def _load_governance_contract(vault: Path) -> tuple[dict[str, Any], list[str]]:
    path = vault / GOVERNANCE_CONTRACT_PATH
    if not path.is_file():
        return {}, ["governance_contract_missing"]
    try:
        return parse_simple_yaml(path.read_text(encoding="utf-8")), []
    except ValueError:
        return {}, ["governance_contract_invalid_yaml"]


def build_report(
    vault: Path,
    *,
    live_input: str | Path | None = None,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    live_input_path = Path(live_input or DEFAULT_LIVE_INPUT)
    resolved_live_input = live_input_path if live_input_path.is_absolute() else vault / live_input_path

    governance, governance_reasons = _load_governance_contract(vault)
    live_payload, live_reasons = _read_live_input(resolved_live_input)
    unavailable_reasons = [*governance_reasons, *live_reasons]

    expected_checks = _expected_required_checks(governance)
    observed_checks = _observed_required_checks(live_payload)
    missing_checks = sorted(set(expected_checks) - set(observed_checks))
    unexpected_checks = sorted(set(observed_checks) - set(expected_checks))

    expected_branches = _expected_protected_branches(governance)
    observed_branches = _observed_protected_branches(live_payload)
    missing_branches = sorted(set(expected_branches) - set(observed_branches))
    branch_contract = _expected_branch_contract(governance)
    observed_protection = _observed_branch_protection(live_payload)
    branch_protection = [
        _branch_drift(
            branch=branch,
            expected=branch_contract,
            observed=observed_protection.get(branch, {}),
        )
        for branch in expected_branches
    ]
    mismatched_branch_count = sum(
        1 for item in branch_protection if item["status"] != "pass"
    )

    if unavailable_reasons:
        status = "attention"
    elif missing_checks or missing_branches or mismatched_branch_count:
        status = "fail"
    else:
        status = "pass"

    live_input_available = resolved_live_input.is_file() and not live_reasons
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind=ARTIFACT_KIND,
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=GITHUB_GOVERNANCE_LIVE_DRIFT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/github_governance_live_drift.py",
                GOVERNANCE_CONTRACT_PATH,
                GITHUB_GOVERNANCE_LIVE_DRIFT_SCHEMA_PATH,
            ],
            file_inputs={
                "release_governance": GOVERNANCE_CONTRACT_PATH,
                "live_input": resolved_live_input,
            },
        ),
        "status": status,
        "expected_source": {
            "path": GOVERNANCE_CONTRACT_PATH,
            "sha256": _sha256_file(vault / GOVERNANCE_CONTRACT_PATH)
            if (vault / GOVERNANCE_CONTRACT_PATH).is_file()
            else "",
        },
        "live_input": {
            "path": report_path(vault, resolved_live_input),
            "sha256": _sha256_file(resolved_live_input)
            if live_input_available
            else "",
            "available": live_input_available,
        },
        "summary": {
            "expected_protected_branch_count": len(expected_branches),
            "observed_protected_branch_count": len(observed_branches),
            "missing_protected_branch_count": len(missing_branches),
            "expected_required_check_count": len(expected_checks),
            "observed_required_check_count": len(observed_checks),
            "missing_required_check_count": len(missing_checks),
            "unexpected_required_check_count": len(unexpected_checks),
            "mismatched_branch_protection_count": mismatched_branch_count,
            "unavailable_reason_count": len(unavailable_reasons),
        },
        "required_status_checks": {
            "status": "pass" if not missing_checks else "fail",
            "expected": expected_checks,
            "observed": observed_checks,
            "missing": missing_checks,
            "unexpected": unexpected_checks,
        },
        "protected_branches": {
            "status": "pass" if not missing_branches else "fail",
            "expected": expected_branches,
            "observed": observed_branches,
            "missing": missing_branches,
        },
        "branch_protection": branch_protection,
        "unavailable_reasons": unavailable_reasons,
        "redaction": {
            "raw_live_payload_retained": False,
            "live_input_digest_only": True,
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=GITHUB_GOVERNANCE_LIVE_DRIFT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="GitHub governance live drift report schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare sanitized live GitHub governance evidence with the release governance contract."
    )
    parser.add_argument("--vault", default=".", help="Repository or vault root.")
    parser.add_argument(
        "--live-input",
        default=DEFAULT_LIVE_INPUT,
        help="Operator-created sanitized JSON input with live governance state.",
    )
    parser.add_argument("--out", default=DEFAULT_OUT, help="Report output path.")
    parser.add_argument("--policy-path", default=None, help="Optional policy path.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        live_input=args.live_input,
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(destination)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
