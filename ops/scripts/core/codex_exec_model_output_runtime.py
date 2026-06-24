from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .schema_constants_runtime import EXECUTOR_REPORT_SCHEMA_PATH
from .schema_runtime import load_schema, validate_with_schema

EXECUTOR_REPORT_SCHEMA = EXECUTOR_REPORT_SCHEMA_PATH
ALLOWED_MODEL_OUTPUT_STATUSES = frozenset({"pass", "fail"})


class ModelOutputRequest(Protocol):
    @property
    def artifact_root(self) -> Path: ...

    @property
    def run_id(self) -> str: ...

    @property
    def role(self) -> str: ...

    @property
    def scope_freeze(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModelOutputRead:
    payload: dict[str, Any] | None
    status: str
    note: str
    raw_bytes: bytes | None = None


def scope_freeze_input_digest(scope_freeze: dict[str, Any]) -> str:
    normalized = json.dumps(scope_freeze, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _invalid_model_output(
    model_output: ModelOutputRead,
    *,
    status: str,
    note: str,
) -> ModelOutputRead:
    return ModelOutputRead(
        payload=None,
        status=status,
        note=note,
        raw_bytes=model_output.raw_bytes,
    )


def validate_model_output_contract(
    model_output: ModelOutputRead,
    *,
    request: ModelOutputRequest,
) -> ModelOutputRead:
    if model_output.payload is None:
        return model_output
    payload = model_output.payload
    schema_errors = validate_with_schema(
        payload,
        load_schema(request.artifact_root / EXECUTOR_REPORT_SCHEMA),
    )
    if schema_errors:
        return _invalid_model_output(
            model_output,
            status="schema_invalid",
            note=(
                "codex exec model output failed executor-report schema validation: "
                f"{schema_errors[0]}"
            ),
        )
    if "status" not in payload:
        return _invalid_model_output(
            model_output,
            status="missing_status",
            note="codex exec model output omitted required status field",
        )
    returned_status = str(payload.get("status", "")).strip()
    if returned_status not in ALLOWED_MODEL_OUTPUT_STATUSES:
        return _invalid_model_output(
            model_output,
            status="invalid_status",
            note="codex exec model output status must be pass or fail",
        )
    if str(payload.get("run_id", "")).strip() != request.run_id:
        return _invalid_model_output(
            model_output,
            status="identity_mismatch",
            note="codex exec model output run_id does not match request",
        )
    if str(payload.get("role", "")).strip() != request.role:
        return _invalid_model_output(
            model_output,
            status="identity_mismatch",
            note="codex exec model output role does not match request",
        )
    expected_digest = scope_freeze_input_digest(request.scope_freeze)
    if str(payload.get("input_digest", "")).strip() != expected_digest:
        return _invalid_model_output(
            model_output,
            status="identity_mismatch",
            note="codex exec model output input_digest does not match scope freeze",
        )
    return model_output


def read_model_output(path: Path) -> ModelOutputRead:
    if not path.exists() and not path.is_symlink():
        return ModelOutputRead(
            payload=None,
            status="missing",
            note=f"codex exec completed without model output: {path.name} was not written",
        )
    try:
        path_stat = path.lstat()
    except OSError as exc:
        return ModelOutputRead(
            payload=None,
            status="invalid_file",
            note=f"codex exec wrote unreadable model output file: {exc}",
        )
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        return ModelOutputRead(
            payload=None,
            status="invalid_file",
            note="codex exec wrote invalid model output file: expected a regular file, not a symlink or special file",
        )
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            fd_stat = os.fstat(fd)
            if not stat.S_ISREG(fd_stat.st_mode):
                return ModelOutputRead(
                    payload=None,
                    status="invalid_file",
                    note="codex exec wrote invalid model output file: expected a regular file, not a symlink or special file",
                )
            with os.fdopen(fd, "rb") as handle:
                fd = -1
                raw_bytes = handle.read()
        finally:
            if fd != -1:
                os.close(fd)
    except OSError as exc:
        return ModelOutputRead(
            payload=None,
            status="invalid_file",
            note=f"codex exec wrote unreadable model output file: {exc}",
        )
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        return ModelOutputRead(
            payload=None,
            status="invalid_json",
            note=f"codex exec wrote invalid UTF-8 model output JSON: {exc}",
            raw_bytes=raw_bytes,
        )
    except json.JSONDecodeError as exc:
        return ModelOutputRead(
            payload=None,
            status="invalid_json",
            note=f"codex exec wrote invalid model output JSON: {exc}",
            raw_bytes=raw_bytes,
        )
    if not isinstance(payload, dict):
        return ModelOutputRead(
            payload=None,
            status="invalid_root",
            note="codex exec wrote invalid model output: root must be an object",
            raw_bytes=raw_bytes,
        )
    return ModelOutputRead(payload=payload, status="ok", note="", raw_bytes=raw_bytes)
