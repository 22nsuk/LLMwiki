#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path, resolve_vault_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.run_artifact_envelope_runtime import (
        maybe_embed_run_artifact_envelope,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import MECHANISM_ASSESSMENT_SCHEMA_PATH
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        resolve_schema_backed_report_output_path,
        write_schema_backed_report,
    )
    from ops.scripts.output_runtime import display_path, resolve_vault_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.run_artifact_envelope_runtime import (
        maybe_embed_run_artifact_envelope,
    )
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import MECHANISM_ASSESSMENT_SCHEMA_PATH


MECHANISM_ASSESSMENT_SCHEMA = MECHANISM_ASSESSMENT_SCHEMA_PATH
MARKDOWN_HEADING_RE = re.compile(r"^#{2,6}\s", re.MULTILINE)
DEPENDENCY_FILES = {
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
    "package.json",
    "package-lock.json",
}
INTERFACE_SCRIPTS = {
    "ops/scripts/promotion_gate.py",
    "ops/scripts/wiki_lint.py",
    "ops/scripts/wiki_eval.py",
}
SECURITY_SURFACE_TOKENS = (
    "security",
    "auth",
    "permission",
    "credential",
    "secret",
    "token",
)
DESTRUCTIVE_PATTERNS = (
    re.compile(r"\bgit reset --hard\b"),
    re.compile(r"\brm -rf\b"),
    re.compile(r"\bDROP TABLE\b", re.IGNORECASE),
    re.compile(r"\bshutil\.rmtree\s*\("),
)
SECURITY_CONTENT_PATTERNS = (
    re.compile(
        r"\b(api[_-]?key|authorization|bearer|credential|jwt|oauth|password|secret|token)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bos\.environ\s*\[\s*['\"][^'\"]*(KEY|SECRET|TOKEN|PASSWORD)[^'\"]*['\"]\s*\]",
        re.IGNORECASE,
    ),
)
SCHEMA_CONTENT_PATTERNS = (
    re.compile(r"\"\$schema\"\s*:"),
    re.compile(r"https://json-schema.org/", re.IGNORECASE),
)
MIGRATION_CONTENT_PATTERNS = (
    re.compile(r"\b(alembic|migration|upgrade\s*\(|downgrade\s*\()\b", re.IGNORECASE),
)
SEMANTIC_COMPLEXITY_NODE_WEIGHTS_TENTHS: tuple[tuple[type[ast.AST], int], ...] = (
    (ast.If, 10),
    (ast.For, 10),
    (ast.AsyncFor, 10),
    (ast.While, 10),
    (ast.Try, 10),
    (ast.With, 10),
    (ast.AsyncWith, 10),
    (ast.Match, 10),
    (ast.BoolOp, 5),
    (ast.ExceptHandler, 5),
    (ast.ListComp, 5),
    (ast.DictComp, 5),
    (ast.SetComp, 5),
    (ast.GeneratorExp, 5),
    (ast.IfExp, 3),
    (ast.Assert, 3),
    (ast.Raise, 3),
)
LARGE_TARGET_LINE_THRESHOLD = 400
PER_TARGET_VOLUME_CAP = 240
SUPPORTED_HIGH_RISK_FLAGS = {
    "schema_change",
    "dependency_change",
    "migration",
    "security_surface",
    "destructive_command",
    "policy_surface",
    "log_append_surface",
}


class MechanismAssessmentState:
    def __init__(self) -> None:
        self.unreadable_targets: list[dict] = []
        self.python_parse_failures: list[dict] = []
        self._text_cache: dict[str, str | None] = {}
        self._tree_cache: dict[str, ast.AST | None] = {}

    def _append_unique(self, bucket: list[dict], diagnostic: dict) -> None:
        if diagnostic not in bucket:
            bucket.append(diagnostic)

    def read_text(self, rel_path: str, path: Path) -> str | None:
        if rel_path in self._text_cache:
            return self._text_cache[rel_path]
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            self._append_unique(
                self.unreadable_targets,
                {
                    "path": rel_path,
                    "reason": "unicode_decode_error",
                },
            )
            text = None
        except OSError as exc:
            self._append_unique(
                self.unreadable_targets,
                {
                    "path": rel_path,
                    "reason": "os_error",
                    "detail": str(exc),
                },
            )
            text = None
        self._text_cache[rel_path] = text
        return text

    def parse_python_tree(self, rel_path: str, path: Path) -> ast.AST | None:
        if rel_path in self._tree_cache:
            return self._tree_cache[rel_path]
        text = self.read_text(rel_path, path)
        if text is None:
            self._tree_cache[rel_path] = None
            return None
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            self._append_unique(
                self.python_parse_failures,
                {
                    "path": rel_path,
                    "reason": "syntax_error",
                    "detail": f"line {exc.lineno}: {exc.msg}",
                },
            )
            tree = None
        self._tree_cache[rel_path] = tree
        return tree

    def report(self) -> dict:
        return {
            "unreadable_targets": self.unreadable_targets,
            "python_parse_failures": self.python_parse_failures,
        }


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def normalize_targets(vault: Path, raw_targets: list[str]) -> list[tuple[str, Path]]:
    normalized: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for raw_target in raw_targets:
        resolved = resolve_vault_path(vault, raw_target)
        if not resolved.exists():
            raise ValueError(f"missing target: {report_path(vault, resolved)}")
        rel_path = report_path(vault, resolved)
        if rel_path in seen:
            continue
        seen.add(rel_path)
        normalized.append((rel_path, resolved))
    return normalized


def count_nonempty_lines(state: MechanismAssessmentState, rel_path: str, path: Path) -> int:
    text = state.read_text(rel_path, path)
    if text is None:
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def python_function_count(state: MechanismAssessmentState, rel_path: str, path: Path) -> int:
    tree = state.parse_python_tree(rel_path, path)
    if tree is None:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def python_branch_node_count(state: MechanismAssessmentState, rel_path: str, path: Path) -> int:
    tree = state.parse_python_tree(rel_path, path)
    if tree is None:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.Try,
                ast.With,
                ast.AsyncWith,
                ast.Match,
            ),
        )
    )


def python_semantic_complexity_points(state: MechanismAssessmentState, rel_path: str, path: Path) -> int:
    tree = state.parse_python_tree(rel_path, path)
    if tree is None:
        return 0
    points = 0
    for node in ast.walk(tree):
        for node_type, weight in SEMANTIC_COMPLEXITY_NODE_WEIGHTS_TENTHS:
            if isinstance(node, node_type):
                points += weight
                break
    return points


def _target_kind(rel_path: str, path: Path) -> str:
    if path.suffix == ".py":
        return "python"
    if path.suffix == ".md":
        return "markdown"
    if path.suffix in {".yaml", ".yml"}:
        return "yaml"
    if path.suffix == ".json":
        return "json"
    return "other"


def target_structural_profiles(
    state: MechanismAssessmentState,
    targets: list[tuple[str, Path]],
) -> list[dict]:
    profiles: list[dict] = []
    for rel_path, path in _dedupe_target_pairs(targets):
        nonempty_lines = count_nonempty_lines(state, rel_path, path)
        python_functions = python_function_count(state, rel_path, path) if path.suffix == ".py" else 0
        python_branches = python_branch_node_count(state, rel_path, path) if path.suffix == ".py" else 0
        markdown_headings = markdown_heading_count(state, rel_path, path) if path.suffix == ".md" else 0
        semantic_points = (
            python_semantic_complexity_points(state, rel_path, path)
            if path.suffix == ".py"
            else 0
        )
        profiles.append(
            {
                "path": rel_path,
                "kind": _target_kind(rel_path, path),
                "nonempty_line_count": nonempty_lines,
                "python_function_count": python_functions,
                "python_branch_node_count": python_branches,
                "markdown_heading_count": markdown_headings,
                "python_semantic_complexity_points": semantic_points,
                "whole_file_volume": (
                    nonempty_lines
                    + python_functions * 5
                    + python_branches * 3
                    + markdown_headings * 2
                    + round(semantic_points / 10)
                ),
                "coarse_target": nonempty_lines >= LARGE_TARGET_LINE_THRESHOLD,
            }
        )
    return profiles


def markdown_heading_count(state: MechanismAssessmentState, rel_path: str, path: Path) -> int:
    text = state.read_text(rel_path, path)
    if text is None:
        return 0
    return len(MARKDOWN_HEADING_RE.findall(text))


def _is_test_case_class(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id.endswith("TestCase"):
            return True
        if isinstance(base, ast.Attribute) and base.attr.endswith("TestCase"):
            return True
    return False


def python_test_case_count(state: MechanismAssessmentState, rel_path: str, path: Path) -> int:
    tree = state.parse_python_tree(rel_path, path)
    if tree is None:
        return 0

    count = 0
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            count += 1
        elif isinstance(node, ast.ClassDef) and _is_test_case_class(node):
            count += sum(
                1
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name.startswith("test_")
            )
    return count


def _dedupe_target_pairs(targets: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for rel_path, path in targets:
        if rel_path in seen:
            continue
        seen.add(rel_path)
        deduped.append((rel_path, path))
    return deduped


def build_structural_metrics(
    state: MechanismAssessmentState,
    measured_targets: list[tuple[str, Path]],
    test_files: list[tuple[str, Path]],
) -> dict:
    measured_targets = _dedupe_target_pairs(measured_targets)
    nonempty_line_count_total = sum(
        count_nonempty_lines(state, rel_path, path)
        for rel_path, path in measured_targets
    )
    python_function_total = sum(
        python_function_count(state, rel_path, path)
        for rel_path, path in measured_targets
        if path.suffix == ".py"
    )
    python_branch_total = sum(
        python_branch_node_count(state, rel_path, path)
        for rel_path, path in measured_targets
        if path.suffix == ".py"
    )
    markdown_heading_total = sum(
        markdown_heading_count(state, rel_path, path)
        for rel_path, path in measured_targets
        if path.suffix == ".md"
    )
    test_case_total = sum(
        python_test_case_count(state, rel_path, path)
        for rel_path, path in test_files
        if path.suffix == ".py"
    )

    return {
        "nonempty_line_count_total": nonempty_line_count_total,
        "python_function_count": python_function_total,
        "python_branch_node_count": python_branch_total,
        "markdown_heading_count": markdown_heading_total,
        "test_file_count": len(test_files),
        "test_case_count": test_case_total,
    }


def configured_high_risk_flags(policy: dict) -> list[str]:
    configured = policy["complexity_policy"]["risk_overrides"]["high_risk_flags"]
    ordered: list[str] = []
    seen: set[str] = set()
    for flag in configured:
        if flag not in SUPPORTED_HIGH_RISK_FLAGS:
            raise ValueError(f"unsupported high-risk flag: {flag}")
        if flag in seen:
            continue
        seen.add(flag)
        ordered.append(flag)
    return ordered


def _risk_evidence_entry(flag: str, rel_path: str, reason: str) -> dict:
    return {
        "flag": flag,
        "path": rel_path,
        "reason": reason,
    }


def detect_risk_flag_evidence(
    state: MechanismAssessmentState,
    targets: list[tuple[str, Path]],
    enabled_flags: list[str],
) -> list[dict]:
    enabled = set(enabled_flags)
    evidence: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(flag: str, rel_path: str, reason: str) -> None:
        if flag not in enabled:
            return
        key = (flag, rel_path, reason)
        if key in seen:
            return
        seen.add(key)
        evidence.append(_risk_evidence_entry(flag, rel_path, reason))

    for rel_path, path in targets:
        lowered = rel_path.lower()
        parts = Path(rel_path).parts
        if rel_path.startswith("ops/schemas/") or rel_path.endswith(".schema.json"):
            add("schema_change", rel_path, "schema_path")
        if rel_path.startswith("ops/policies/"):
            add("policy_surface", rel_path, "policy_path")
        if Path(rel_path).name in DEPENDENCY_FILES:
            add("dependency_change", rel_path, "dependency_file")
        if any(part == "migrations" for part in parts) or "migration" in lowered:
            add("migration", rel_path, "migration_path")
        if any(token in lowered for token in SECURITY_SURFACE_TOKENS):
            add("security_surface", rel_path, "security_path_token")
        if rel_path == "system/system-log.md":
            add("log_append_surface", rel_path, "system_log_append_surface")

        text = state.read_text(rel_path, path)
        if not text:
            continue
        if any(pattern.search(text) for pattern in DESTRUCTIVE_PATTERNS):
            add("destructive_command", rel_path, "destructive_command_content")
        if any(pattern.search(text) for pattern in SECURITY_CONTENT_PATTERNS):
            add("security_surface", rel_path, "security_content_token")
        if any(pattern.search(text) for pattern in SCHEMA_CONTENT_PATTERNS):
            add("schema_change", rel_path, "schema_content_marker")
        if any(pattern.search(text) for pattern in MIGRATION_CONTENT_PATTERNS):
            add("migration", rel_path, "migration_content_marker")
    return evidence


def detect_risk_flags(
    state: MechanismAssessmentState,
    targets: list[tuple[str, Path]],
    enabled_flags: list[str],
) -> list[str]:
    return sorted(
        {
            entry["flag"]
            for entry in detect_risk_flag_evidence(state, targets, enabled_flags)
        }
    )


def _bucket_score(value: int, thresholds: tuple[int, int, int, int, int]) -> int:
    for index, threshold in enumerate(thresholds):
        if value <= threshold:
            return index
    return 5


def target_count_score(target_count: int) -> int:
    return _bucket_score(target_count, (1, 2, 4, 6, 8))


def volume_score(volume: int) -> int:
    return _bucket_score(volume, (40, 120, 240, 400, 700))


def target_effective_volume(profile: dict) -> int:
    line_cap = PER_TARGET_VOLUME_CAP
    if profile["kind"] == "markdown":
        line_cap = 120
    elif profile["kind"] in {"json", "yaml"}:
        line_cap = 180
    return (
        min(profile["nonempty_line_count"], line_cap)
        + profile["python_function_count"] * 5
        + profile["python_branch_node_count"] * 3
        + profile["markdown_heading_count"] * 2
        + round(profile["python_semantic_complexity_points"] / 10)
    )


def change_surface_evidence(
    target_count: int,
    structural_metrics: dict,
    target_profiles: list[dict],
) -> dict:
    whole_file_volume = (
        structural_metrics["nonempty_line_count_total"]
        + structural_metrics["python_function_count"] * 5
        + structural_metrics["python_branch_node_count"] * 3
        + structural_metrics["markdown_heading_count"] * 2
    )
    whole_file_volume_score = volume_score(whole_file_volume)
    capped_volume_total = sum(target_effective_volume(profile) for profile in target_profiles)
    capped_volume_score = volume_score(capped_volume_total)
    semantic_volume = sum(
        profile["python_function_count"] * 3
        + profile["python_branch_node_count"] * 4
        + round(profile["python_semantic_complexity_points"] / 5)
        + profile["markdown_heading_count"] * 2
        for profile in target_profiles
    )
    semantic_volume_score = volume_score(semantic_volume)
    count_score = target_count_score(target_count)
    large_file_target_count = sum(1 for profile in target_profiles if profile["coarse_target"])
    selected_score = max(
        count_score,
        min(whole_file_volume_score, max(capped_volume_score, semantic_volume_score)),
    )
    return {
        "target_count": target_count,
        "target_count_score": count_score,
        "whole_file_volume": whole_file_volume,
        "whole_file_volume_score": whole_file_volume_score,
        "per_target_capped_volume": capped_volume_total,
        "per_target_capped_volume_score": capped_volume_score,
        "semantic_volume": semantic_volume,
        "semantic_volume_score": semantic_volume_score,
        "large_file_target_count": large_file_target_count,
        "coarse_target_bias_mitigated": large_file_target_count > 0
        and selected_score < whole_file_volume_score,
        "selected_score": selected_score,
    }


def change_surface_score(
    target_count: int,
    structural_metrics: dict,
    target_profiles: list[dict] | None = None,
) -> int:
    return change_surface_evidence(
        target_count,
        structural_metrics,
        target_profiles or [],
    )["selected_score"]


def dependency_impact_score(target_paths: list[str]) -> int:
    sensitive: set[str] = set()
    if any(path.startswith("ops/scripts/") for path in target_paths):
        sensitive.add("ops_scripts")
    for rel_path in target_paths:
        if rel_path.startswith("ops/schemas/") or rel_path.endswith(".schema.json"):
            sensitive.add("schemas")
        if rel_path.startswith("ops/policies/"):
            sensitive.add("policies")
        if rel_path == "AGENTS.md":
            sensitive.add("agents")
        if rel_path == "README.md":
            sensitive.add("readme")
        if rel_path == "Makefile":
            sensitive.add("makefile")
        if rel_path in INTERFACE_SCRIPTS:
            sensitive.add("interface")
        if Path(rel_path).name in DEPENDENCY_FILES:
            sensitive.add("dependency")

    if not sensitive:
        return 0
    if sensitive == {"readme"}:
        return 1
    if "dependency" in sensitive:
        return 5
    if "schemas" in sensitive and "interface" in sensitive:
        return 5
    if {"schemas", "policies", "agents", "makefile"} & sensitive:
        return 4 if len(sensitive) < 3 else 5
    if "interface" in sensitive:
        return 4
    if "ops_scripts" in sensitive:
        return 2 if len(sensitive) == 1 else 3
    return 2


def verification_cost_evidence(
    target_count: int,
    test_file_count: int,
    test_case_count: int,
    risk_flags: list[str],
    target_paths: list[str],
) -> dict:
    if target_count == 0 and test_file_count == 0 and not risk_flags:
        return {
            "target_count": target_count,
            "test_file_count": test_file_count,
            "test_case_count": test_case_count,
            "verification_scope": "empty_scope",
            "reasons": ["empty_scope"],
            "selected_score": 0,
        }
    if test_file_count == 0:
        score = 1
        scope = "no_focused_tests_declared"
    elif test_file_count == 1:
        if test_case_count <= 5:
            score = 2
            scope = "focused_single_file"
        elif test_case_count <= 20:
            score = 3
            scope = "dense_single_file"
        else:
            score = 4
            scope = "broad_single_file"
    elif test_file_count == 2:
        score = 3 if test_case_count <= 30 else 4
        scope = "focused_multi_file" if test_case_count <= 30 else "broad_multi_file"
    elif test_file_count == 3:
        score = 4
        scope = "multi_file_suite"
    else:
        score = 5
        scope = "broad_suite"

    reasons: list[str] = [scope]
    if target_count >= 6:
        score = max(score, 4)
        reasons.append("many_targets")
    if any(
        rel_path.startswith("ops/schemas/")
        or rel_path.startswith("ops/policies/")
        or rel_path in INTERFACE_SCRIPTS
        for rel_path in target_paths
    ):
        score = max(score, 4)
        reasons.append("contract_surface")
    if any(flag in {"schema_change", "dependency_change", "migration"} for flag in risk_flags):
        score = 5
        reasons.append("high_risk_flag_requires_full_validation")
    return {
        "target_count": target_count,
        "test_file_count": test_file_count,
        "test_case_count": test_case_count,
        "verification_scope": scope,
        "reasons": reasons,
        "selected_score": min(score, 5),
    }


def verification_cost_score(
    target_count: int,
    test_file_count: int,
    risk_flags: list[str],
    target_paths: list[str],
    test_case_count: int = 0,
) -> int:
    return verification_cost_evidence(
        target_count,
        test_file_count,
        test_case_count,
        risk_flags,
        target_paths,
    )["selected_score"]


def artifact_heterogeneity_score(target_paths: list[str]) -> int:
    type_buckets: set[str] = set()
    for rel_path in target_paths:
        suffix = Path(rel_path).suffix.lower()
        if suffix == ".py":
            type_buckets.add("py")
        elif suffix == ".md":
            type_buckets.add("md")
        elif suffix in {".yaml", ".yml"}:
            type_buckets.add("yaml")
        elif suffix == ".json":
            type_buckets.add("json")
        else:
            type_buckets.add("other")
    return max(0, min(5, len(type_buckets) - 1))


def environment_risk_score(risk_flags: list[str]) -> int:
    if not risk_flags:
        return 0
    if "destructive_command" in risk_flags or "migration" in risk_flags:
        return 5
    if len(risk_flags) == 1:
        return 2
    if len(risk_flags) == 2:
        return 3
    if len(risk_flags) == 3:
        return 4
    return 5


def complexity_dimension_evidence(
    structural_metrics: dict,
    primary_targets: list[tuple[str, Path]],
    supporting_targets: list[tuple[str, Path]],
    risk_flags: list[str],
    target_profiles: list[dict] | None = None,
) -> dict:
    all_target_paths = _dedupe_preserve_order(
        [rel_path for rel_path, _ in (*primary_targets, *supporting_targets)]
    )
    target_count = len(all_target_paths)
    return {
        "change_surface": change_surface_evidence(
            target_count,
            structural_metrics,
            target_profiles or [],
        ),
        "verification_cost": verification_cost_evidence(
            target_count,
            structural_metrics["test_file_count"],
            structural_metrics["test_case_count"],
            risk_flags,
            all_target_paths,
        ),
    }


def complexity_dimensions(
    structural_metrics: dict,
    primary_targets: list[tuple[str, Path]],
    supporting_targets: list[tuple[str, Path]],
    risk_flags: list[str],
    target_profiles: list[dict] | None = None,
) -> dict[str, int]:
    all_target_paths = _dedupe_preserve_order(
        [rel_path for rel_path, _ in (*primary_targets, *supporting_targets)]
    )
    evidence = complexity_dimension_evidence(
        structural_metrics,
        primary_targets,
        supporting_targets,
        risk_flags,
        target_profiles,
    )
    return {
        "change_surface": evidence["change_surface"]["selected_score"],
        "dependency_impact": dependency_impact_score(all_target_paths),
        "verification_cost": evidence["verification_cost"]["selected_score"],
        "artifact_heterogeneity": artifact_heterogeneity_score(all_target_paths),
        "environment_risk": environment_risk_score(risk_flags),
    }


def complexity_score(policy: dict, dimensions: dict[str, int]) -> int:
    weighted = 0
    for name, score in dimensions.items():
        weight = policy["complexity_policy"]["dimensions"][name]["weight"]
        weighted += weight * score
    return round(weighted / 5)


def build_report(
    vault: Path,
    policy: dict,
    resolved_policy_path: Path,
    primary_targets: list[tuple[str, Path]],
    supporting_targets: list[tuple[str, Path]],
    test_files: list[tuple[str, Path]],
    *,
    context: RuntimeContext | None = None,
) -> dict:
    runtime_context = context or RuntimeContext.from_policy(policy)
    state = MechanismAssessmentState()
    primary_structural_metrics = build_structural_metrics(state, primary_targets, test_files)
    total_structural_metrics = build_structural_metrics(
        state,
        [*primary_targets, *supporting_targets],
        test_files,
    )
    total_target_profiles = target_structural_profiles(
        state,
        primary_targets + supporting_targets,
    )
    risk_flag_evidence = detect_risk_flag_evidence(
        state,
        primary_targets + supporting_targets,
        configured_high_risk_flags(policy),
    )
    risk_flags = sorted({entry["flag"] for entry in risk_flag_evidence})
    dimensions = complexity_dimensions(
        total_structural_metrics,
        primary_targets,
        supporting_targets,
        risk_flags,
        total_target_profiles,
    )
    dimension_evidence = complexity_dimension_evidence(
        total_structural_metrics,
        primary_targets,
        supporting_targets,
        risk_flags,
        total_target_profiles,
    )
    primary_target_paths = [rel_path for rel_path, _ in primary_targets]
    supporting_target_paths = [rel_path for rel_path, _ in supporting_targets]
    test_file_paths = [rel_path for rel_path, _ in test_files]

    return {
        "$schema": MECHANISM_ASSESSMENT_SCHEMA,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "primary_targets": primary_target_paths,
        "supporting_targets": supporting_target_paths,
        "test_files": test_file_paths,
        "structural_metrics": primary_structural_metrics,
        "total_structural_metrics": total_structural_metrics,
        "diagnostics": state.report(),
        "complexity_profile": {
            "dimensions": dimensions,
            "complexity_score": complexity_score(policy, dimensions),
            "risk_flags": risk_flags,
            "risk_flag_evidence": risk_flag_evidence,
            "target_profiles": total_target_profiles,
            "dimension_evidence": dimension_evidence,
            "primary_targets": primary_target_paths,
            "supporting_targets": supporting_target_paths,
            "test_files": test_file_paths,
        },
    }


def write_report(vault: Path, report: dict, out_path: str | None) -> Path:
    destination = resolve_schema_backed_report_output_path(
        vault,
        out_path,
        default_relative_path="ops/reports/mechanism-assessment.json",
    )
    rel_path = report_path(vault, destination)
    report = maybe_embed_run_artifact_envelope(
        vault,
        rel_path,
        report,
        schema_path=MECHANISM_ASSESSMENT_SCHEMA,
    )
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=MECHANISM_ASSESSMENT_SCHEMA,
            out_path=out_path,
            default_relative_path="ops/reports/mechanism-assessment.json",
            context="mechanism assessment schema validation failed",
            trailing_newline=False,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--primary-target", action="append", required=True)
    ap.add_argument("--supporting-target", action="append", default=[])
    ap.add_argument("--test-file", action="append", default=[])
    ap.add_argument("--out")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    policy, resolved_policy_path = load_policy(vault, args.policy)
    primary_targets = normalize_targets(vault, _dedupe_preserve_order(args.primary_target))
    supporting_targets = normalize_targets(vault, _dedupe_preserve_order(args.supporting_target))
    test_files = normalize_targets(vault, _dedupe_preserve_order(args.test_file))

    report = build_report(
        vault,
        policy,
        resolved_policy_path,
        primary_targets,
        supporting_targets,
        test_files,
    )
    destination = write_report(vault, report, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nwritten_to={display_path(vault, destination)}")


if __name__ == "__main__":
    main()
