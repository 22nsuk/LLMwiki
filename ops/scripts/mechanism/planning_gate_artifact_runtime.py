from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from ops.scripts.core.schema_constants_runtime import (
    PLANNING_GATE_COMPLETED_MECHANISM_INPUT_SCHEMAS,
    PLANNING_GATE_OPTIONAL_ARTIFACT_SCHEMAS,
    PLANNING_GATE_OPTIONAL_COMPLETED_MECHANISM_INPUT_SCHEMAS,
    PLANNING_GATE_REQUIRED_ARTIFACT_SCHEMAS,
)
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)
from ops.scripts.core.yaml_runtime import parse_simple_yaml

ARTIFACT_SCHEMAS = PLANNING_GATE_REQUIRED_ARTIFACT_SCHEMAS
OPTIONAL_ARTIFACT_SCHEMAS = PLANNING_GATE_OPTIONAL_ARTIFACT_SCHEMAS
COMPLETED_MECHANISM_INPUT_SCHEMAS = PLANNING_GATE_COMPLETED_MECHANISM_INPUT_SCHEMAS
OPTIONAL_COMPLETED_MECHANISM_INPUT_SCHEMAS = (
    PLANNING_GATE_OPTIONAL_COMPLETED_MECHANISM_INPUT_SCHEMAS
)


class PlanningArtifactError(Exception):
    pass


class ArtifactLoadError(PlanningArtifactError):
    pass


ArtifactPayload = dict[str, Any]


ArtifactValidationResultBase = TypedDict(
    "ArtifactValidationResultBase",
    {
        "artifact": str,
        "schema": str,
        "pass": bool,
        "errors": list[str],
    },
)


class ArtifactValidationResult(ArtifactValidationResultBase, total=False):
    data: ArtifactPayload


def artifact_result_without_data(
    result: ArtifactValidationResult,
) -> ArtifactValidationResult:
    return {
        "artifact": result["artifact"],
        "schema": result["schema"],
        "pass": result["pass"],
        "errors": result["errors"],
    }


def load_artifact(path: Path) -> ArtifactPayload:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ArtifactLoadError(f"unable to read {path.name}: {exc}") from exc

    try:
        data = parse_simple_yaml(text) if path.suffix == ".yaml" else json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ArtifactLoadError(f"unable to parse {path.name}: {exc}") from exc

    if not isinstance(data, dict):
        raise ArtifactLoadError(f"{path.name} root must be an object")
    return data


def load_and_validate_reported_json_artifact(
    vault: Path,
    rel_path: str,
    schema_rel_path: str,
) -> tuple[ArtifactPayload | None, str]:
    artifact_path = (vault / rel_path).resolve()
    if not artifact_path.exists():
        return None, f"missing artifact: {rel_path}"

    schema = load_schema_with_vault_override(vault, schema_rel_path)
    try:
        data = load_artifact(artifact_path)
    except ArtifactLoadError as exc:
        return None, f"failed to load artifact {rel_path}: {exc}"

    errors = validate_with_schema(data, schema)
    if errors:
        return None, f"schema validation failed for {rel_path}: {errors[0]}"
    return data, ""


def validate_artifact(
    vault: Path,
    artifact_dir: Path,
    artifact_name: str,
    schema_rel_path: str,
) -> ArtifactValidationResult:
    artifact_path = artifact_dir / artifact_name
    if not artifact_path.exists():
        return {
            "artifact": artifact_name,
            "schema": schema_rel_path,
            "pass": False,
            "errors": [f"missing artifact: {artifact_name}"],
        }

    schema = load_schema_with_vault_override(vault, schema_rel_path)
    try:
        data = load_artifact(artifact_path)
    except ArtifactLoadError as exc:
        return {
            "artifact": artifact_name,
            "schema": schema_rel_path,
            "pass": False,
            "errors": [f"failed to load artifact: {exc}"],
        }

    errors = validate_with_schema(data, schema)
    return {
        "artifact": artifact_name,
        "schema": schema_rel_path,
        "pass": len(errors) == 0,
        "errors": errors,
        "data": data,
    }


def validate_optional_artifact(
    vault: Path,
    artifact_dir: Path,
    artifact_name: str,
    schema_rel_path: str,
) -> ArtifactValidationResult | None:
    artifact_path = artifact_dir / artifact_name
    if not artifact_path.exists():
        return None
    return validate_artifact(vault, artifact_dir, artifact_name, schema_rel_path)
