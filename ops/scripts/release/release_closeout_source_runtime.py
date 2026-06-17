from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_freshness_runtime import canonical_report_loading_issue
from ops.scripts.core.artifact_io_runtime import (
    load_optional_json_object_with_diagnostics,
)

from .release_closeout_risk_runtime import release_closeout_issue

BASE_PROFILE = "base"
PROVENANCE_PROFILE = "provenance"
SBOM_PROFILE = "sbom"
VALID_PROFILES = (BASE_PROFILE, PROVENANCE_PROFILE, SBOM_PROFILE)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: str
    artifact_kind: str


BASE_SOURCE_SPECS = (
    SourceSpec(
        "bootstrap_preflight",
        "ops/reports/bootstrap-preflight-report.json",
        "bootstrap_preflight_report",
    ),
    SourceSpec("release_smoke", "ops/reports/release-smoke-report.json", "release_smoke_report"),
    SourceSpec(
        "source_package_clean_extract",
        "ops/reports/source-package-clean-extract.json",
        "source_package_clean_extract",
    ),
    SourceSpec(
        "external_report_reference_manifest",
        "external-reports/report-reference-manifest.json",
        "external_report_reference_manifest",
    ),
    SourceSpec("test_summary", "ops/reports/test-execution-summary.json", "test_execution_summary"),
    SourceSpec("live_make_check", "ops/reports/test-execution-summary-full.json", "test_execution_summary"),
    SourceSpec(
        "raw_registry",
        "ops/reports/raw-registry-preflight-report.json",
        "raw_registry_preflight_report",
    ),
    SourceSpec(
        "artifact_freshness",
        "ops/reports/artifact-freshness-report.json",
        "artifact_freshness_report",
    ),
    SourceSpec(
        "generated_index",
        "ops/reports/generated-artifact-index.json",
        "generated_artifact_index_report",
    ),
    SourceSpec(
        "auto_improve_readiness",
        "ops/reports/auto-improve-readiness.json",
        "auto_improve_readiness_report",
    ),
)
PROVENANCE_SOURCE_SPECS = (
    *BASE_SOURCE_SPECS,
    SourceSpec(
        "supply_chain_gate",
        "ops/reports/supply-chain-gate-report.json",
        "supply_chain_gate_report",
    ),
)
SBOM_SOURCE_SPECS = (
    *PROVENANCE_SOURCE_SPECS,
    SourceSpec(
        "sbom_readiness",
        "ops/reports/sbom-readiness-gate-report.json",
        "sbom_readiness_gate_report",
    ),
)
SOURCE_SPECS_BY_PROFILE = {
    BASE_PROFILE: BASE_SOURCE_SPECS,
    PROVENANCE_PROFILE: PROVENANCE_SOURCE_SPECS,
    SBOM_PROFILE: SBOM_SOURCE_SPECS,
}
SOURCE_SPECS = BASE_SOURCE_SPECS


def source_specs_for_profile(profile: str) -> tuple[SourceSpec, ...]:
    try:
        return SOURCE_SPECS_BY_PROFILE[profile]
    except KeyError as exc:
        raise ValueError(f"unsupported release closeout profile: {profile}") from exc


def load_closeout_source(
    vault: Path,
    spec: SourceSpec,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    path = vault / spec.path
    payload, diagnostics = load_optional_json_object_with_diagnostics(path)
    load_status = str(diagnostics.get("status", "unknown")).strip() or "unknown"
    if load_status != "ok":
        return payload, load_status, [
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_report_{load_status}",
                message=f"{spec.path} could not be loaded: {diagnostics.get('message', load_status)}",
                required_evidence=[f"Regenerate {spec.path} before release closeout."],
            )
        ]

    loading_issue = canonical_report_loading_issue(path, payload)
    if loading_issue is not None:
        return payload, "unusable", [
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_report_not_current",
                message=f"{spec.path} is not usable release evidence: {loading_issue}.",
                required_evidence=[f"Regenerate {spec.path} with a current artifact envelope."],
            )
        ]

    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if artifact_kind != spec.artifact_kind:
        return payload, "kind_mismatch", [
            release_closeout_issue(
                source=spec.name,
                source_path=spec.path,
                code=f"{spec.name}_artifact_kind_mismatch",
                message=(
                    f"{spec.path} declares artifact_kind={artifact_kind or '<missing>'}; "
                    f"expected {spec.artifact_kind}."
                ),
                required_evidence=[f"Regenerate {spec.path} from the expected producer."],
            )
        ]

    return payload, "ok", []
