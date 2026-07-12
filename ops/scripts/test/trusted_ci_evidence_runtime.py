from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.test.test_execution_evidence_runtime import (
    junit_test_count_from_xml,
)

BUNDLE_MANIFEST_MEMBER = "trusted-ci-evidence-bundle-manifest.json"
SUMMARY_MEMBER = "test-execution-summary-full.json"
COLLECTION_MEMBER = "test-execution-summary-full.collection.json"
JUNIT_MEMBER = "test-execution-summary-full.junit.xml"
PAYLOAD_MEMBERS = (SUMMARY_MEMBER, COLLECTION_MEMBER, JUNIT_MEMBER)
EXPECTED_MEMBERS = frozenset((*PAYLOAD_MEMBERS, BUNDLE_MANIFEST_MEMBER))
DETERMINISTIC_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_MEMBER_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_BUNDLE_UNCOMPRESSED_BYTES = 256 * 1024 * 1024


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def junit_test_count(payload: bytes) -> int:
    count = junit_test_count_from_xml(payload)
    if count is None:
        raise ValueError("JUnit XML is unreadable")
    return count


def safe_zip_member_name(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe ZIP member path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value != path.as_posix()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"unsafe ZIP member path: {value!r}")
    return value


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF)


def read_strict_bundle(bundle_path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            members: dict[str, bytes] = {}
            total_size = 0
            for info in archive.infolist():
                name = safe_zip_member_name(info.filename)
                if info.is_dir():
                    raise ValueError(f"directory ZIP member is not allowed: {name}")
                if _is_symlink(info):
                    raise ValueError(f"symlink ZIP member is not allowed: {name}")
                if name in members:
                    raise ValueError(f"duplicate ZIP member: {name}")
                if name not in EXPECTED_MEMBERS:
                    raise ValueError(f"undeclared ZIP member: {name}")
                if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                    raise ValueError(f"ZIP member exceeds size limit: {name}")
                total_size += info.file_size
                if total_size > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                    raise ValueError("ZIP bundle exceeds total uncompressed size limit")
                payload = archive.read(info)
                if len(payload) != info.file_size:
                    raise ValueError(f"ZIP member size metadata mismatch: {name}")
                members[name] = payload
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid ZIP evidence bundle: {exc}") from exc
    missing = sorted(EXPECTED_MEMBERS.difference(members))
    if missing:
        raise ValueError(f"missing ZIP members: {', '.join(missing)}")
    return members


def json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def validate_embedded_json(
    vault: Path, payload: dict[str, Any], schema_path: str, *, label: str
) -> None:
    schema = load_schema_with_vault_override(vault, schema_path)
    validate_or_raise(payload, schema, context=f"{label} schema validation failed")


def write_deterministic_member(
    archive: zipfile.ZipFile, name: str, payload: bytes
) -> None:
    info = zipfile.ZipInfo(safe_zip_member_name(name), DETERMINISTIC_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, payload)
