from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from .schema_constants_runtime import LOCAL_SCHEMA_ALIASES

try:
    from jsonschema import ValidationError
    from jsonschema.exceptions import SchemaError
    from jsonschema.validators import validator_for
    from referencing import Registry, Resource
except ImportError as exc:  # pragma: no cover - dependency contract
    raise RuntimeError(
        "jsonschema is required; install the project dependencies from pyproject.toml"
    ) from exc


REQUIRED_PROPERTY_RE = re.compile(r"'([^']+)' is a required property")
UNEXPECTED_PROPERTIES_RE = re.compile(r"\((.+) (?:was|were) unexpected\)")
UNEXPECTED_PROPERTY_RE = re.compile(r"'([^']+)'")


@dataclass(frozen=True)
class SchemaIssue:
    instance_path: str
    schema_path: str
    validator: str
    message: str


def _normalize_schema_identifier(identifier: str) -> str:
    if identifier.startswith("http:/") and not identifier.startswith("http://"):
        return f"http://{identifier.removeprefix('http:/')}"
    if identifier.startswith("https:/") and not identifier.startswith("https://"):
        return f"https://{identifier.removeprefix('https:/')}"
    return identifier


def _schema_alias(identifier: str) -> str | None:
    return LOCAL_SCHEMA_ALIASES.get(_normalize_schema_identifier(identifier))


@cache
def _load_bundled_schema(schema_rel_path: str) -> dict[str, Any]:
    parts = Path(schema_rel_path).parts
    if parts and parts[0] == "ops":
        parts = parts[1:]
    schema_resource = resources.files("ops")
    for part in parts:
        schema_resource = schema_resource.joinpath(part)
    return json.loads(schema_resource.read_text(encoding="utf-8"))


def load_schema(path: Path | str) -> dict:
    identifier = path.as_posix() if isinstance(path, Path) else path
    schema_alias = _schema_alias(identifier)
    if schema_alias is not None:
        return _load_bundled_schema(schema_alias)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_schema_with_vault_override(vault: Path, schema_rel_path: str) -> dict:
    schema_rel_path = _schema_alias(schema_rel_path) or schema_rel_path
    vault_schema_path = vault / schema_rel_path
    if vault_schema_path.exists():
        return load_schema(vault_schema_path)

    return _load_bundled_schema(schema_rel_path)


@cache
def _local_schema_registry() -> Registry:
    registry = Registry()
    for schema_uri, schema_rel_path in LOCAL_SCHEMA_ALIASES.items():
        registry = registry.with_resource(
            schema_uri,
            Resource.from_contents(_load_bundled_schema(schema_rel_path)),
        )
    return registry


def _build_validator(schema: dict) -> Any:
    validator_cls = validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"invalid schema: {exc.message}") from exc
    return validator_cls(schema, registry=_local_schema_registry())


def _format_absolute_path(base_path: str, segments: Iterable[Any]) -> str:
    formatted = base_path or "$"
    for segment in segments:
        if isinstance(segment, int):
            formatted = f"{formatted}[{segment}]"
        else:
            formatted = f"{formatted}.{segment}"
    return formatted


def _format_schema_path(error: ValidationError) -> str:
    return _format_absolute_path("$", error.absolute_schema_path)


def _extract_unexpected_properties(message: str) -> list[str]:
    matched = UNEXPECTED_PROPERTIES_RE.search(message)
    if not matched:
        return []
    return UNEXPECTED_PROPERTY_RE.findall(matched.group(1))


def _format_issue_message(error: ValidationError, instance_path: str) -> list[str]:
    validator = error.validator
    if validator == "required":
        matched = REQUIRED_PROPERTY_RE.search(error.message)
        property_name = matched.group(1) if matched else str(error.validator_value)
        return [f"{instance_path}: missing required property '{property_name}'"]
    if validator == "type":
        return [f"{instance_path}: expected {error.validator_value}"]
    if validator == "enum":
        return [f"{instance_path}: expected one of {list(error.validator_value)}"]
    if validator == "additionalProperties":
        unexpected_properties = _extract_unexpected_properties(error.message)
        if unexpected_properties:
            return [
                f"{instance_path}: unexpected property '{property_name}'"
                for property_name in unexpected_properties
            ]
        return [f"{instance_path}: unexpected property"]
    if validator == "minItems":
        return [f"{instance_path}: expected at least {error.validator_value} item(s)"]
    if validator == "minProperties":
        return [f"{instance_path}: expected at least {error.validator_value} propert(ies)"]
    if validator == "oneOf":
        return [f"{instance_path}: does not match any allowed schema"]
    if validator == "const":
        return [f"{instance_path}: expected constant {error.validator_value!r}"]
    if validator == "minimum":
        return [f"{instance_path}: expected at least {error.validator_value}"]
    return [f"{instance_path}: {error.message}"]


def iter_schema_issues(data: Any, schema: dict, path: str = "$") -> list[SchemaIssue]:
    validator = _build_validator(schema)
    return iter_validator_issues(data, validator, path)


def build_validator_for_schema(schema: dict) -> Any:
    return _build_validator(schema)


def iter_validator_issues(data: Any, validator: Any, path: str = "$") -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    errors = sorted(validator.iter_errors(data), key=lambda error: list(error.absolute_path))
    for error in errors:
        instance_path = _format_absolute_path(path, error.absolute_path)
        schema_path = _format_schema_path(error)
        for message in _format_issue_message(error, instance_path):
            issues.append(
                SchemaIssue(
                    instance_path=instance_path,
                    schema_path=schema_path,
                    validator=error.validator,
                    message=message,
                )
            )
    return issues


def validate_with_schema(data: Any, schema: dict, path: str = "$") -> list[str]:
    return [issue.message for issue in iter_schema_issues(data, schema, path)]


def validate_with_validator(data: Any, validator: Any, path: str = "$") -> list[str]:
    return [issue.message for issue in iter_validator_issues(data, validator, path)]


def validate_or_raise(data: Any, schema: dict, context: str, path: str = "$") -> None:
    errors = validate_with_schema(data, schema, path)
    if errors:
        raise ValueError(f"{context}: {'; '.join(errors)}")
