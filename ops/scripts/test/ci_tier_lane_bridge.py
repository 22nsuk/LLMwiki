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
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.yaml_runtime import parse_simple_yaml
    from ops.scripts.test.test_lane_registry_runtime import (
        compatibility_map,
        compatibility_names,
        derived_packs,
        load_registry,
        persistent_lanes,
    )
else:
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.yaml_runtime import parse_simple_yaml
    from ops.scripts.test.test_lane_registry_runtime import (
        compatibility_map,
        compatibility_names,
        derived_packs,
        load_registry,
        persistent_lanes,
    )


DEFAULT_OUT = "tmp/ci-tier-lane-bridge.json"
PRODUCER = "ops.scripts.ci_tier_lane_bridge"
CI_WORKFLOW = ".github/workflows/ci.yml"


def _workflow_test_tier_job(vault: Path) -> dict[str, Any]:
    workflow = parse_simple_yaml((vault / CI_WORKFLOW).read_text(encoding="utf-8"))
    jobs = workflow.get("jobs", {})
    return jobs.get("test-tier", {}) if isinstance(jobs, dict) else {}


def _workflow_matrix_tiers(test_tier: dict[str, Any]) -> list[str]:
    strategy = test_tier.get("strategy", {}) if isinstance(test_tier, dict) else {}
    matrix = strategy.get("matrix", {}) if isinstance(strategy, dict) else {}
    tiers = matrix.get("tier", []) if isinstance(matrix, dict) else []
    return [str(item) for item in tiers if str(item).strip()] if isinstance(tiers, list) else []


def _workflow_tier_run_texts(test_tier: dict[str, Any]) -> dict[str, str]:
    raw_steps = test_tier.get("steps", []) if isinstance(test_tier, dict) else []
    steps = raw_steps if isinstance(raw_steps, list) else []
    run_texts: dict[str, list[str]] = {}
    for step in steps:
        if not isinstance(step, dict) or "run" not in step:
            continue
        condition = str(step.get("if", "")).strip()
        marker = "matrix.tier == '"
        if marker not in condition:
            continue
        tier = condition.split(marker, 1)[1].split("'", 1)[0].strip()
        if not tier:
            continue
        run_texts.setdefault(tier, []).append(str(step.get("run", "")))
    return {tier: "\n".join(texts) for tier, texts in run_texts.items()}


def _non_empty_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _workflow_command_lines(run_text: str) -> set[str]:
    return {line.strip() for line in run_text.splitlines() if line.strip()}


def _registry_bridge_entries(
    registry: dict[str, Any],
    workflow_tiers: list[str],
    workflow_run_texts: dict[str, str],
) -> list[dict[str, Any]]:
    lane_by_id = {str(item.get("lane_id", "")).strip(): item for item in persistent_lanes(registry)}
    pack_by_id = {str(item.get("pack_id", "")).strip(): item for item in derived_packs(registry)}
    tier_map = compatibility_map(registry, "ci_tier")
    entries: list[dict[str, Any]] = []
    for tier in workflow_tiers:
        registry_id = tier_map.get(tier, "")
        lane = lane_by_id.get(registry_id)
        pack = pack_by_id.get(registry_id)
        item = lane or pack or {}
        ci_entrypoint = str(item.get("ci_entrypoint", "")).strip()
        ci_entrypoint_command = f"make {ci_entrypoint}" if ci_entrypoint else ""
        ci_steps = _non_empty_str_list(item.get("ci_steps", []))
        workflow_run_text = workflow_run_texts.get(tier, "")
        workflow_commands = _workflow_command_lines(workflow_run_text)
        missing_ci_steps = [step for step in ci_steps if step not in workflow_commands]
        entries.append(
            {
                "ci_tier": tier,
                "registry_id": registry_id,
                "registry_kind": "persistent_lane" if lane else "derived_pack" if pack else "",
                "make_target": str(item.get("make_target", "")).strip(),
                "ci_entrypoint": ci_entrypoint,
                "ci_entrypoint_declared": bool(ci_entrypoint_command in workflow_commands),
                "ci_steps": ci_steps,
                "workflow_run_text": workflow_run_text,
                "workflow_run_text_present": bool(workflow_run_text),
                "missing_ci_steps": missing_ci_steps,
                "registry_backed": bool(item),
            }
        )
    return entries


def build_report(vault: Path, *, context: RuntimeContext | None = None) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    resolved_vault = vault.resolve()
    registry = load_registry(resolved_vault)
    test_tier = _workflow_test_tier_job(resolved_vault)
    workflow_tiers = _workflow_matrix_tiers(test_tier)
    workflow_run_texts = _workflow_tier_run_texts(test_tier)
    registry_tiers = list(compatibility_names(registry, "ci_tier"))
    missing_in_workflow = sorted(set(registry_tiers) - set(workflow_tiers))
    unknown_in_workflow = sorted(set(workflow_tiers) - set(registry_tiers))
    bridge_entries = _registry_bridge_entries(registry, workflow_tiers, workflow_run_texts)
    missing_bridge_count = sum(1 for item in bridge_entries if not item["registry_backed"])
    missing_workflow_run_text_count = sum(1 for item in bridge_entries if not item["workflow_run_text_present"])
    missing_ci_entrypoint_count = sum(
        1 for item in bridge_entries if item["registry_backed"] and not item["ci_entrypoint_declared"]
    )
    missing_ci_step_count = sum(len(item["missing_ci_steps"]) for item in bridge_entries)
    status = (
        "pass"
        if not missing_in_workflow
        and not unknown_in_workflow
        and missing_bridge_count == 0
        and missing_workflow_run_text_count == 0
        and missing_ci_entrypoint_count == 0
        and missing_ci_step_count == 0
        else "fail"
    )
    return {
        "$schema": "ops/schemas/ci-tier-lane-bridge.schema.json",
        "artifact_kind": "ci_tier_lane_bridge",
        "generated_at": runtime_context.isoformat_z(),
        "producer": PRODUCER,
        "status": status,
        "summary": {
            "workflow_tier_count": len(workflow_tiers),
            "registry_tier_count": len(registry_tiers),
            "missing_in_workflow_count": len(missing_in_workflow),
            "unknown_in_workflow_count": len(unknown_in_workflow),
            "missing_bridge_count": missing_bridge_count,
            "missing_workflow_run_text_count": missing_workflow_run_text_count,
            "missing_ci_entrypoint_count": missing_ci_entrypoint_count,
            "missing_ci_step_count": missing_ci_step_count,
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
