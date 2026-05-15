from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .output_runtime import display_path, resolve_repo_output_path, write_output_text
from .schema_runtime import load_schema_with_vault_override, validate_or_raise


@dataclass(frozen=True)
class SchemaBackedReportWriteRequest:
    vault: Path
    payload: Mapping[str, Any]
    schema_path: str
    out_path: str | Path | None
    default_relative_path: str
    context: str = ""
    instance_path: str = "$"
    trailing_newline: bool = True


@dataclass(frozen=True)
class ReportWriterKernelRequest:
    vault: Path
    payload: Mapping[str, Any]
    schema_path: str
    out_path: str | Path | None
    default_relative_path: str
    artifact_kind: str | None = None
    producer: str | None = None
    output_role: str = "canonical_report"
    context: str = ""
    instance_path: str = "$"
    trailing_newline: bool = True


CANONICAL_REPORT_ENVELOPE_FIELDS = (
    "$schema",
    "artifact_kind",
    "generated_at",
    "producer",
    "source_command",
    "source_revision",
    "source_tree_fingerprint",
    "input_fingerprints",
    "schema_version",
    "artifact_status",
    "retention_policy",
    "encoding",
    "currentness",
)


def resolve_repo_artifact_path(
    vault: Path,
    out_path: str | Path | None,
    *,
    default_relative_path: str,
) -> Path:
    return resolve_repo_output_path(
        vault,
        out_path,
        default_relative_path=default_relative_path,
    )


def resolve_schema_backed_report_output_path(
    vault: Path,
    out_path: str | Path | None,
    *,
    default_relative_path: str,
) -> Path:
    return resolve_repo_artifact_path(
        vault,
        out_path,
        default_relative_path=default_relative_path,
    )


def read_json_object(path: Path, *, context: str | None = None) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        label = context or path.as_posix()
        raise ValueError(f"{label}: JSON root must be an object")
    return payload


def load_optional_json_object_with_diagnostics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "path": path.as_posix(),
        "missing": False,
        "decode_error": False,
        "type_error": False,
        "message": "",
        "status": "ok",
    }
    if not path.exists():
        diagnostics.update(
            {
                "missing": True,
                "message": "file does not exist",
                "status": "missing",
            }
        )
        return {}, diagnostics
    try:
        return read_json_object(path), diagnostics
    except json.JSONDecodeError as exc:
        diagnostics.update(
            {
                "decode_error": True,
                "message": str(exc),
                "status": "decode_error",
            }
        )
    except ValueError as exc:
        diagnostics.update(
            {
                "type_error": True,
                "message": str(exc),
                "status": "type_error",
            }
        )
    except OSError as exc:
        diagnostics.update(
            {
                "message": f"{exc.__class__.__name__}: {exc}",
                "status": "read_error",
            }
        )
    return {}, diagnostics


def load_optional_json_object(path: Path) -> dict[str, Any]:
    payload, _diagnostics = load_optional_json_object_with_diagnostics(path)
    return payload


def describe_output_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {
            "exists": False,
            "size_bytes": 0,
            "sha256": "",
        }

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return {
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def serialized_json(payload: Any, *, trailing_newline: bool = False) -> str:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"{text}\n" if trailing_newline else text


def write_json_object(path: Path, payload: Any, *, trailing_newline: bool = False) -> Path:
    destination = write_output_text(path, serialized_json(payload, trailing_newline=trailing_newline))
    _sync_generated_at_mtime(destination, payload)
    return destination


def _sync_generated_at_mtime(path: Path, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    generated_at = str(payload.get("generated_at", "")).strip()
    if not generated_at:
        return
    try:
        generated_dt = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return
    if generated_dt.tzinfo is None:
        generated_dt = generated_dt.replace(tzinfo=dt.timezone.utc)
    timestamp = generated_dt.astimezone(dt.timezone.utc).timestamp()
    os.utime(path, (timestamp, timestamp))


def write_schema_validated_json(
    path: Path,
    payload: Any,
    schema: dict[str, Any],
    *,
    context: str,
    instance_path: str = "$",
    trailing_newline: bool = False,
) -> Path:
    validate_or_raise(payload, schema, context=context, path=instance_path)
    return write_json_object(path, payload, trailing_newline=trailing_newline)


def write_schema_backed_report(request: SchemaBackedReportWriteRequest) -> Path:
    destination = resolve_schema_backed_report_output_path(
        request.vault,
        request.out_path,
        default_relative_path=request.default_relative_path,
    )
    schema = load_schema_with_vault_override(request.vault, request.schema_path)
    context = request.context or f"schema validation failed for {display_path(request.vault, destination)}"
    return write_schema_validated_json(
        destination,
        request.payload,
        schema,
        context=context,
        instance_path=request.instance_path,
        trailing_newline=request.trailing_newline,
    )


def _require_report_field(payload: Mapping[str, Any], field: str) -> Any:
    value = payload.get(field)
    if value is None:
        raise ValueError(f"canonical report envelope missing field: {field}")
    return value


def _require_nonempty_report_text(payload: Mapping[str, Any], field: str) -> str:
    value = _require_report_field(payload, field)
    text = str(value).strip() if isinstance(value, str) else ""
    if not text:
        raise ValueError(f"canonical report envelope field must be non-empty string: {field}")
    return text


def _validate_canonical_report_kernel(request: ReportWriterKernelRequest) -> None:
    payload = request.payload
    missing = [field for field in CANONICAL_REPORT_ENVELOPE_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"canonical report envelope missing fields: {', '.join(missing)}")
    if request.artifact_kind is not None and payload.get("artifact_kind") != request.artifact_kind:
        raise ValueError(
            f"canonical report artifact_kind={payload.get('artifact_kind')!r}; "
            f"expected {request.artifact_kind!r}"
        )
    if request.producer is not None and payload.get("producer") != request.producer:
        raise ValueError(
            f"canonical report producer={payload.get('producer')!r}; "
            f"expected {request.producer!r}"
        )
    for field in (
        "$schema",
        "artifact_kind",
        "generated_at",
        "producer",
        "source_command",
        "source_revision",
        "source_tree_fingerprint",
        "encoding",
    ):
        _require_nonempty_report_text(payload, field)
    input_fingerprints = _require_report_field(payload, "input_fingerprints")
    if not isinstance(input_fingerprints, Mapping) or not input_fingerprints:
        raise ValueError("canonical report envelope input_fingerprints must be a non-empty object")
    currentness = _require_report_field(payload, "currentness")
    if not isinstance(currentness, Mapping):
        raise ValueError("canonical report envelope currentness must be an object")
    if currentness.get("status") != "current":
        raise ValueError(
            f"canonical report currentness.status={currentness.get('status')!r}; expected 'current'"
        )
    if not str(currentness.get("checked_at", "")).strip():
        raise ValueError("canonical report currentness.checked_at must be non-empty")
    if payload.get("artifact_status") != "current":
        raise ValueError(
            f"canonical report artifact_status={payload.get('artifact_status')!r}; expected 'current'"
        )
    if payload.get("retention_policy") != "canonical_report":
        raise ValueError(
            f"canonical report retention_policy={payload.get('retention_policy')!r}; "
            "expected 'canonical_report'"
        )


def write_report_with_kernel(request: ReportWriterKernelRequest) -> Path:
    if request.output_role == "canonical_report":
        _validate_canonical_report_kernel(request)
    else:
        raise ValueError(f"unsupported report writer output_role: {request.output_role}")
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=request.vault,
            payload=request.payload,
            schema_path=request.schema_path,
            out_path=request.out_path,
            default_relative_path=request.default_relative_path,
            context=request.context,
            instance_path=request.instance_path,
            trailing_newline=request.trailing_newline,
        )
    )


def schema_path_from_payload(payload: dict[str, Any], *, override: str | None = None) -> str:
    schema_path = (override or str(payload.get("$schema", ""))).strip()
    if not schema_path:
        raise ValueError("canonical artifact candidate is missing $schema")
    return schema_path


def promote_schema_validated_json(
    vault: Path,
    *,
    candidate_path: Path,
    destination_path: Path,
    schema_path: str | None = None,
    expected_artifact_kind: str | None = None,
    expected_producer: str | None = None,
    context: str,
    trailing_newline: bool = True,
) -> Path:
    payload = read_json_object(candidate_path, context=candidate_path.as_posix())
    resolved_schema_path = schema_path_from_payload(payload, override=schema_path)
    if expected_artifact_kind is not None and payload.get("artifact_kind") != expected_artifact_kind:
        raise ValueError(
            f"{candidate_path.as_posix()}: artifact_kind={payload.get('artifact_kind')!r}; "
            f"expected {expected_artifact_kind!r}"
        )
    if expected_producer is not None and payload.get("producer") != expected_producer:
        raise ValueError(
            f"{candidate_path.as_posix()}: producer={payload.get('producer')!r}; "
            f"expected {expected_producer!r}"
        )
    schema = load_schema_with_vault_override(vault, resolved_schema_path)
    return write_schema_validated_json(
        destination_path,
        payload,
        schema,
        context=context,
        trailing_newline=trailing_newline,
    )


def write_vault_schema_validated_json(
    vault: Path,
    rel_path: str,
    payload: dict[str, Any],
    schema_rel_path: str,
    *,
    context: str,
    trailing_newline: bool = False,
) -> str:
    schema = load_schema_with_vault_override(vault, schema_rel_path)
    write_schema_validated_json(
        vault / rel_path,
        payload,
        schema,
        context=context,
        trailing_newline=trailing_newline,
    )
    return rel_path
