#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.output_runtime import display_path  # noqa: PLC0415
    from ops.scripts.runtime_context import RuntimeContext  # noqa: PLC0415
    from ops.scripts.test_lane_registry_runtime import (  # noqa: PLC0415
        compatibility_map,
        compatibility_names,
        derived_packs,
        load_registry,
        persistent_lanes,
    )
    from ops.scripts.yaml_runtime import parse_simple_yaml  # noqa: PLC0415
else:
    from ..core.output_runtime import display_path
    from ..core.runtime_context import RuntimeContext
    from ..core.yaml_runtime import parse_simple_yaml
    from .test_lane_registry_runtime import (
        compatibility_map,
        compatibility_names,
        derived_packs,
        load_registry,
        persistent_lanes,
    )


DEFAULT_OUT = "tmp/ci-tier-lane-bridge.json"
PRODUCER = "ops.scripts.ci_tier_lane_bridge"
CI_WORKFLOW = ".github/workflows/ci.yml"


def _workflow_matrix_tiers(vault: Path) -> list[str]:
    workflow = parse_simple_yaml((vault / CI_WORKFLOW).read_text(encoding="utf-8"))
    jobs = workflow.get("jobs", {})
    test_tier = jobs.get("test-tier", {}) if isinstance(jobs, dict) else {}
    strategy = test_tier.get("strategy", {}) if isinstance(test_tier, dict) else {}
    matrix = strategy.get("matrix", {}) if isinstance(strategy, dict) else {}
    tiers = matrix.get("tier", []) if isinstance(matrix, dict) else []
    return [str(item) for item in tiers if str(item).strip()] if isinstance(tiers, list) else []


def _registry_bridge_entries(registry: dict[str, Any], workflow_tiers: list[str]) -> list[dict[str, Any]]:
    lane_by_id = {str(item.get("lane_id", "")).strip(): item for item in persistent_lanes(registry)}
    pack_by_id = {str(item.get("pack_id", "")).strip(): item for item in derived_packs(registry)}
    tier_map = compatibility_map(registry, "ci_tier")
    entries: list[dict[str, Any]] = []
    for tier in workflow_tiers:
        registry_id = tier_map.get(tier, "")
        lane = lane_by_id.get(registry_id)
        pack = pack_by_id.get(registry_id)
        item = lane or pack or {}
        entries.append(
            {
                "ci_tier": tier,
                "registry_id": registry_id,
                "registry_kind": "persistent_lane" if lane else "derived_pack" if pack else "",
                "make_target": str(item.get("make_target", "")).strip(),
                "ci_entrypoint": str(item.get("ci_entrypoint", "")).strip(),
                "registry_backed": bool(item),
            }
        )
    return entries


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    registry = load_registry(resolved_vault)
    workflow_tiers = _workflow_matrix_tiers(resolved_vault)
    registry_tiers = list(compatibility_names(registry, "ci_tier"))
    missing_in_workflow = sorted(set(registry_tiers) - set(workflow_tiers))
    unknown_in_workflow = sorted(set(workflow_tiers) - set(registry_tiers))
    bridge_entries = _registry_bridge_entries(registry, workflow_tiers)
    missing_bridge_count = sum(1 for item in bridge_entries if not item["registry_backed"])
    return {
        "$schema": "ops/schemas/ci-tier-lane-bridge.schema.json",
        "artifact_kind": "ci_tier_lane_bridge",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": "pass" if not missing_in_workflow and not unknown_in_workflow and missing_bridge_count == 0 else "fail",
        "summary": {
            "workflow_tier_count": len(workflow_tiers),
            "registry_tier_count": len(registry_tiers),
            "missing_in_workflow_count": len(missing_in_workflow),
            "unknown_in_workflow_count": len(unknown_in_workflow),
            "missing_bridge_count": missing_bridge_count,
        },
        "workflow_tiers": workflow_tiers,
        "registry_tiers": registry_tiers,
        "bridge": bridge_entries,
        "missing_in_workflow": missing_in_workflow,
        "unknown_in_workflow": unknown_in_workflow,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str) -> Path:
    destination = (vault / out_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check CI matrix tiers against the test lane registry.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
