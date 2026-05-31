from __future__ import annotations

import pytest

from ops.scripts.release.release_closeout_source_runtime import (
    BASE_PROFILE,
    PROVENANCE_PROFILE,
    SBOM_PROFILE,
    SourceSpec,
    load_closeout_source,
    source_specs_for_profile,
)


def test_source_specs_for_profile_extends_base_in_order() -> None:
    base = source_specs_for_profile(BASE_PROFILE)
    provenance = source_specs_for_profile(PROVENANCE_PROFILE)
    sbom = source_specs_for_profile(SBOM_PROFILE)

    assert [spec.name for spec in base][:2] == ["bootstrap_preflight", "release_smoke"]
    assert [spec.name for spec in provenance[: len(base)]] == [spec.name for spec in base]
    assert provenance[-1].name == "supply_chain_gate"
    assert [spec.name for spec in sbom[: len(provenance)]] == [
        spec.name for spec in provenance
    ]
    assert sbom[-1].name == "sbom_readiness"


def test_source_specs_for_profile_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError, match="unsupported release closeout profile"):
        source_specs_for_profile("unknown")


def test_load_closeout_source_reports_missing_input(tmp_path) -> None:
    spec = SourceSpec(
        "test_summary",
        "ops/reports/test-execution-summary.json",
        "test_execution_summary",
    )

    payload, load_status, blockers = load_closeout_source(tmp_path, spec)

    assert payload == {}
    assert load_status == "missing"
    assert blockers[0]["code"] == "test_summary_report_missing"
    assert blockers[0]["source_path"] == spec.path
