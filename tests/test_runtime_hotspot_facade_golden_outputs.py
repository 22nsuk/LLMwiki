from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest import mock

import pytest
from ops.scripts.auto_improve_runtime import run_auto_improve_session
from ops.scripts.mutation_proposal_runtime import (
    build_report as build_mutation_proposal_report,
)
from ops.scripts.policy_runtime import load_policy
from ops.scripts.release_closeout_summary import build_report as build_closeout_report
from ops.scripts.release_evidence_dashboard import (
    build_report as build_dashboard_report,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema

import tests.test_release_closeout_summary as closeout_fixture
import tests.test_release_evidence_dashboard as dashboard_fixture
from tests.test_auto_improve_runtime import (
    _fake_successful_mechanism_experiment,
    _incrementing_runtime_context,
    _load_successful_auto_improve_artifacts,
    seed_subagent_profiles,
    seed_wrapper_vault,
)
from tests.test_auto_improve_runtime import (
    mutation_proposal_report as auto_improve_mutation_proposal_report,
)
from tests.test_mutation_proposal import (
    ENVELOPE_SCHEMA_PATH,
    mechanism_review_report,
    write_json_exact,
)
from tests.test_mutation_proposal import (
    fixed_context as mutation_fixed_context,
)
from tests.test_mutation_proposal import (
    seed_vault as seed_mutation_vault,
)
from tests.test_release_closeout_summary import (
    BASE_PROFILE,
)
from tests.test_release_closeout_summary import (
    ENVELOPE_SCHEMA_PATH as CLOSEOUT_ENVELOPE_SCHEMA_PATH,
)
from tests.test_release_closeout_summary import (
    REPORT_SCHEMA_PATH as CLOSEOUT_SCHEMA_PATH,
)
from tests.test_release_closeout_summary import (
    fixed_context as closeout_fixed_context,
)
from tests.test_release_evidence_dashboard import (
    DASHBOARD_SCHEMA_PATH,
)
from tests.test_release_evidence_dashboard import (
    fixed_context as dashboard_fixed_context,
)

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parents[1]
AUTO_IMPROVE_SESSION_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "auto-improve-session.schema.json"

GOLDEN_DIGESTS = {
    "mutation_proposal": "bf585d9978c882613d72d3b789a4440b9d144ec44bb1ccbdcb21aee87c2e0356",
    "release_evidence_dashboard": "0f1aa3a12f6fb124b6daf12f79a35df65e91583124502f5a3483d628f8a960e9",
    "release_closeout_summary": "b754f7c21ef4507c0662246540ba0b92457307da718ba464aaabe26044c969f0",
    "auto_improve_session_bundle": "129183c429b7d84069c1bd9d116b1fa19aad760594372cd002f7d0b0c9977fda",
}


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _assert_schema_valid(payload: dict[str, object], schema_path: Path) -> None:
    assert validate_with_schema(payload, load_schema(schema_path)) == []


def _assert_no_local_path_leak(payload: object) -> None:
    forbidden_fragments = (
        "/tmp/",
        "/var/folders/",
        "/mnt/",
        "/home/",
        "\\Users\\",
        "C:\\",
    )

    def strings(value: object) -> Iterator[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from strings(str(key))
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    for text in strings(payload):
        assert not any(fragment in text for fragment in forbidden_fragments), text


def _mutation_proposal_payload() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir)
        seed_mutation_vault(vault)
        write_json_exact(
            vault / "ops" / "reports" / "mechanism-review-candidates.json",
            mechanism_review_report(),
        )
        (vault / "system" / "system-log.md").write_text(
            "# System Log\n\n"
            "## [2026-04-14 00:00] decision | prior experiment\n\n"
            "### Artifacts\n"
            "- `ops/scripts/wiki_lint.py`\n",
            encoding="utf-8",
        )
        policy, policy_path = load_policy(vault)
        report = build_mutation_proposal_report(
            vault,
            policy,
            policy_path,
            context=mutation_fixed_context(policy),
        )
        _assert_schema_valid(report, vault / "ops" / "schemas" / "mutation-proposals.schema.json")
        _assert_schema_valid(report, ENVELOPE_SCHEMA_PATH)
        return report


def _dashboard_payload() -> dict[str, object]:
    case = dashboard_fixture.ReleaseEvidenceDashboardTests(
        methodName="test_dashboard_validates_and_labels_checked_in_claims"
    )
    case.setUp()
    try:
        case._write_inputs()
        report = build_dashboard_report(case.vault, context=dashboard_fixed_context())
        _assert_schema_valid(report, DASHBOARD_SCHEMA_PATH)
        return report
    finally:
        case.tearDown()


def _closeout_payload() -> dict[str, object]:
    case = closeout_fixture.ReleaseCloseoutSummaryTests(
        methodName="test_build_report_passes_when_all_required_inputs_are_closeout_clean_pass"
    )
    case.setUp()
    try:
        case._write_dependency_lockfiles()
        case._write_happy_sources()
        report = build_closeout_report(case.vault, profile=BASE_PROFILE, context=closeout_fixed_context())
        _assert_schema_valid(report, CLOSEOUT_SCHEMA_PATH)
        _assert_schema_valid(report, CLOSEOUT_ENVELOPE_SCHEMA_PATH)
        return report
    finally:
        case.tearDown()


def _auto_improve_bundle() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_wrapper_vault(vault)
        seed_subagent_profiles(vault, ["worker", "validator"])
        proposal = auto_improve_mutation_proposal_report("ops/scripts/example.py")["proposals"][0]

        def fake_refresh_reports(*_: object, **__: object) -> tuple[dict[str, object], dict[str, object]]:
            return {}, {"proposals": [proposal]}

        context = _incrementing_runtime_context(
            dt.datetime(2026, 4, 15, 0, 0, tzinfo=dt.UTC)
        )
        with (
            mock.patch(
                "ops.scripts.auto_improve_runtime._refresh_reports",
                side_effect=fake_refresh_reports,
            ),
            mock.patch(
                "ops.scripts.auto_improve_runtime.run_mechanism_experiment",
                side_effect=_fake_successful_mechanism_experiment,
            ),
            mock.patch("ops.scripts.auto_improve_runtime.time.monotonic", return_value=0.0),
        ):
            result = run_auto_improve_session(
                vault,
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                session_id="auto-session",
                max_proposals=1,
                max_minutes=90,
                max_consecutive_failures=2,
                executor_name="codex_exec",
                allow_learning_uncertain=True,
                context=context,
            )

        artifacts = _load_successful_auto_improve_artifacts(vault, result)
        session = artifacts["session"]
        run_artifact_fingerprint = copy.deepcopy(artifacts["run_artifact_fingerprint"])
        telemetry_sha256 = hashlib.sha256(_canonical_bytes(artifacts["telemetry"])).hexdigest()
        for artifact in run_artifact_fingerprint["artifacts"]:
            if artifact.get("artifact_role") == "run_telemetry":
                artifact["sha256"] = telemetry_sha256
        _assert_schema_valid(session, AUTO_IMPROVE_SESSION_SCHEMA_PATH)
        return {
            "result": result,
            "session": session,
            "routing_provenance_aggregate": artifacts["provenance_aggregate"],
            "promotion_decision_trends": artifacts["promotion_trends"],
            "run_artifact_fingerprint": run_artifact_fingerprint,
            "run_telemetry": artifacts["telemetry"],
            "runtime_events": {
                "run": artifacts["run_events"],
                "session": artifacts["session_events"],
            },
            "routing_reports": artifacts["routing_reports"],
        }


FACADES: dict[str, Callable[[], dict[str, object]]] = {
    "mutation_proposal": _mutation_proposal_payload,
    "release_evidence_dashboard": _dashboard_payload,
    "release_closeout_summary": _closeout_payload,
    "auto_improve_session_bundle": _auto_improve_bundle,
}


@pytest.mark.parametrize("facade_name", sorted(FACADES))
def test_runtime_hotspot_facade_golden_output_is_byte_stable(facade_name: str) -> None:
    first_payload = FACADES[facade_name]()
    second_payload = FACADES[facade_name]()
    first_bytes = _canonical_bytes(first_payload)
    second_bytes = _canonical_bytes(second_payload)

    assert first_bytes == second_bytes
    _assert_no_local_path_leak(first_payload)
    assert hashlib.sha256(first_bytes).hexdigest() == GOLDEN_DIGESTS[facade_name]
