#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.frontmatter_runtime import parse_frontmatter
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import (
        load_policy,
        report_path,
        resolve_policy_path,
    )
    from ops.scripts.core.runtime_context import RuntimeContext
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.frontmatter_runtime import parse_frontmatter
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import (
        load_policy,
        report_path,
        resolve_policy_path,
    )
    from ops.scripts.core.runtime_context import RuntimeContext


DEFAULT_POLICY = "ops/policies/wiki-maintainer-policy.yaml"
DEFAULT_OUT = "tmp/raw-registry-shard-policy-sync-report.json"
PRODUCER = "ops.scripts.raw_registry_shard_policy_sync"
SCHEMA_PATH = "ops/schemas/raw-registry-shard-policy-sync-report.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.registry.raw_registry_shard_policy_sync"
RAW_REGISTRY_SHARD_ROOT = "system/system-raw-registry"
RAW_REGISTRY_SHARD_FRONTMATTER = {
    "page_type": "registry-shard",
    "corpus": "system",
    "special_role": "raw-registry-shard",
}


def _heading_sections(text: str) -> list[str]:
    sections: list[str] = []
    for line in text.splitlines():
        if not line.startswith("## "):
            continue
        heading = line[3:].strip()
        if heading:
            sections.append(heading)
    return sections


def _entry_corpus_for_shard(path: str) -> str:
    prefix = f"{RAW_REGISTRY_SHARD_ROOT}/"
    if not path.startswith(prefix):
        return ""
    remainder = path.removeprefix(prefix)
    first_part = remainder.split("/", 1)[0]
    if first_part in {"wiki.md", "wiki"}:
        return "wiki"
    if first_part == "system.md" or first_part.startswith("system-"):
        return "system"
    return ""


def discover_raw_registry_shards(vault: Path) -> list[dict[str, Any]]:
    shard_root = vault / RAW_REGISTRY_SHARD_ROOT
    if not shard_root.exists():
        return []

    discovered: list[dict[str, Any]] = []
    for path in sorted(shard_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text)
        if not isinstance(frontmatter, dict):
            continue
        if frontmatter.get("special_role") != "raw-registry-shard":
            continue
        relative_path = report_path(vault, path)
        discovered.append(
            {
                "path": relative_path,
                "entry_corpus": _entry_corpus_for_shard(relative_path),
                "required_sections": _heading_sections(text),
            }
        )
    return discovered


def shard_root_exists(vault: Path) -> bool:
    return (vault / RAW_REGISTRY_SHARD_ROOT).is_dir()


def _raw_registry_special_page_paths(policy: dict[str, Any]) -> set[str]:
    special_pages = policy.get("frontmatter_contract", {}).get("special_pages", {})
    if not isinstance(special_pages, dict):
        return set()
    paths: set[str] = set()
    for path, rules in special_pages.items():
        if not isinstance(rules, dict):
            continue
        expected = rules.get("expected", {})
        if not isinstance(expected, dict):
            continue
        if expected.get("special_role") == "raw-registry-shard":
            paths.add(str(path))
    return paths


def _shape_mismatches(policy: dict[str, Any], discovered_paths: set[str]) -> list[dict[str, str]]:
    special_pages = policy.get("frontmatter_contract", {}).get("special_pages", {})
    mismatches: list[dict[str, str]] = []
    for path in sorted(discovered_paths):
        rules = special_pages.get(path, {}) if isinstance(special_pages, dict) else {}
        required = rules.get("required", []) if isinstance(rules, dict) else []
        expected = rules.get("expected", {}) if isinstance(rules, dict) else {}
        if "special_role" not in required:
            mismatches.append({"path": path, "field": "required.special_role"})
        for key, expected_value in RAW_REGISTRY_SHARD_FRONTMATTER.items():
            if not isinstance(expected, dict) or expected.get(key) != expected_value:
                mismatches.append({"path": path, "field": f"expected.{key}"})
    return mismatches


def _section_mismatches(
    policy: dict[str, Any],
    discovered_by_path: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    required_sections = policy.get("page_shape", {}).get(
        "special_page_required_sections", {}
    )
    if not isinstance(required_sections, dict):
        return []

    mismatches: list[dict[str, Any]] = []
    for path, shard in sorted(discovered_by_path.items()):
        policy_sections = required_sections.get(path, [])
        discovered_sections = shard["required_sections"]
        if list(policy_sections) == discovered_sections:
            continue
        mismatches.append(
            {
                "path": path,
                "policy_sections": list(policy_sections)
                if isinstance(policy_sections, list)
                else [],
                "discovered_sections": discovered_sections,
            }
        )
    return mismatches


def _entry_corpus_mismatches(
    policy: dict[str, Any],
    discovered_by_path: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    entry_page_corpus = policy.get("registry_contract", {}).get(
        "raw_registry_entry_page_corpus", {}
    )
    if not isinstance(entry_page_corpus, dict):
        return []

    mismatches: list[dict[str, str]] = []
    for path, shard in sorted(discovered_by_path.items()):
        expected = str(shard["entry_corpus"])
        actual = str(entry_page_corpus.get(path, ""))
        if actual == expected:
            continue
        mismatches.append({"path": path, "expected": expected, "actual": actual})
    return mismatches


def _drift_report(
    policy: dict[str, Any],
    discovered: list[dict[str, Any]],
) -> dict[str, Any]:
    discovered_by_path = {str(item["path"]): item for item in discovered}
    discovered_paths = set(discovered_by_path)
    registry_contract = policy.get("registry_contract", {})
    shard_pages = registry_contract.get("raw_registry_shard_pages", [])
    policy_shard_paths = {str(path) for path in shard_pages if str(path)}
    entry_page_corpus = registry_contract.get("raw_registry_entry_page_corpus", {})
    entry_page_paths = set(entry_page_corpus) if isinstance(entry_page_corpus, dict) else set()
    required_sections = policy.get("page_shape", {}).get(
        "special_page_required_sections", {}
    )
    required_section_paths = (
        set(required_sections) if isinstance(required_sections, dict) else set()
    )
    special_page_paths = _raw_registry_special_page_paths(policy)

    return {
        "missing_raw_registry_shard_pages": sorted(
            discovered_paths - policy_shard_paths
        ),
        "extra_raw_registry_shard_pages": sorted(
            policy_shard_paths - discovered_paths
        ),
        "missing_raw_registry_entry_page_corpus": sorted(
            discovered_paths - entry_page_paths
        ),
        "extra_raw_registry_entry_page_corpus": sorted(
            entry_page_paths - discovered_paths
        ),
        "wrong_raw_registry_entry_page_corpus": _entry_corpus_mismatches(
            policy,
            discovered_by_path,
        ),
        "missing_special_required_sections": sorted(
            discovered_paths - required_section_paths
        ),
        "missing_frontmatter_special_pages": sorted(
            discovered_paths - special_page_paths
        ),
        "extra_frontmatter_special_pages": sorted(
            special_page_paths - discovered_paths
        ),
        "special_page_shape_mismatches": _shape_mismatches(
            policy,
            discovered_paths,
        ),
        "required_sections_mismatches": _section_mismatches(
            policy,
            discovered_by_path,
        ),
    }


def _drift_count(drift: dict[str, Any]) -> int:
    total = 0
    for value in drift.values():
        if isinstance(value, list):
            total += len(value)
    return total


def build_report(
    vault: Path,
    *,
    policy_path: str = DEFAULT_POLICY,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    discovered = discover_raw_registry_shards(vault)
    drift = _drift_report(policy, discovered)
    drift_count = _drift_count(drift)
    status = "pass" if drift_count == 0 else "fail"

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_registry_shard_policy_sync_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/registry/raw_registry_shard_policy_sync.py"],
            file_inputs={"policy": resolved_policy_path},
            text_inputs={"shard_root": RAW_REGISTRY_SHARD_ROOT},
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "shard_root": RAW_REGISTRY_SHARD_ROOT,
        "status": status,
        "summary": {
            "discovered_shard_count": len(discovered),
            "drift_count": drift_count,
            "missing_policy_surface_count": sum(
                len(drift[key])
                for key in (
                    "missing_raw_registry_shard_pages",
                    "missing_raw_registry_entry_page_corpus",
                    "missing_special_required_sections",
                    "missing_frontmatter_special_pages",
                )
            ),
            "extra_policy_surface_count": sum(
                len(drift[key])
                for key in (
                    "extra_raw_registry_shard_pages",
                    "extra_raw_registry_entry_page_corpus",
                    "extra_frontmatter_special_pages",
                )
            ),
            "mismatch_count": sum(
                len(drift[key])
                for key in (
                    "wrong_raw_registry_entry_page_corpus",
                    "special_page_shape_mismatches",
                    "required_sections_mismatches",
                )
            ),
        },
        "discovered_shard_pages": discovered,
        "drift": drift,
    }


def _special_page_rule() -> dict[str, Any]:
    return {
        "required": ["special_role"],
        "expected": dict(RAW_REGISTRY_SHARD_FRONTMATTER),
    }


def synchronized_policy(policy: dict[str, Any], discovered: list[dict[str, Any]]) -> dict[str, Any]:
    synced = copy.deepcopy(policy)
    discovered_by_path = {str(item["path"]): item for item in discovered}
    discovered_paths = sorted(discovered_by_path)

    page_shape = synced.setdefault("page_shape", {})
    required_sections = page_shape.setdefault("special_page_required_sections", {})
    for path in list(required_sections):
        if path.startswith(f"{RAW_REGISTRY_SHARD_ROOT}/") and path not in discovered_by_path:
            del required_sections[path]
    for path in discovered_paths:
        required_sections[path] = list(discovered_by_path[path]["required_sections"])

    frontmatter_contract = synced.setdefault("frontmatter_contract", {})
    special_pages = frontmatter_contract.setdefault("special_pages", {})
    for path, rules in list(special_pages.items()):
        if not path.startswith(f"{RAW_REGISTRY_SHARD_ROOT}/"):
            continue
        expected = rules.get("expected", {}) if isinstance(rules, dict) else {}
        if (
            isinstance(expected, dict)
            and expected.get("special_role") == "raw-registry-shard"
            and path not in discovered_by_path
        ):
            del special_pages[path]
    for path in discovered_paths:
        special_pages[path] = _special_page_rule()

    registry_contract = synced.setdefault("registry_contract", {})
    registry_contract["raw_registry_shard_pages"] = discovered_paths
    registry_contract["raw_registry_entry_page_corpus"] = {
        path: str(discovered_by_path[path]["entry_corpus"]) for path in discovered_paths
    }
    return synced


def write_policy(vault: Path, policy_path: str) -> Path:
    resolved_policy_path = resolve_policy_path(vault, policy_path)
    policy, _ = load_policy(vault, policy_path)
    if not shard_root_exists(vault):
        raise FileNotFoundError(
            f"raw registry shard root is absent: {RAW_REGISTRY_SHARD_ROOT}"
        )
    discovered = discover_raw_registry_shards(vault)
    synced = synchronized_policy(policy, discovered)
    resolved_policy_path.write_text(
        yaml.safe_dump(
            synced,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=120,
        ),
        encoding="utf-8",
    )
    return resolved_policy_path


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw registry shard policy sync report schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check or synchronize raw registry shard policy surfaces.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default=DEFAULT_POLICY)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the policy from discovered raw registry shard pages before reporting.",
    )
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="Return success even when the report status is fail.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    if args.write:
        try:
            write_policy(vault, args.policy)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    report = build_report(vault, policy_path=args.policy)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.allow_drift:
        return 0
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
