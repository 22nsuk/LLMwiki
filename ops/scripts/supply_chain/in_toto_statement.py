#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.schema_constants_runtime import IN_TOTO_STATEMENT_SCHEMA_PATH
    from ops.scripts.supply_chain_artifact_model import build_model
    from ops.scripts.supply_chain_provenance import (
        build_report as build_supply_chain_provenance_report,
        sha256_file,
    )
else:
    from ops.scripts.artifact_freshness_runtime import (
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.schema_constants_runtime import IN_TOTO_STATEMENT_SCHEMA_PATH

    from .supply_chain_artifact_model import build_model
    from .supply_chain_provenance import (
        build_report as build_supply_chain_provenance_report,
        sha256_file,
    )


DEFAULT_OUT = "ops/reports/in-toto-statement.json"
TOOL_NAME = "ops.scripts.in_toto_statement"
ARTIFACT_KIND = "in_toto_statement"
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.in_toto_statement"


def _resolve_path(vault: Path, report_ref: str) -> Path:
    path = Path(report_ref)
    if path.is_absolute():
        return path
    return (vault / path).resolve()


def _subject_entry(path: Path, vault: Path) -> dict[str, Any]:
    return {
        "name": report_path(vault, path),
        "digest": {
            "sha256": sha256_file(path),
        },
    }


def build_in_toto_statement(
    vault: Path,
    *,
    policy_path: str | None = None,
    artifact_model: dict[str, Any] | None = None,
    provenance_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    model = artifact_model or build_model(vault, policy_path=policy_path)
    active_provenance_report = provenance_report or build_supply_chain_provenance_report(vault, policy_path=policy_path)
    refs = [
        model["artifact_context"]["cyclonedx_ref"],
        model["artifact_context"]["spdx_ref"],
        model["artifact_context"]["openvex_ref"],
        model["artifact_context"]["model_ref"],
    ]
    subjects = []
    for report_ref in refs:
        path = _resolve_path(vault, report_ref)
        if path.exists():
            subjects.append(_subject_entry(path, vault))
    if not subjects:
        serialized_model = json.dumps(model, ensure_ascii=False, sort_keys=True).encode("utf-8")
        subjects.append(
            {
                "name": model["artifact_context"]["model_ref"],
                "digest": {
                    "sha256": __import__("hashlib").sha256(serialized_model).hexdigest(),
                },
            }
        )
    materials = [
        {
            "uri": item["path"],
            "digest": {"sha256": item["sha256"]},
        }
        for item in active_provenance_report["inputs"]
        if item.get("exists") and item.get("sha256")
    ]
    artifact_context = {
        "artifact_set_id": model["artifact_context"]["artifact_set_id"],
        "model_ref": model["artifact_context"]["model_ref"],
        "spdx_ref": model["artifact_context"]["spdx_ref"],
        "openvex_ref": model["artifact_context"]["openvex_ref"],
    }
    report = {
        "$schema": IN_TOTO_STATEMENT_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": model["generated_at"],
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "_type": "https://in-toto.io/Statement/v1",
        "subject": subjects,
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://llm-wiki-vnext.invalid/supply-chain-artifacts",
                "externalParameters": {
                    "artifact_set_id": artifact_context["artifact_set_id"],
                    "subject_count": len(subjects),
                },
                "internalParameters": {
                    "provenance_status": model["provenance_summary"]["status"],
                    "mapping_status": model["mapping_summary"]["status"],
                },
                "resolvedDependencies": materials,
            },
            "runDetails": {
                "builder": {
                    "id": TOOL_NAME,
                },
                "metadata": {
                    "invocationId": artifact_context["artifact_set_id"],
                    "startedOn": model["generated_at"],
                    "finishedOn": model["generated_at"],
                },
            },
        },
        "artifact_context": artifact_context,
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=str(model["generated_at"]),
        artifact_kind=ARTIFACT_KIND,
        producer=TOOL_NAME,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=IN_TOTO_STATEMENT_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/in_toto_statement.py",
            "ops/scripts/supply_chain_artifact_model.py",
            "ops/scripts/supply_chain_provenance.py",
        ],
        text_inputs={
            "artifact_set_id": str(artifact_context["artifact_set_id"]),
            "subject_count": str(len(subjects)),
            "material_count": str(len(materials)),
        },
    )
    return embed_artifact_envelope_metadata(report, envelope)


def write_in_toto_statement(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=IN_TOTO_STATEMENT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="In-toto statement schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an in-toto Statement with an SLSA provenance predicate")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_in_toto_statement(vault, policy_path=args.policy_path)
    destination = write_in_toto_statement(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
