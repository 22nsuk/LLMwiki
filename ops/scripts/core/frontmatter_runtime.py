from __future__ import annotations

from pathlib import Path
from typing import Any

from ops.scripts.registry.raw_registry_runtime import (
    normalize_registry_locator,
    registry_entry_locators,
)

from .policy_runtime import report_path
from .source_page_naming_runtime import source_slug_validation_detail
from .yaml_runtime import parse_simple_yaml

FRONTMATTER_DELIMITER = "---"


def parse_frontmatter(text: str) -> dict | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None

    for index in range(1, len(lines)):
        if lines[index].strip() != FRONTMATTER_DELIMITER:
            continue
        payload = "\n".join(lines[1:index]).strip()
        if not payload:
            return {}
        data = parse_simple_yaml(payload)
        if not isinstance(data, dict):
            raise ValueError("frontmatter root must be a mapping")
        return data

    raise ValueError("unterminated frontmatter block")


def _type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "string_array":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return True


def frontmatter_contract_for_page(vault: Path, path: Path, stem: str, contract: dict) -> dict:
    relative_path = report_path(vault, path)
    root_name = path.relative_to(vault).parts[0]

    required = list(contract.get("common_required", []))
    expected = {}

    corpus_by_root = contract.get("corpus_by_root", {})
    if root_name in corpus_by_root:
        expected["corpus"] = corpus_by_root[root_name]

    special_page_rules = contract.get("special_pages", {})
    if relative_path in special_page_rules:
        special = special_page_rules[relative_path]
        required.extend(special.get("required", []))
        expected.update(special.get("expected", {}))
        return {
            "required": list(dict.fromkeys(required)),
            "expected": expected,
        }

    prefix_rules = contract.get("prefix_pages", {})
    for prefix, rules in prefix_rules.items():
        if not stem.startswith(prefix):
            continue
        required.extend(rules.get("required", []))
        expected.update(rules.get("expected", {}))
        break

    return {
        "required": list(dict.fromkeys(required)),
        "expected": expected,
    }


def validate_frontmatter(
    vault: Path,
    path: Path,
    stem: str,
    frontmatter: dict,
    contract: dict,
) -> list[dict]:
    page_contract = frontmatter_contract_for_page(vault, path, stem, contract)
    issues: list[dict] = []
    required_fields = list(page_contract["required"])

    conditional_rules = contract.get("conditional_rules", {})
    allowed_value_mismatches = {}
    for trigger_field, trigger_map in conditional_rules.items():
        trigger_value = frontmatter.get(trigger_field)
        if trigger_value not in trigger_map:
            continue
        rule = trigger_map[trigger_value]
        required_fields.extend(rule.get("required", []))
        for field, expected_value in rule.get("expected", {}).items():
            page_contract["expected"][field] = expected_value
        for field, allowed_values in rule.get("allowed_values", {}).items():
            if field not in frontmatter:
                continue
            if frontmatter[field] in allowed_values:
                continue
            allowed_value_mismatches[field] = {
                "expected_one_of": allowed_values,
                "actual": frontmatter[field],
            }

    missing_fields = [
        field for field in list(dict.fromkeys(required_fields))
        if field not in frontmatter
    ]
    if missing_fields:
        issues.append(
            {
                "type": "missing_frontmatter_field",
                "detail": {
                    "missing_fields": missing_fields,
                },
            }
        )

    common_type_checks = contract.get("common_type_checks", {})
    optional_type_checks = contract.get("optional_type_checks", {})

    type_mismatches = {}
    for field, expected_type in common_type_checks.items():
        if field not in frontmatter:
            continue
        if _type_matches(frontmatter[field], expected_type):
            continue
        type_mismatches[field] = {
            "expected_type": expected_type,
            "actual_type": type(frontmatter[field]).__name__,
        }

    for field, expected_type in optional_type_checks.items():
        if field not in frontmatter:
            continue
        if _type_matches(frontmatter[field], expected_type):
            continue
        type_mismatches[field] = {
            "expected_type": expected_type,
            "actual_type": type(frontmatter[field]).__name__,
        }

    if type_mismatches:
        issues.append(
            {
                "type": "frontmatter_type_mismatch",
                "detail": type_mismatches,
            }
        )

    value_mismatches = {}
    for field, expected_value in page_contract["expected"].items():
        actual_value = frontmatter.get(field)
        if actual_value == expected_value:
            continue
        value_mismatches[field] = {
            "expected": expected_value,
            "actual": actual_value,
        }

    if value_mismatches:
        issues.append(
            {
                "type": "frontmatter_value_mismatch",
                "detail": value_mismatches,
            }
        )

    if allowed_value_mismatches:
        issues.append(
            {
                "type": "frontmatter_value_mismatch",
                "detail": allowed_value_mismatches,
            }
        )

    return issues


def validate_frontmatter_metadata(
    frontmatter: dict,
    stem: str,
    contract: dict,
) -> list[dict]:
    review = contract.get("metadata_review", {})
    issues: list[dict] = []

    if review.get("require_alias_stem", False):
        aliases = frontmatter.get("aliases", [])
        if isinstance(aliases, list) and stem not in aliases:
            issues.append(
                {
                    "type": "frontmatter_alias_missing_stem",
                    "detail": {
                        "expected_alias": stem,
                        "aliases": aliases,
                    },
                }
            )

    required_tag_templates = review.get("required_tag_templates", [])
    tags = frontmatter.get("tags", [])
    missing_tags: list[str] = []
    if isinstance(tags, list):
        for template in required_tag_templates:
            try:
                expected_tag = template.format(**frontmatter)
            except KeyError:
                continue
            if expected_tag not in tags:
                missing_tags.append(expected_tag)
    if missing_tags:
        issues.append(
            {
                "type": "frontmatter_tag_mismatch",
                "detail": {
                    "missing_tags": missing_tags,
                    "actual_tags": tags,
                },
            }
        )

    source_page_slug_review = review.get("source_page_slug", {})
    slug_issue_detail = source_slug_validation_detail(stem, source_page_slug_review)
    if slug_issue_detail is not None:
        issues.append(
            {
                "type": "noncanonical_source_page_slug",
                "detail": slug_issue_detail,
            }
        )

    return issues


def validate_frontmatter_pending_required_fields(
    frontmatter: dict,
    schema_versioning: dict | None,
) -> list[dict]:
    if not schema_versioning:
        return []

    issues: list[dict] = []
    page_type = frontmatter.get("page_type")
    frontmatter_contract_version = schema_versioning.get("frontmatter_contract_version")
    artifact_contract_version = schema_versioning.get("artifact_contract_version")

    for rollout in schema_versioning.get("frontmatter_field_rollouts", []):
        if rollout.get("status") != "optional_before_required":
            continue
        if rollout.get("severity") != "warn":
            continue

        field = rollout.get("field")
        if not isinstance(field, str) or field in frontmatter:
            continue

        applies_to_page_types = rollout.get("applies_to_page_types", [])
        if applies_to_page_types and page_type not in applies_to_page_types:
            continue

        issues.append(
            {
                "type": "frontmatter_field_pending_required",
                "detail": {
                    "missing_field": field,
                    "status": rollout.get("status"),
                    "introduced_on": rollout.get("introduced_on"),
                    "required_after": rollout.get("required_after"),
                    "migration": rollout.get("migration"),
                    "rationale": rollout.get("rationale"),
                    "frontmatter_contract_version": frontmatter_contract_version,
                    "artifact_contract_version": artifact_contract_version,
                },
            }
        )

    return issues


def validate_source_frontmatter_against_registry(
    stem: str,
    frontmatter: dict,
    registry_entry: dict,
    contract: dict,
) -> list[dict]:
    review = contract.get("metadata_review", {})
    issues: list[dict] = []
    mismatches: dict[str, dict] = {}

    if registry_entry.get("target_page") != stem:
        mismatches["target_page"] = {
            "expected": stem,
            "actual": registry_entry.get("target_page"),
            "source": "registry",
        }

    if registry_entry.get("corpus") != frontmatter.get("corpus"):
        mismatches["corpus"] = {
            "expected": registry_entry.get("corpus"),
            "actual": frontmatter.get("corpus"),
            "registry_field": "corpus",
        }

    for frontmatter_field, registry_field in review.get("source_registry_required_alignment", {}).items():
        if frontmatter_field == "raw_path" and registry_field == "storage_path":
            actual_raw_path = normalize_registry_locator(frontmatter.get(frontmatter_field))
            accepted_locators = registry_entry_locators(registry_entry)
            if actual_raw_path in accepted_locators:
                continue
            mismatches[frontmatter_field] = {
                "expected": registry_entry.get(registry_field),
                "actual": frontmatter.get(frontmatter_field),
                "registry_field": registry_field,
                "accepted_locators": accepted_locators,
            }
            continue
        if frontmatter.get(frontmatter_field) == registry_entry.get(registry_field):
            continue
        mismatches[frontmatter_field] = {
            "expected": registry_entry.get(registry_field),
            "actual": frontmatter.get(frontmatter_field),
            "registry_field": registry_field,
        }

    for frontmatter_field, registry_field in review.get("source_registry_optional_alignment", {}).items():
        if registry_field not in registry_entry:
            continue
        if frontmatter.get(frontmatter_field) == registry_entry.get(registry_field):
            continue
        mismatches[frontmatter_field] = {
            "expected": registry_entry.get(registry_field),
            "actual": frontmatter.get(frontmatter_field),
            "registry_field": registry_field,
        }

    if mismatches:
        issues.append(
            {
                "type": "source_frontmatter_registry_mismatch",
                "detail": mismatches,
            }
        )

    return issues
