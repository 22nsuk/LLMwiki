from __future__ import annotations

from pathlib import Path

from .path_runtime import stable_report_path
from .policy_validation_runtime import (
    SUPPORTED_SUBAGENT_LADDER as _SUPPORTED_SUBAGENT_LADDER,
)
from .policy_validation_runtime import (
    _registry_keys,
    validate_policy_registry_references,
    validate_policy_safety_invariants,
)
from .policy_validation_runtime import (
    display_timezone_from_policy as _display_timezone_from_policy,
)
from .policy_validation_runtime import (
    release_archive_root_name_from_policy as _release_archive_root_name_from_policy,
)
from .policy_validation_runtime import (
    workspace_preparation_declared_dependencies_from_policy as _workspace_preparation_declared_dependencies_from_policy,
)
from .policy_validation_runtime import (
    workspace_preparation_mode_from_policy as _workspace_preparation_mode_from_policy,
)
from .policy_validation_runtime import (
    zip_normalization_from_policy as _zip_normalization_from_policy,
)
from .schema_constants_runtime import POLICY_SCHEMA_PATH
from .schema_runtime import load_schema_with_vault_override, validate_or_raise
from .yaml_runtime import parse_simple_yaml

RequiredSections = dict[str, list[str] | dict[str, list[str]]]

SUPPORTED_SUBAGENT_LADDER = _SUPPORTED_SUBAGENT_LADDER
display_timezone_from_policy = _display_timezone_from_policy
release_archive_root_name_from_policy = _release_archive_root_name_from_policy
zip_normalization_from_policy = _zip_normalization_from_policy
workspace_preparation_declared_dependencies_from_policy = (
    _workspace_preparation_declared_dependencies_from_policy
)
workspace_preparation_mode_from_policy = _workspace_preparation_mode_from_policy


def resolve_policy_path(vault: Path, policy_path: str | None = None) -> Path:
    relative_path = Path(policy_path or "ops/policies/wiki-maintainer-policy.yaml")
    if relative_path.is_absolute():
        return relative_path
    return vault / relative_path


def report_path(vault: Path, path: Path) -> str:
    return stable_report_path(vault, path)


def subagent_ladder_rungs(policy: dict) -> tuple[int, ...]:
    return tuple(entry["rung"] for entry in policy["subagent_routing_policy"]["ladder"])


def subagent_ladder_model_effort(policy: dict, rung: int) -> tuple[str, str]:
    for entry in policy["subagent_routing_policy"]["ladder"]:
        if entry["rung"] == rung:
            return entry["model"], entry["reasoning_effort"]
    raise ValueError(f"unsupported subagent rung: {rung}")


def subagent_score_band_names(policy: dict) -> tuple[str, ...]:
    return tuple(
        _registry_keys(
            policy["subagent_routing_policy"]["score_bands"],
            "subagent_routing_policy.score_bands",
        )
    )


def validate_policy_contract(policy: dict, resolved_path: Path, vault: Path) -> None:
    schema = load_schema_with_vault_override(vault, POLICY_SCHEMA_PATH)
    validate_or_raise(
        policy,
        schema,
        context=f"invalid policy schema in {report_path(vault, resolved_path)}",
    )
    validate_policy_safety_invariants(policy)
    validate_policy_registry_references(policy)


def load_policy(vault: Path, policy_path: str | None = None) -> tuple[dict, Path]:
    resolved_path = resolve_policy_path(vault, policy_path)
    text = resolved_path.read_text(encoding="utf-8")
    policy = parse_simple_yaml(text)
    validate_policy_contract(policy, resolved_path, vault)
    return policy, resolved_path


def required_sections_from_policy(policy: dict) -> RequiredSections:
    page_shape = policy["page_shape"]
    synthesis_sections = list(page_shape["synthesis_required_sections"])
    return {
        "special_pages": {
            path: list(sections)
            for path, sections in page_shape["special_page_required_sections"].items()
        },
        "source--": list(page_shape["source_required_sections"]),
        "concept--": list(page_shape["concept_required_sections"]),
        "synthesis--": synthesis_sections,
        "query--": list(page_shape.get("query_required_sections", synthesis_sections)),
        "lint--": list(page_shape["lint_required_sections"]),
    }
