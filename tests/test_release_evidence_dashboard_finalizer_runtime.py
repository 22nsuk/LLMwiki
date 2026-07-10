from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from ops.scripts.release.release_evidence_dashboard_finalizer_runtime import (
    finalizer_duration_signal,
)
from ops.scripts.release.release_evidence_dashboard_render_runtime import (
    FIXED_POINT_COST_TREND_PATH,
    FIXED_POINT_PATH,
)

pytestmark = pytest.mark.runtime_hotspot_smoke


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixed_point_payload() -> dict:
    return {
        "schema_version": 2,
        "generated_at": "2026-04-30T08:30:00Z",
        "status": "pass",
        "execution_pass_count": 1,
        "duration_summary": {
            "execution_pass_count": 1,
            "command_run_count": 12,
            "total_duration_ms": 1200,
            "writer_costs": [
                {
                    "name": "release-evidence-dashboard",
                    "target": "release-evidence-dashboard-report",
                    "produces": ["ops/reports/release-evidence-dashboard.json"],
                    "run_count": 1,
                    "selected": True,
                    "total_duration_ms": 450,
                    "average_duration_ms": 150,
                    "max_duration_ms": 200,
                }
            ],
            "expensive_prerequisites": {
                "targets": ["release-risk-taxonomy-matrix"],
                "configured_target_count": 1,
                "observed_target_count": 1,
                "run_count": 1,
                "total_duration_ms": 450,
                "summary": "expensive prerequisites ran once",
            },
            "summary": "1 writer ran 12 commands in one execution pass",
        },
    }


def _cost_trend_payload(fixed_point_digest: str, *, status: str = "pass") -> dict:
    breached = status == "attention"
    return {
        "schema_version": 2,
        "status": status,
        "sample_count": 2,
        "latest_sample": {"fixed_point_report_raw_digest": fixed_point_digest},
        "threshold_summary": {
            "status": status,
            "breached_writer_count": 1 if breached else 0,
            "breached_writers": ["release-evidence-dashboard"] if breached else [],
            "summary": "1 fixed-point writer cost threshold breach"
            if breached
            else "fixed-point writer costs are within configured thresholds",
        },
    }


def test_finalizer_duration_signal_reads_current_digest_and_writer_costs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        fixed_point_path = vault / FIXED_POINT_PATH
        cost_trend_path = vault / FIXED_POINT_COST_TREND_PATH
        _write_json(fixed_point_path, _fixed_point_payload())
        fixed_point_digest = hashlib.sha256(fixed_point_path.read_bytes()).hexdigest()
        _write_json(cost_trend_path, _cost_trend_payload(fixed_point_digest))

        signal = finalizer_duration_signal(
            vault,
            json.loads(fixed_point_path.read_text(encoding="utf-8")),
            "ok",
            json.loads(cost_trend_path.read_text(encoding="utf-8")),
            "ok",
        )

    assert signal["status"] == "pass"
    assert signal["fixed_point_report_status"] == "pass"
    assert (
        signal["evidence_basis"]["fixed_point_report_raw_digest"] == fixed_point_digest
    )
    assert (
        signal["evidence_basis"]["basis_relation_to_current_fixed_point"]
        == "sampled_current_fixed_point"
    )
    assert signal["writer_costs"] == [
        {
            "name": "release-evidence-dashboard",
            "target": "release-evidence-dashboard-report",
            "produces": ["ops/reports/release-evidence-dashboard.json"],
            "run_count": 1,
            "selected": True,
            "total_duration_ms": 450,
            "average_duration_ms": 150,
            "max_duration_ms": 200,
        }
    ]


def test_finalizer_duration_signal_surfaces_threshold_attention() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        fixed_point_path = vault / FIXED_POINT_PATH
        cost_trend_path = vault / FIXED_POINT_COST_TREND_PATH
        _write_json(fixed_point_path, _fixed_point_payload())
        fixed_point_digest = hashlib.sha256(fixed_point_path.read_bytes()).hexdigest()
        _write_json(
            cost_trend_path,
            _cost_trend_payload(fixed_point_digest, status="attention"),
        )

        signal = finalizer_duration_signal(
            vault,
            json.loads(fixed_point_path.read_text(encoding="utf-8")),
            "ok",
            json.loads(cost_trend_path.read_text(encoding="utf-8")),
            "ok",
        )

    assert signal["status"] == "attention"
    assert signal["threshold_summary"]["breached_writer_count"] == 1
    assert signal["threshold_summary"]["breached_writers"] == [
        "release-evidence-dashboard"
    ]


def test_finalizer_duration_signal_preserves_missing_evidence_basis() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        cost_trend_path = vault / FIXED_POINT_COST_TREND_PATH
        _write_json(cost_trend_path, _cost_trend_payload("old-fixed-point-digest"))
        cost_trend_digest = hashlib.sha256(cost_trend_path.read_bytes()).hexdigest()

        signal = finalizer_duration_signal(
            vault,
            {},
            "missing",
            json.loads(cost_trend_path.read_text(encoding="utf-8")),
            "ok",
        )

    assert signal["load_status"] == "missing"
    assert signal["status"] == "unknown"
    assert signal["evidence_basis"]["fixed_point_report_raw_digest"] == ""
    assert signal["evidence_basis"]["cost_trend_raw_digest"] == cost_trend_digest
    assert (
        signal["evidence_basis"]["basis_relation_to_current_fixed_point"]
        == "cost_trend_unavailable"
    )


def test_finalizer_duration_signal_rejects_v1_current_authority() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        fixed_point = _fixed_point_payload()
        fixed_point["schema_version"] = 1

        signal = finalizer_duration_signal(vault, fixed_point, "ok", {}, "missing")

    assert signal["load_status"] == "unsupported_schema_version"
    assert signal["status"] == "unknown"
    assert signal["execution_pass_count"] == 0
