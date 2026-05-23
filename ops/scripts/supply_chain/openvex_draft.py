#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.cyclonedx_sbom import build_bom, normalize_requirement_name
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import CYCLONEDX_16_SCHEMA_PATH, OPENVEX_DRAFT_SCHEMA_PATH
    from ops.scripts.schema_runtime import load_schema, validate_or_raise
    from ops.scripts.security_advisories import build_report as build_security_advisories_report
    from ops.scripts.supply_chain_artifact_model import build_model
else:
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from .cyclonedx_sbom import build_bom, normalize_requirement_name
    from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import CYCLONEDX_16_SCHEMA_PATH, OPENVEX_DRAFT_SCHEMA_PATH
    from ops.scripts.schema_runtime import load_schema, validate_or_raise
    from .security_advisories import build_report as build_security_advisories_report
    from .supply_chain_artifact_model import build_model


OPENVEX_SCHEMA_PATH = OPENVEX_DRAFT_SCHEMA_PATH
CYCLONEDX_SCHEMA_PATH = CYCLONEDX_16_SCHEMA_PATH
DEFAULT_OUT = "ops/reports/openvex-draft.json"
DEFAULT_BOM_REF = "ops/reports/cyclonedx-bom.json"
SPDX_DECISION = "shared-artifact-model-spdx-enabled"
TOOL_NAME = "ops.scripts.openvex_draft"
PRODUCER = TOOL_NAME
SOURCE_COMMAND = "python -m ops.scripts.supply_chain.openvex_draft"
ARTIFACT_KIND = "openvex_draft"


def _canonical_json_text(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _resolve_report_ref(vault: Path, report_ref: str) -> Path:
    path = Path(report_ref)
    if path.is_absolute():
        return path
    return (vault / path).resolve()


def _load_existing_bom(vault: Path, report_ref: str) -> dict[str, Any] | None:
    path = _resolve_report_ref(vault, report_ref)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    schema = load_schema(vault / CYCLONEDX_SCHEMA_PATH)
    validate_or_raise(
        payload,
        schema,
        context=f"CycloneDX schema validation failed for reusable BOM {display_path(vault, path)}",
    )
    return payload


def _envelope_file_inputs(
    vault: Path,
    *,
    cyclonedx_bom_ref: str,
    use_existing_bom: bool,
    cyclonedx_bom: dict[str, Any] | None,
) -> dict[str, Path]:
    if cyclonedx_bom is not None or not use_existing_bom:
        return {}
    path = _resolve_report_ref(vault, cyclonedx_bom_ref)
    if not path.exists():
        return {}
    return {"cyclonedx_bom": path}


def _dependency_edge_count(bom: dict[str, Any]) -> int:
    count = 0
    for item in bom.get("dependencies", []):
        depends_on = item.get("dependsOn", [])
        if isinstance(depends_on, list):
            count += len(depends_on)
    return count


def _model_dependency_edge_count(model: dict[str, Any]) -> int:
    return sum(len(item.get("dependsOn", [])) for item in model.get("dependencies", []))


def _component_count(bom: dict[str, Any] | None, model: dict[str, Any]) -> int:
    if bom is not None:
        components = bom.get("components")
        if isinstance(components, list):
            return len(components)
    return len(model.get("components", []))


def _bom_summary(bom: dict[str, Any] | None, model: dict[str, Any]) -> dict[str, int]:
    return {
        "component_count": _component_count(bom, model),
        "dependency_edge_count": _dependency_edge_count(bom) if bom else _model_dependency_edge_count(model),
    }


def _matching_product_refs(model: dict[str, Any], package_name: str) -> list[str]:
    normalized = normalize_requirement_name(package_name)
    matches = [
        component["bom-ref"]
        for component in model.get("components", [])
        if normalize_requirement_name(component.get("name", "")) == normalized
    ]
    return matches or [model["subject"]["bom_ref"]]


def _statement_from_advisory(advisory: dict[str, Any], model: dict[str, Any], timestamp: str) -> dict[str, Any]:
    analysis = advisory["analysis"]
    statement = {
        "vulnerability": {
            "id": advisory["id"],
            "aliases": advisory["aliases"],
            "summary": advisory["summary"],
            "reference_urls": advisory["reference_urls"],
        },
        "products": [{"@id": ref} for ref in _matching_product_refs(model, advisory["package"])],
        "status": analysis["state"],
        "timestamp": timestamp,
    }
    if analysis["justification"]:
        statement["justification"] = analysis["justification"]
    if analysis["action_statement"]:
        statement["action_statement"] = analysis["action_statement"]
    if analysis["resolved_version"]:
        statement["resolved_version"] = analysis["resolved_version"]
    if analysis["note"]:
        statement["impact_statement"] = analysis["note"]
    return statement


def _validate_statement_rules(statement: dict[str, Any]) -> None:
    status = str(statement.get("status", "")).strip()
    justification = str(statement.get("justification", "")).strip()
    action_statement = str(statement.get("action_statement", "")).strip()
    resolved_version = str(statement.get("resolved_version", "")).strip()

    if status == "not_affected" and not justification:
        raise ValueError("OpenVEX not_affected statements must include justification")
    if status in {"affected", "under_investigation"} and not action_statement:
        raise ValueError(f"OpenVEX {status} statements must include action_statement")
    if status == "fixed":
        if not action_statement:
            raise ValueError("OpenVEX fixed statements must include action_statement")
        if not resolved_version:
            raise ValueError("OpenVEX fixed statements must include resolved_version")


def _build_statements(security_advisories_report: dict[str, Any], model: dict[str, Any], timestamp: str) -> list[dict[str, Any]]:
    statements = []
    for advisory in security_advisories_report.get("advisories", []):
        statement = _statement_from_advisory(advisory, model, timestamp)
        _validate_statement_rules(statement)
        statements.append(statement)
    return statements


def build_openvex_draft(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    document_id: str | None = None,
    cyclonedx_bom_ref: str = DEFAULT_BOM_REF,
    use_existing_bom: bool = True,
    cyclonedx_bom: dict[str, Any] | None = None,
    artifact_model: dict[str, Any] | None = None,
    security_advisories_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    active_security_advisories_report = security_advisories_report or build_security_advisories_report(
        vault,
        policy_path=policy_path,
        context=runtime_context,
    )
    model = artifact_model or build_model(
        vault,
        policy_path=policy_path,
        context=runtime_context,
        security_advisories_report=active_security_advisories_report,
    )
    bom = cyclonedx_bom or (_load_existing_bom(vault, cyclonedx_bom_ref) if use_existing_bom else None)
    if bom is None:
        bom = build_bom(vault, policy_path=policy_path, context=runtime_context)

    bom_summary = _bom_summary(bom, model)
    statements = _build_statements(active_security_advisories_report, model, generated_at)
    vulnerability_source = "repo-native-advisory-input" if statements else "not_scanned"
    artifact_envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=ARTIFACT_KIND,
        producer=PRODUCER,
        source_command=SOURCE_COMMAND,
        resolved_policy_path=resolved_policy_path,
        schema_path=OPENVEX_SCHEMA_PATH,
        source_paths=["ops/scripts/openvex_draft.py"],
        file_inputs=_envelope_file_inputs(
            vault,
            cyclonedx_bom_ref=cyclonedx_bom_ref,
            use_existing_bom=use_existing_bom,
            cyclonedx_bom=cyclonedx_bom,
        ),
        text_inputs={
            "artifact_model": _canonical_json_text(model),
            "security_advisories_report": _canonical_json_text(active_security_advisories_report),
            "cyclonedx_bom_ref": cyclonedx_bom_ref,
            "cyclonedx_summary": _canonical_json_text(bom_summary),
            "vulnerability_source": vulnerability_source,
        },
    )

    return {
        **artifact_envelope,
        "@context": "https://openvex.dev/ns/v0.2.0",
        "@id": document_id or f"urn:uuid:{uuid.uuid4()}",
        "author": "LLM Wiki vNext",
        "timestamp": generated_at,
        "version": 1,
        "tooling": {
            "generator": TOOL_NAME,
            "cyclonedx_bom_ref": cyclonedx_bom_ref,
            "security_advisories_ref": model["artifact_context"]["security_advisories_ref"],
            "spdx_ref": model["artifact_context"]["spdx_ref"],
            "spdx_emitter_decision": SPDX_DECISION,
            "vulnerability_source": vulnerability_source,
        },
        "artifact_context": {
            "artifact_set_id": model["artifact_context"]["artifact_set_id"],
            "security_advisories_ref": model["artifact_context"]["security_advisories_ref"],
            "spdx_ref": model["artifact_context"]["spdx_ref"],
        },
        "metadata": {
            "status": "draft",
            "component_count": bom_summary["component_count"],
            "statement_count": len(statements),
            "dependency_edge_count": bom_summary["dependency_edge_count"],
            "advisory_count": active_security_advisories_report["advisory_count"],
            "artifact_set_id": model["artifact_context"]["artifact_set_id"],
        },
        "statements": statements,
        "notes": [
            "This OpenVEX artifact is generated from the shared supply-chain artifact model.",
            "Repo-native advisory input is optional; when absent, the draft remains an applicability shell with no statements.",
            "SPDX emission is enabled from the same canonical model used by CycloneDX and OpenVEX.",
            "In-toto/SLSA, Sigstore verification metadata, and PyPI release hardening attach to the same artifact set.",
        ],
    }


def write_openvex_draft(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    for statement in report.get("statements", []):
        _validate_statement_rules(statement)
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=OPENVEX_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="OpenVEX draft schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a repo-native OpenVEX draft shell")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--cyclonedx-bom-ref", default=DEFAULT_BOM_REF)
    parser.add_argument(
        "--rebuild-cyclonedx",
        action="store_true",
        help="Ignore an existing CycloneDX BOM and rebuild it in memory before drafting OpenVEX.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_openvex_draft(
        vault,
        policy_path=args.policy_path,
        cyclonedx_bom_ref=args.cyclonedx_bom_ref,
        use_existing_bom=not args.rebuild_cyclonedx,
    )
    destination = write_openvex_draft(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
