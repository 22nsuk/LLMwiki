#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.yaml_runtime import parse_simple_yaml
    from ops.scripts.test.test_lane_registry_runtime import (
        compatibility_names,
        load_registry,
    )
else:
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.yaml_runtime import parse_simple_yaml
    from ops.scripts.test.test_lane_registry_runtime import (
        compatibility_names,
        load_registry,
    )

GOVERNANCE_PATH = Path(".github/release-governance.yml")
SUPPORTED_PYTHON_VERSIONS = ("3.12", "3.13", "3.14")
PYTHON_VERSION_SOURCE = (
    "constant in "
    "ops/scripts/test/generate_release_governance_from_lane_registry.py::SUPPORTED_PYTHON_VERSIONS"
)
TIER_SOURCE = "ops/test-lane-registry.json compatibility_layers(kind=ci_tier)"
BEGIN_MARKER = (
    "# BEGIN MANAGED ci_matrix: "
    "ops/scripts/test/generate_release_governance_from_lane_registry.py"
)
END_MARKER = "# END MANAGED ci_matrix"
MANAGED_BLOCK_INDENT = "  "


def expected_ci_matrix(registry: dict[str, Any]) -> dict[str, Any]:
    tiers = list(compatibility_names(registry, "ci_tier"))
    exclude = [
        {"tier": tier, "python-version": version}
        for tier in tiers
        if tier != "fast"
        for version in SUPPORTED_PYTHON_VERSIONS
        if version != "3.12"
    ]
    return {
        "python_versions": list(SUPPORTED_PYTHON_VERSIONS),
        "tiers": tiers,
        "exclude": exclude,
    }


def governance_ci_matrix(vault: Path) -> dict[str, Any]:
    payload = parse_simple_yaml((vault / GOVERNANCE_PATH).read_text(encoding="utf-8"))
    required = payload.get("required_status_checks", {})
    if not isinstance(required, dict):
        return {}
    ci_matrix = required.get("ci_matrix", {})
    return ci_matrix if isinstance(ci_matrix, dict) else {}


def validate_alignment(vault: Path) -> dict[str, Any]:
    registry = load_registry(vault)
    expected = expected_ci_matrix(registry)
    actual = governance_ci_matrix(vault)
    mismatches: list[str] = []
    for key in ("python_versions", "tiers", "exclude"):
        if actual.get(key) != expected.get(key):
            mismatches.append(key)
    text_report = validate_managed_block_text(vault, registry)
    return {
        "status": "pass" if not mismatches and text_report["status"] == "pass" else "fail",
        "expected": expected,
        "actual": actual,
        "mismatched_fields": mismatches,
        "registry_tier_count": len(expected["tiers"]),
        "python_versions_source": PYTHON_VERSION_SOURCE,
        "tiers_source": TIER_SOURCE,
        "managed_block": text_report,
    }


def _indent_lines(lines: list[str], indent: str) -> list[str]:
    return [f"{indent}{line}" if line else line for line in lines]


def render_ci_matrix_block(registry: dict[str, Any], *, indent: str = MANAGED_BLOCK_INDENT) -> str:
    matrix = expected_ci_matrix(registry)
    lines = [
        BEGIN_MARKER,
        f"# Tier source: {TIER_SOURCE}",
        f"# Python versions source: {PYTHON_VERSION_SOURCE}",
        "# Regenerate/check with: make release-governance-sync",
        "ci_matrix:",
    ]
    lines.append("  python_versions:")
    for version in matrix["python_versions"]:
        lines.append(f'    - "{version}"')
    lines.append("  tiers:")
    for tier in matrix["tiers"]:
        lines.append(f"    - {tier}")
    lines.append("  exclude:")
    for item in matrix["exclude"]:
        lines.append(f'    - tier: {item["tier"]}')
        lines.append(f'      python-version: "{item["python-version"]}"')
    lines.append(END_MARKER)
    return "\n".join(_indent_lines(lines, indent)) + "\n"


def render_governance_fragment(registry: dict[str, Any]) -> str:
    return render_ci_matrix_block(registry, indent="")


def _leading_space_count(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _find_managed_block(lines: list[str]) -> tuple[int, int] | None:
    begin_indexes = [index for index, line in enumerate(lines) if line.strip() == BEGIN_MARKER]
    end_indexes = [index for index, line in enumerate(lines) if line.strip() == END_MARKER]
    if not begin_indexes and not end_indexes:
        return None
    if len(begin_indexes) != 1 or len(end_indexes) != 1 or begin_indexes[0] >= end_indexes[0]:
        raise ValueError("release-governance ci_matrix managed block markers are malformed")
    return begin_indexes[0], end_indexes[0] + 1


def _find_required_status_checks_block(lines: list[str]) -> tuple[int, int, int]:
    for index, line in enumerate(lines):
        if line.strip() != "required_status_checks:":
            continue
        indent = _leading_space_count(line)
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            candidate = lines[next_index]
            if not candidate.strip():
                continue
            if _leading_space_count(candidate) <= indent and not candidate.lstrip().startswith("#"):
                end = next_index
                break
        return index, end, indent
    raise ValueError("release-governance.yml is missing required_status_checks")


def _find_unmanaged_ci_matrix_block(lines: list[str]) -> tuple[int, int] | None:
    required_start, required_end, required_indent = _find_required_status_checks_block(lines)
    ci_indent = required_indent + 2
    for index in range(required_start + 1, required_end):
        if lines[index].strip() != "ci_matrix:" or _leading_space_count(lines[index]) != ci_indent:
            continue
        end = required_end
        for next_index in range(index + 1, required_end):
            candidate = lines[next_index]
            if not candidate.strip():
                continue
            if _leading_space_count(candidate) <= ci_indent and not candidate.lstrip().startswith("#"):
                end = next_index
                break
        return index, end
    return None


def _ci_matrix_insert_index(lines: list[str]) -> int:
    required_start, required_end, _required_indent = _find_required_status_checks_block(lines)
    for index in range(required_start + 1, required_end):
        if lines[index].strip().startswith("singleton_checks:"):
            return index
    return required_end


def replace_ci_matrix_block(text: str, registry: dict[str, Any]) -> str:
    lines = text.splitlines()
    block = render_ci_matrix_block(registry).rstrip("\n").splitlines()
    managed_range = _find_managed_block(lines)
    if managed_range is not None:
        start, end = managed_range
        updated = [*lines[:start], *block, *lines[end:]]
    else:
        unmanaged_range = _find_unmanaged_ci_matrix_block(lines)
        if unmanaged_range is not None:
            start, end = unmanaged_range
            updated = [*lines[:start], *block, *lines[end:]]
        else:
            insert_at = _ci_matrix_insert_index(lines)
            updated = [*lines[:insert_at], *block, *lines[insert_at:]]
    return "\n".join(updated) + "\n"


def expected_governance_text(vault: Path, registry: dict[str, Any]) -> str:
    path = vault / GOVERNANCE_PATH
    return replace_ci_matrix_block(path.read_text(encoding="utf-8"), registry)


def validate_managed_block_text(vault: Path, registry: dict[str, Any]) -> dict[str, Any]:
    path = vault / GOVERNANCE_PATH
    actual_text = path.read_text(encoding="utf-8")
    try:
        expected_text = replace_ci_matrix_block(actual_text, registry)
        text_drift = actual_text != expected_text
        marker_error = ""
    except ValueError as exc:
        text_drift = True
        marker_error = str(exc)
    lines = actual_text.splitlines()
    begin_count = sum(1 for line in lines if line.strip() == BEGIN_MARKER)
    end_count = sum(1 for line in lines if line.strip() == END_MARKER)
    return {
        "status": "fail" if text_drift else "pass",
        "path": GOVERNANCE_PATH.as_posix(),
        "text_drift": text_drift,
        "begin_marker": BEGIN_MARKER,
        "end_marker": END_MARKER,
        "begin_marker_count": begin_count,
        "end_marker_count": end_count,
        "error": marker_error,
    }


def sync_governance_file(vault: Path) -> Path:
    registry = load_registry(vault)
    path = vault / GOVERNANCE_PATH
    updated = expected_governance_text(vault, registry)
    path.write_text(updated, encoding="utf-8")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or generate release-governance ci_matrix from lane registry."
    )
    parser.add_argument("--vault", type=Path, default=Path())
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the managed ci_matrix fragment to this path instead of syncing release-governance.yml.",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print validation report as JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = args.vault.resolve()
    if args.check:
        report = validate_alignment(vault)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(json.dumps(report["mismatched_fields"]))
        return 0 if report["status"] == "pass" else 1

    if args.out is not None:
        registry = load_registry(vault)
        out_path = (vault / args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render_governance_fragment(registry), encoding="utf-8")
        print(display_path(vault, out_path))
        return 0

    out_path = sync_governance_file(vault)
    print(display_path(vault, out_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
