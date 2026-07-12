from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import (
    read_json_object,
    resolve_repo_artifact_path,
)
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.test.trusted_ci_evidence_runtime import (
    BUNDLE_MANIFEST_MEMBER,
    COLLECTION_MEMBER,
    JUNIT_MEMBER,
    PAYLOAD_MEMBERS,
    SUMMARY_MEMBER,
    junit_test_count,
    semantic_digest,
    sha256_bytes,
    write_deterministic_member,
)

DEFAULT_SUMMARY = "ops/reports/test-execution-summary-full.json"
DEFAULT_COLLECTION = (
    "build/release-payloads/test-execution-summary-full.collection.json"
)
DEFAULT_JUNIT = "build/release-payloads/test-execution-summary-full.junit.xml"
DEFAULT_OUT = "build/trusted-ci/test-execution-summary-full-evidence.zip"
MANIFEST_SCHEMA = "ops/schemas/trusted-ci-evidence-bundle-manifest.schema.json"
SUMMARY_SCHEMA = "ops/schemas/test-execution-summary.schema.json"
COLLECTION_SCHEMA = "ops/schemas/test-execution-collection-manifest.schema.json"


def _required_file(vault: Path, value: str, *, label: str) -> Path:
    path = resolve_repo_artifact_path(vault, value, default_relative_path=value)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be an existing non-symlink file: {value}")
    return path


def _junit_summary_identity(summary: dict[str, Any]) -> dict[str, Any]:
    artifacts = summary.get("evidence_artifacts", [])
    matches = [
        item
        for item in artifacts
        if isinstance(item, dict) and item.get("kind") == "junit_xml"
    ]
    if len(matches) != 1:
        raise ValueError(
            "full summary must declare exactly one JUnit evidence artifact"
        )
    return matches[0]


def _validate_evidence(
    summary: dict[str, Any],
    collection: dict[str, Any],
    collection_bytes: bytes,
    junit: bytes,
) -> dict[str, int]:
    if (
        summary.get("status") != "pass"
        or summary.get("represents_full_suite") is not True
    ):
        raise ValueError("full summary must be passing full-suite evidence")
    for field in ("source_revision", "source_tree_fingerprint"):
        if summary.get(field) != collection.get(field):
            raise ValueError(f"summary/collection {field} mismatch")
    digest = summary.get("pytest_collect_nodeid_digest", {})
    if digest.get("status") != "collected":
        raise ValueError("full summary collection digest must be collected")
    if digest.get("sha256") != collection.get("nodeids_sha256"):
        raise ValueError("summary/collection nodeid digest mismatch")
    if digest.get("nodeid_count") != collection.get("nodeid_count"):
        raise ValueError("summary/collection nodeid count mismatch")
    if digest.get("manifest_sha256") != sha256_bytes(collection_bytes):
        raise ValueError("summary/collection manifest file digest mismatch")
    if digest.get("manifest_nodeids_sha256") != collection.get("nodeids_sha256"):
        raise ValueError("summary/collection manifest nodeid digest mismatch")
    if digest.get("source_revision") != collection.get("source_revision"):
        raise ValueError("summary/collection digest source revision mismatch")
    if digest.get("source_tree_fingerprint") != collection.get(
        "source_tree_fingerprint"
    ):
        raise ValueError("summary/collection digest source tree mismatch")
    junit_count = junit_test_count(junit)
    junit_identity = _junit_summary_identity(summary)
    if junit_identity.get("sha256") != sha256_bytes(junit):
        raise ValueError("summary/JUnit digest mismatch")
    if junit_identity.get("observed_count") != junit_count:
        raise ValueError("summary/JUnit test count mismatch")
    if junit_identity.get("consistency_status") != "pass":
        raise ValueError("summary/JUnit consistency is not passing")
    return {
        "collection_count": int(collection["nodeid_count"]),
        "junit_count": junit_count,
    }


def _load_bundle_inputs(
    vault: Path, *, summary_path: str, collection_path: str, junit_path: str
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    inputs = {
        SUMMARY_MEMBER: _required_file(vault, summary_path, label="summary"),
        COLLECTION_MEMBER: _required_file(
            vault, collection_path, label="collection manifest"
        ),
        JUNIT_MEMBER: _required_file(vault, junit_path, label="JUnit"),
    }
    payloads = {name: path.read_bytes() for name, path in inputs.items()}
    summary = read_json_object(inputs[SUMMARY_MEMBER])
    collection = read_json_object(inputs[COLLECTION_MEMBER])
    validate_or_raise(
        summary,
        load_schema_with_vault_override(vault, SUMMARY_SCHEMA),
        context="full summary schema validation failed",
    )
    validate_or_raise(
        collection,
        load_schema_with_vault_override(vault, COLLECTION_SCHEMA),
        context="collection manifest schema validation failed",
    )
    return payloads, summary, collection


def _bundle_manifest(
    summary: dict[str, Any],
    collection: dict[str, Any],
    payloads: dict[str, bytes],
    counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "$schema": MANIFEST_SCHEMA,
        "artifact_kind": "trusted_ci_full_suite_evidence_bundle_manifest",
        "schema_version": 1,
        "manifest_member": BUNDLE_MANIFEST_MEMBER,
        "members": [
            {
                "path": name,
                "sha256": sha256_bytes(payloads[name]),
                "size_bytes": len(payloads[name]),
            }
            for name in PAYLOAD_MEMBERS
        ],
        "source_revision": summary["source_revision"],
        "source_tree_fingerprint": summary["source_tree_fingerprint"],
        "semantic_command": summary["semantic_command"],
        "semantic_command_sha256": semantic_digest(summary["semantic_command"]),
        "toolchain_fingerprint": summary["toolchain_fingerprint"],
        "execution_environment": summary["execution_environment"],
        "collection": {
            "sha256": collection["nodeids_sha256"],
            "manifest_sha256": sha256_bytes(payloads[COLLECTION_MEMBER]),
            "count": counts["collection_count"],
        },
        "junit": {
            "sha256": sha256_bytes(payloads[JUNIT_MEMBER]),
            "count": counts["junit_count"],
        },
    }


def build_bundle(
    vault: Path,
    *,
    summary_path: str,
    collection_path: str,
    junit_path: str,
    out_path: str,
) -> Path:
    payloads, summary, collection = _load_bundle_inputs(
        vault,
        summary_path=summary_path,
        collection_path=collection_path,
        junit_path=junit_path,
    )
    counts = _validate_evidence(
        summary,
        collection,
        payloads[COLLECTION_MEMBER],
        payloads[JUNIT_MEMBER],
    )
    manifest = _bundle_manifest(summary, collection, payloads, counts)
    validate_or_raise(
        manifest,
        load_schema_with_vault_override(vault, MANIFEST_SCHEMA),
        context="bundle manifest schema validation failed",
    )
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    out = resolve_repo_artifact_path(vault, out_path, default_relative_path=DEFAULT_OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{out.name}.", suffix=".tmp", dir=out.parent
    )
    os.close(fd)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for name in PAYLOAD_MEMBERS:
                write_deterministic_member(archive, name, payloads[name])
            write_deterministic_member(archive, BUNDLE_MANIFEST_MEMBER, manifest_bytes)
        Path(temporary).replace(out)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build deterministic trusted-CI full-suite evidence ZIP."
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--summary", default=DEFAULT_SUMMARY)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--junit", default=DEFAULT_JUNIT)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    try:
        out = build_bundle(
            Path(args.vault).resolve(),
            summary_path=args.summary,
            collection_path=args.collection,
            junit_path=args.junit,
            out_path=args.out,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"trusted CI evidence bundle failed: {exc}\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
