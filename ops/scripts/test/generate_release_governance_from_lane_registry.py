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
GENERATED_HEADER = """# Generated fragment for .github/release-governance.yml ci_matrix
# Source of truth: ops/test-lane-registry.json
# Regenerate/check with: make release-governance-sync
"""


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
    return {
        "status": "pass" if not mismatches else "fail",
        "expected": expected,
        "actual": actual,
        "mismatched_fields": mismatches,
        "registry_tier_count": len(expected["tiers"]),
    }


def render_governance_fragment(registry: dict[str, Any]) -> str:
    matrix = expected_ci_matrix(registry)
    lines = [GENERATED_HEADER.rstrip(), "ci_matrix:"]
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
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate or generate release-governance ci_matrix from lane registry."
    )
    parser.add_argument("--vault", type=Path, default=Path())
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tmp/release-governance-ci-matrix.fragment.yml"),
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

    registry = load_registry(vault)
    rendered = render_governance_fragment(registry)
    out_path = (vault / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(display_path(vault, out_path))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
