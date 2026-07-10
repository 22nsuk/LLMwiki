from __future__ import annotations

import datetime as dt
import json
import shlex
import tempfile
import unittest
from pathlib import Path
from typing import Any

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_workflow_order_guard import (
    build_report,
    check_report,
    check_workflow_order_spec_raw_lines,
    write_report,
    write_workflow_order_spec_raw_lines,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-workflow-order-guard.schema.json"
SPEC_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-workflow-order-guard-spec.schema.json"
SPEC_PATH = REPO_ROOT / "ops" / "policies" / "release-workflow-order-guard.json"
CRITICAL_GUARD_ARRAYS = (
    "protected_recipes",
    "expected_subsequences",
    "terminal_checks",
    "first_role_checks",
    "repetition_budgets",
    "forbidden_target_checks",
)


def _make_recipe(*roles: str) -> str:
    return "".join(_recipe_line_for_role(role) for role in roles)


def _workflow_order_spec() -> dict[str, object]:
    payload = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("workflow order spec must be a JSON object")
    return payload


def _cloned_workflow_order_spec() -> dict[str, object]:
    return json.loads(json.dumps(_workflow_order_spec()))


def _sequence_roles(check_id: str) -> tuple[str, ...]:
    for entry in _workflow_order_spec()["expected_subsequences"]:
        if isinstance(entry, dict) and entry.get("id") == check_id:
            return tuple(str(role) for role in entry["roles"])
    raise AssertionError(f"missing workflow order sequence: {check_id}")


def _make_assignment_args(assignments: dict[str, object]) -> str:
    return " ".join(
        f"{name}={shlex.quote(str(value))}"
        for name, value in assignments.items()
    )


def _role_overrides() -> dict[str, str]:
    spec = _workflow_order_spec()
    return {
        str(override["role"]): " ".join(
            item
            for item in (
                str(override["target"]),
                _make_assignment_args(dict(override["required_assignments"])),
            )
            if item
        )
        for override in spec["role_overrides"]
        if isinstance(override, dict)
    }


def _role_targets() -> dict[str, str]:
    spec = _workflow_order_spec()
    return {
        str(override["role"]): str(override["target"])
        for override in spec["role_overrides"]
        if isinstance(override, dict)
    }


def _protected_recipe_lines(target: str | None = None) -> dict[str, dict[str, str]]:
    spec = _workflow_order_spec()
    return {
        str(line["role"]): {
            "target": str(line["target"]),
            "raw_line": str(line["raw_line"]),
        }
        for protected_recipe in spec["protected_recipes"]
        if isinstance(protected_recipe, dict)
        if target is None or protected_recipe.get("target") == target
        for line in protected_recipe.get("expected_lines", [])
        if isinstance(line, dict)
    }


def _first_role_checks() -> dict[str, dict[str, str]]:
    spec = _workflow_order_spec()
    return {
        str(entry["id"]): {
            "target": str(entry["target"]),
            "role": str(entry["role"]),
            "reason": str(entry["reason"]),
        }
        for entry in spec["first_role_checks"]
        if isinstance(entry, dict)
    }


def _recipe_line_for_role(role: str) -> str:
    protected_line = _protected_recipe_lines().get(role)
    if protected_line is not None:
        return f"\t{protected_line['raw_line']}\n"
    override = _role_overrides().get(role)
    if override is not None:
        return f"\t$(MAKE) {override}\n"
    return f"\t$(MAKE) {role}\n"


def _terminal_roles() -> dict[str, str]:
    roles: dict[str, str] = {}
    for entry in _workflow_order_spec()["terminal_checks"]:
        if isinstance(entry, dict):
            roles[str(entry["target"])] = str(entry["role"])
    return roles


def _forbidden_targets(check_id: str) -> set[str]:
    for entry in _workflow_order_spec()["forbidden_target_checks"]:
        if isinstance(entry, dict) and entry.get("id") == check_id:
            return {str(target) for target in entry["forbidden_targets"]}
    raise AssertionError(f"missing forbidden target check: {check_id}")


def _add_unique_target_name(target_names: list[str], value: object) -> None:
    name = str(value).strip()
    if name and name not in target_names:
        target_names.append(name)


def _add_role_target_name(
    target_names: list[str],
    role_targets: dict[str, str],
    role: object,
) -> None:
    role_name = str(role).strip()
    _add_unique_target_name(target_names, role_targets.get(role_name, role_name))


def _add_protected_recipe_target_names(
    target_names: list[str],
    role_targets: dict[str, str],
    spec: dict[str, object],
) -> None:
    for protected_recipe in spec["protected_recipes"]:
        if not isinstance(protected_recipe, dict):
            continue
        _add_unique_target_name(target_names, protected_recipe.get("target", ""))
        for line in protected_recipe.get("expected_lines", []):
            if isinstance(line, dict):
                _add_unique_target_name(
                    target_names,
                    line.get("target")
                    or role_targets.get(str(line.get("role", "")), ""),
                )


def _add_expected_subsequence_target_names(
    target_names: list[str],
    role_targets: dict[str, str],
    spec: dict[str, object],
) -> None:
    for entry in spec["expected_subsequences"]:
        if not isinstance(entry, dict):
            continue
        _add_unique_target_name(target_names, entry.get("target", ""))
        for role in entry.get("roles", []):
            _add_role_target_name(target_names, role_targets, role)


def _add_role_check_target_names(
    target_names: list[str],
    role_targets: dict[str, str],
    spec: dict[str, object],
) -> None:
    for check_key in ("terminal_checks", "first_role_checks"):
        for entry in spec[check_key]:
            if isinstance(entry, dict):
                _add_unique_target_name(target_names, entry.get("target", ""))
                _add_role_target_name(target_names, role_targets, entry.get("role", ""))


def _add_repetition_budget_target_names(
    target_names: list[str],
    spec: dict[str, object],
) -> None:
    for entry in spec["repetition_budgets"]:
        if not isinstance(entry, dict):
            continue
        _add_unique_target_name(target_names, entry.get("target", ""))
        for target in entry.get("allowed_repeated_targets", []):
            _add_unique_target_name(target_names, target)


def _add_forbidden_check_target_names(
    target_names: list[str],
    spec: dict[str, object],
) -> None:
    for entry in spec["forbidden_target_checks"]:
        if not isinstance(entry, dict):
            continue
        _add_unique_target_name(target_names, entry.get("target", ""))
        for target in entry.get("forbidden_targets", []):
            _add_unique_target_name(target_names, target)


def _release_workflow_order_spec_target_names() -> tuple[str, ...]:
    spec = _workflow_order_spec()
    role_targets = _role_targets()
    target_names: list[str] = []

    for target in spec["target_recipe_order"]:
        _add_unique_target_name(target_names, target)
    _add_protected_recipe_target_names(target_names, role_targets, spec)
    _add_expected_subsequence_target_names(target_names, role_targets, spec)
    _add_role_check_target_names(target_names, role_targets, spec)
    _add_repetition_budget_target_names(target_names, spec)
    _add_forbidden_check_target_names(target_names, spec)
    return tuple(target_names)


def _release_workflow_order_phony_targets() -> tuple[str, ...]:
    target_names: list[str] = []

    def add(value: str) -> None:
        if value not in target_names:
            target_names.append(value)

    for target in RELEASE_WORKFLOW_ORDER_SUPPORT_PHONY_TARGETS:
        add(target)
    for target in _release_workflow_order_spec_target_names():
        add(target)
    return tuple(target_names)


CHECK_FINALIZED_TARGETS = _sequence_roles("check_finalized_post_check_sequence")
CHECK_FINALIZED_LINES = _make_recipe(
    "auto-improve-readiness-report-body",
    "generated-artifact-converge",
    *CHECK_FINALIZED_TARGETS,
)
CHECK_FINALIZED_MISORDER_LINES = _make_recipe(
    CHECK_FINALIZED_TARGETS[3],
    CHECK_FINALIZED_TARGETS[1],
    CHECK_FINALIZED_TARGETS[2],
    CHECK_FINALIZED_TARGETS[4],
)
RELEASE_SOURCE_READY_TARGETS = _sequence_roles(
    "release_source_ready_transaction_sequence"
)
RELEASE_SOURCE_READY_LINES = _make_recipe(*RELEASE_SOURCE_READY_TARGETS)
RELEASE_SOURCE_READY_MISORDER_LINES = _make_recipe(
    RELEASE_SOURCE_READY_TARGETS[0],
    RELEASE_SOURCE_READY_TARGETS[2],
    RELEASE_SOURCE_READY_TARGETS[3],
    RELEASE_SOURCE_READY_TARGETS[1],
)
RELEASE_SOURCE_READY_PREPARE_LINES = _make_recipe(
    *_sequence_roles("release_source_ready_prepare_sequence")
)
RELEASE_SOURCE_READY_POST_VERIFY_TARGETS = _sequence_roles(
    "release_source_ready_post_verify_sequence"
)
RELEASE_SOURCE_READY_POST_VERIFY_LINES = _make_recipe(*RELEASE_SOURCE_READY_POST_VERIFY_TARGETS)
RELEASE_SOURCE_READY_POST_VERIFY_MISORDER_LINES = _make_recipe(
    RELEASE_SOURCE_READY_POST_VERIFY_TARGETS[0],
    "goal-runtime-local-evidence-refresh",
    "generated-artifact-converge",
    "remediation-backlog",
    "release-closeout-fixed-point",
    RELEASE_SOURCE_READY_POST_VERIFY_TARGETS[1],
)
RELEASE_CONVERGE_PREFLIGHT_TARGETS = _sequence_roles(
    "release_converge_preflight_sequence"
)
RELEASE_CONVERGE_PREFLIGHT_LINES = _make_recipe(*RELEASE_CONVERGE_PREFLIGHT_TARGETS)
RELEASE_CONVERGE_PREFLIGHT_MISORDER_LINES = _make_recipe(
    RELEASE_CONVERGE_PREFLIGHT_TARGETS[1],
    RELEASE_CONVERGE_PREFLIGHT_TARGETS[0],
    *RELEASE_CONVERGE_PREFLIGHT_TARGETS[2:],
)
AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_TARGETS = _sequence_roles(
    "release_auto_promotion_preflight_prerequisites_sequence"
)
AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_LINES = _make_recipe(
    *AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_TARGETS
)
AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_MISORDER_LINES = _make_recipe(
    AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_TARGETS[1],
    AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_TARGETS[0],
)
AUTO_PROMOTION_PREFLIGHT_TARGETS = _sequence_roles(
    "release_auto_promotion_preflight_sequence"
)
AUTO_PROMOTION_PREFLIGHT_LINES = _make_recipe(*AUTO_PROMOTION_PREFLIGHT_TARGETS)
AUTO_PROMOTION_PREFLIGHT_MISORDER_LINES = _make_recipe(
    AUTO_PROMOTION_PREFLIGHT_TARGETS[1],
    AUTO_PROMOTION_PREFLIGHT_TARGETS[0],
    *AUTO_PROMOTION_PREFLIGHT_TARGETS[2:],
)
AUTO_PROMOTION_PRESEAL_TARGETS = _sequence_roles(
    "release_auto_promotion_preseal_sequence"
)
AUTO_PROMOTION_PRESEAL_LINES = _make_recipe(*AUTO_PROMOTION_PRESEAL_TARGETS)
AUTO_PROMOTION_PRESEAL_MISORDER_LINES = _make_recipe(
    AUTO_PROMOTION_PRESEAL_TARGETS[0],
    AUTO_PROMOTION_PRESEAL_TARGETS[1],
    AUTO_PROMOTION_PRESEAL_TARGETS[3],
    AUTO_PROMOTION_PRESEAL_TARGETS[2],
    *AUTO_PROMOTION_PRESEAL_TARGETS[4:],
)
AUTO_PROMOTION_PRESEAL_FORBIDDEN_WRITER_LINES = (
    AUTO_PROMOTION_PRESEAL_LINES + _make_recipe("generated-artifact-converge")
)
RELEASE_CONVERGE_ALL_LINES = _make_recipe(
    "release-converge-preflight",
    "registry-preflight",
    "release-smoke-full-reuse",
    "sync-public-policy",
    "public-check-all",
    "test-execution-summary-full-current-or-refresh",
    "release-converge-post",
)
RELEASE_EVIDENCE_CONVERGE_LINES = _make_recipe(
    *_sequence_roles("release_evidence_converge_finalizer_sequence")
)
RELEASE_FINALITY_RESETTLE_LINES = _make_recipe(
    *_sequence_roles("release_finality_resettle_sequence")
)
RELEASE_TERMINAL_FINALITY_LINES = _make_recipe(
    *_sequence_roles("release_terminal_finality_sequence")
)
RELEASE_AUTHORITY_POST_READY_FINALITY_LINES = _make_recipe(
    *_sequence_roles("release_authority_post_ready_finality_sequence")
)
RELEASE_AUTHORITY_SETTLE_LINES = _make_recipe(
    *_sequence_roles("release_authority_settle_sequence")
)
RELEASE_POST_COMMIT_FINALIZE_LINES = _make_recipe(
    *_sequence_roles("release_post_commit_finalizer_sequence")
)
RELEASE_WORKFLOW_ORDER_SUPPORT_PHONY_TARGETS = (
    "check",
    "release-evidence-closeout",
    "sync-public-policy",
    "public-check-all",
    "release-converge",
    "release-converge-post",
    "generated-artifact-index",
    "artifact-freshness",
    "release-closeout-summary",
    "script-output-surfaces",
)
RELEASE_WORKFLOW_ORDER_PHONY_TARGETS = _release_workflow_order_phony_targets()
RELEASE_WORKFLOW_ORDER_MAKEFILE_TEMPLATE = (
    ".PHONY: {phony}\n"
    "check:\n"
    "\t@true\n"
    "check-finalized: check\n"
    "{check_finalized_lines}"
    "release-evidence-converge:\n"
    "{release_evidence_converge_lines}"
    "release-evidence-closeout: release-evidence-converge\n"
    "\t@echo compatibility alias\n"
    "release-finality-resettle:\n"
    "{release_finality_resettle_lines}"
    "release-terminal-finality:\n"
    "{release_terminal_finality_lines}"
    "release-authority-post-ready-finality:\n"
    "{release_authority_post_ready_finality_lines}"
    "release-authority-settle:\n"
    "{release_authority_settle_lines}"
    "release-source-ready:\n"
    "{release_source_ready_lines}"
    "release-source-ready-prepare:\n"
    "{release_source_ready_prepare_lines}"
    "release-source-ready-post-verify:\n"
    "{release_source_ready_post_verify_lines}"
    "release-converge-all-surfaces:\n"
    "{release_converge_all_lines}"
    "release-converge:\n"
    "\t$(MAKE) release-converge-preflight\n"
    "\t$(MAKE) release-converge-post\n"
    "release-converge-preflight:\n"
    "{release_converge_preflight_lines}"
    "release-converge-post:\n"
    "\t$(MAKE) generated-artifact-converge\n"
    "\t$(MAKE) remediation-backlog\n"
    "\t$(MAKE) operator-release-summary\n"
    "\t$(MAKE) release-terminal-finality\n"
    "release-source-ready-snapshot:\n"
    "\t@true\n"
    "release-source-ready-commit:\n"
    "\t@true\n"
    "release-post-commit-finalize:\n"
    "{release_post_commit_finalize_lines}"
    "release-source-ready-status:\n"
    "\t@true\n"
    "release-finality-resettle-current-or-refresh:\n"
    "\t@true\n"
    "release-auto-promotion-goal-run-id-verified-check:\n"
    "\t@true\n"
    "release-auto-promotion-preflight-prerequisites:\n"
    "{auto_promotion_preflight_prerequisites_lines}"
    "release-auto-promotion-preflight:\n"
    "{auto_promotion_preflight_lines}"
    "release-run-ready:\n"
    "\t@true\n"
    "release-auto-promotion-preseal:\n"
    "{auto_promotion_preseal_lines}"
    "release-sealed-run-ready:\n"
    "\t@true\n"
    "release-auto-promotion-ready:\n"
    "\t@true\n"
    "release-authority-archive-candidate-gate:\n"
    "\t@true\n"
    "release-authority-post-ready-finality-current-or-refresh:\n"
    "\t@true\n"
    "release-check-all-surfaces:\n"
    "\t@true\n"
    "sync-public-policy:\n"
    "\t@true\n"
    "public-check-summary:\n"
    "\t@true\n"
    "public-check-all:\n"
    "\t@true\n"
    "script-output-surfaces-check:\n"
    "\t@true\n"
    "release-smoke-fast-current-check:\n"
    "\t@true\n"
    "release-smoke-fast-refresh-check:\n"
    "\t@true\n"
    "release-smoke-full-current-check:\n"
    "\t@true\n"
    "test-execution-summary-current-check:\n"
    "\t@true\n"
    "test-execution-summary-current-or-refresh:\n"
    "\t@true\n"
    "test-execution-summary-full-current-check:\n"
    "\t@true\n"
    "test-execution-summary-full-refresh:\n"
    "\t@true\n"
    "test-execution-summary-full-body:\n"
    "\t@true\n"
    "sync-public-policy-check:\n"
    "\t@true\n"
    "public-check-summary-current-check:\n"
    "\t@true\n"
    "artifact-freshness-check:\n"
    "\t@true\n"
    "bootstrap-preflight:\n"
    "\t@true\n"
    "registry-preflight:\n"
    "\t@true\n"
    "goal-runtime-local-evidence-refresh:\n"
    "\t@true\n"
    "auto-improve-readiness-worktree-guard:\n"
    "\t@true\n"
    "remediation-backlog:\n"
    "\t@true\n"
    "generated-artifact-converge:\n"
    "\t$(MAKE) artifact-freshness\n"
    "\t$(MAKE) external-report-action-matrix\n"
    "\t$(MAKE) generated-artifact-index\n"
    "generated-artifact-script-output:\n"
    "\t$(MAKE) script-output-surfaces\n"
    "script-output-surfaces:\n"
    "\t@true\n"
    "external-report-action-matrix:\n"
    "\t@true\n"
    "external-report-reference-manifest-settle:\n"
    "\t@true\n"
    "generated-artifact-index:\n"
    "\t@true\n"
    "generated-artifact-index-body:\n"
    "\t@true\n"
    "artifact-freshness:\n"
    "\t@true\n"
    "release-closeout-batch-manifest-promote:\n"
    "\t@true\n"
    "release-closeout-batch-manifest-replay-verify:\n"
    "\t@true\n"
    "release-auto-promotion-ready-invalidate:\n"
    "\t@true\n"
    "release-auto-promotion-goal-run-id-guard:\n"
    "\t@true\n"
    "release-run-ready-plan-check:\n"
    "\t@true\n"
    "release-run-ready-check:\n"
    "\t@true\n"
    "release-auto-promotion-safe-cleanup-cleanup-only:\n"
    "\t@true\n"
    "learning-readiness-signoff-revalidation:\n"
    "\t@true\n"
    "release-evidence-cohort-preseal-refresh:\n"
    "\t@true\n"
    "release-evidence-cohort:\n"
    "\t@true\n"
    "artifact-freshness-refresh-check:\n"
    "\t@true\n"
    "operator-release-summary:\n"
    "\t@true\n"
    "report-schema-samples-regenerate:\n"
    "\t@true\n"
    "test-execution-summary-report-contract-refresh-no-smoke:\n"
    "\t@true\n"
)


def _workflow_order_guard_makefile_text(
    *,
    misorder_check_finalized: bool = False,
    misorder_release_source_ready: bool = False,
    misorder_release_source_ready_post_verify: bool = False,
    misorder_release_converge_preflight: bool = False,
    misorder_auto_promotion_preflight_prerequisites: bool = False,
    misorder_auto_promotion_preflight: bool = False,
    misorder_auto_promotion_preseal: bool = False,
    auto_promotion_preseal_forbidden_writer: bool = False,
) -> str:
    return RELEASE_WORKFLOW_ORDER_MAKEFILE_TEMPLATE.format(
        phony=" ".join(RELEASE_WORKFLOW_ORDER_PHONY_TARGETS),
        release_evidence_converge_lines=RELEASE_EVIDENCE_CONVERGE_LINES,
        release_finality_resettle_lines=RELEASE_FINALITY_RESETTLE_LINES,
        release_terminal_finality_lines=RELEASE_TERMINAL_FINALITY_LINES,
        release_authority_post_ready_finality_lines=RELEASE_AUTHORITY_POST_READY_FINALITY_LINES,
        release_authority_settle_lines=RELEASE_AUTHORITY_SETTLE_LINES,
        check_finalized_lines=(
            CHECK_FINALIZED_MISORDER_LINES
            if misorder_check_finalized
            else CHECK_FINALIZED_LINES
        ),
        release_source_ready_lines=(
            RELEASE_SOURCE_READY_MISORDER_LINES
            if misorder_release_source_ready
            else RELEASE_SOURCE_READY_LINES
        ),
        release_source_ready_prepare_lines=RELEASE_SOURCE_READY_PREPARE_LINES,
        release_source_ready_post_verify_lines=(
            RELEASE_SOURCE_READY_POST_VERIFY_MISORDER_LINES
            if misorder_release_source_ready_post_verify
            else RELEASE_SOURCE_READY_POST_VERIFY_LINES
        ),
        release_converge_all_lines=RELEASE_CONVERGE_ALL_LINES,
        release_converge_preflight_lines=(
            RELEASE_CONVERGE_PREFLIGHT_MISORDER_LINES
            if misorder_release_converge_preflight
            else RELEASE_CONVERGE_PREFLIGHT_LINES
        ),
        auto_promotion_preflight_prerequisites_lines=(
            AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_MISORDER_LINES
            if misorder_auto_promotion_preflight_prerequisites
            else AUTO_PROMOTION_PREFLIGHT_PREREQUISITES_LINES
        ),
        auto_promotion_preflight_lines=(
            AUTO_PROMOTION_PREFLIGHT_MISORDER_LINES
            if misorder_auto_promotion_preflight
            else AUTO_PROMOTION_PREFLIGHT_LINES
        ),
        auto_promotion_preseal_lines=(
            AUTO_PROMOTION_PRESEAL_FORBIDDEN_WRITER_LINES
            if auto_promotion_preseal_forbidden_writer
            else AUTO_PROMOTION_PRESEAL_MISORDER_LINES
            if misorder_auto_promotion_preseal
            else AUTO_PROMOTION_PRESEAL_LINES
        ),
        release_post_commit_finalize_lines=RELEASE_POST_COMMIT_FINALIZE_LINES,
    )


_PostCommitDriftCase = tuple[str, str, set[str]]


def _post_commit_recipe_structure_drift_cases(
    *,
    canonical_recipe: str,
    snapshot_line: str,
    post_commit_tail: str,
) -> tuple[_PostCommitDriftCase, ...]:
    return (
        (
            "extra target before snapshot",
            "release-post-commit-finalize:\n"
            "\t$(MAKE) release-check-all-surfaces\n"
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            {"protected_recipe_line_count_mismatch", "protected_recipe_line_mismatch"},
        ),
        (
            "raw command before snapshot",
            "release-post-commit-finalize:\n"
            '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
            '--stored "ops/script-output-surfaces.json" --check\n'
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            {"protected_recipe_line_count_mismatch", "protected_recipe_line_mismatch"},
        ),
        (
            "blank inside recipe",
            canonical_recipe.replace(snapshot_line, snapshot_line + "\n"),
            {"protected_recipe_line_count_mismatch", "protected_recipe_line_mismatch"},
        ),
        (
            "comment inside recipe",
            canonical_recipe.replace(snapshot_line, snapshot_line + "# comment\n"),
            {"protected_recipe_line_count_mismatch", "protected_recipe_line_mismatch"},
        ),
        (
            "inline header recipe",
            'release-post-commit-finalize: ; rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"\n',
            {
                "protected_recipe_inline_recipe_forbidden",
                "protected_recipe_line_count_mismatch",
            },
        ),
        (
            "prerequisite on protected recipe",
            "release-post-commit-finalize: release-post-commit-prerequisite\n"
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}"
            "release-post-commit-prerequisite:\n"
            "\t@true\n",
            {"protected_recipe_prerequisites_forbidden"},
        ),
        (
            "duplicate protected recipe",
            "release-post-commit-finalize:\n"
            f"{snapshot_line}"
            "release-post-commit-finalize:\n"
            f"{post_commit_tail}",
            {"protected_recipe_definition_count_mismatch"},
        ),
        (
            "empty inline duplicate override",
            f"{canonical_recipe}release-post-commit-finalize: ;\n",
            {
                "protected_recipe_definition_count_mismatch",
                "protected_recipe_inline_recipe_forbidden",
            },
        ),
        (
            "double-colon protected recipe",
            "release-post-commit-finalize::\n"
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            {"protected_recipe_double_colon_rule"},
        ),
        (
            "mixed single and double colon protected recipe",
            f"{canonical_recipe}release-post-commit-finalize::\n"
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            {
                "protected_recipe_definition_count_mismatch",
                "protected_recipe_double_colon_rule",
            },
        ),
        (
            "multi-target protected recipe",
            "alias release-post-commit-finalize:\n"
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            {"protected_recipe_multi_target_rule"},
        ),
        (
            "target-specific assignment",
            "release-post-commit-finalize: PYTHON := python3\n"
            f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            {"protected_recipe_prerequisites_forbidden"},
        ),
        (
            "post-finality raw command after separator",
            canonical_recipe
            + "\n"
            + '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
            + '--stored "ops/script-output-surfaces.json" --check\n',
            {"protected_recipe_line_count_mismatch"},
        ),
    )


def _post_commit_recipe_line_drift_cases(
    *,
    canonical_recipe: str,
    snapshot_line: str,
    verify_line: str,
) -> tuple[_PostCommitDriftCase, ...]:
    return (
        (
            "command substitution in make args",
            canonical_recipe.replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check "
                'FOO=$$(rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)")\n',
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "make shell function in make args",
            canonical_recipe.replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check "
                'FOO=$(shell rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)")\n',
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "backtick substitution in make args",
            canonical_recipe.replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check "
                'FOO=`rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"`\n',
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "continued make recipe fragment",
            canonical_recipe.replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check \\\n"
                '; rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"\n',
            ),
            {"protected_recipe_line_count_mismatch", "protected_recipe_line_mismatch"},
        ),
        (
            "lowercase make variable",
            canonical_recipe.replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(make) script-output-surfaces-check\n",
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "redirection on make invocation",
            canonical_recipe.replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check "
                '> "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"\n',
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "snapshot writes noncanonical path",
            canonical_recipe.replace(
                '"$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
                '"tmp/wrong-release-post-commit-finalization.snapshot.json"',
                1,
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "snapshot output overridden",
            canonical_recipe.replace(
                snapshot_line,
                snapshot_line.replace(
                    "\n",
                    ' --out "tmp/wrong-release-post-commit-finalization.snapshot.json"\n',
                ),
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "verify before freshness check",
            canonical_recipe.replace(
                "\t$(MAKE) artifact-freshness-check\n" + verify_line,
                verify_line + "\t$(MAKE) artifact-freshness-check\n",
            ),
            {"protected_recipe_line_mismatch"},
        ),
        (
            "verify reads noncanonical snapshot",
            canonical_recipe.replace(
                verify_line,
                verify_line.replace(
                    '"$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
                    '"tmp/wrong-release-post-commit-finalization.snapshot.json"',
                ),
            ),
            {"protected_recipe_line_mismatch"},
        ),
    )


def _post_commit_protected_recipe_drift_cases() -> tuple[_PostCommitDriftCase, ...]:
    canonical_recipe = (
        "release-post-commit-finalize:\n" + RELEASE_POST_COMMIT_FINALIZE_LINES
    )
    snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
    verify_line = _recipe_line_for_role("release-post-commit-finalizer-verify")
    post_commit_tail = _make_recipe(
        *_sequence_roles("release_post_commit_finalizer_sequence")[1:]
    )
    return (
        *_post_commit_recipe_structure_drift_cases(
            canonical_recipe=canonical_recipe,
            snapshot_line=snapshot_line,
            post_commit_tail=post_commit_tail,
        ),
        *_post_commit_recipe_line_drift_cases(
            canonical_recipe=canonical_recipe,
            snapshot_line=snapshot_line,
            verify_line=verify_line,
        ),
    )


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 10, 4, 0, tzinfo=dt.UTC),
    )


class ReleaseWorkflowOrderGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()
        seed_minimal_vault(self.vault)
        self._copy_support_file("ops/schemas/release-workflow-order-guard.schema.json")
        self._copy_support_file("ops/schemas/release-workflow-order-guard-spec.schema.json")
        self._copy_support_file("ops/policies/release-workflow-order-guard.json")
        self._write_fixed_point_policy()
        self._write_makefile()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _copy_support_file(self, rel_path: str) -> None:
        destination = self.vault / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((REPO_ROOT / rel_path).read_text(encoding="utf-8"), encoding="utf-8")

    def _write_fixed_point_policy(self, *, invert_dependency: bool = False) -> None:
        writers = [
            {
                "name": "generated-artifact-index",
                "target": "generated-artifact-index-body",
                "produces": ["ops/reports/generated-artifact-index.json"],
                "depends_on": ["artifact-freshness"] if invert_dependency else [],
                "expensive_prerequisites": ["release-risk-taxonomy-matrix"],
            },
            {
                "name": "artifact-freshness",
                "target": "artifact-freshness",
                "produces": ["ops/reports/artifact-freshness-report.json"],
                "depends_on": ["generated-artifact-index-body"],
                "expensive_prerequisites": [],
            },
        ]
        path = self.vault / "ops" / "policies" / "release-closeout-fixed-point.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "writers": writers, "tracked_artifacts": []}, indent=2),
            encoding="utf-8",
        )

    def _write_workflow_order_spec(self, payload: dict[str, object]) -> None:
        path = self.vault / "ops" / "policies" / "release-workflow-order-guard.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_makefile(
        self,
        *,
        misorder_check_finalized: bool = False,
        misorder_release_source_ready: bool = False,
        misorder_release_source_ready_post_verify: bool = False,
        misorder_release_converge_preflight: bool = False,
        misorder_auto_promotion_preflight_prerequisites: bool = False,
        misorder_auto_promotion_preflight: bool = False,
        misorder_auto_promotion_preseal: bool = False,
        auto_promotion_preseal_forbidden_writer: bool = False,
    ) -> None:
        self.vault.joinpath("Makefile").write_text(
            _workflow_order_guard_makefile_text(
                misorder_check_finalized=misorder_check_finalized,
                misorder_release_source_ready=misorder_release_source_ready,
                misorder_release_source_ready_post_verify=misorder_release_source_ready_post_verify,
                misorder_release_converge_preflight=misorder_release_converge_preflight,
                misorder_auto_promotion_preflight_prerequisites=misorder_auto_promotion_preflight_prerequisites,
                misorder_auto_promotion_preflight=misorder_auto_promotion_preflight,
                misorder_auto_promotion_preseal=misorder_auto_promotion_preseal,
                auto_promotion_preseal_forbidden_writer=auto_promotion_preseal_forbidden_writer,
            ),
            encoding="utf-8",
        )

    def _replace_post_commit_recipe(self, replacement: str) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n" + RELEASE_POST_COMMIT_FINALIZE_LINES,
                replacement,
            ),
            encoding="utf-8",
        )

    def _protected_post_commit_recipe_check(
        self,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        return next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_protected_recipe"
        )

    def _check_with_violation(
        self,
        report: dict[str, Any],
        *,
        check_id: str,
        reason: str | None = None,
        target: str | None = None,
        expected_role: str | None = None,
    ) -> dict[str, Any]:
        matches = [
            check
            for check in report["checks"]
            if check["id"] == check_id
            if any(
                (reason is None or violation.get("reason") == reason)
                and (target is None or violation.get("target") == target)
                and (
                    expected_role is None
                    or violation.get("expected_role") == expected_role
                )
                for violation in check["violations"]
            )
        ]
        self.assertEqual(len(matches), 1, matches)
        return matches[0]

    def test_spec_keeps_critical_release_safety_roles(self) -> None:
        spec = _workflow_order_spec()
        role_overrides = {
            str(entry["role"]): str(entry["target"])
            for entry in spec["role_overrides"]
            if isinstance(entry, dict)
        }
        structured_role_overrides = {
            str(entry["role"]): dict(entry.get("required_assignments", {}))
            for entry in spec["role_overrides"]
            if isinstance(entry, dict)
        }

        self.assertEqual(
            role_overrides["release-closeout-post-check-finalizer-strict-dry-run"],
            "release-closeout-post-check-finalizer-dry-run",
        )
        for role in (
            "auto-improve-readiness-report-body-worktree-guard-refresh",
            "release-run-ready-plan-check-auto-promotion-distribution",
            "release-run-ready-check-auto-promotion-distribution",
            "release-evidence-cohort-preseal-refresh-auto-promotion-metadata",
            "release-closeout-fixed-point-auto-promotion-artifacts",
            "release-run-ready-auto-promotion-distribution",
            "release-evidence-cohort-strict-same-fingerprint-auto-promotion-metadata",
        ):
            with self.subTest(role=role, surface="role-overrides"):
                self.assertIn(role, role_overrides)
                self.assertTrue(structured_role_overrides[role])
        self.assertEqual(
            spec["role_override_sequence_coverage"],
            {
                "allowlisted_roles": [],
                "details": (
                    "Observed role overrides must be named in the expected "
                    "subsequence for the target where they appear, unless an "
                    "override is intentionally allowlisted here."
                ),
            },
        )
        self.assertEqual(
            _terminal_roles()["release-terminal-finality"],
            "release-closeout-finality-verify",
        )
        self.assertEqual(
            _terminal_roles()["release-source-ready"],
            "release-source-ready-post-verify",
        )
        self.assertIn(
            "release-closeout-post-check-finalizer-strict-dry-run",
            _sequence_roles("release_terminal_finality_sequence"),
        )
        self.assertIn(
            "release-source-ready-status",
            _sequence_roles("release_source_ready_post_verify_sequence"),
        )
        protected_lines = _protected_recipe_lines("release-post-commit-finalize")
        self.assertEqual(
            list(protected_lines),
            list(_sequence_roles("release_post_commit_finalizer_sequence")),
        )
        preflight_protected_lines = _protected_recipe_lines("release-converge-preflight")
        self.assertEqual(
            list(preflight_protected_lines),
            list(_sequence_roles("release_converge_preflight_sequence")),
        )
        auto_promotion_prerequisite_lines = _protected_recipe_lines(
            "release-auto-promotion-preflight-prerequisites"
        )
        self.assertEqual(
            list(auto_promotion_prerequisite_lines),
            list(
                _sequence_roles(
                    "release_auto_promotion_preflight_prerequisites_sequence"
                )
            ),
        )
        self.assertIn(
            "auto-improve-readiness-report-body-worktree-guard-refresh",
            _sequence_roles("release_auto_promotion_preflight_sequence"),
        )
        self.assertEqual(
            _sequence_roles("release_auto_promotion_preflight_sequence")[-2:],
            (
                "tmp-json-clean",
                "release-auto-promotion-preflight-authority-write",
            ),
        )
        self.assertIn(
            "release-closeout-fixed-point-auto-promotion-artifacts",
            _sequence_roles("release_auto_promotion_preseal_sequence"),
        )
        self.assertEqual(
            _sequence_roles("release_auto_promotion_preseal_sequence")[-2:],
            (
                "tmp-json-clean",
                "release-auto-promotion-preseal-authority-write",
            ),
        )
        protected_preflight_lines = _protected_recipe_lines(
            "release-auto-promotion-preflight"
        )
        self.assertEqual(
            list(protected_preflight_lines),
            list(_sequence_roles("release_auto_promotion_preflight_sequence")),
        )

        self.assertIn(
            "--phase preflight",
            protected_preflight_lines[
                "release-auto-promotion-preflight-authority-write"
            ]["raw_line"],
        )
        protected_preseal_lines = _protected_recipe_lines(
            "release-auto-promotion-preseal"
        )
        self.assertIn(
            "--phase preseal",
            protected_preseal_lines[
                "release-auto-promotion-preseal-authority-write"
            ]["raw_line"],
        )
        self.assertIn(
            '--out "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
            protected_lines["release-post-commit-finalizer-snapshot"]["raw_line"],
        )
        self.assertIn(
            '--previous "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
            protected_lines["release-post-commit-finalizer-verify"]["raw_line"],
        )
        self.assertEqual(
            _first_role_checks()["release_post_commit_finalizer_sequence"],
            {
                "target": "release-post-commit-finalize",
                "role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
        )
        post_commit_roles = _sequence_roles("release_post_commit_finalizer_sequence")
        self.assertLess(
            post_commit_roles.index("release-post-commit-finalizer-snapshot"),
            post_commit_roles.index("script-output-surfaces-check"),
        )
        self.assertLess(
            post_commit_roles.index("artifact-freshness-check"),
            post_commit_roles.index("release-post-commit-finalizer-verify"),
        )
        self.assertLess(
            post_commit_roles.index("release-post-commit-finalizer-verify"),
            post_commit_roles.index("release-closeout-finality-verify"),
        )
        self.assertTrue(
            {
                "goal-runtime-local-evidence-refresh",
                "generated-artifact-converge",
                "remediation-backlog",
                "release-closeout-fixed-point",
            }.issubset(
                _forbidden_targets("release_source_ready_post_verify_sequence")
            )
        )
        preseal_repetition_budget = next(
            entry
            for entry in spec["repetition_budgets"]
            if isinstance(entry, dict)
            and entry["id"] == "release_auto_promotion_preseal_repetition_budget"
        )
        self.assertNotIn("forbidden_targets", preseal_repetition_budget)
        self.assertNotIn("forbidden_violation_reason", preseal_repetition_budget)
        self.assertTrue(
            {
                "test-execution-summary-full-refresh",
                "test-execution-summary-full-body",
                "generated-artifact-converge",
            }.issubset(
                _forbidden_targets(
                    "release_auto_promotion_preseal_forbidden_targets"
                )
            )
        )

    def test_release_converge_post_protected_recipe_matches_sequence(self) -> None:
        self.assertEqual(
            list(_protected_recipe_lines("release-converge-post")),
            list(_sequence_roles("release_converge_post_sequence")),
        )

    def test_spec_schema_rejects_empty_critical_guard_arrays(self) -> None:
        schema = load_schema(SPEC_SCHEMA_PATH)

        for key in CRITICAL_GUARD_ARRAYS:
            with self.subTest(key=key):
                spec = _cloned_workflow_order_spec()
                spec[key] = []

                errors = validate_with_schema(spec, schema)

                self.assertIn(f"$.{key}: expected at least 1 item(s)", errors)

    def test_spec_schema_rejects_unsensible_check_ids_and_targets(self) -> None:
        schema = load_schema(SPEC_SCHEMA_PATH)
        spec = _cloned_workflow_order_spec()
        spec["expected_subsequences"][0]["id"] = "release terminal finality"
        spec["terminal_checks"][0]["target"] = "release terminal finality"

        errors = validate_with_schema(spec, schema)

        self.assertTrue(
            any("$.expected_subsequences[0].id" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("$.terminal_checks[0].target" in error for error in errors),
            errors,
        )

    def test_spec_schema_rejects_forbidden_targets_on_repetition_budgets(self) -> None:
        schema = load_schema(SPEC_SCHEMA_PATH)
        spec = _cloned_workflow_order_spec()
        spec["repetition_budgets"][0]["forbidden_targets"] = [
            "generated-artifact-converge"
        ]

        errors = validate_with_schema(spec, schema)

        self.assertTrue(
            any(
                "$.repetition_budgets[0]: unexpected property 'forbidden_targets'"
                in error
                for error in errors
            ),
            errors,
        )

    def test_spec_schema_requires_role_override_matcher(self) -> None:
        schema = load_schema(SPEC_SCHEMA_PATH)
        spec = _cloned_workflow_order_spec()
        del spec["role_overrides"][0]["required_assignments"]

        errors = validate_with_schema(spec, schema)

        self.assertTrue(
            any("$.role_overrides[0]" in error for error in errors),
            errors,
        )

    def test_spec_schema_rejects_empty_structured_role_override_assignments(
        self,
    ) -> None:
        schema = load_schema(SPEC_SCHEMA_PATH)
        spec = _cloned_workflow_order_spec()
        spec["role_overrides"][0]["required_assignments"] = {}

        errors = validate_with_schema(spec, schema)

        self.assertIn(
            "$.role_overrides[0].required_assignments: expected at least 1 propert(ies)",
            errors,
        )

    def test_guard_rejects_spec_with_empty_critical_guard_array(self) -> None:
        spec = _cloned_workflow_order_spec()
        spec["terminal_checks"] = []
        self._write_workflow_order_spec(spec)

        with self.assertRaisesRegex(
            ValueError,
            r"invalid release workflow order spec.*\$\.terminal_checks: expected at least 1 item",
        ):
            build_report(self.vault, context=fixed_context())

    def test_spec_raw_recipe_sync_refreshes_only_make_line_snapshots(self) -> None:
        spec = _cloned_workflow_order_spec()
        protected_recipe = next(
            entry
            for entry in spec["protected_recipes"]
            if entry["target"] == "release-post-commit-finalize"
        )
        protected_line = protected_recipe["expected_lines"][1]
        original_role = protected_line["role"]
        original_target = protected_line["target"]
        protected_line["raw_line"] = "$(MAKE) stale-script-output-surfaces-check"
        self._write_workflow_order_spec(spec)

        drift = check_workflow_order_spec_raw_lines(self.vault)

        self.assertEqual(
            drift,
            [
                {
                    "target": "release-post-commit-finalize",
                    "recipe_index": 0,
                    "line_index": 1,
                    "role": "script-output-surfaces-check",
                    "old_raw_line": "$(MAKE) stale-script-output-surfaces-check",
                    "new_raw_line": "$(MAKE) script-output-surfaces-check",
                    "reason": "protected_recipe_raw_line_drift",
                }
            ],
        )

        destination = write_workflow_order_spec_raw_lines(self.vault)

        rewritten = json.loads(destination.read_text(encoding="utf-8"))
        rewritten_recipe = next(
            entry
            for entry in rewritten["protected_recipes"]
            if entry["target"] == "release-post-commit-finalize"
        )
        rewritten_line = rewritten_recipe["expected_lines"][1]
        self.assertEqual(rewritten_line["role"], original_role)
        self.assertEqual(rewritten_line["target"], original_target)
        self.assertEqual(
            rewritten_line["raw_line"],
            "$(MAKE) script-output-surfaces-check",
        )
        self.assertEqual(check_workflow_order_spec_raw_lines(self.vault), [])
        self.assertEqual(validate_with_schema(rewritten, load_schema(SPEC_SCHEMA_PATH)), [])

    def test_spec_raw_recipe_sync_refuses_structural_recipe_drift(self) -> None:
        replacement = (
            "release-post-commit-finalize:\n"
            + RELEASE_POST_COMMIT_FINALIZE_LINES
            + "\t$(MAKE) extra-human-reviewed-target\n"
        )
        self._replace_post_commit_recipe(replacement)

        drift = check_workflow_order_spec_raw_lines(self.vault)

        self.assertTrue(
            any(
                item.get("target") == "release-post-commit-finalize"
                and item.get("reason") == "protected_recipe_line_count_mismatch"
                for item in drift
            ),
            drift,
        )
        with self.assertRaisesRegex(
            ValueError,
            "protected_recipe_line_count_mismatch",
        ):
            write_workflow_order_spec_raw_lines(self.vault)

    def test_spec_raw_recipe_sync_refuses_unparseable_line_changes(self) -> None:
        recipe_lines = RELEASE_POST_COMMIT_FINALIZE_LINES.splitlines()
        recipe_lines[0] = "\t@echo raw-shell-fragment"
        self._replace_post_commit_recipe(
            "release-post-commit-finalize:\n" + "\n".join(recipe_lines) + "\n"
        )

        drift = check_workflow_order_spec_raw_lines(self.vault)

        self.assertTrue(
            any(
                item.get("target") == "release-post-commit-finalize"
                and item.get("reason") == "protected_recipe_unparseable_line"
                and item.get("observed_line") == "@echo raw-shell-fragment"
                for item in drift
            ),
            drift,
        )
        with self.assertRaisesRegex(
            ValueError,
            "protected_recipe_unparseable_line",
        ):
            write_workflow_order_spec_raw_lines(self.vault)

    def test_guard_rejects_matching_raw_shell_in_spec_and_makefile(self) -> None:
        raw_shell_line = "@echo raw-shell-fragment"
        spec = _cloned_workflow_order_spec()
        protected_recipe = next(
            entry
            for entry in spec["protected_recipes"]
            if entry["target"] == "release-post-commit-finalize"
        )
        protected_recipe["expected_lines"][0]["raw_line"] = raw_shell_line
        self._write_workflow_order_spec(spec)
        recipe_lines = RELEASE_POST_COMMIT_FINALIZE_LINES.splitlines()
        recipe_lines[0] = f"\t{raw_shell_line}"
        self._replace_post_commit_recipe(
            "release-post-commit-finalize:\n" + "\n".join(recipe_lines) + "\n"
        )

        drift = check_workflow_order_spec_raw_lines(self.vault)
        report = build_report(self.vault, context=fixed_context())
        check = self._protected_post_commit_recipe_check(report)

        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                item.get("reason") == "protected_recipe_unparseable_line"
                and item.get("observed_line") == raw_shell_line
                for item in drift
            ),
            drift,
        )
        self.assertTrue(
            any(
                item.get("reason") == "protected_recipe_unparseable_line"
                and item.get("observed_line") == raw_shell_line
                for item in check["violations"]
            ),
            check["violations"],
        )
        with self.assertRaisesRegex(
            ValueError,
            "protected_recipe_unparseable_line",
        ):
            write_workflow_order_spec_raw_lines(self.vault)

    def test_guard_rejects_matching_extra_make_args_in_spec_and_makefile(self) -> None:
        unsafe_make_line = "$(MAKE) script-output-surfaces-check FOO=bar"
        spec = _cloned_workflow_order_spec()
        protected_recipe = next(
            entry
            for entry in spec["protected_recipes"]
            if entry["target"] == "release-post-commit-finalize"
        )
        protected_recipe["expected_lines"][1]["raw_line"] = unsafe_make_line
        self._write_workflow_order_spec(spec)
        self._replace_post_commit_recipe(
            (
                "release-post-commit-finalize:\n"
                + RELEASE_POST_COMMIT_FINALIZE_LINES
            ).replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                f"\t{unsafe_make_line}\n",
            )
        )

        drift = check_workflow_order_spec_raw_lines(self.vault)
        report = build_report(self.vault, context=fixed_context())
        check = self._protected_post_commit_recipe_check(report)

        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                item.get("reason") == "protected_recipe_make_args_mismatch"
                and item.get("observed_assignments") == {"FOO": "bar"}
                for item in drift
            ),
            drift,
        )
        self.assertTrue(
            any(
                item.get("reason") == "protected_recipe_make_args_mismatch"
                and item.get("observed_assignments") == {"FOO": "bar"}
                for item in check["violations"]
            ),
            check["violations"],
        )
        with self.assertRaisesRegex(
            ValueError,
            "protected_recipe_make_args_mismatch",
        ):
            write_workflow_order_spec_raw_lines(self.vault)

    def test_guard_rejects_matching_shell_suffix_in_spec_and_makefile(self) -> None:
        unsafe_make_line = "$(MAKE) script-output-surfaces-check; @echo raw-shell-fragment"
        spec = _cloned_workflow_order_spec()
        protected_recipe = next(
            entry
            for entry in spec["protected_recipes"]
            if entry["target"] == "release-post-commit-finalize"
        )
        protected_recipe["expected_lines"][1]["raw_line"] = unsafe_make_line
        self._write_workflow_order_spec(spec)
        self._replace_post_commit_recipe(
            (
                "release-post-commit-finalize:\n"
                + RELEASE_POST_COMMIT_FINALIZE_LINES
            ).replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                f"\t{unsafe_make_line}\n",
            )
        )

        drift = check_workflow_order_spec_raw_lines(self.vault)
        report = build_report(self.vault, context=fixed_context())
        check = self._protected_post_commit_recipe_check(report)

        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                item.get("reason")
                in {
                    "protected_recipe_make_args_mismatch",
                    "protected_recipe_target_mismatch",
                }
                for item in drift
            ),
            drift,
        )
        self.assertTrue(
            any(
                item.get("reason")
                in {
                    "protected_recipe_make_args_mismatch",
                    "protected_recipe_target_mismatch",
                }
                for item in check["violations"]
            ),
            check["violations"],
        )
        with self.assertRaisesRegex(
            ValueError,
            "protected_recipe_(make_args|target)_mismatch",
        ):
            write_workflow_order_spec_raw_lines(self.vault)

    def test_guard_rejects_matching_make_modifiers_in_spec_and_makefile(self) -> None:
        for modifier in ("@", "-", "+"):
            with self.subTest(modifier=modifier):
                self._write_makefile()
                spec = _cloned_workflow_order_spec()
                unsafe_make_line = f"{modifier}$(MAKE) script-output-surfaces-check"
                protected_recipe = next(
                    entry
                    for entry in spec["protected_recipes"]
                    if entry["target"] == "release-post-commit-finalize"
                )
                protected_recipe["expected_lines"][1]["raw_line"] = unsafe_make_line
                self._write_workflow_order_spec(spec)
                self._replace_post_commit_recipe(
                    (
                        "release-post-commit-finalize:\n"
                        + RELEASE_POST_COMMIT_FINALIZE_LINES
                    ).replace(
                        "\t$(MAKE) script-output-surfaces-check\n",
                        f"\t{unsafe_make_line}\n",
                    )
                )

                drift = check_workflow_order_spec_raw_lines(self.vault)
                report = build_report(self.vault, context=fixed_context())
                check = self._protected_post_commit_recipe_check(report)

                self.assertEqual(report["status"], "fail")
                self.assertEqual(check["status"], "fail")
                self.assertTrue(
                    any(
                        item.get("reason") == "protected_recipe_unparseable_line"
                        and item.get("observed_line") == unsafe_make_line
                        for item in drift
                    ),
                    drift,
                )
                self.assertTrue(
                    any(
                        item.get("reason") == "protected_recipe_unparseable_line"
                        and item.get("observed_line") == unsafe_make_line
                        for item in check["violations"]
                    ),
                    check["violations"],
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "protected_recipe_unparseable_line",
                ):
                    write_workflow_order_spec_raw_lines(self.vault)

    def test_guard_passes_for_current_closeout_sequence_and_validates_schema(self) -> None:
        report = build_report(self.vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertIn("release-evidence-converge", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-source-ready", {item["target"] for item in report["target_recipes"]})
        self.assertEqual(report["fixed_point_policy"]["writer_count"], 2)
        planner_hook = next(item for item in report["checks"] if item["id"] == "workflow_dependency_planner_closeout_hooks")
        self.assertEqual(planner_hook["status"], "pass")
        resettle_check = next(item for item in report["checks"] if item["id"] == "release_finality_resettle_sequence")
        self.assertEqual(resettle_check["status"], "pass")
        terminal_finality_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_terminal_finality_sequence"
        )
        self.assertEqual(terminal_finality_check["status"], "pass")
        post_commit_sequence = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(post_commit_sequence["status"], "pass")
        protected_post_commit_recipe = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_protected_recipe"
        )
        self.assertEqual(protected_post_commit_recipe["status"], "pass")
        protected_preflight_recipe = next(
            item
            for item in report["checks"]
            if item["id"] == "release_converge_preflight_protected_recipe"
        )
        self.assertEqual(protected_preflight_recipe["status"], "pass")
        protected_auto_promotion_prerequisites = next(
            item
            for item in report["checks"]
            if item["id"]
            == "release_auto_promotion_preflight_prerequisites_protected_recipe"
        )
        self.assertEqual(protected_auto_promotion_prerequisites["status"], "pass")
        role_override_coverage = next(
            item
            for item in report["checks"]
            if item["id"] == "role_override_sequence_coverage"
        )
        self.assertEqual(role_override_coverage["status"], "pass")
        preflight_check = next(item for item in report["checks"] if item["id"] == "release_converge_preflight_sequence")
        self.assertEqual(preflight_check["status"], "pass")
        auto_promotion_preflight_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_auto_promotion_preflight_sequence"
        )
        self.assertEqual(auto_promotion_preflight_check["status"], "pass")
        auto_promotion_preflight_recipe = next(
            item
            for item in report["checks"]
            if item["id"] == "release_auto_promotion_preflight_protected_recipe"
        )
        self.assertEqual(auto_promotion_preflight_recipe["status"], "pass")
        auto_promotion_preseal_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_auto_promotion_preseal_sequence"
        )
        self.assertEqual(auto_promotion_preseal_check["status"], "pass")
        auto_promotion_preseal_recipe = next(
            item
            for item in report["checks"]
            if item["id"] == "release_auto_promotion_preseal_protected_recipe"
        )
        self.assertEqual(auto_promotion_preseal_recipe["status"], "pass")
        auto_promotion_preseal_forbidden_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_auto_promotion_preseal_forbidden_targets"
        )
        self.assertEqual(auto_promotion_preseal_forbidden_check["status"], "pass")
        self.assertIn("release-finality-resettle", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-terminal-finality", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-post-commit-finalize", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-converge-preflight", {item["target"] for item in report["target_recipes"]})
        self.assertIn(
            "release-auto-promotion-preflight",
            {item["target"] for item in report["target_recipes"]},
        )
        self.assertIn(
            "release-auto-promotion-preseal",
            {item["target"] for item in report["target_recipes"]},
        )
        self.assertTrue(write_report(self.vault, report).exists())

    def test_real_repo_release_order_report_builds_from_current_make_graph(self) -> None:
        report = build_report(REPO_ROOT, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])
        self.assertIn(
            "release-auto-promotion-preseal",
            {item["target"] for item in report["target_recipes"]},
        )
        self.assertEqual(
            {
                item["id"]: item["status"]
                for item in report["checks"]
                if item["id"]
                in {
                    "release_auto_promotion_preseal_sequence",
                    "release_auto_promotion_preseal_forbidden_targets",
                    "workflow_dependency_planner_closeout_hooks",
                }
            },
            {
                "release_auto_promotion_preseal_sequence": "pass",
                "release_auto_promotion_preseal_forbidden_targets": "pass",
                "workflow_dependency_planner_closeout_hooks": "pass",
            },
        )

    def test_check_mode_validates_live_candidate_when_canonical_report_is_missing(
        self,
    ) -> None:
        check_out = "tmp/release-workflow-order-guard-check.json"

        result = check_report(
            self.vault,
            check_out=check_out,
            context=fixed_context(),
        )

        self.assertEqual(result, 0)
        self.assertTrue((self.vault / check_out).exists())
        self.assertFalse((self.vault / "ops/reports/release-workflow-order-guard.json").exists())

    def test_check_mode_passes_when_canonical_report_is_semantically_current(
        self,
    ) -> None:
        write_report(self.vault, build_report(self.vault, context=fixed_context()))

        result = check_report(self.vault, context=fixed_context())

        self.assertEqual(result, 0)

    def test_check_mode_fails_when_canonical_report_is_semantically_stale(self) -> None:
        report = build_report(self.vault, context=fixed_context())
        report["summary"]["check_count"] = 0
        write_report(self.vault, report)

        result = check_report(self.vault, context=fixed_context())

        self.assertEqual(result, 1)

    def test_guard_fails_when_check_finalized_skips_initial_dry_run(self) -> None:
        self._write_makefile(misorder_check_finalized=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "check_finalized_post_check_sequence")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["expected_role"], "release-closeout-post-check-finalizer-dry-run")

    def test_guard_fails_when_check_finalized_runs_steps_after_finality_verify(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) release-closeout-finality-verify\n",
                "\t$(MAKE) release-closeout-finality-verify\n\t$(MAKE) external-report-action-matrix\n",
                1,
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "check_finalized_finality_terminal")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["reason"], "finality_verify_must_be_terminal")

    def test_guard_fails_when_finality_resettle_skips_sealed_preflight(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) release-authority-sealed-preflight\n",
                "",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_finality_resettle_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][0]["expected_role"],
            "release-authority-sealed-preflight",
        )

    def test_guard_fails_when_terminal_finality_runs_writer_after_verify(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) release-closeout-finality-verify\n"
                "release-authority-post-ready-finality:\n",
                "\t$(MAKE) release-closeout-finality-verify\n"
                "\t$(MAKE) external-report-action-matrix\n"
                "release-authority-post-ready-finality:\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_terminal_finality_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            "finality_verify_must_be_terminal",
            {item["reason"] for item in check["violations"]},
        )

    def test_guard_fails_when_terminal_finality_runs_writer_after_attestation(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-terminal-finality:\n"
                "\t$(MAKE) release-closeout-fixed-point\n"
                "\t$(MAKE) tmp-json-clean\n",
                "release-terminal-finality:\n"
                "\t$(MAKE) release-closeout-fixed-point\n"
                "\t$(MAKE) external-report-action-matrix\n"
                "\t$(MAKE) tmp-json-clean\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_terminal_finality_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            "sequence_must_be_exact",
            {item["reason"] for item in check["violations"]},
        )

    def test_guard_fails_when_fixed_point_policy_order_is_not_topological(self) -> None:
        self._write_fixed_point_policy(invert_dependency=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "fixed_point_policy_topological_order")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["reason"], "dependency_not_before_target")

    def test_guard_fails_when_unplanned_closeout_target_repeats(self) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) release-lane-summary\n",
                "\t$(MAKE) release-lane-summary\n"
                "\t$(MAKE) release-lane-summary\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_evidence_converge_repetition_budget"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["target"], "release-lane-summary")
        self.assertEqual(
            check["violations"][0]["reason"],
            "unexpected_repeated_closeout_target",
        )

    def test_guard_fails_when_post_commit_protected_recipe_drifts(self) -> None:
        for name, replacement, expected_reasons in (
            _post_commit_protected_recipe_drift_cases()
        ):
            with self.subTest(name=name):
                self._write_makefile()
                self._replace_post_commit_recipe(replacement)

                report = build_report(self.vault, context=fixed_context())

                check = self._protected_post_commit_recipe_check(report)
                reasons = {str(item["reason"]) for item in check["violations"]}
                self.assertEqual(report["status"], "fail")
                self.assertEqual(check["status"], "fail")
                self.assertTrue(expected_reasons <= reasons, check)

    def test_guard_fails_when_release_source_ready_status_is_not_terminal(self) -> None:
        self._write_makefile(misorder_release_source_ready=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(item for item in report["checks"] if item["id"] == "release_source_ready_transaction_sequence")
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][-1]["reason"],
            "release_source_ready_post_verify_must_be_terminal",
        )

    def test_guard_fails_when_release_source_ready_post_verify_runs_writers(
        self,
    ) -> None:
        self._write_makefile(misorder_release_source_ready_post_verify=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_source_ready_post_verify_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                violation.get("reason") == "post_verify_must_be_write_free"
                for violation in check["violations"]
            )
        )

    def test_guard_fails_when_release_converge_preflight_delays_script_output_refresh(
        self,
    ) -> None:
        self._write_makefile(misorder_release_converge_preflight=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_converge_preflight_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                violation.get("reason") == "script_output_surface_refresh_must_start_preflight"
                for violation in check["violations"]
            )
        )

    def test_guard_fails_when_release_converge_preflight_runs_raw_before_refresh(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-converge-preflight:\n",
                "release-converge-preflight:\n"
                '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
                '--stored "ops/script-output-surfaces.json" --check\n',
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_converge_preflight_protected_recipe"
        )
        reasons = {str(item["reason"]) for item in check["violations"]}
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            {
                "protected_recipe_line_count_mismatch",
                "protected_recipe_line_mismatch",
            }
            <= reasons,
            check,
        )

    def test_guard_fails_when_auto_promotion_prerequisites_drift(self) -> None:
        self._write_makefile(misorder_auto_promotion_preflight_prerequisites=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"]
            == "release_auto_promotion_preflight_prerequisites_protected_recipe"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                violation.get("reason") == "protected_recipe_line_mismatch"
                for violation in check["violations"]
            ),
            check,
        )

    def test_guard_fails_when_auto_promotion_preflight_skips_initial_invalidation(
        self,
    ) -> None:
        self._write_makefile(misorder_auto_promotion_preflight=True)

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_auto_promotion_preflight_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertTrue(
            any(
                violation.get("reason")
                == "ready_manifest_invalidation_must_start_auto_promotion_preflight"
                for violation in check["violations"]
            ),
            check,
        )

    def test_guard_fails_when_observed_role_override_is_dropped_from_sequence(
        self,
    ) -> None:
        spec = _cloned_workflow_order_spec()
        for entry in spec["expected_subsequences"]:
            if (
                isinstance(entry, dict)
                and entry["id"] == "release_auto_promotion_preflight_sequence"
            ):
                entry["roles"] = [
                    "auto-improve-readiness-report-body"
                    if role
                    == "auto-improve-readiness-report-body-worktree-guard-refresh"
                    else role
                    for role in entry["roles"]
                ]
                break
        self._write_workflow_order_spec(spec)

        report = build_report(self.vault, context=fixed_context())

        check = self._check_with_violation(
            report,
            check_id="role_override_sequence_coverage",
            reason="role_override_missing_from_expected_subsequence",
            target="release-auto-promotion-preflight",
            expected_role="auto-improve-readiness-report-body-worktree-guard-refresh",
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")

    def test_guard_structured_role_override_matching_is_order_independent(
        self,
    ) -> None:
        spec = _cloned_workflow_order_spec()
        spec["target_recipe_order"].append("custom-override-release")
        spec["role_overrides"].append(
            {
                "target": "custom-override-target",
                "required_assignments": {
                    "FOO": "1",
                    "BAR": "two words",
                },
                "role": "custom-override-role",
            }
        )
        spec["expected_subsequences"].append(
            {
                "id": "custom_override_sequence",
                "target": "custom-override-release",
                "roles": ["custom-override-role"],
                "details": "custom override role must be observed through structured assignments.",
            }
        )
        self._write_workflow_order_spec(spec)
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8")
            + "\ncustom-override-release:\n"
            + "\t$(MAKE) custom-override-target BAR=\"two words\" FOO=1\n"
            + "custom-override-target:\n"
            + "\t@true\n",
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item for item in report["checks"] if item["id"] == "custom_override_sequence"
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(check["status"], "pass")
        custom_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "custom-override-release"
        )
        self.assertEqual(
            custom_recipe["invocations"][0]["role"],
            "custom-override-role",
        )

    def test_guard_validates_protected_recipe_roles_through_structured_overrides(
        self,
    ) -> None:
        spec = _cloned_workflow_order_spec()
        for override in spec["role_overrides"]:
            if (
                isinstance(override, dict)
                and override.get("role")
                == "release-run-ready-plan-check-auto-promotion-distribution"
            ):
                override["required_assignments"] = {
                    "RELEASE_CLOSEOUT_DISTRIBUTION_ZIP": "$(WRONG_DISTRIBUTION_ZIP)"
                }
                break
        else:
            self.fail("missing auto-promotion distribution role override")
        self._write_workflow_order_spec(spec)

        report = build_report(self.vault, context=fixed_context())

        check = self._check_with_violation(
            report,
            check_id="release_auto_promotion_preseal_protected_recipe",
            reason="protected_recipe_role_mismatch",
            target="release-auto-promotion-preseal",
            expected_role="release-run-ready-plan-check-auto-promotion-distribution",
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")

    def test_guard_fails_when_auto_promotion_preseal_misorders_run_ready_checks(
        self,
    ) -> None:
        self._write_makefile(misorder_auto_promotion_preseal=True)

        report = build_report(self.vault, context=fixed_context())

        check = self._check_with_violation(
            report,
            check_id="release_auto_promotion_preseal_sequence",
            expected_role="release-run-ready-check-auto-promotion-distribution",
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")

    def test_guard_fails_when_auto_promotion_preseal_runs_forbidden_writer(
        self,
    ) -> None:
        self._write_makefile(auto_promotion_preseal_forbidden_writer=True)

        report = build_report(self.vault, context=fixed_context())

        check = self._check_with_violation(
            report,
            check_id="release_auto_promotion_preseal_protected_recipe",
            reason="protected_recipe_line_count_mismatch",
            target="release-auto-promotion-preseal",
        )
        forbidden_check = self._check_with_violation(
            report,
            check_id="release_auto_promotion_preseal_forbidden_targets",
            reason="preseal_must_not_run_expensive_or_full_converge_writers",
            target="generated-artifact-converge",
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(forbidden_check["status"], "fail")

    def test_guard_fails_when_preseal_delegated_cleanup_runs_forbidden_writer(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-auto-promotion-safe-cleanup-cleanup-only:\n"
                "\t@true\n",
                "release-auto-promotion-safe-cleanup-cleanup-only:\n"
                "\t$(MAKE) generated-artifact-converge\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = self._check_with_violation(
            report,
            check_id="release_auto_promotion_preseal_forbidden_targets",
            reason="preseal_must_not_run_expensive_or_full_converge_writers",
            target="generated-artifact-converge",
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            "release-auto-promotion-safe-cleanup-cleanup-only",
            check["violations"][0]["invocation_path"],
        )

    def test_guard_fails_when_auto_promotion_preseal_authority_writer_moves_before_cleanup(
        self,
    ) -> None:
        cleanup_line = _recipe_line_for_role("tmp-json-clean")
        writer_line = _recipe_line_for_role(
            "release-auto-promotion-preseal-authority-write"
        )
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                cleanup_line + writer_line,
                writer_line + cleanup_line,
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = self._check_with_violation(
            report,
            check_id="release_auto_promotion_preseal_protected_recipe",
            reason="protected_recipe_line_mismatch",
            target="release-auto-promotion-preseal",
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")


if __name__ == "__main__":
    unittest.main()
