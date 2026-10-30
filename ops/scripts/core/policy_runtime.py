from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .filesystem_runtime import atomic_write_text
from .path_runtime import stable_report_path
from .policy_validation_runtime import (
    SUPPORTED_SUBAGENT_LADDER as _SUPPORTED_SUBAGENT_LADDER,
    _registry_keys,
    display_timezone_from_policy as _display_timezone_from_policy,
    release_archive_root_name_from_policy as _release_archive_root_name_from_policy,
    validate_policy_registry_references,
    validate_policy_safety_invariants,
    workspace_preparation_declared_dependencies_from_policy as _workspace_preparation_declared_dependencies_from_policy,
    workspace_preparation_mode_from_policy as _workspace_preparation_mode_from_policy,
    zip_normalization_from_policy as _zip_normalization_from_policy,
)
from .schema_constants_runtime import (
    LOCAL_CORPUS_POLICY_SCHEMA_PATH,
    POLICY_SCHEMA_PATH,
)
from .schema_runtime import load_schema_with_vault_override, validate_or_raise
from .yaml_runtime import parse_simple_yaml

RequiredSections = dict[str, list[str] | dict[str, list[str]]]
DEFAULT_POLICY_PATH = "ops/policies/wiki-maintainer-policy.yaml"
LOCAL_CORPUS_POLICY_PATH = "ops/policies/wiki-maintainer-policy.local.yaml"
LOCAL_CORPUS_POLICY_SECTIONS = (
    ("page_shape", "special_page_required_sections"),
    ("frontmatter_contract", "special_pages"),
    ("registry_contract", "raw_registry_shard_pages"),
    ("registry_contract", "raw_registry_entry_page_corpus"),
)

SUPPORTED_SUBAGENT_LADDER = _SUPPORTED_SUBAGENT_LADDER
display_timezone_from_policy = _display_timezone_from_policy
release_archive_root_name_from_policy = _release_archive_root_name_from_policy
zip_normalization_from_policy = _zip_normalization_from_policy
workspace_preparation_declared_dependencies_from_policy = (
    _workspace_preparation_declared_dependencies_from_policy
)
workspace_preparation_mode_from_policy = _workspace_preparation_mode_from_policy


def resolve_policy_path(vault: Path, policy_path: str | None = None) -> Path:
    relative_path = Path(policy_path or DEFAULT_POLICY_PATH)
    if relative_path.is_absolute():
        return relative_path
    return vault / relative_path


def local_corpus_policy_path(vault: Path, resolved_policy_path: Path) -> Path | None:
    if resolved_policy_path.resolve() != (vault / DEFAULT_POLICY_PATH).resolve():
        return None
    return vault / LOCAL_CORPUS_POLICY_PATH


def read_local_corpus_policy_bytes(vault: Path) -> bytes | None:
    """Read the optional overlay, propagating failures other than file absence."""
    try:
        return (vault / LOCAL_CORPUS_POLICY_PATH).read_bytes()
    except FileNotFoundError:
        return None


def _merge_policy_overrides(base: dict, overrides: dict) -> dict:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            existing = merged.get(key)
            merged[key] = _merge_policy_overrides(
                existing if isinstance(existing, dict) else {}, value
            )
        else:
            merged[key] = deepcopy(value)
    return merged


def _policy_mapping_delta(base: dict, effective: dict) -> dict:
    delta: dict[str, Any] = {}
    for key in sorted(base.keys() | effective.keys()):
        if key not in effective:
            delta[key] = None
        elif key not in base:
            delta[key] = deepcopy(effective[key])
        elif base[key] != effective[key]:
            if isinstance(base[key], dict) and isinstance(effective[key], dict):
                delta[key] = _policy_mapping_delta(base[key], effective[key])
            else:
                delta[key] = deepcopy(effective[key])
    return delta


def _validate_local_corpus_payload(vault: Path, payload: dict, path: Path) -> None:
    validate_or_raise(
        payload,
        load_schema_with_vault_override(vault, LOCAL_CORPUS_POLICY_SCHEMA_PATH),
        context=f"invalid local corpus policy in {report_path(vault, path)}",
    )


def local_corpus_policy_payload(base: dict, effective: dict) -> dict:
    overrides: dict[str, Any] = {}
    for section, field in LOCAL_CORPUS_POLICY_SECTIONS:
        before, after = base[section][field], effective[section][field]
        if before == after:
            continue
        value = (
            _policy_mapping_delta(before, after)
            if isinstance(before, dict) and isinstance(after, dict)
            else deepcopy(after)
        )
        overrides.setdefault(section, {})[field] = value
    if _merge_policy_overrides(base, overrides) != effective:
        raise ValueError("local corpus policy cannot change non-corpus settings")
    return {"schema_version": 1, "overrides": overrides}


def write_local_corpus_policy(vault: Path, effective: dict) -> Path:
    base_path = vault / DEFAULT_POLICY_PATH
    local_path = vault / LOCAL_CORPUS_POLICY_PATH
    base = parse_simple_yaml(base_path.read_text(encoding="utf-8"))
    validate_policy_contract(base, base_path, vault)
    payload = local_corpus_policy_payload(base, effective)
    _validate_local_corpus_payload(vault, payload, local_path)
    validate_policy_contract(effective, local_path, vault)
    return atomic_write_text(
        local_path,
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
    )


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
    local_path = local_corpus_policy_path(vault, resolved_path)
    if local_path is not None:
        local_bytes = read_local_corpus_policy_bytes(vault)
        if local_bytes is not None:
            payload = parse_simple_yaml(local_bytes.decode("utf-8"))
            _validate_local_corpus_payload(vault, payload, local_path)
            policy = _merge_policy_overrides(policy, payload["overrides"])
            validate_policy_contract(policy, local_path, vault)
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
