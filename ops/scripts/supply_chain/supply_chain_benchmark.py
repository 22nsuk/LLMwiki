#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope, embed_artifact_envelope_metadata
    from ops.scripts.cyclonedx_sbom import build_bom
    from ops.scripts.openvex_draft import build_openvex_draft
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from ops.scripts.sbom_readiness_gate_runtime import build_gate_report as build_sbom_readiness_gate_report
    from ops.scripts.schema_constants_runtime import SUPPLY_CHAIN_BENCHMARK_SCHEMA_PATH
    from ops.scripts.supply_chain_provenance import build_report as build_supply_chain_provenance_report
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope, embed_artifact_envelope_metadata
    from .cyclonedx_sbom import build_bom
    from .openvex_draft import build_openvex_draft
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from .sbom_export_mapping import build_report as build_sbom_export_mapping_report
    from .sbom_readiness_gate_runtime import build_gate_report as build_sbom_readiness_gate_report
    from ops.scripts.schema_constants_runtime import SUPPLY_CHAIN_BENCHMARK_SCHEMA_PATH
    from .supply_chain_provenance import build_report as build_supply_chain_provenance_report


DEFAULT_OUT = "ops/reports/supply-chain-benchmark.json"
TOOL_NAME = "ops.scripts.supply_chain_benchmark"
ARTIFACT_KIND = "supply_chain_benchmark"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.supply_chain_benchmark"


def _elapsed_seconds(fn: Any) -> float:
    start = time.perf_counter()
    fn()
    return round(time.perf_counter() - start, 6)


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)

    strict_elapsed = _elapsed_seconds(
        lambda: (
            build_supply_chain_provenance_report(vault, policy_path=policy_path, context=runtime_context),
            build_sbom_export_mapping_report(vault, policy_path=policy_path, context=runtime_context),
            build_sbom_readiness_gate_report(vault, policy_path=policy_path, context=runtime_context, refresh_mapping=True),
            build_bom(vault, policy_path=policy_path, context=runtime_context),
            build_openvex_draft(vault, policy_path=policy_path, context=runtime_context, use_existing_bom=False),
        )
    )

    def _cached_path() -> None:
        provenance_report = build_supply_chain_provenance_report(vault, policy_path=policy_path, context=runtime_context)
        mapping_report = build_sbom_export_mapping_report(
            vault,
            policy_path=policy_path,
            context=runtime_context,
            provenance_report=provenance_report,
        )
        build_sbom_readiness_gate_report(
            vault,
            policy_path=policy_path,
            context=runtime_context,
            mapping_report=mapping_report,
        )
        bom = build_bom(
            vault,
            policy_path=policy_path,
            context=runtime_context,
            provenance_report=provenance_report,
            mapping_report=mapping_report,
        )
        build_openvex_draft(
            vault,
            policy_path=policy_path,
            context=runtime_context,
            use_existing_bom=False,
            cyclonedx_bom=bom,
        )

    cached_elapsed = _elapsed_seconds(_cached_path)
    ratio = round(strict_elapsed / cached_elapsed, 6) if cached_elapsed else 0.0
    report = {
        "$schema": SUPPLY_CHAIN_BENCHMARK_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "strict_path": {
            "elapsed_seconds": strict_elapsed,
            "intermediate_reuse": False,
        },
        "cached_path": {
            "elapsed_seconds": cached_elapsed,
            "intermediate_reuse": True,
        },
        "comparison": {
            "strict_over_cached_ratio": ratio,
            "cached_faster_or_equal": cached_elapsed <= strict_elapsed,
        },
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=runtime_context.isoformat_z(),
        artifact_kind=ARTIFACT_KIND,
        producer=TOOL_NAME,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=SUPPLY_CHAIN_BENCHMARK_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/supply_chain_benchmark.py",
            "ops/scripts/supply_chain_provenance.py",
            "ops/scripts/sbom_export_mapping.py",
            "ops/scripts/sbom_readiness_gate_runtime.py",
            "ops/scripts/cyclonedx_sbom.py",
            "ops/scripts/openvex_draft.py",
        ],
        text_inputs={
            "strict_elapsed": str(strict_elapsed),
            "cached_elapsed": str(cached_elapsed),
            "strict_over_cached_ratio": str(ratio),
        },
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SUPPLY_CHAIN_BENCHMARK_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="Supply-chain benchmark schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark strict and cached supply-chain generation paths")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
