from __future__ import annotations

import datetime as dt
import json
import stat
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.command_runtime import TimedProcessResult
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.test import trusted_ci_evidence_runtime as trusted_runtime
from ops.scripts.test.test_execution_aggregate_runtime import build_aggregate_report
from ops.scripts.test.test_execution_command_runtime import toolchain_fingerprint
from ops.scripts.test.test_execution_derivation_runtime import (
    build_collection_manifest,
    load_collection_manifest_digest,
    write_collection_manifest,
)
from ops.scripts.test.test_execution_evidence_runtime import (
    junit_artifact_identity,
    sha256_file,
)
from ops.scripts.test.test_execution_summary import build_report
from ops.scripts.test.trusted_ci_evidence_bundle import build_bundle
from ops.scripts.test.trusted_ci_evidence_import import import_bundle
from ops.scripts.test.trusted_ci_evidence_runtime import (
    BUNDLE_MANIFEST_MEMBER,
    COLLECTION_MEMBER,
    JUNIT_MEMBER,
    SUMMARY_MEMBER,
    read_strict_bundle,
    sha256_bytes,
    write_deterministic_member,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
]


def _context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC, clock=lambda: dt.datetime(2026, 7, 12, tzinfo=dt.UTC)
    )


def _result(*, subtests_passed: int = 0) -> TimedProcessResult:
    subtest_summary = f", {subtests_passed} subtests passed" if subtests_passed else ""
    return TimedProcessResult(
        args=[sys.executable, "-m", "pytest"],
        returncode=0,
        stdout=f"= 1 passed{subtest_summary} in 0.01s =",
        stderr="",
        timed_out=False,
        timeout_seconds=30,
        termination_reason="completed",
    )


def _ci_environment() -> dict[str, object]:
    return {
        "python_version": "3.12.10",
        "pytest_version": "8.4.1",
        "plugin_autoload_policy": {
            "env_var": "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            "value": "1",
            "autoload_disabled": True,
            "policy": "disabled",
        },
        "interpreter_path_class": "path_lookup",
        "toolchain_contract": {
            "status": "pass",
            "python_supported": True,
            "pytest_supported": True,
            "supported_python_major_minor": ["3.11", "3.12", "3.13", "3.14"],
            "minimum_pytest_major": 8,
            "release_evidence_effect": "eligible",
            "reason": "toolchain is eligible for release evidence",
        },
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _seed_evidence(vault: Path, *, subtests_passed: int = 0) -> Path:
    seed_minimal_vault(vault)
    (vault / "ops" / "test-lane-registry.json").write_bytes(
        (REPO_ROOT / "ops" / "test-lane-registry.json").read_bytes()
    )
    (vault / "tests").mkdir(exist_ok=True)
    (vault / "tests" / "test_sample.py").write_text(
        "def test_sample():\n    assert True\n", encoding="utf-8"
    )
    collection_path = (
        vault / "build/release-payloads/test-execution-summary-full.collection.json"
    )
    junit_path = vault / "build/release-payloads/test-execution-summary-full.junit.xml"
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    junit_total = 1 + subtests_passed
    subtest_property = (
        "<properties><property name='llmwiki.subtests_passed' "
        f"value='{subtests_passed}'/></properties>"
        if subtests_passed
        else ""
    )
    junit_path.write_text(
        f"<testsuite tests='{junit_total}'><testcase classname='sample' "
        f"name='test_sample'>{subtest_property}</testcase></testsuite>\n",
        encoding="utf-8",
    )
    lifecycle = {
        "status": "pass",
        "checked_at": "2026-07-12T00:00:00Z",
        "actual_deselected_count": 0,
        "max_allowed_deselected_count": 0,
        "over_budget": False,
        "expired_count": 0,
        "release_blocking_count": 0,
        "missing_lifecycle_count": 0,
        "duplicate_policy_entry_count": 0,
        "unused_policy_entry_count": 0,
        "risk_owner": "",
        "expires_at": "",
        "count_increase_gate_effect": "pass",
        "expiry_gate_effect": "pass",
        "next_action": "none",
        "blockers": [],
    }
    collection = build_collection_manifest(
        vault,
        suite="full-shard-1",
        semantic_command="-m pytest",
        nodeids=["tests/test_sample.py::test_sample"],
        selection_kind="full_suite",
        deselected_tests=[],
        deselection_lifecycle=lifecycle,
        context=_context(),
    )
    write_collection_manifest(vault, collection, collection_path)
    digest = load_collection_manifest_digest(vault, collection_path)
    junit = junit_artifact_identity(
        vault,
        junit_path,
        counts={
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
            "subtests_passed": subtests_passed,
        },
    )
    shard = build_report(
        vault,
        command=[sys.executable, "-m", "pytest"],
        result=_result(subtests_passed=subtests_passed),
        duration_ms=10,
        suite="full-shard-1",
        context=_context(),
        collect_nodeids=True,
        collect_nodeid_digest=digest,
        evidence_artifacts=[junit],
    )
    shard["execution_environment"] = _ci_environment()
    shard["toolchain_fingerprint"] = toolchain_fingerprint(
        shard["execution_environment"]
    )
    shard_dir = vault / "ops/reports/test-execution-summary-full-shards"
    _write_json(shard_dir / "full-suite-shard-1.json", shard)
    summary = build_aggregate_report(
        vault,
        shard_paths=[
            "ops/reports/test-execution-summary-full-shards/full-suite-shard-1.json"
        ],
        suite="full",
        context=_context(),
    )
    summary["execution_environment"] = _ci_environment()
    summary["toolchain_fingerprint"] = toolchain_fingerprint(
        summary["execution_environment"]
    )
    _write_json(vault / "ops/reports/test-execution-summary-full.json", summary)
    return build_bundle(
        vault,
        summary_path="ops/reports/test-execution-summary-full.json",
        collection_path="build/release-payloads/test-execution-summary-full.collection.json",
        junit_path="build/release-payloads/test-execution-summary-full.junit.xml",
        out_path="build/trusted-ci/evidence.zip",
    )


def _verification_json(bundle: Path, digest: str | None = None) -> str:
    return json.dumps(
        [
            {
                "attestation": {"bundle": "verified"},
                "verificationResult": {
                    "signature": {
                        "certificate": {"subjectAlternativeName": "trusted-workflow"}
                    },
                    "verifiedTimestamps": [{"type": "transparency-log"}],
                    "statement": {
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "subject": [
                            {
                                "name": bundle.name,
                                "digest": {"sha256": digest or sha256_file(bundle)},
                            }
                        ],
                    },
                },
            }
        ]
    )


def _run_import(
    vault: Path, bundle: Path, stdout: str | None = None, returncode: int = 0
) -> dict[str, object]:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=stdout or _verification_json(bundle),
        stderr="verification failed" if returncode else "",
    )
    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        return (
            completed
            if command[0] == "/usr/bin/gh"
            else real_run(command, *args, **kwargs)
        )

    with patch(
        "ops.scripts.test.trusted_ci_evidence_import.subprocess.run",
        side_effect=fake_run,
    ) as run:
        report = import_bundle(
            vault,
            bundle_path=bundle.relative_to(vault).as_posix(),
            out_path="tmp/import.json",
            gh_executable="/usr/bin/gh",
            context=_context(),
        )
    if returncode == 0:
        command = next(
            call.args[0]
            for call in run.call_args_list
            if call.args[0][0] == "/usr/bin/gh"
        )
        contract = json.loads((vault / "ops/test-lane-registry.json").read_text())[
            "trusted_ci_evidence"
        ]
        assert command == [
            "/usr/bin/gh",
            "attestation",
            "verify",
            str(bundle),
            "--repo",
            contract["repository"],
            "--signer-workflow",
            contract["signer_workflow"],
            "--source-digest",
            report["source_revision"],
            "--deny-self-hosted-runners",
            "--predicate-type",
            "https://slsa.dev/provenance/v1",
            "--format",
            "json",
        ]
    return report


def _rewrite_bundle(bundle: Path, mutator) -> None:
    members = read_strict_bundle(bundle)
    decoded = {
        name: json.loads(payload)
        for name, payload in members.items()
        if name.endswith(".json")
    }
    mutator(decoded)
    for name, payload in decoded.items():
        members[name] = (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode()
    manifest = decoded[BUNDLE_MANIFEST_MEMBER]
    for item in manifest["members"]:
        item["sha256"] = sha256_bytes(members[item["path"]])
        item["size_bytes"] = len(members[item["path"]])
    members[BUNDLE_MANIFEST_MEMBER] = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    with zipfile.ZipFile(bundle, "w") as archive:
        for name, payload in members.items():
            write_deterministic_member(archive, name, payload)


def test_bundle_is_deterministic_and_valid_import_is_diagnostic_only(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    bundle = _seed_evidence(vault)
    second = build_bundle(
        vault,
        summary_path="ops/reports/test-execution-summary-full.json",
        collection_path="build/release-payloads/test-execution-summary-full.collection.json",
        junit_path="build/release-payloads/test-execution-summary-full.junit.xml",
        out_path="build/trusted-ci/evidence-second.zip",
    )
    assert bundle.read_bytes() == second.read_bytes()
    report = _run_import(vault, bundle)
    assert report["status"] == "pass", (report["diagnostics"], report["checks"])
    assert report["authority_effect"] == "diagnostic_only_no_promotion"
    assert not (
        vault / "ops/reports/test-execution-summary-full-imported.json"
    ).exists()


def test_repository_contract_matches_hosted_python_workflow() -> None:
    contract = json.loads(
        (REPO_ROOT / "ops/test-lane-registry.json").read_text(encoding="utf-8")
    )["trusted_ci_evidence"]
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(
        encoding="utf-8"
    )
    setup_action = (REPO_ROOT / ".github/actions/setup-python-uv/action.yml").read_text(
        encoding="utf-8"
    )

    assert "uses: ./.github/actions/setup-python-uv" in workflow
    assert "python -m pip install -r" in setup_action
    assert ".venv" not in setup_action
    assert contract["environment"]["interpreter_path_class"] == "path_lookup"


def test_bundle_and_import_use_junit_suite_totals_for_subtests(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    bundle = _seed_evidence(vault, subtests_passed=2)

    members = read_strict_bundle(bundle)
    manifest = json.loads(members[BUNDLE_MANIFEST_MEMBER])
    summary = json.loads(members[SUMMARY_MEMBER])
    report = _run_import(vault, bundle)

    assert manifest["junit"]["count"] == 3
    assert summary["counts"]["subtests_passed"] == 2
    assert report["status"] == "pass", (report["diagnostics"], report["checks"])


@pytest.mark.parametrize(
    ("code", "mutator"),
    [
        (
            "source_revision",
            lambda values: values[SUMMARY_MEMBER].update(source_revision="wrong"),
        ),
        (
            "source_tree_fingerprint",
            lambda values: values[SUMMARY_MEMBER].update(
                source_tree_fingerprint="wrong"
            ),
        ),
        (
            "semantic_command",
            lambda values: values[SUMMARY_MEMBER].update(
                semantic_command="wrong command"
            ),
        ),
        (
            "toolchain_environment",
            lambda values: values[SUMMARY_MEMBER]["execution_environment"].update(
                python_version="3.13.0"
            ),
        ),
        ("collection", lambda values: values[COLLECTION_MEMBER].update(nodeid_count=2)),
        (
            "junit",
            lambda values: values[BUNDLE_MANIFEST_MEMBER]["junit"].update(count=2),
        ),
    ],
)
def test_import_rejects_tampered_evidence_binding(
    tmp_path: Path, code: str, mutator
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    bundle = _seed_evidence(vault)
    _rewrite_bundle(bundle, mutator)
    report = _run_import(vault, bundle)
    assert report["status"] == "fail"
    assert code in {
        item["code"] for item in report["checks"] if item["status"] == "fail"
    }


def test_import_rejects_forged_verification_json_and_wrong_subject(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    bundle = _seed_evidence(vault)
    forged = json.dumps(
        [{"attestation": {}, "verificationResult": {"statement": {"subject": []}}}]
    )
    assert _run_import(vault, bundle, forged)["status"] == "fail"
    assert (
        _run_import(vault, bundle, _verification_json(bundle, "0" * 64))["status"]
        == "fail"
    )


@pytest.mark.parametrize("failure", ["missing_gh", "nonzero"])
def test_import_reports_gh_failures(tmp_path: Path, failure: str) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    bundle = _seed_evidence(vault)
    if failure == "missing_gh":
        with patch(
            "ops.scripts.test.trusted_ci_evidence_import.shutil.which",
            return_value=None,
        ):
            report = import_bundle(
                vault,
                bundle_path=bundle.relative_to(vault).as_posix(),
                out_path="tmp/import.json",
                context=_context(),
            )
    else:
        report = _run_import(vault, bundle, returncode=1)
    assert report["status"] == "fail"
    assert (vault / "tmp/import.json").is_file()


@pytest.mark.parametrize(
    "reason", ["signer workflow mismatch", "source digest mismatch"]
)
def test_import_treats_gh_identity_filter_failures_as_failures(
    tmp_path: Path, reason: str
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    bundle = _seed_evidence(vault)
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr=reason
    )
    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        return (
            completed
            if command[0] == "/usr/bin/gh"
            else real_run(command, *args, **kwargs)
        )

    with patch(
        "ops.scripts.test.trusted_ci_evidence_import.subprocess.run",
        side_effect=fake_run,
    ):
        report = import_bundle(
            vault,
            bundle_path=bundle.relative_to(vault).as_posix(),
            out_path="tmp/import.json",
            gh_executable="/usr/bin/gh",
            context=_context(),
        )
    assert report["status"] == "fail"
    assert reason in report["diagnostics"][0]


@pytest.mark.parametrize(
    "kind", ["traversal", "symlink", "duplicate", "undeclared", "missing"]
)
def test_strict_bundle_reader_rejects_unsafe_zip_shapes(
    tmp_path: Path, kind: str
) -> None:
    archive_path = tmp_path / "unsafe.zip"
    names = [SUMMARY_MEMBER, COLLECTION_MEMBER, JUNIT_MEMBER, BUNDLE_MANIFEST_MEMBER]
    with zipfile.ZipFile(archive_path, "w") as archive:
        if kind == "traversal":
            archive.writestr("../summary.json", b"x")
        elif kind == "symlink":
            info = zipfile.ZipInfo(SUMMARY_MEMBER)
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"target")
        else:
            selected = names[:-1] if kind == "missing" else names
            for name in selected:
                archive.writestr(name, b"{}")
            if kind == "duplicate":
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive.writestr(SUMMARY_MEMBER, b"{}")
            if kind == "undeclared":
                archive.writestr("extra.txt", b"x")
    with pytest.raises(ValueError):
        read_strict_bundle(archive_path)


def test_strict_bundle_reader_rejects_oversized_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_path = tmp_path / "oversized.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name in (
            SUMMARY_MEMBER,
            COLLECTION_MEMBER,
            JUNIT_MEMBER,
            BUNDLE_MANIFEST_MEMBER,
        ):
            archive.writestr(name, b"{}")
    monkeypatch.setattr(trusted_runtime, "MAX_MEMBER_UNCOMPRESSED_BYTES", 1)

    with pytest.raises(ValueError, match="exceeds size limit"):
        read_strict_bundle(archive_path)
