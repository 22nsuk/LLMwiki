#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import (  # noqa: PLC0415
        build_canonical_report_envelope,
        embed_artifact_envelope_metadata,
    )
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.schema_constants_runtime import SPDX_SBOM_DRAFT_SCHEMA_PATH
    from ops.scripts.supply_chain_artifact_model import build_model
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
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.schema_constants_runtime import SPDX_SBOM_DRAFT_SCHEMA_PATH

    from .supply_chain_artifact_model import build_model


DEFAULT_OUT = "ops/reports/spdx-sbom.json"
TOOL_NAME = "ops.scripts.spdx_sbom"


def _spdx_id(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"SPDXRef-Package-{digest}"


def _external_ref(locator: str) -> dict[str, str]:
    return {
        "referenceCategory": "PACKAGE-MANAGER",
        "referenceType": "purl",
        "referenceLocator": locator,
    }


def _package_from_subject(subject: dict[str, str]) -> dict[str, Any]:
    return {
        "SPDXID": _spdx_id(subject["bom_ref"]),
        "name": subject["name"],
        "versionInfo": subject["version"],
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "primaryPackagePurpose": "APPLICATION",
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "externalRefs": [_external_ref(subject["purl"])],
    }


def _package_from_component(component: dict[str, Any]) -> dict[str, Any]:
    return {
        "SPDXID": _spdx_id(component["bom-ref"]),
        "name": component["name"],
        "versionInfo": str(component.get("version", "")),
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "primaryPackagePurpose": "APPLICATION" if component.get("type") == "application" else "LIBRARY",
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "externalRefs": [_external_ref(component["purl"])],
    }


def build_spdx_sbom(
    vault: Path,
    *,
    policy_path: str | None = None,
    artifact_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _policy, resolved_policy_path = load_policy(vault, policy_path)
    model = artifact_model or build_model(vault, policy_path=policy_path)
    subject = model["subject"]
    root_package = _package_from_subject(subject)
    packages = [root_package] + [_package_from_component(component) for component in model["components"]]
    spdx_id_by_ref = {subject["bom_ref"]: root_package["SPDXID"]}
    for component, package in zip(model["components"], packages[1:], strict=False):
        spdx_id_by_ref[component["bom-ref"]] = package["SPDXID"]

    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": root_package["SPDXID"],
        }
    ]
    for item in model["dependencies"]:
        parent = spdx_id_by_ref.get(item["ref"])
        if parent is None:
            continue
        for child in item.get("dependsOn", []):
            child_spdx_id = spdx_id_by_ref.get(child)
            if child_spdx_id is None:
                continue
            relationships.append(
                {
                    "spdxElementId": parent,
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": child_spdx_id,
                }
            )

    artifact_context = {
        "artifact_set_id": model["artifact_context"]["artifact_set_id"],
        "model_ref": model["artifact_context"]["model_ref"],
        "cyclonedx_ref": model["artifact_context"]["cyclonedx_ref"],
        "openvex_ref": model["artifact_context"]["openvex_ref"],
    }
    report = {
        "$schema": SPDX_SBOM_DRAFT_SCHEMA_PATH,
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{subject['name']}-supply-chain-sbom",
        "documentNamespace": f"https://llm-wiki-vnext.invalid/spdx/{artifact_context['artifact_set_id']}",
        "creationInfo": {
            "created": model["generated_at"],
            "creators": [f"Tool: {TOOL_NAME}"],
        },
        "documentDescribes": [root_package["SPDXID"]],
        "artifact_context": artifact_context,
        "packages": packages,
        "relationships": relationships,
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": f"Tool: {TOOL_NAME}",
                "annotationDate": model["generated_at"],
                "comment": f"artifact_set_id={artifact_context['artifact_set_id']}",
            }
        ],
    }
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=str(model["generated_at"]),
        artifact_kind="spdx_sbom",
        producer=TOOL_NAME,
        source_command="python -m ops.scripts.supply_chain.spdx_sbom",
        resolved_policy_path=resolved_policy_path,
        schema_path=SPDX_SBOM_DRAFT_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/spdx_sbom.py",
            "ops/scripts/supply_chain_artifact_model.py",
            "ops/scripts/artifact_freshness_runtime.py",
        ],
        text_inputs={
            "artifact_model_generated_at": str(model.get("generated_at", "")),
            "artifact_set_id": str(artifact_context["artifact_set_id"]),
        },
    )
    return embed_artifact_envelope_metadata({**envelope, **report}, envelope)


def write_spdx_sbom(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SPDX_SBOM_DRAFT_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="SPDX draft schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an SPDX draft SBOM from the shared artifact model")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_spdx_sbom(vault, policy_path=args.policy_path)
    destination = write_spdx_sbom(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
