from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_envelope_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    resolve_repo_artifact_path,
    write_schema_backed_report,
)
from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.test.test_execution_derivation_runtime import (
    validate_collection_manifest_payload,
)
from ops.scripts.test.trusted_ci_evidence_runtime import (
    BUNDLE_MANIFEST_MEMBER,
    COLLECTION_MEMBER,
    JUNIT_MEMBER,
    PAYLOAD_MEMBERS,
    SUMMARY_MEMBER,
    json_object,
    junit_testcase_count,
    read_strict_bundle,
    semantic_digest,
    sha256_bytes,
    sha256_file,
    validate_embedded_json,
)

DEFAULT_BUNDLE = "build/trusted-ci/test-execution-summary-full-evidence.zip"
DEFAULT_OUT = "tmp/trusted-ci-evidence-import-report.json"
REGISTRY_PATH = "ops/test-lane-registry.json"
REGISTRY_SCHEMA = "ops/schemas/test-lane-registry.schema.json"
MANIFEST_SCHEMA = "ops/schemas/trusted-ci-evidence-bundle-manifest.schema.json"
SUMMARY_SCHEMA = "ops/schemas/test-execution-summary.schema.json"
COLLECTION_SCHEMA = "ops/schemas/test-execution-collection-manifest.schema.json"
REPORT_SCHEMA = "ops/schemas/trusted-ci-evidence-import-report.schema.json"
PRODUCER = "ops.scripts.test.trusted_ci_evidence_import"
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"


def _registry_contract(vault: Path) -> dict[str, Any]:
    registry = json.loads((vault / REGISTRY_PATH).read_text(encoding="utf-8"))
    validate_or_raise(
        registry,
        load_schema_with_vault_override(vault, REGISTRY_SCHEMA),
        context="test lane registry validation failed",
    )
    contract = registry.get("trusted_ci_evidence")
    if not isinstance(contract, dict):
        raise ValueError("test lane registry trusted_ci_evidence contract is missing")
    return contract


def _gh_command(
    gh: str, bundle: Path, contract: dict[str, Any], revision: str
) -> list[str]:
    return [
        gh,
        "attestation",
        "verify",
        str(bundle),
        "--repo",
        str(contract["repository"]),
        "--signer-workflow",
        str(contract["signer_workflow"]),
        "--source-digest",
        revision,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]


def _verified_subject(stdout: str) -> str:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"gh verification output is not JSON: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError("gh verification JSON must be a non-empty array")
    subjects: set[str] = set()
    for item in payload:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("attestation"), dict)
            or not item["attestation"]
        ):
            raise ValueError(
                "gh verification JSON is missing the verified attestation bundle"
            )
        result = item.get("verificationResult")
        if not isinstance(result, dict):
            raise ValueError("gh verification JSON is missing verificationResult")
        signature = result.get("signature")
        if (
            not isinstance(signature, dict)
            or not isinstance(signature.get("certificate"), dict)
            or not signature["certificate"]
        ):
            raise ValueError("gh verification JSON is missing the verified certificate")
        if (
            not isinstance(result.get("verifiedTimestamps"), list)
            or not result["verifiedTimestamps"]
        ):
            raise ValueError("gh verification JSON is missing verified timestamps")
        statement = result.get("statement")
        if (
            not isinstance(statement, dict)
            or statement.get("predicateType") != PREDICATE_TYPE
        ):
            raise ValueError("gh verification JSON has an unexpected predicate type")
        statement_subjects = statement.get("subject")
        if not isinstance(statement_subjects, list):
            raise ValueError("gh verification JSON statement subject must be an array")
        for subject in statement_subjects:
            if not isinstance(subject, dict):
                continue
            digest = subject.get("digest")
            if isinstance(digest, dict) and isinstance(digest.get("sha256"), str):
                subjects.add(digest["sha256"])
    if len(subjects) != 1:
        raise ValueError(
            "gh verification JSON must bind exactly one SHA256 subject for the bundle"
        )
    subject = next(iter(subjects))
    if len(subject) != 64 or any(character not in "0123456789abcdef" for character in subject):
        raise ValueError("gh verification JSON subject SHA256 is malformed")
    return subject


def _environment_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    plugin = actual.get("plugin_autoload_policy", {})
    toolchain = actual.get("toolchain_contract", {})
    python_version = str(actual.get("python_version", ""))
    pytest_version = str(actual.get("pytest_version", "0"))
    try:
        pytest_major = int(pytest_version.split(".", 1)[0])
    except ValueError:
        return False
    return all(
        (
            ".".join(python_version.split(".")[:2]) == expected["python_major_minor"],
            pytest_major >= int(expected["minimum_pytest_major"]),
            plugin.get("autoload_disabled") is expected["plugin_autoload_disabled"],
            actual.get("interpreter_path_class") == expected["interpreter_path_class"],
            toolchain.get("status") == expected["toolchain_status"],
            toolchain.get("release_evidence_effect")
            == expected["release_evidence_effect"],
        )
    )


def _check(code: str, condition: bool, message: str) -> dict[str, str]:
    return {"code": code, "status": "pass" if condition else "fail", "message": message}


def _load_embedded_evidence(
    vault: Path, members: dict[str, bytes]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = json_object(members[BUNDLE_MANIFEST_MEMBER], label="bundle manifest")
    summary = json_object(members[SUMMARY_MEMBER], label="full summary")
    collection = json_object(members[COLLECTION_MEMBER], label="collection manifest")
    validate_embedded_json(vault, manifest, MANIFEST_SCHEMA, label="bundle manifest")
    validate_embedded_json(vault, summary, SUMMARY_SCHEMA, label="full summary")
    validate_embedded_json(
        vault, collection, COLLECTION_SCHEMA, label="collection manifest"
    )
    return manifest, summary, collection


def _member_identity_checks(
    members: dict[str, bytes], manifest: dict[str, Any]
) -> list[dict[str, str]]:
    entries = manifest["members"]
    paths = [item["path"] for item in entries]
    inventory_ok = len(paths) == len(set(paths)) and set(paths) == set(PAYLOAD_MEMBERS)
    identity_ok = inventory_ok and all(
        item["sha256"] == sha256_bytes(members[item["path"]])
        and item["size_bytes"] == len(members[item["path"]])
        for item in entries
    )
    return [
        _check(
            "bundle_member_inventory",
            inventory_ok,
            "bundle manifest declares exactly the three evidence payload members",
        ),
        _check(
            "bundle_member_identity",
            identity_ok,
            "manifest member sizes and SHA256 values match ZIP bytes",
        ),
    ]


def _collection_check(
    manifest: dict[str, Any], summary: dict[str, Any], collection: dict[str, Any]
) -> dict[str, str]:
    digest = summary["pytest_collect_nodeid_digest"]
    valid = (
        not validate_collection_manifest_payload(collection)
        and manifest["collection"]
        == {
            "sha256": collection["nodeids_sha256"],
            "count": collection["nodeid_count"],
        }
        and digest.get("sha256") == collection["nodeids_sha256"]
        and digest.get("nodeid_count") == collection["nodeid_count"]
    )
    return _check(
        "collection",
        valid,
        "collection digest and count match manifest, summary, and nodeids",
    )


def _junit_check(
    members: dict[str, bytes], manifest: dict[str, Any], summary: dict[str, Any]
) -> dict[str, str]:
    junit_sha = sha256_bytes(members[JUNIT_MEMBER])
    junit_count = junit_testcase_count(members[JUNIT_MEMBER])
    artifacts = [
        item
        for item in summary["evidence_artifacts"]
        if item.get("kind") == "junit_xml"
    ]
    valid = (
        len(artifacts) == 1
        and artifacts[0].get("sha256") == junit_sha
        and artifacts[0].get("observed_count") == junit_count
        and artifacts[0].get("consistency_status") == "pass"
        and manifest["junit"] == {"sha256": junit_sha, "count": junit_count}
    )
    return _check(
        "junit",
        valid,
        "JUnit digest and testcase count match manifest and summary",
    )


def _contract_checks(
    vault: Path,
    manifest: dict[str, Any],
    summary: dict[str, Any],
    collection: dict[str, Any],
    contract: dict[str, Any],
) -> list[dict[str, str]]:
    revision = resolve_source_revision(vault).revision
    tree = release_source_tree_fingerprint(vault)
    command_ok = (
        manifest["semantic_command"]
        == summary["semantic_command"]
        == contract["semantic_command"]
        and manifest["semantic_command_sha256"]
        == semantic_digest(manifest["semantic_command"])
    )
    environment_ok = (
        manifest["toolchain_fingerprint"] == summary["toolchain_fingerprint"]
        and manifest["execution_environment"] == summary["execution_environment"]
        and _environment_matches(
            summary["execution_environment"], contract["environment"]
        )
    )
    return [
        _check(
            "source_revision",
            manifest["source_revision"]
            == summary["source_revision"]
            == collection["source_revision"]
            == revision,
            "embedded evidence source revision matches current revision",
        ),
        _check(
            "source_tree_fingerprint",
            manifest["source_tree_fingerprint"]
            == summary["source_tree_fingerprint"]
            == collection["source_tree_fingerprint"]
            == tree,
            "embedded evidence source tree matches current tree",
        ),
        _check(
            "semantic_command",
            command_ok,
            "semantic command and digest match registry contract",
        ),
        _check(
            "toolchain_environment",
            environment_ok,
            "toolchain and execution environment match registry contract",
        ),
        _check(
            "full_summary",
            summary["suite"] == contract["summary_suite"]
            and summary["status"] == "pass"
            and summary["represents_full_suite"] is True,
            "summary is passing full-suite evidence",
        ),
    ]


def _embedded_checks(
    vault: Path, members: dict[str, bytes], contract: dict[str, Any]
) -> list[dict[str, str]]:
    manifest, summary, collection = _load_embedded_evidence(vault, members)
    return [
        *_member_identity_checks(members, manifest),
        *_contract_checks(vault, manifest, summary, collection, contract),
        _collection_check(manifest, summary, collection),
        _junit_check(members, manifest, summary),
    ]


def _verify_attestation(
    vault: Path,
    bundle: Path,
    contract: dict[str, Any],
    bundle_sha: str,
    gh_executable: str | None,
) -> tuple[str, list[dict[str, str]]]:
    gh = gh_executable or shutil.which("gh")
    if not gh:
        raise ValueError("gh executable is unavailable")
    revision = resolve_source_revision(vault).revision
    completed = subprocess.run(
        _gh_command(gh, bundle, contract, revision),
        cwd=vault,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"gh attestation verify failed with exit {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    subject = _verified_subject(completed.stdout)
    return subject, [
        _check(
            "attested_subject",
            subject == bundle_sha,
            "attested subject SHA256 matches the ZIP bytes",
        )
    ]


def _write_import_report(
    vault: Path,
    *,
    bundle: Path,
    bundle_path: str,
    bundle_sha: str,
    out_path: str,
    generated_at: str,
    contract: dict[str, Any],
    verified_subject: str,
    checks: list[dict[str, str]],
    diagnostics: list[str],
) -> dict[str, Any]:
    status = (
        "pass"
        if not diagnostics
        and checks
        and all(item["status"] == "pass" for item in checks)
        else "fail"
    )
    if status == "fail" and not diagnostics:
        diagnostics.extend(
            item["message"] for item in checks if item["status"] == "fail"
        )
    revision = resolve_source_revision(vault).revision
    _policy, resolved_policy_path = load_policy(vault, None)
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind="trusted_ci_full_suite_evidence_import_report",
        producer=PRODUCER,
        source_command=(
            f"python -m {PRODUCER} --vault . --bundle {bundle_path} --out {out_path}"
        ),
        resolved_policy_path=resolved_policy_path,
        schema_path=REPORT_SCHEMA,
        source_paths=[
            "ops/scripts/test/trusted_ci_evidence_import.py",
            "ops/scripts/test/trusted_ci_evidence_runtime.py",
        ],
        text_inputs={
            "bundle_path": bundle_path,
            "bundle_sha256": bundle_sha or "missing",
        },
    )
    report = {
        **envelope,
        "status": status,
        "authority_effect": "diagnostic_only_no_promotion",
        "bundle": {
            "path": bundle_path,
            "sha256": bundle_sha,
            "size_bytes": bundle.stat().st_size if bundle_sha else 0,
        },
        "attestation": {
            "repository": str(contract.get("repository", "unknown")),
            "signer_workflow": str(contract.get("signer_workflow", "unknown")),
            "source_digest": revision,
            "deny_self_hosted_runners": True,
            "verified_subject_sha256": verified_subject,
        },
        "checks": checks,
        "diagnostics": diagnostics,
    }
    write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=REPORT_SCHEMA,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="trusted CI evidence import report schema validation failed",
        )
    )
    return report


def import_bundle(
    vault: Path,
    *,
    bundle_path: str,
    out_path: str,
    gh_executable: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    runtime = context or RuntimeContext.from_policy({})
    generated_at = runtime.isoformat_z()
    bundle = resolve_repo_artifact_path(
        vault, bundle_path, default_relative_path=DEFAULT_BUNDLE
    )
    contract: dict[str, Any] = {}
    checks: list[dict[str, str]] = []
    diagnostics: list[str] = []
    verified_subject = ""
    bundle_sha = (
        sha256_file(bundle) if bundle.is_file() and not bundle.is_symlink() else ""
    )
    try:
        contract = _registry_contract(vault)
        if not bundle_sha:
            raise ValueError("bundle must be an existing non-symlink file")
        verified_subject, attestation_checks = _verify_attestation(
            vault, bundle, contract, bundle_sha, gh_executable
        )
        checks.extend(attestation_checks)
        checks.extend(_embedded_checks(vault, read_strict_bundle(bundle), contract))
    except (OSError, ValueError) as exc:
        diagnostics.append(str(exc))
    return _write_import_report(
        vault,
        bundle=bundle,
        bundle_path=bundle_path,
        bundle_sha=bundle_sha,
        out_path=out_path,
        generated_at=generated_at,
        contract=contract,
        verified_subject=verified_subject,
        checks=checks,
        diagnostics=diagnostics,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify and diagnose a trusted-CI full-suite evidence ZIP without promotion."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    report = import_bundle(
        Path(args.vault).resolve(), bundle_path=args.bundle, out_path=args.out
    )
    print(
        json.dumps(
            {"status": report["status"], "diagnostics": report["diagnostics"]},
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
