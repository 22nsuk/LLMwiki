from __future__ import annotations

import argparse
import fnmatch
import json
import re
import stat as stat_module
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object,
        write_schema_backed_report,
    )
    from ops.scripts.core.command_runtime import RunWithTimeoutRequest, run_with_timeout
    from ops.scripts.core.derived_surfaces import (
        MANIFEST_PATH as DERIVED_SURFACES_MANIFEST_PATH,
        currentness_output_paths as derived_surface_currentness_output_paths,
        currentness_path_patterns as derived_surface_currentness_path_patterns,
        load_manifest as load_derived_surfaces_manifest,
    )
    from ops.scripts.core.git_runtime import (
        resolve_trusted_git_executable,
        trusted_git_subprocess_env,
    )
    from ops.scripts.core.makefile_runtime import load_makefile_text
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.core.schema_constants_runtime import (
        WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH,
    )
    from ops.scripts.release.release_closeout_fixed_point import (
        fixed_point_initial_targets_from_policy,
        fixed_point_writer_specs_from_policy,
    )
else:
    from ops.scripts.release.release_closeout_fixed_point import (
        fixed_point_initial_targets_from_policy,
        fixed_point_writer_specs_from_policy,
    )

    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        load_optional_json_object,
        write_schema_backed_report,
    )
    from .command_runtime import RunWithTimeoutRequest, run_with_timeout
    from .derived_surfaces import (
        MANIFEST_PATH as DERIVED_SURFACES_MANIFEST_PATH,
        currentness_output_paths as derived_surface_currentness_output_paths,
        currentness_path_patterns as derived_surface_currentness_path_patterns,
        load_manifest as load_derived_surfaces_manifest,
    )
    from .git_runtime import (
        resolve_trusted_git_executable,
        trusted_git_subprocess_env,
    )
    from .makefile_runtime import load_makefile_text
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH


DEFAULT_OUT = "ops/reports/workflow-dependency-planner.json"
DEFAULT_TEST_LANE_REGISTRY = "ops/test-lane-registry.json"
PRODUCER = "ops.scripts.workflow_dependency_planner"
SOURCE_COMMAND = (
    "python -m ops.scripts.workflow_dependency_planner "
    "--vault . --out ops/reports/workflow-dependency-planner.json"
)
TARGET_RE = re.compile(r"^([A-Za-z0-9_.%/@-][A-Za-z0-9_.%/@ -]*):(?P<deps>[^\n#]*)")
MAKE_RECIPE_RE = re.compile(r"\$\((?:MAKE|make)\)\s+(?P<args>[^\n;&|]+)")
TARGET_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.%/@-]+$")
OPTION_OR_ASSIGNMENT_RE = re.compile(r"^(?:-|[A-Za-z_][A-Za-z0-9_]*=)")
GIT_LS_FILES_DEBUG_RE = re.compile(
    r"^  ctime: (?P<ctime_s>\d+):(?P<ctime_ns>\d+)\n"
    r"  mtime: (?P<mtime_s>\d+):(?P<mtime_ns>\d+)\n"
    r"  dev: (?P<dev>\d+)\tino: (?P<ino>\d+)\n"
    r"  uid: (?P<uid>\d+)\tgid: (?P<gid>\d+)\n"
    r"  size: (?P<size>\d+)\tflags: (?P<flags>\d+)\n"
)
GIT_LS_FILES_STAGE_RE = re.compile(
    r"^(?P<mode>\d{6}) (?P<object_id>[0-9a-fA-F]{40,64}) "
    r"(?P<stage>\d)\t(?P<path>.+)$"
)
GIT_OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
GIT_CHANGED_PATHS_TIMEOUT_SECONDS = 30
GIT_BASE_CONFIG_ARGS = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
)


@dataclass(frozen=True)
class _GitCommandObservation:
    command_id: str
    status: str
    returncode: int
    timed_out: bool
    path_count: int = 0
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.command_id,
            "status": self.status,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "path_count": self.path_count,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class _GitChangedPathsResult:
    paths: list[str]
    diagnostics: dict[str, Any]

    @property
    def failed(self) -> bool:
        return self.diagnostics.get("status") in {
            "failed",
            "timed_out",
            "unavailable",
        }


@dataclass(frozen=True)
class _GitIndexEntry:
    mode: str
    object_id: str
    rel_path: str


REPORT_CLOSEOUT_TARGETS = [
    "test-execution-summary-report-contract",
    "generated-artifact-converge",
    "release-closeout-summary-conditional",
    "release-evidence-cohort",
    "learning-readiness-signoff-revalidation",
    "release-evidence-dashboard-report",
    "release-lane-summary",
    "release-clean-blocker-ledger",
    "release-closeout-batch-manifest-promote",
    "release-evidence-closeout-self-check",
    "release-closeout-fixed-point",
    "tmp-json-clean",
    "operator-release-summary",
    "release-closeout-finality-verify",
]
EXTERNAL_REPORT_TARGETS = [
    "external-report-reference-manifest",
    "generated-artifact-converge",
    "release-closeout-summary-conditional",
    "release-evidence-cohort",
    "release-evidence-dashboard-report",
    "release-lane-summary",
    "release-clean-blocker-ledger",
    "release-closeout-batch-manifest-promote",
    "release-evidence-closeout-self-check",
    "release-closeout-fixed-point",
    "tmp-json-clean",
    "operator-release-summary",
    "release-closeout-finality-verify",
]
FINALITY_RESETTLE_TARGETS = [
    "workflow-dependency-planner",
    "release-authority-sealed-preflight",
    "release-terminal-finality",
]

GENERATED_ARTIFACT_CONVERGE_FANOUT_TARGETS = [
    "artifact-freshness",
    "external-report-action-matrix",
    "generated-artifact-index",
]

GENERATED_ARTIFACT_SCRIPT_OUTPUT_TARGETS = [
    "script-output-surfaces",
]

GENERATED_ARTIFACT_FINALITY_SUFFIX_TARGETS = [
    "artifact-freshness",
    "external-report-action-matrix",
    "generated-artifact-index",
]
PLANNER_CLOSEOUT_FALLBACK_TARGETS = [
    "workflow-dependency-planner",
    "generated-artifact-converge",
    "release-closeout-summary-conditional",
    "release-evidence-cohort",
    "release-evidence-dashboard-report",
    "release-lane-summary",
    "release-clean-blocker-ledger",
    "release-closeout-batch-manifest-promote",
    "release-evidence-closeout-self-check",
    "tmp-json-clean",
    "operator-release-summary",
    "release-closeout-finality-verify",
]
WORKFLOW_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "workflow_dependency_planner_contract_change",
        "path_patterns": [
            "Makefile",
            "mk/*.mk",
            ".github/workflows/*.yml",
            ".github/workflows/*.yaml",
            "ops/scripts/core/git_runtime.py",
            "ops/scripts/core/workflow_dependency_planner.py",
            "ops/schemas/workflow-dependency-planner.schema.json",
            "ops/README.md",
            "pyproject.toml",
        ],
        "workflow_id": "workflow_dependency_planner_closeout",
        "recommended_lane": "workflow-dependency-planner",
        "reason_code": "workflow_dependency_planner_input_or_contract_changed",
        "description": "Workflow planner source, schema, Make orchestration, CI fingerprint, or CLI/documentation surface changed; refresh the planner before finality verification.",
        "targets": PLANNER_CLOSEOUT_FALLBACK_TARGETS,
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "generated_artifact_converge_contract_change",
        "path_patterns": [
            "mk/artifact.mk",
            "ops/scripts/core/generated_artifact_*.py",
            "ops/scripts/core/script_output_surfaces.py",
            "ops/schemas/artifact-freshness-report.schema.json",
            "ops/schemas/generated-artifact-index.schema.json",
            "ops/schemas/script-output-surfaces.schema.json",
        ],
        "workflow_id": "generated_artifact_converge_closeout",
        "recommended_lane": "generated-artifact-converge",
        "reason_code": "generated_artifact_converge_contract_changed",
        "description": "Generated-artifact orchestration, source inventory, index, or freshness contract changed; refresh the script-output slice explicitly before the generated-report suffix.",
        "targets": [
            "generated-artifact-script-output",
            "generated-artifact-converge",
            "release-closeout-fixed-point",
            "tmp-json-clean",
            "release-closeout-finality-verify",
        ],
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "runtime_python_source_change",
        "path_patterns": [
            "ops/scripts/**/*.py",
        ],
        "workflow_id": "runtime_python_source_validation",
        "recommended_lane": "runtime-source",
        "reason_code": "runtime_python_source_changed",
        "description": "Ops runtime Python source changed; run static analysis and the default pytest lane before relying on generated or release evidence.",
        "targets": [
            "static",
            "test",
        ],
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "release_runtime_contract_change",
        "path_patterns": [
            "Makefile",
            "mk/*.mk",
            "ops/scripts/release/*.py",
            "ops/scripts/learning/learning_readiness_signoff_revalidation.py",
            "ops/scripts/core/artifact_freshness_runtime.py",
            "ops/scripts/core/generated_artifact_index.py",
            "ops/schemas/release-*.schema.json",
            "ops/schemas/operator-release-summary.schema.json",
            "ops/schemas/learning-readiness-signoff-revalidation.schema.json",
            "ops/schemas/artifact-freshness-report.schema.json",
            "ops/schemas/generated-artifact-index.schema.json",
            "ops/schemas/external-report-reference-manifest.schema.json",
        ],
        "workflow_id": "release_evidence_converge",
        "recommended_lane": "release-evidence-converge",
        "reason_code": "release_runtime_or_schema_contract_changed",
        "description": "Release evidence producers, schemas, or Make orchestration changed; rebuild the ordered release evidence converge chain before trusting operator summaries.",
        "targets": [
            "release-evidence-converge",
            "operator-release-summary",
        ],
        "expensive": True,
        "reusable": False,
    },
    {
        "rule_id": "report_contract_or_test_fingerprint_change",
        "path_patterns": [
            "tests/test_*.py",
            "tests/fixtures/report_schema_sample*.json",
            "tests/report_contract_test_runtime.py",
            "tests/release_run_ready_sample_runtime.py",
            "tests/supply_chain_sample_runtime.py",
            "ops/policies/wiki-maintainer-policy.yaml",
            "ops/schemas/*.schema.json",
            "tools/regenerate_report_schema_samples.py",
        ],
        "workflow_id": "report_contract_closeout",
        "recommended_lane": "report-contract-closeout",
        "reason_code": "report_contract_policy_or_test_target_fingerprint_changed",
        "description": "Report-contract tests, policy input, or schema samples changed; refresh schema samples and test-execution evidence, then close the generated artifact convergence loop.",
        "targets": ["report-contract-closeout", "operator-release-summary"],
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "external_report_reference_change",
        "path_patterns": [
            "external-reports/*.md",
            "external-reports/*.json",
            "ops/scripts/release/external_report_*.py",
            "ops/schemas/external-report-*.schema.json",
        ],
        "workflow_id": "external_report_reference_closeout",
        "recommended_lane": "external-report-reference-manifest",
        "reason_code": "external_report_inventory_or_provenance_changed",
        "description": "Root external reports or their manifest changed; refresh report provenance before generated artifact convergence and release summaries.",
        "targets": EXTERNAL_REPORT_TARGETS,
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "task_observation_inventory_change",
        "path_patterns": [
            "ops/reports/task-improvement-observations/**/improvement-observations.json",
        ],
        "workflow_id": "observation_inventory_closeout",
        "recommended_lane": "release-finality-resettle",
        "reason_code": "task_improvement_observation_inventory_changed",
        "description": "Task observation inventory changed; resettle generated surfaces through the fixed-point writer before finality verification.",
        "targets": FINALITY_RESETTLE_TARGETS,
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "canonical_release_report_change",
        "path_patterns": [
            "ops/reports/*.json",
        ],
        "workflow_id": "canonical_report_finalization",
        "recommended_lane": "release-finality-resettle",
        "reason_code": "canonical_report_finality_suffix_changed",
        "description": "Canonical generated reports changed; use the focused resettle lane so finality is rewritten only after generated artifact convergence and fixed-point closeout.",
        "targets": FINALITY_RESETTLE_TARGETS,
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "script_output_surface_inventory_change",
        "path_patterns": [
            "ops/script-output-surfaces.json",
        ],
        "workflow_id": "script_output_surface_finalization",
        "recommended_lane": "generated-artifact-script-output",
        "reason_code": "script_output_surface_inventory_changed",
        "description": "The script output surface inventory changed; refresh only the script-output slice before fixed-point finality verification.",
        "targets": [
            "workflow-dependency-planner",
            "generated-artifact-script-output",
            "release-closeout-fixed-point",
            "tmp-json-clean",
            "release-closeout-finality-verify",
        ],
        "expensive": False,
        "reusable": True,
    },
    {
        "rule_id": "public_surface_boundary_change",
        "path_patterns": [
            ".gitignore",
            "AGENTS.md",
            "ARCHITECTURE.md",
            ".github/*.yml",
            ".github/*.yaml",
            ".github/workflows/*.yml",
            ".github/workflows/*.yaml",
        ],
        "workflow_id": "public_boundary_closeout",
        "recommended_lane": "public-boundary",
        "reason_code": "public_surface_or_ci_boundary_changed",
        "description": "Public-surface or CI workflow boundaries changed; run static/public policy checks in addition to the relevant evidence refresh.",
        "targets": [
            "static",
            "sync-derived",
            "test-report-contract-core",
            "generated-artifact-converge",
            "operator-release-summary",
        ],
        "expensive": False,
        "reusable": True,
    },
]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _planner_closeout_targets(vault: Path) -> list[str]:
    try:
        policy_targets = fixed_point_initial_targets_from_policy(vault)
    except (OSError, ValueError, json.JSONDecodeError):
        return list(PLANNER_CLOSEOUT_FALLBACK_TARGETS)
    targets = ["workflow-dependency-planner", *policy_targets]
    if "learning-readiness-signoff-revalidation" in policy_targets:
        revalidation_index = targets.index("learning-readiness-signoff-revalidation") + 1
        targets.insert(revalidation_index, "release-evidence-cohort")
    elif "release-closeout-summary-report" in policy_targets:
        summary_index = targets.index("release-closeout-summary-report") + 1
        targets.insert(summary_index, "release-evidence-cohort")
    targets.extend(
        [
            "tmp-json-clean",
            "operator-release-summary",
            "release-closeout-finality-verify",
        ]
    )
    return _dedupe_preserve_order(targets)


def _workflow_rules(vault: Path) -> list[dict[str, Any]]:
    rules = [dict(rule) for rule in WORKFLOW_RULES]
    planner_targets = _planner_closeout_targets(vault)
    for rule in rules:
        if rule.get("workflow_id") == "workflow_dependency_planner_closeout":
            rule["targets"] = planner_targets
    return rules


def _parse_makefile(content: str) -> tuple[set[str], set[str], list[dict[str, str]]]:
    targets: set[str] = set()
    phony: set[str] = set()
    edges: list[dict[str, str]] = []
    current_targets: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(".PHONY:"):
            phony.update(item for item in stripped.split(":", 1)[1].split() if item)
            current_targets = []
            continue
        if line.startswith(("\t", " ")):
            if not line.startswith("\t"):
                continue
            for make_match in MAKE_RECIPE_RE.finditer(line):
                dependency = _first_make_target(make_match.group("args").split())
                if dependency is None:
                    continue
                for consumer in current_targets:
                    edges.append(
                        {
                            "from": consumer,
                            "to": dependency,
                            "source": "make_recipe",
                        }
                    )
            continue
        match = TARGET_RE.match(line)
        if match is None:
            current_targets = []
            continue
        current_targets = [item.strip() for item in match.group(1).split() if item.strip()]
        targets.update(current_targets)
        for dependency in _target_line_dependencies(match.group("deps")):
            for consumer in current_targets:
                edges.append(
                    {
                        "from": consumer,
                        "to": dependency,
                        "source": "make_prerequisite",
                    }
                )
    return targets, phony, sorted(edges, key=lambda item: (item["from"], item["to"], item["source"]))


def _first_make_target(tokens: list[str]) -> str | None:
    for token in tokens:
        cleaned = token.strip().strip('"').strip("'")
        if not cleaned or OPTION_OR_ASSIGNMENT_RE.match(cleaned):
            continue
        if TARGET_TOKEN_RE.match(cleaned):
            return cleaned
    return None


def _target_line_dependencies(raw_deps: str) -> list[str]:
    dependencies: list[str] = []
    for token in raw_deps.split():
        cleaned = token.strip()
        if not cleaned or cleaned.startswith("$") or OPTION_OR_ASSIGNMENT_RE.match(cleaned):
            continue
        if TARGET_TOKEN_RE.match(cleaned):
            dependencies.append(cleaned)
    return dependencies


def _matches_rule(path: str, rule: dict[str, Any]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in rule["path_patterns"])


def _selected_workflows(
    changed_paths: list[str], workflow_rules: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for path in changed_paths:
        for rule in workflow_rules:
            if not _matches_rule(path, rule):
                continue
            workflow_id = str(rule["workflow_id"])
            workflow = selected.setdefault(
                workflow_id,
                {
                    "workflow_id": workflow_id,
                    "recommended_lane": rule["recommended_lane"],
                    "reason_codes": [],
                    "matched_rules": [],
                    "matched_paths": [],
                    "steps": [],
                    "expensive": bool(rule["expensive"]),
                    "reusable": bool(rule["reusable"]),
                },
            )
            workflow["reason_codes"].append(rule["reason_code"])
            workflow["matched_rules"].append(rule["rule_id"])
            workflow["matched_paths"].append(path)
            workflow["expensive"] = bool(workflow["expensive"] or rule["expensive"])
            workflow["reusable"] = bool(workflow["reusable"] and rule["reusable"])
            existing_targets = {step["target"] for step in workflow["steps"]}
            for target in rule["targets"]:
                if target in existing_targets:
                    continue
                workflow["steps"].append(
                    {
                        "order": len(workflow["steps"]) + 1,
                        "target": target,
                        "reason_code": rule["reason_code"],
                        "primary_report": _primary_report_for_target(str(target)),
                        "fanout_targets": _fanout_targets_for_target(str(target)),
                        "expensive": bool(rule["expensive"]),
                        "reusable": bool(rule["reusable"]),
                    }
                )
                existing_targets.add(target)
    for workflow in selected.values():
        workflow["reason_codes"] = sorted(set(workflow["reason_codes"]))
        workflow["matched_rules"] = sorted(set(workflow["matched_rules"]))
        workflow["matched_paths"] = sorted(set(workflow["matched_paths"]))
    return sorted(selected.values(), key=lambda item: item["workflow_id"])


def _primary_report_for_target(target: str) -> str:
    return {
        "artifact-freshness": "ops/reports/artifact-freshness-report.json",
        "external-report-reference-manifest": "external-reports/report-reference-manifest.json",
        "external-report-action-matrix": "ops/reports/external-report-action-matrix.json",
        "generated-artifact-converge": "ops/reports/artifact-freshness-report.json",
        "generated-artifact-script-output": "ops/script-output-surfaces.json",
        "generated-artifact-finality-suffix": "ops/reports/artifact-freshness-report.json",
        "generated-artifact-index": "ops/reports/generated-artifact-index.json",
        "generated-artifact-index-body": "ops/reports/generated-artifact-index.json",
        "learning-readiness-signoff-revalidation": "ops/reports/learning-readiness-signoff-revalidation.json",
        "operator-release-summary": "ops/operator/operator-release-summary.json",
        "release-risk-taxonomy-matrix": "ops/reports/release-risk-taxonomy-matrix.json",
        "release-clean-blocker-ledger": "ops/reports/release-clean-blocker-ledger.json",
        "release-closeout-batch-manifest-promote": "ops/reports/release-closeout-batch-manifest.json",
        "release-closeout-finality-verify": "ops/reports/release-closeout-finality-attestation.json",
        "release-closeout-fixed-point": "ops/reports/release-closeout-fixed-point.json",
        "release-closeout-summary-conditional": "ops/reports/release-closeout-summary.json",
        "release-closeout-summary-report": "ops/reports/release-closeout-summary.json",
        "release-authority-sealed-preflight": "ops/reports/release-closeout-sealed-rehearsal-check.json",
        "release-evidence-closeout-self-check": "ops/reports/release-evidence-closeout-self-check.json",
        "release-evidence-cohort": "ops/reports/release-evidence-cohort.json",
        "release-evidence-dashboard-report": "ops/reports/release-evidence-dashboard.json",
        "release-lane-summary": "ops/reports/release-lane-summary.json",
        "release-smoke-full": "ops/reports/release-smoke-report.json",
        "release-terminal-finality": "ops/reports/release-closeout-finality-attestation.json",
        "test-execution-summary-report-contract": "ops/reports/test-execution-summary.json",
        "workflow-dependency-planner": "ops/reports/workflow-dependency-planner.json",
    }.get(target, "")


def _fanout_targets_for_target(target: str) -> list[str]:
    return {
        "generated-artifact-converge": list(GENERATED_ARTIFACT_CONVERGE_FANOUT_TARGETS),
        "generated-artifact-script-output": list(GENERATED_ARTIFACT_SCRIPT_OUTPUT_TARGETS),
        "generated-artifact-finality-suffix": list(GENERATED_ARTIFACT_FINALITY_SUFFIX_TARGETS),
        "release-terminal-finality": [
            "generated-artifact-finality-suffix",
            "release-closeout-summary-report",
            "release-closeout-fixed-point",
            "release-closeout-post-check-finalizer-dry-run",
            "release-closeout-finality-verify",
        ],
    }.get(target, [])


def _missing_dependencies(targets: set[str], edges: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "consumer": edge["from"],
            "dependency": edge["to"],
            "source": edge["source"],
        }
        for edge in edges
        if edge["to"] not in targets
    ]


def _unknown_change_paths(
    changed_paths: list[str],
    workflow_rules: list[dict[str, Any]],
    changed_path_minimum_plan: dict[str, Any],
) -> list[str]:
    minimum_unknown_paths = {
        str(path) for path in changed_path_minimum_plan.get("unknown_paths", [])
    }
    minimum_known_paths = {
        str(item["path"])
        for item in changed_path_minimum_plan.get("path_recommendations", [])
        if str(item.get("path", "")) and str(item["path"]) not in minimum_unknown_paths
    }
    return [
        path
        for path in changed_paths
        if path not in minimum_known_paths
        and not any(_matches_rule(path, rule) for rule in workflow_rules)
    ]


def _test_lane_registry(vault: Path) -> dict[str, Any]:
    payload = load_optional_json_object(vault / DEFAULT_TEST_LANE_REGISTRY)
    return payload if isinstance(payload, dict) else {}


def _format_command(
    command: str,
    path: str,
    *,
    changed_files_manifest: str | None = None,
) -> str:
    manifest = changed_files_manifest or "<changed-files-manifest>"
    return command.replace("{path}", path).replace("{changed_files_manifest}", manifest)


def _changed_path_minimum_rules(registry: dict[str, Any]) -> dict[str, Any]:
    plan = registry.get("changed_path_minimums")
    return plan if isinstance(plan, dict) else {}


def _derived_surface_currentness(vault: Path) -> dict[str, Any]:
    manifest_path = vault / DERIVED_SURFACES_MANIFEST_PATH
    if not manifest_path.exists():
        return {
            "status": "skipped",
            "path": DERIVED_SURFACES_MANIFEST_PATH,
            "message": "manifest not found",
            "paths": [],
            "output_paths": [],
        }
    try:
        manifest = load_derived_surfaces_manifest(vault)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "path": DERIVED_SURFACES_MANIFEST_PATH,
            "message": f"{exc.__class__.__name__}: {exc}",
            "paths": [],
            "output_paths": [],
        }
    return {
        "status": "pass",
        "path": DERIVED_SURFACES_MANIFEST_PATH,
        "message": "",
        "paths": derived_surface_currentness_path_patterns(manifest),
        "output_paths": derived_surface_currentness_output_paths(manifest),
    }


def _derived_surface_currentness_rules(paths: list[str]) -> list[dict[str, Any]]:
    if not paths:
        return []
    return [
        {
            "rule_id": "derived_surface_currentness",
            "path_patterns": paths,
            "commands": ["make sync-derived-check"],
            "reason": (
                "Derived surface output changes should verify the manifest-owned "
                "source-derived aggregate is current."
            ),
            "coverage_class": "generated_artifact_currentness",
            "static_required": False,
            "duration_seconds": 120,
        }
    ]


def _command_duration_seconds(config: dict[str, Any]) -> dict[str, int]:
    raw_durations = config.get("command_duration_seconds")
    if not isinstance(raw_durations, dict):
        return {}
    durations: dict[str, int] = {}
    for command, duration in raw_durations.items():
        command_text = str(command).strip()
        if not command_text:
            continue
        try:
            durations[command_text] = max(0, int(duration))
        except (TypeError, ValueError):
            continue
    return durations


def _changed_path_final_checkpoint_commands(config: dict[str, Any]) -> list[str]:
    commands = [
        str(command).strip()
        for command in config.get("final_checkpoint_commands", [])
        if str(command).strip()
    ]
    return commands or ["make release-run-ready"]


def _estimate_selected_command_duration_seconds(
    selected_commands: list[str],
    recommendation_duration_inputs: list[dict[str, Any]],
    command_duration_seconds: dict[str, int],
) -> int:
    selected_estimates = _selected_command_duration_seconds(
        selected_commands,
        recommendation_duration_inputs,
        command_duration_seconds,
    )
    if selected_estimates:
        return sum(selected_estimates.values())

    unique_recommendation_durations: dict[tuple[str, ...], int] = {}
    for item in recommendation_duration_inputs:
        command_key = tuple(str(command) for command in item["commands"])
        if not command_key:
            continue
        unique_recommendation_durations[command_key] = max(
            unique_recommendation_durations.get(command_key, 0),
            int(item["duration_seconds"]),
        )
    return sum(unique_recommendation_durations.values())


def _selected_command_duration_seconds(
    selected_commands: list[str],
    recommendation_duration_inputs: list[dict[str, Any]],
    command_duration_seconds: dict[str, int],
) -> dict[str, int]:
    if not command_duration_seconds:
        return {}
    selected_estimates: dict[str, int] = dict.fromkeys(selected_commands, 0)
    missing_estimates: set[str] = set(selected_commands)
    for item in recommendation_duration_inputs:
        commands = item["commands"]
        templates = item["command_templates"]
        for command, template in zip(commands, templates, strict=False):
            template_text = str(template)
            command_text = str(command)
            duration = command_duration_seconds.get(template_text)
            if duration is None:
                duration = command_duration_seconds.get(command_text)
            if duration is None:
                continue
            missing_estimates.discard(command_text)
            selected_estimates[command_text] = max(
                selected_estimates.get(command_text, 0),
                duration,
            )
    if missing_estimates or not any(selected_estimates.values()):
        return {}
    return selected_estimates


def _changed_path_minimum_plan(
    changed_paths: list[str],
    registry: dict[str, Any],
    *,
    changed_files_manifest: str | None = None,
    derived_surface_currentness_paths: list[str] | None = None,
    derived_surface_currentness_status: str = "skipped",
) -> dict[str, Any]:
    config = _changed_path_minimum_rules(registry)
    derived_rules = _derived_surface_currentness_rules(
        derived_surface_currentness_paths or []
    )
    rules = [item for item in config.get("rules", []) if isinstance(item, dict)]
    command_duration_seconds = _command_duration_seconds(config)
    default_rule = config.get("unknown_path")
    if not isinstance(default_rule, dict):
        default_rule = {
            "commands": ["make static", "make test-fast"],
            "reason": "Unknown paths use the conservative advisory minimum lane.",
            "coverage_class": "conservative",
            "static_required": True,
            "duration_seconds": 300,
        }
    path_recommendations: list[dict[str, Any]] = []
    recommendation_duration_inputs: list[dict[str, Any]] = []
    unknown_paths: list[str] = []
    for path in changed_paths:
        matched_rule = next(
            (
                rule
                for rule in rules
                if any(
                    fnmatch.fnmatch(path, str(pattern))
                    for pattern in rule.get("path_patterns", [])
                )
            ),
            None,
        )
        derived_rule = next(
            (
                rule
                for rule in derived_rules
                if any(
                    fnmatch.fnmatch(path, str(pattern))
                    for pattern in rule.get("path_patterns", [])
                )
            ),
            None,
        )
        rule = _combined_changed_path_rule(matched_rule, derived_rule) or default_rule
        if matched_rule is None:
            if derived_rule is None:
                unknown_paths.append(path)
            else:
                matched_rule = derived_rule
        command_templates = [
            str(command) for command in rule.get("commands", []) if str(command).strip()
        ]
        commands = [
            _format_command(
                command,
                path,
                changed_files_manifest=changed_files_manifest,
            )
            for command in command_templates
        ]
        duration_seconds = int(rule.get("duration_seconds", 0) or 0)
        path_recommendations.append(
            {
                "path": path,
                "matched_rule_id": str(rule.get("rule_id", "unknown_path")),
                "commands": commands,
                "reason": str(rule.get("reason", "")).strip(),
                "coverage_class": str(rule.get("coverage_class", "conservative")).strip(),
                "static_required": bool(rule.get("static_required", True)),
                "duration_seconds": duration_seconds,
            }
        )
        recommendation_duration_inputs.append(
            {
                "commands": commands,
                "command_templates": command_templates,
                "duration_seconds": duration_seconds,
            }
        )
    selected_commands = _dedupe_preserve_order(
        [
            command
            for recommendation in path_recommendations
            for command in recommendation["commands"]
        ]
    )
    estimated_duration_seconds = _estimate_selected_command_duration_seconds(
        selected_commands,
        recommendation_duration_inputs,
        command_duration_seconds,
    )
    selected_command_duration_seconds = _selected_command_duration_seconds(
        selected_commands,
        recommendation_duration_inputs,
        command_duration_seconds,
    )
    duration_budget_seconds = int(config.get("default_duration_budget_seconds", 0) or 0)
    if not path_recommendations:
        budget_status = "not_applicable"
        coverage_class = "none"
    else:
        budget_status = (
            "unknown"
            if duration_budget_seconds <= 0
            else "within_budget"
            if estimated_duration_seconds <= duration_budget_seconds
            else "over_budget"
        )
        coverage_classes = sorted(
            {str(item["coverage_class"]) for item in path_recommendations}
        )
        coverage_class = coverage_classes[0] if len(coverage_classes) == 1 else "mixed"
    status = (
        "attention"
        if unknown_paths or derived_surface_currentness_status == "failed"
        else "pass"
    )
    return {
        "status": status,
        "advisory": True,
        "registry_path": DEFAULT_TEST_LANE_REGISTRY,
        "selected_commands": selected_commands,
        "final_checkpoint_required": True,
        "final_checkpoint_commands": _changed_path_final_checkpoint_commands(config),
        "release_proof_replacement": False,
        "coverage_class": coverage_class,
        "static_required": any(item["static_required"] for item in path_recommendations),
        "budget_status": budget_status,
        "duration_budget_seconds": duration_budget_seconds,
        "estimated_duration_seconds": estimated_duration_seconds,
        "command_duration_seconds": selected_command_duration_seconds,
        "unknown_paths": unknown_paths,
        "path_recommendations": path_recommendations,
    }


def _combined_changed_path_rule(
    matched_rule: dict[str, Any] | None,
    derived_rule: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if matched_rule is None:
        return derived_rule
    if derived_rule is None:
        return matched_rule
    matched_rule_id = str(matched_rule.get("rule_id", "")).strip()
    derived_rule_id = str(derived_rule.get("rule_id", "")).strip()
    commands = _dedupe_preserve_order(
        [
            *[
                str(command)
                for command in matched_rule.get("commands", [])
                if str(command).strip()
            ],
            *[
                str(command)
                for command in derived_rule.get("commands", [])
                if str(command).strip()
            ],
        ]
    )
    return {
        "rule_id": "+".join(
            rule_id for rule_id in (matched_rule_id, derived_rule_id) if rule_id
        ),
        "commands": commands,
        "reason": " ".join(
            reason
            for reason in (
                str(matched_rule.get("reason", "")).strip(),
                str(derived_rule.get("reason", "")).strip(),
            )
            if reason
        ),
        "coverage_class": str(
            matched_rule.get("coverage_class", "conservative")
        ).strip(),
        "static_required": bool(
            matched_rule.get("static_required", True)
            or derived_rule.get("static_required", True)
        ),
        "duration_seconds": int(matched_rule.get("duration_seconds", 0) or 0)
        + int(derived_rule.get("duration_seconds", 0) or 0),
    }


def _current_evidence_signals() -> list[dict[str, str]]:
    return [
        {
            "source": "workflow_rules",
            "name": "full_suite_evidence",
            "status": "required_for_clean_release",
            "recommended_target": "test-execution-summary-full",
        },
        {
            "source": "workflow_rules",
            "name": "tmp_json_hygiene",
            "status": "required_before_batch_verify",
            "recommended_target": "tmp-json-clean",
        },
        {
            "source": "workflow_rules",
            "name": "operator_summary",
            "status": "refresh_after_batch_manifest",
            "recommended_target": "operator-release-summary",
        },
        {
            "source": "workflow_rules",
            "name": "finality_resettle",
            "status": "required_after_canonical_report_or_observation_changes",
            "recommended_target": "release-finality-resettle",
        },
    ]


def _evidence_dag(vault: Path) -> dict[str, Any]:
    try:
        writers = fixed_point_writer_specs_from_policy(vault)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "source": "ops/policies/release-closeout-fixed-point.json",
            "status": "attention",
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
            "diagnostics": {
                "policy_load_status": "failed",
                "message": f"{exc.__class__.__name__}: {exc}",
            },
        }
    nodes = _evidence_dag_nodes(writers)
    edges = _evidence_dag_edges(writers)
    return {
        "source": "ops/policies/release-closeout-fixed-point.json",
        "status": "pass",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "diagnostics": {
            "policy_load_status": "pass",
            "message": "",
        },
    }


def _evidence_dag_nodes(writers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for order, writer in enumerate(writers, start=1):
        target = str(writer["target"])
        produces = [str(path) for path in writer["produces"]]
        nodes.append(
            {
                "order": order,
                "name": str(writer["name"]),
                "target": target,
                "primary_report": _primary_report_for_target(target)
                or (produces[0] if produces else ""),
                "produces": produces,
                "output_role": "canonical_report",
                "source": "fixed_point_policy_writer",
            }
        )
    return nodes


def _evidence_dag_edges(writers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    writer_by_target = {str(writer["target"]): writer for writer in writers}
    edges: list[dict[str, Any]] = []
    for writer in writers:
        consumer_target = str(writer["target"])
        consumer_reports = [str(path) for path in writer["produces"]]
        for dependency in writer["depends_on"]:
            producer = writer_by_target.get(str(dependency))
            producer_reports = (
                [str(path) for path in producer["produces"]] if producer is not None else []
            )
            edges.append(
                {
                    "from": str(dependency),
                    "to": consumer_target,
                    "source": "fixed_point_policy_depends_on",
                    "from_reports": producer_reports,
                    "to_reports": consumer_reports,
                }
            )
    return sorted(edges, key=lambda item: (item["to"], item["from"], item["source"]))


def _read_changed_paths(vault: Path, changed_files_manifest: str | None) -> list[str]:
    if not changed_files_manifest:
        return []
    payload = load_optional_json_object(vault / changed_files_manifest)
    paths: list[str] = []
    for key in ("changed_files", "files", "paths"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.append(item["path"])
    return paths


def _git_changed_paths_diagnostics(
    *,
    status: str,
    source: str,
    path_count: int = 0,
    reason: str = "",
    commands: list[_GitCommandObservation] | None = None,
    failures: list[dict[str, str]] | None = None,
    ignored_path_entry_count: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "source": source,
        "path_count": path_count,
        "commands": [command.to_payload() for command in commands or []],
        "failures": failures or [],
        "ignored_path_entry_count": ignored_path_entry_count,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _skipped_git_changed_paths(
    reason: str,
    *,
    source: str = "none",
    commands: list[_GitCommandObservation] | None = None,
    ignored_path_entry_count: int = 0,
) -> _GitChangedPathsResult:
    return _GitChangedPathsResult(
        paths=[],
        diagnostics=_git_changed_paths_diagnostics(
            status="skipped",
            source=source,
            reason=reason,
            commands=commands,
            ignored_path_entry_count=ignored_path_entry_count,
        ),
    )


def _split_nul_paths(stdout: str) -> list[str]:
    return [item for item in stdout.split("\0") if item]


def _run_git_raw_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    command_id: str,
    args: list[str],
) -> tuple[str, _GitCommandObservation, dict[str, str] | None]:
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[git_executable, *GIT_BASE_CONFIG_ARGS, *args],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
        )
    )
    if result.timed_out:
        observation = _GitCommandObservation(
            command_id=command_id,
            status="timed_out",
            returncode=result.returncode,
            timed_out=True,
            reason="git_probe_timed_out",
        )
        return "", observation, {
            "command_id": command_id,
            "code": "git_probe_timed_out",
        }
    if result.returncode != 0:
        observation = _GitCommandObservation(
            command_id=command_id,
            status="failed",
            returncode=result.returncode,
            timed_out=False,
            reason="git_probe_failed",
        )
        return "", observation, {
            "command_id": command_id,
            "code": "git_probe_failed",
        }
    return (
        result.stdout,
        _GitCommandObservation(
            command_id=command_id,
            status="pass",
            returncode=result.returncode,
            timed_out=False,
        ),
        None,
    )


def _run_git_changed_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    command_id: str,
    args: list[str],
) -> tuple[list[str], _GitCommandObservation, dict[str, str] | None]:
    stdout, observation, failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id=command_id,
        args=args,
    )
    if failure is not None:
        return [], observation, failure
    paths = _split_nul_paths(stdout)
    return (
        paths,
        _GitCommandObservation(
            command_id=observation.command_id,
            status=observation.status,
            returncode=observation.returncode,
            timed_out=observation.timed_out,
            path_count=len(paths),
            reason=observation.reason,
        ),
        None,
    )


def _stderr_indicates_missing_worktree(stderr: str) -> bool:
    normalized = stderr.lower()
    return "not a git repository" in normalized or "not a git repo" in normalized


def _git_worktree_exists(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, _GitCommandObservation, dict[str, str] | None]:
    command_id = "rev-parse-worktree"
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[
                git_executable,
                *GIT_BASE_CONFIG_ARGS,
                "rev-parse",
                "--is-inside-work-tree",
            ],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
        )
    )
    if result.timed_out:
        return (
            False,
            _GitCommandObservation(
                command_id=command_id,
                status="timed_out",
                returncode=result.returncode,
                timed_out=True,
                reason="git_probe_timed_out",
            ),
            {"command_id": command_id, "code": "git_probe_timed_out"},
        )
    if result.returncode == 0 and result.stdout.strip() == "true":
        return (
            True,
            _GitCommandObservation(
                command_id=command_id,
                status="pass",
                returncode=result.returncode,
                timed_out=False,
            ),
            None,
        )
    if result.returncode == 0 or _stderr_indicates_missing_worktree(result.stderr):
        return (
            False,
            _GitCommandObservation(
                command_id=command_id,
                status="not_worktree",
                returncode=result.returncode,
                timed_out=False,
                reason="git_worktree_missing",
            ),
            None,
        )
    return (
        False,
        _GitCommandObservation(
            command_id=command_id,
            status="failed",
            returncode=result.returncode,
            timed_out=False,
            reason="git_probe_failed",
        ),
        {"command_id": command_id, "code": "git_probe_failed"},
    )


def _index_time_ns(match: re.Match[str], prefix: str) -> int:
    return int(match.group(f"{prefix}_s")) * 1_000_000_000 + int(
        match.group(f"{prefix}_ns")
    )


def _git_index_entry(record: str) -> _GitIndexEntry | None:
    match = GIT_LS_FILES_STAGE_RE.match(record)
    if match is None:
        return None
    return _GitIndexEntry(
        mode=match.group("mode"),
        object_id=match.group("object_id").lower(),
        rel_path=match.group("path"),
    )


def _git_mode_from_lstat_mode(mode: int) -> str | None:
    if stat_module.S_ISLNK(mode):
        return "120000"
    if stat_module.S_ISREG(mode):
        return "100755" if mode & 0o111 else "100644"
    return None


def _index_entry_stat_changed(
    vault: Path,
    entry: _GitIndexEntry,
    match: re.Match[str],
) -> bool:
    try:
        stat_result = (vault / entry.rel_path).lstat()
    except OSError:
        return False
    worktree_mode = _git_mode_from_lstat_mode(stat_result.st_mode)
    if entry.mode not in {"160000", worktree_mode}:
        return True
    return any(
        (
            stat_result.st_size != int(match.group("size")),
            stat_result.st_mtime_ns != _index_time_ns(match, "mtime"),
            stat_result.st_ctime_ns != _index_time_ns(match, "ctime"),
            stat_result.st_dev != int(match.group("dev")),
            stat_result.st_ino != int(match.group("ino")),
        )
    )


def _modified_paths_from_index_debug(vault: Path, stdout: str) -> list[str]:
    segments = stdout.split("\0")
    if not segments:
        return []
    stage_record = segments[0]
    modified_paths: list[str] = []
    for segment in segments[1:]:
        if not stage_record:
            break
        entry = _git_index_entry(stage_record)
        if entry is None:
            break
        match = GIT_LS_FILES_DEBUG_RE.match(segment)
        if match is None:
            break
        if _index_entry_stat_changed(vault, entry, match):
            modified_paths.append(entry.rel_path)
        stage_record = segment[match.end() :]
    return modified_paths


def _gitlink_entries_from_ls_files_stage(stdout: str) -> dict[str, _GitIndexEntry]:
    entries: dict[str, _GitIndexEntry] = {}
    for record in _split_nul_paths(stdout):
        entry = _git_index_entry(record)
        if entry is None or entry.mode != "160000":
            continue
        entries[entry.rel_path] = entry
    return entries


def _git_dir_from_marker(marker: Path) -> Path | None:
    try:
        if marker.is_symlink():
            return None
        if marker.is_dir():
            return marker.resolve()
        if not marker.is_file():
            return None
        first_line = marker.read_text(encoding="utf-8", errors="replace").splitlines()[
            0:1
        ]
    except OSError:
        return None
    if not first_line:
        return None
    prefix, separator, raw_git_dir = first_line[0].partition(":")
    if prefix.strip().lower() != "gitdir" or not separator:
        return None
    try:
        return (marker.parent / raw_git_dir.strip()).resolve()
    except OSError:
        return None


def _submodule_git_dir(vault: Path, rel_path: str) -> Path | None:
    git_dir = _git_dir_from_marker(vault / rel_path / ".git")
    storage_root = _git_dir_from_marker(vault / ".git")
    if git_dir is None or storage_root is None:
        return None
    try:
        git_dir.relative_to(storage_root)
    except ValueError:
        return None
    return git_dir


def _read_packed_git_ref(git_dir: Path, ref_name: str) -> str | None:
    try:
        lines = (git_dir / "packed-refs").read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        return None
    for line in lines:
        if not line or line.startswith(("#", "^")):
            continue
        object_id, separator, name = line.partition(" ")
        if separator and name == ref_name and GIT_OBJECT_ID_RE.fullmatch(object_id):
            return object_id.lower()
    return None


def _read_git_dir_head(git_dir: Path) -> str | None:
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if GIT_OBJECT_ID_RE.fullmatch(head):
        return head.lower()
    prefix, separator, ref_name = head.partition(":")
    if prefix != "ref" or not separator:
        return None
    ref_name = ref_name.strip()
    try:
        ref_path = (git_dir / ref_name).resolve()
        ref_path.relative_to(git_dir.resolve())
        ref_value = ref_path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, ValueError):
        ref_value = ""
    if GIT_OBJECT_ID_RE.fullmatch(ref_value):
        return ref_value.lower()
    return _read_packed_git_ref(git_dir, ref_name)


def _submodule_command_id(rel_path: str, command_id: str) -> str:
    return f"submodule:{rel_path}:{command_id}"


def _submodule_worktree_dirty(
    *,
    vault: Path,
    entry: _GitIndexEntry,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, list[_GitCommandObservation], list[dict[str, str]]]:
    submodule_root = vault / entry.rel_path
    if not submodule_root.is_dir():
        return False, [], []
    commands: list[_GitCommandObservation] = []
    failures: list[dict[str, str]] = []
    worktree_paths, worktree_observation, worktree_failure = _run_git_changed_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        command_id=_submodule_command_id(entry.rel_path, "ls-files-worktree"),
        args=["ls-files", "-z", "-d", "-o", "--exclude-standard"],
    )
    commands.append(worktree_observation)
    if worktree_failure is not None:
        failures.append(worktree_failure)
        return False, commands, failures
    modified_paths, modified_observation, modified_failure = _run_git_modified_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        command_id=_submodule_command_id(entry.rel_path, "ls-files-index-stats"),
    )
    commands.append(modified_observation)
    if modified_failure is not None:
        failures.append(modified_failure)
        return False, commands, failures
    has_head, head_observation, head_failure = _git_head_exists(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
    )
    commands.append(
        _GitCommandObservation(
            command_id=_submodule_command_id(entry.rel_path, head_observation.command_id),
            status=head_observation.status,
            returncode=head_observation.returncode,
            timed_out=head_observation.timed_out,
            path_count=head_observation.path_count,
            reason=head_observation.reason,
        )
    )
    if head_failure is not None:
        failures.append(
            {
                "command_id": _submodule_command_id(
                    entry.rel_path,
                    str(head_failure.get("command_id", "rev-parse-head")),
                ),
                "code": str(head_failure["code"]),
            }
        )
        return False, commands, failures
    if has_head:
        staged_args = ["diff-index", "--cached", "-z", "--name-only", "HEAD", "--"]
        staged_command_id = "diff-index-cached"
    else:
        staged_args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        staged_command_id = "ls-files-no-head"
    staged_paths, staged_observation, staged_failure = _run_git_changed_paths_command(
        vault=submodule_root,
        git_executable=git_executable,
        env=env,
        command_id=_submodule_command_id(entry.rel_path, staged_command_id),
        args=staged_args,
    )
    commands.append(staged_observation)
    if staged_failure is not None:
        failures.append(staged_failure)
        return False, commands, failures
    return (
        bool(worktree_paths or modified_paths or staged_paths),
        commands,
        failures,
    )


def _submodule_changed(
    *,
    vault: Path,
    entry: _GitIndexEntry,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, list[_GitCommandObservation], list[dict[str, str]]]:
    git_dir = _submodule_git_dir(vault, entry.rel_path)
    if git_dir is None:
        return False, [], []
    current_head = _read_git_dir_head(git_dir)
    head_changed = current_head is None or current_head != entry.object_id
    dirty, commands, failures = _submodule_worktree_dirty(
        vault=vault,
        entry=entry,
        git_executable=git_executable,
        env=env,
    )
    return head_changed or dirty, commands, failures


def _submodule_changed_paths(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    stdout: str,
) -> tuple[list[str], list[_GitCommandObservation], list[dict[str, str]]]:
    paths: list[str] = []
    commands: list[_GitCommandObservation] = []
    failures: list[dict[str, str]] = []
    for entry in _gitlink_entries_from_ls_files_stage(stdout).values():
        changed, submodule_commands, submodule_failures = _submodule_changed(
            vault=vault,
            entry=entry,
            git_executable=git_executable,
            env=env,
        )
        commands.extend(submodule_commands)
        failures.extend(submodule_failures)
        if changed:
            paths.append(entry.rel_path)
    return paths, commands, failures


def _run_git_submodule_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[list[str], list[_GitCommandObservation], list[dict[str, str]]]:
    stdout, observation, failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="ls-files-gitlinks",
        args=["ls-files", "-z", "-s"],
    )
    if failure is not None:
        return [], [observation], [failure]
    paths, commands, failures = _submodule_changed_paths(
        vault=vault,
        git_executable=git_executable,
        env=env,
        stdout=stdout,
    )
    return (
        paths,
        [
            _GitCommandObservation(
                command_id=observation.command_id,
                status=observation.status,
                returncode=observation.returncode,
                timed_out=observation.timed_out,
                path_count=len(paths),
                reason=observation.reason,
            ),
            *commands,
        ],
        failures,
    )


def _run_git_modified_paths_command(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
    command_id: str = "ls-files-index-stats",
) -> tuple[list[str], _GitCommandObservation, dict[str, str] | None]:
    stdout, observation, failure = _run_git_raw_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id=command_id,
        args=["ls-files", "-z", "-s", "--debug"],
    )
    if failure is not None:
        return [], observation, failure
    paths = _modified_paths_from_index_debug(vault, stdout)
    return (
        paths,
        _GitCommandObservation(
            command_id=observation.command_id,
            status=observation.status,
            returncode=observation.returncode,
            timed_out=observation.timed_out,
            path_count=len(paths),
            reason=observation.reason,
        ),
        None,
    )


def _git_head_exists(
    *,
    vault: Path,
    git_executable: str,
    env: dict[str, str],
) -> tuple[bool, _GitCommandObservation, dict[str, str] | None]:
    result = run_with_timeout(
        RunWithTimeoutRequest(
            argv=[
                git_executable,
                *GIT_BASE_CONFIG_ARGS,
                "rev-parse",
                "--verify",
                "--quiet",
                "HEAD",
            ],
            cwd=vault,
            timeout_seconds=GIT_CHANGED_PATHS_TIMEOUT_SECONDS,
            env=env,
        )
    )
    if result.timed_out:
        observation = _GitCommandObservation(
            command_id="rev-parse-head",
            status="timed_out",
            returncode=result.returncode,
            timed_out=True,
            reason="git_probe_timed_out",
        )
        return False, observation, {
            "command_id": "rev-parse-head",
            "code": "git_probe_timed_out",
        }
    if result.returncode == 0:
        return (
            True,
            _GitCommandObservation(
                command_id="rev-parse-head",
                status="pass",
                returncode=result.returncode,
                timed_out=False,
            ),
            None,
        )
    if result.returncode == 1:
        return (
            False,
            _GitCommandObservation(
                command_id="rev-parse-head",
                status="no_head",
                returncode=result.returncode,
                timed_out=False,
                reason="git_head_missing",
            ),
            None,
        )
    observation = _GitCommandObservation(
        command_id="rev-parse-head",
        status="failed",
        returncode=result.returncode,
        timed_out=False,
        reason="git_probe_failed",
    )
    return False, observation, {
        "command_id": "rev-parse-head",
        "code": "git_probe_failed",
    }


def _failed_git_changed_paths_result(
    *,
    paths: list[str],
    commands: list[_GitCommandObservation],
    failures: list[dict[str, str]],
    ignored_path_entry_count: int,
) -> _GitChangedPathsResult:
    unique_paths = sorted(set(paths))
    failed_statuses = {command.status for command in commands if command.status != "pass"}
    status = "timed_out" if "timed_out" in failed_statuses else "failed"
    return _GitChangedPathsResult(
        paths=unique_paths,
        diagnostics=_git_changed_paths_diagnostics(
            status=status,
            source="git",
            path_count=len(unique_paths),
            reason="git_probe_failed",
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        ),
    )


def _read_git_changed_paths(vault: Path) -> _GitChangedPathsResult:
    if not (vault / ".git").exists():
        return _skipped_git_changed_paths("source_package_without_git")
    git_executable, path_text, ignored_path_entry_count = resolve_trusted_git_executable(
        vault
    )
    if git_executable is None:
        return _GitChangedPathsResult(
            paths=[],
            diagnostics=_git_changed_paths_diagnostics(
                status="unavailable",
                source="git",
                reason="git_executable_unavailable",
                failures=[{"code": "git_executable_unavailable"}],
                ignored_path_entry_count=ignored_path_entry_count,
            ),
        )
    env = trusted_git_subprocess_env(path_text)
    commands: list[_GitCommandObservation] = []
    failures: list[dict[str, str]] = []
    paths: list[str] = []
    has_worktree, worktree_probe, worktree_probe_failure = _git_worktree_exists(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.append(worktree_probe)
    if worktree_probe_failure is not None:
        failures.append(worktree_probe_failure)
    if failures:
        return _failed_git_changed_paths_result(
            paths=paths,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    if not has_worktree:
        return _skipped_git_changed_paths(
            "git_worktree_missing",
            source="git",
            commands=commands,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    worktree_paths, worktree_observation, worktree_failure = _run_git_changed_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id="ls-files-worktree",
        args=["ls-files", "-z", "-d", "-o", "--exclude-standard"],
    )
    commands.append(worktree_observation)
    if worktree_failure is not None:
        failures.append(worktree_failure)
    paths.extend(worktree_paths)
    if failures:
        return _failed_git_changed_paths_result(
            paths=paths,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    modified_paths, modified_observation, modified_failure = _run_git_modified_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.append(modified_observation)
    if modified_failure is not None:
        failures.append(modified_failure)
    paths.extend(modified_paths)
    if failures:
        return _failed_git_changed_paths_result(
            paths=paths,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    submodule_paths, submodule_observations, submodule_failures = (
        _run_git_submodule_paths_command(
            vault=vault,
            git_executable=git_executable,
            env=env,
        )
    )
    commands.extend(submodule_observations)
    failures.extend(submodule_failures)
    paths.extend(submodule_paths)
    if failures:
        return _failed_git_changed_paths_result(
            paths=paths,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    has_head, head_observation, head_failure = _git_head_exists(
        vault=vault,
        git_executable=git_executable,
        env=env,
    )
    commands.append(head_observation)
    if head_failure is not None:
        failures.append(head_failure)
    if failures:
        return _failed_git_changed_paths_result(
            paths=paths,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    if has_head:
        staged_args = ["diff-index", "--cached", "-z", "--name-only", "HEAD", "--"]
        command_id = "diff-index-cached"
    else:
        staged_args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        command_id = "ls-files-no-head"
    staged_paths, staged_observation, staged_failure = _run_git_changed_paths_command(
        vault=vault,
        git_executable=git_executable,
        env=env,
        command_id=command_id,
        args=staged_args,
    )
    commands.append(staged_observation)
    if staged_failure is not None:
        failures.append(staged_failure)
    paths.extend(staged_paths)
    unique_paths = sorted(set(paths))
    if failures:
        return _failed_git_changed_paths_result(
            paths=paths,
            commands=commands,
            failures=failures,
            ignored_path_entry_count=ignored_path_entry_count,
        )
    return _GitChangedPathsResult(
        paths=unique_paths,
        diagnostics=_git_changed_paths_diagnostics(
            status="pass",
            source="git",
            path_count=len(unique_paths),
            commands=commands,
            ignored_path_entry_count=ignored_path_entry_count,
        ),
    )


def build_report(
    vault: Path,
    *,
    changed_paths: list[str] | None = None,
    changed_files_manifest: str | None = None,
    changed_paths_from_git: bool = False,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    resolved_vault = vault.resolve()
    policy, resolved_policy_path = load_policy(resolved_vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    makefile_text, makefile_sources = load_makefile_text(resolved_vault)
    targets, phony, dependency_edges = _parse_makefile(makefile_text)
    manifest_paths = _read_changed_paths(resolved_vault, changed_files_manifest)
    if changed_files_manifest:
        git_changed_paths = _skipped_git_changed_paths("changed_files_manifest")
    elif not changed_paths_from_git:
        git_changed_paths = _skipped_git_changed_paths("changed_paths_from_git_disabled")
    else:
        git_changed_paths = _read_git_changed_paths(resolved_vault)
    git_paths = git_changed_paths.paths
    selected_paths = sorted({*(changed_paths or []), *manifest_paths, *git_paths})
    workflow_rules = _workflow_rules(resolved_vault)
    test_lane_registry = _test_lane_registry(resolved_vault)
    derived_surface_currentness = _derived_surface_currentness(resolved_vault)
    derived_surface_currentness_paths = [
        str(path) for path in derived_surface_currentness["paths"]
    ]
    changed_path_minimum_plan = _changed_path_minimum_plan(
        selected_paths,
        test_lane_registry,
        changed_files_manifest=changed_files_manifest,
        derived_surface_currentness_paths=derived_surface_currentness_paths,
        derived_surface_currentness_status=str(derived_surface_currentness["status"]),
    )
    missing_dependencies = _missing_dependencies(targets, dependency_edges)
    unknown_change_paths = _unknown_change_paths(
        selected_paths,
        workflow_rules,
        changed_path_minimum_plan,
    )
    selected_workflows = _selected_workflows(selected_paths, workflow_rules)
    evidence_dag = _evidence_dag(resolved_vault)
    status = (
        "fail"
        if missing_dependencies or git_changed_paths.failed
        else "attention"
        if unknown_change_paths or derived_surface_currentness["status"] == "failed"
        else "pass"
    )
    file_inputs: dict[str, str] = {path: path for path in makefile_sources}
    ci_workflow = resolved_vault / ".github" / "workflows" / "ci.yml"
    if ci_workflow.exists():
        file_inputs[".github/workflows/ci.yml"] = ".github/workflows/ci.yml"
    if changed_files_manifest:
        file_inputs["changed_files_manifest"] = changed_files_manifest
    if (resolved_vault / DEFAULT_TEST_LANE_REGISTRY).exists():
        file_inputs["test_lane_registry"] = DEFAULT_TEST_LANE_REGISTRY
    if (resolved_vault / DERIVED_SURFACES_MANIFEST_PATH).exists():
        file_inputs["derived_surfaces_manifest"] = DERIVED_SURFACES_MANIFEST_PATH
    return {
        **build_canonical_report_envelope(
            resolved_vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="workflow_dependency_planner",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/core/git_runtime.py",
                "ops/scripts/core/workflow_dependency_planner.py",
                "Makefile",
                *[path for path in makefile_sources if path != "Makefile"],
                DERIVED_SURFACES_MANIFEST_PATH,
                "ops/README.md",
            ],
            file_inputs=file_inputs,
            text_inputs={
                "workflow_rules": json.dumps(workflow_rules, ensure_ascii=False, sort_keys=True),
                "generated_artifact_converge_fanout_targets": json.dumps(
                    {
                        "generated-artifact-converge": GENERATED_ARTIFACT_CONVERGE_FANOUT_TARGETS,
                        "generated-artifact-script-output": GENERATED_ARTIFACT_SCRIPT_OUTPUT_TARGETS,
                        "generated-artifact-finality-suffix": GENERATED_ARTIFACT_FINALITY_SUFFIX_TARGETS,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            },
        ),
        "vault": report_path(resolved_vault, resolved_vault),
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": status,
        "summary": {
            "workflow_rule_count": len(workflow_rules),
            "selected_change_path_count": len(selected_paths),
            "selected_workflow_count": len(selected_workflows),
            "dependency_edge_count": len(dependency_edges),
            "missing_dependency_count": len(missing_dependencies),
            "unknown_change_path_count": len(unknown_change_paths),
            "changed_path_minimum_command_count": len(
                changed_path_minimum_plan["selected_commands"]
            ),
            "changed_path_minimum_budget_status": changed_path_minimum_plan[
                "budget_status"
            ],
            "evidence_node_count": evidence_dag["node_count"],
            "evidence_edge_count": evidence_dag["edge_count"],
        },
        "selected_change_paths": selected_paths,
        "workflow_rules": workflow_rules,
        "selected_workflows": selected_workflows,
        "changed_path_minimum_plan": changed_path_minimum_plan,
        "dependency_edges": dependency_edges,
        "evidence_dag": evidence_dag,
        "current_evidence_signals": _current_evidence_signals(),
        "diagnostics": {
            "makefile_path": "Makefile",
            "target_count": len(targets),
            "phony_count": len(phony),
            "missing_dependencies": missing_dependencies,
            "unknown_change_paths": unknown_change_paths,
            "git_changed_paths": git_changed_paths.diagnostics,
            "derived_surfaces_manifest": {
                "status": str(derived_surface_currentness["status"]),
                "path": str(derived_surface_currentness["path"]),
                "message": str(derived_surface_currentness["message"]),
                "currentness_output_count": len(
                    derived_surface_currentness["output_paths"]
                ),
            },
        },
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=WORKFLOW_DEPENDENCY_PLANNER_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="workflow dependency planner schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a schema-backed workflow dependency planner")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--changed-files-manifest")
    parser.add_argument(
        "--changed-paths-from-git",
        action="store_true",
        help="Use the current git working-tree diff when no manifest is supplied.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        changed_paths=list(args.changed_path),
        changed_files_manifest=args.changed_files_manifest,
        changed_paths_from_git=args.changed_paths_from_git,
        policy_path=args.policy_path,
    )
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0 if report["status"] in {"pass", "attention"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
