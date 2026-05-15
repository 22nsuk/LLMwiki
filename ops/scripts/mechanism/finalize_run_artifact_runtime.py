from __future__ import annotations

import json
from pathlib import Path

from .finalize_run_errors_runtime import (
    FinalizeRunArtifactDecodeError,
    FinalizeRunArtifactMissingError,
    FinalizeRunArtifactSchemaError,
)
from ops.scripts.schema_constants_runtime import (
    CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    PLANNING_VALIDATION_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
    RUN_LEDGER_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_or_raise


CHANGED_FILES_MANIFEST_SCHEMA = CHANGED_FILES_MANIFEST_SCHEMA_PATH
PROMOTION_REPORT_SCHEMA = PROMOTION_REPORT_SCHEMA_PATH
RUN_LEDGER_SCHEMA = RUN_LEDGER_SCHEMA_PATH
PLANNING_VALIDATION_SCHEMA = PLANNING_VALIDATION_SCHEMA_PATH


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FinalizeRunArtifactMissingError(f"missing artifact: {path.as_posix()}") from exc
    except json.JSONDecodeError as exc:
        raise FinalizeRunArtifactDecodeError(
            f"failed to decode JSON artifact {path.as_posix()}: line {exc.lineno} column {exc.colno}"
        ) from exc
    except OSError as exc:
        raise FinalizeRunArtifactDecodeError(
            f"failed to read JSON artifact {path.as_posix()}: {exc}"
        ) from exc


def load_validated_json(vault: Path, path: Path, schema_rel_path: str, *, context: str) -> dict:
    payload = read_json(path)
    try:
        schema = load_schema(vault / schema_rel_path)
        validate_or_raise(payload, schema, context=context)
    except FileNotFoundError as exc:
        raise FinalizeRunArtifactSchemaError(f"missing schema: {schema_rel_path}") from exc
    except ValueError as exc:
        raise FinalizeRunArtifactSchemaError(str(exc)) from exc
    return payload


def validate_finalize_payloads(
    vault: Path,
    *,
    report: dict,
    ledger: dict,
    planning_validation: dict,
) -> None:
    try:
        validate_or_raise(
            report,
            load_schema(vault / PROMOTION_REPORT_SCHEMA),
            context="finalized promotion report schema validation failed",
        )
        validate_or_raise(
            ledger,
            load_schema(vault / RUN_LEDGER_SCHEMA),
            context="finalized run-ledger schema validation failed",
        )
        validate_or_raise(
            planning_validation,
            load_schema(vault / PLANNING_VALIDATION_SCHEMA),
            context="finalized planning-validation schema validation failed",
        )
    except FileNotFoundError as exc:
        raise FinalizeRunArtifactSchemaError(f"missing schema: {exc}") from exc
    except ValueError as exc:
        raise FinalizeRunArtifactSchemaError(str(exc)) from exc
