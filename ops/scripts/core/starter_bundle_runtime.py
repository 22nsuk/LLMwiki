from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .path_runtime import normalize_repo_path_text

DEFAULT_STARTER_BUNDLE = "planning_default"
SYSTEM_MECHANISM_STARTER_BUNDLE = "system_mechanism"


@dataclass(frozen=True)
class StarterBundleDefinition:
    name: str
    path: str
    phase: str
    promotion_report_input_placeholders: dict[str, tuple[str, ...]]


def starter_bundle_registry(policy: dict) -> dict[str, StarterBundleDefinition]:
    raw_bundles = policy.get("starter_bundles", {})
    registry: dict[str, StarterBundleDefinition] = {}
    for name, raw in raw_bundles.items():
        normalized_path = normalize_repo_path_text(raw.get("path"))
        if normalized_path is None:
            raise ValueError(f"starter_bundles.{name}.path must not be empty")
        raw_placeholders = raw.get("promotion_report_input_placeholders", {})
        placeholders: dict[str, tuple[str, ...]] = {}
        for input_name, values in raw_placeholders.items():
            normalized_values: list[str] = []
            seen: set[str] = set()
            for value in values:
                normalized_value = normalize_repo_path_text(value)
                if normalized_value is None or normalized_value in seen:
                    continue
                seen.add(normalized_value)
                normalized_values.append(normalized_value)
            placeholders[str(input_name)] = tuple(normalized_values)
        registry[name] = StarterBundleDefinition(
            name=name,
            path=normalized_path,
            phase=str(raw.get("phase", "starter")),
            promotion_report_input_placeholders=placeholders,
        )
    return registry


def starter_bundle(policy: dict, name: str) -> StarterBundleDefinition:
    registry = starter_bundle_registry(policy)
    try:
        return registry[name]
    except KeyError as exc:
        raise ValueError(f"unknown starter bundle: {name}") from exc


def starter_bundle_path(vault: Path, policy: dict, name: str) -> Path:
    bundle = starter_bundle(policy, name)
    raw_path = Path(bundle.path)
    if raw_path.is_absolute():
        return raw_path
    return (vault / raw_path).resolve()


def starter_bundle_for_artifact_dir(
    policy: dict,
    artifact_dir_report: str,
) -> StarterBundleDefinition | None:
    normalized_dir = normalize_repo_path_text(artifact_dir_report)
    if normalized_dir is None:
        return None
    for bundle in starter_bundle_registry(policy).values():
        if bundle.path == normalized_dir:
            return bundle
    return None


def starter_bundle_allowed_promotion_input_paths(
    bundle: StarterBundleDefinition | None,
    input_name: str,
    *,
    expected_path: str,
) -> list[str]:
    allowed_paths = [expected_path]
    if bundle is None:
        return allowed_paths
    for value in bundle.promotion_report_input_placeholders.get(input_name, ()):
        if value not in allowed_paths:
            allowed_paths.append(value)
    return allowed_paths
