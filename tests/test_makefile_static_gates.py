from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

import pytest
from ops.scripts.test_lane_registry_runtime import (
    authoritative_markers,
    compatibility_map,
    compatibility_names,
    documentation_authority,
    documentation_out_of_scope,
    lane_ci_entrypoint,
    lane_ci_steps,
    load_registry,
    marker_semantics,
    pack_by_id,
    pack_ci_entrypoint,
    pack_ci_steps,
    pack_mark_expr,
    pack_selectors,
    pack_summary_suite,
    selection_by_make_target,
)

from tests.makefile_static_helpers import (
    _assert_assignment_exists,
    _assert_recipe_contains_tokens,
    _makefile_assignment_value,
    _makefile_text,
    _recipe_lines,
    _target_block,
    _target_dependencies,
)

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


MAKEFILE = Path("Makefile")
README = Path("README.md")
DOCS_DEVELOPMENT = Path("docs/development.md")
DOCS_CBM = Path("docs/codebase-memory-mcp.md")
CONFTEST = Path("tests/conftest.py")
PYTEST_INI = Path("pytest.ini")
CI_WORKFLOW = Path(".github/workflows/ci.yml")
REPO_ROOT = Path(__file__).resolve().parents[1]


def _test_lane_registry() -> dict[str, object]:
    return load_registry(REPO_ROOT)


def _makefile_assignment_items(text: str, variable: str) -> tuple[str, ...]:
    prefix = f"{variable} ?="
    lines = text.splitlines()
    collecting = False
    items: list[str] = []
    for line in lines:
        if not collecting:
            if not line.startswith(prefix):
                continue
            collecting = True
            remainder = line[len(prefix) :].strip()
        else:
            if not line.startswith(("\t", " ")):
                break
            remainder = line.strip()

        continued = remainder.endswith("\\")
        remainder = remainder[:-1].strip() if continued else remainder
        if remainder:
            items.extend(remainder.split())
        if collecting and not continued:
            break

    if not collecting:
        raise AssertionError(f"missing Makefile assignment: {variable}")
    return tuple(items)


def _assert_make_selector_variable_matches_pack(
    case: unittest.TestCase,
    registry: dict[str, object],
    text: str,
    *,
    variable: str,
    pack_id: str,
) -> tuple[str, ...]:
    pack = pack_by_id(registry)[pack_id]
    selection = pack.get("selection", {})
    case.assertIsInstance(selection, dict)
    assert isinstance(selection, dict)
    case.assertEqual(selection.get("mode"), "explicit_selectors")
    items = _makefile_assignment_items(text, variable)
    case.assertEqual(items, pack_selectors(registry, pack_id))
    return items


def _report_contract_marked_test_files() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.as_posix()
            for path in Path("tests").glob("test_*.py")
            if "pytest.mark.report_contract" in path.read_text(encoding="utf-8")
        )
    )


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _pytest_ini_marker_docs() -> dict[str, str]:
    parser = configparser.ConfigParser()
    parser.read_string(PYTEST_INI.read_text(encoding="utf-8"))
    markers_value = parser["pytest"]["markers"]
    marker_docs: dict[str, str] = {}
    for line in markers_value.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        marker, separator, description = stripped.partition(":")
        if not separator:
            raise AssertionError(f"invalid pytest.ini marker declaration: {stripped}")
        marker_docs[marker.strip()] = description.strip()
    return marker_docs


def _assert_refresh_generated_split_targets(case: unittest.TestCase, text: str) -> None:
    case.assertIn(
        "refresh-generated-core: registry-preflight raw-registry-export manifest script-output-surfaces routing-provenance-aggregate outcome-metrics promotion-decision-trends mechanism-review mutation-proposal",
        text,
    )
    case.assertEqual(
        _recipe_lines(text, "refresh-generated-observability"),
        [
            "$(MAKE) make-target-inventory",
            "$(MAKE) workflow-dependency-planner",
            "$(MAKE) release-workflow-order-guard",
            "$(MAKE) function-budget-refactor-proposals",
            "$(MAKE) outcome-provenance-gate-policy",
            "$(MAKE) generated-artifact-converge",
        ],
    )
    case.assertIn("refresh-generated: refresh-generated-core refresh-generated-observability", text)
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-converge"),
        [
            '$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase before --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)"',
            "$(MAKE) generated-artifact-finality-suffix",
            '$(PYTHON) -m ops.scripts.generated_artifact_converge_summary --vault "$(VAULT)" --phase after --before "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT)" --out "$(GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT)"',
        ],
    )
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-script-output"),
        ["$(MAKE) script-output-surfaces"],
    )
    case.assertEqual(
        _recipe_lines(text, "generated-artifact-finality-suffix"),
        [
            "$(MAKE) artifact-freshness",
            "$(MAKE) external-report-action-matrix",
            "$(MAKE) generated-artifact-index",
        ],
    )
    case.assertIn(
        "GENERATED_ARTIFACT_CONVERGE_SUMMARY_OUT ?= tmp/generated-artifact-converge-summary.json",
        text,
    )
    case.assertIn(
        "GENERATED_ARTIFACT_CONVERGE_SUMMARY_BEFORE_OUT ?= tmp/generated-artifact-converge-summary.before.json",
        text,
    )
    for phony_target in (
        "refresh-generated-core",
        "refresh-generated-observability",
        "generated-artifact-converge",
        "generated-artifact-script-output",
        "generated-artifact-finality-suffix",
        "generated-artifact-retention-clean",
        "script-output-surfaces",
        "function-budget-refactor-proposals",
        "outcome-provenance-gate-policy",
        "external-report-action-matrix",
        "artifact-relocation-audit",
    ):
        with case.subTest(phony_target=phony_target):
            case.assertIn(phony_target, _target_block(text, ".PHONY"))


def _assert_observability_output_variables(case: unittest.TestCase, text: str) -> None:
    expected_variables = (
        "FUNCTION_BUDGET_REFACTOR_PROPOSALS_OUT ?= ops/reports/function-budget-refactor-proposals.json",
        "FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT ?= tmp/function-budget-refactor-proposals.candidate.json",
        "OUTCOME_PROVENANCE_GATE_POLICY_OUT ?= ops/reports/outcome-provenance-gate-policy.json",
        "OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT ?= tmp/outcome-provenance-gate-policy.candidate.json",
        "EXTERNAL_REPORT_ACTION_MATRIX_OUT ?= ops/reports/external-report-action-matrix.json",
        "SCRIPT_OUTPUT_SURFACES_OUT ?= ops/script-output-surfaces.json",
        "GENERATED_ARTIFACT_RETENTION_CLEAN_OUT ?= tmp/generated-artifact-retention-clean.json",
        "GENERATED_ARTIFACT_RETENTION_CLEAN_APPLY ?=",
        "CLEAN_FIXTURE_REGENERATION_GUARD_OUT ?= tmp/clean-fixture-regeneration-guard.json",
        "MAKE_TARGET_INVENTORY_OUT ?= tmp/make-target-inventory.json",
        "WORKFLOW_DEPENDENCY_PLANNER_OUT ?= ops/reports/workflow-dependency-planner.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT ?= tmp/workflow-dependency-planner.candidate.json",
        "WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT ?= tmp/workflow-dependency-planner-check.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_OUT ?= ops/reports/release-workflow-order-guard.json",
        "RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT ?= tmp/release-workflow-order-guard.candidate.json",
    )
    for variable in expected_variables:
        with case.subTest(variable=variable):
            case.assertIn(variable, text)


def _assert_script_surface_and_inventory_targets(case: unittest.TestCase, text: str) -> None:
    script_output_block = _target_block(text, "script-output-surfaces")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" --out "$(SCRIPT_OUTPUT_SURFACES_OUT)"',
        script_output_block,
    )
    case.assertNotIn("ops.scripts.canonical_artifact_promote", script_output_block)
    case.assertNotIn("--preserve-existing-on-semantic-match", script_output_block)
    case.assertNotIn("--semantic-match-includes-source-tree-fingerprint", script_output_block)
    script_output_check_block = _target_block(text, "script-output-surfaces-check")
    case.assertIn("script-output-surfaces-check", _target_block(text, ".PHONY"))
    case.assertIn("ops.scripts.script_output_surfaces", script_output_check_block)
    case.assertIn('--stored "$(SCRIPT_OUTPUT_SURFACES_OUT)"', script_output_check_block)
    case.assertIn("--check", script_output_check_block)
    case.assertNotIn("SCRIPT_OUTPUT_SURFACES_CANDIDATE_OUT", script_output_check_block)
    case.assertNotIn("ops.scripts.canonical_artifact_promote", script_output_check_block)
    retention_clean_block = _target_block(text, "generated-artifact-retention-clean")
    case.assertIn("generated-artifact-retention-clean", _target_block(text, ".PHONY"))
    case.assertIn("ops.scripts.generated_artifact_retention_clean", retention_clean_block)
    case.assertIn('--out "$(GENERATED_ARTIFACT_RETENTION_CLEAN_OUT)"', retention_clean_block)
    case.assertIn("--apply", retention_clean_block)
    guard_block = _target_block(text, "clean-fixture-regeneration-guard")
    case.assertIn("clean-fixture-regeneration-guard", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.clean_fixture_regeneration_guard --vault "$(VAULT)" --out "$(CLEAN_FIXTURE_REGENERATION_GUARD_OUT)"',
        guard_block,
    )
    case.assertIn(
        "script-output-surfaces-clean-regenerate: clean-fixture-regeneration-guard script-output-surfaces",
        text,
    )
    case.assertIn("make-target-inventory", _target_block(text, ".PHONY"))
    case.assertIn(
        '$(PYTHON) -m ops.scripts.make_target_inventory --vault "$(VAULT)" --out "$(MAKE_TARGET_INVENTORY_OUT)"',
        _target_block(text, "make-target-inventory"),
    )


def _assert_workflow_dependency_planner_target(case: unittest.TestCase, text: str) -> None:
    case.assertIn("workflow-dependency-planner", _target_block(text, ".PHONY"))
    case.assertIn("workflow-dependency-planner-check", _target_block(text, ".PHONY"))
    planner_block = _target_block(text, "workflow-dependency-planner")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CANDIDATE_OUT)"',
        planner_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", planner_block)
    case.assertIn("--schema ops/schemas/workflow-dependency-planner.schema.json", planner_block)
    case.assertIn("--expected-artifact-kind workflow_dependency_planner", planner_block)
    case.assertIn("--expected-producer ops.scripts.workflow_dependency_planner", planner_block)
    planner_check_block = _target_block(text, "workflow-dependency-planner-check")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.workflow_dependency_planner --vault "$(VAULT)" --out "$(WORKFLOW_DEPENDENCY_PLANNER_CHECK_OUT)"',
        planner_check_block,
    )
    case.assertNotIn("canonical_artifact_promote", planner_check_block)
    for target in ("static", "check", "check-all", "release-check", "release-clean"):
        with case.subTest(target=target):
            case.assertNotIn("workflow-dependency-planner", _target_block(text, target))
    case.assertNotIn("$(MAKE) workflow-dependency-planner", _target_block(text, "release-evidence-converge"))
    case.assertNotIn("$(MAKE) workflow-dependency-planner", _target_block(text, "check-finalized"))


def _assert_release_workflow_order_guard_target(case: unittest.TestCase, text: str) -> None:
    case.assertIn("release-workflow-order-guard", _target_block(text, ".PHONY"))
    order_guard_block = _target_block(text, "release-workflow-order-guard")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.release_workflow_order_guard --vault "$(VAULT)" --out "$(RELEASE_WORKFLOW_ORDER_GUARD_CANDIDATE_OUT)"',
        order_guard_block,
    )
    case.assertIn("ops.scripts.canonical_artifact_promote", order_guard_block)
    case.assertIn("--schema ops/schemas/release-workflow-order-guard.schema.json", order_guard_block)
    case.assertIn("--expected-artifact-kind release_workflow_order_guard", order_guard_block)
    case.assertIn("--expected-producer ops.scripts.release_workflow_order_guard", order_guard_block)
    case.assertNotIn("$(MAKE) release-workflow-order-guard", _target_block(text, "release-evidence-converge"))
    case.assertNotIn("$(MAKE) release-workflow-order-guard", _target_block(text, "check-finalized"))


def _assert_function_budget_and_outcome_targets(case: unittest.TestCase, text: str) -> None:
    proposal_block = _target_block(text, "function-budget-refactor-proposals")
    case.assertIn("function-budget-refactor-proposals: wiki-lint-review-classification", text)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.function_budget_refactor_proposals --vault "$(VAULT)" --classification "$(WIKI_LINT_REVIEW_CLASSIFICATION_OUT)" --out "$(FUNCTION_BUDGET_REFACTOR_PROPOSALS_CANDIDATE_OUT)"',
        proposal_block,
    )
    case.assertIn("--schema ops/schemas/function-budget-refactor-proposals.schema.json", proposal_block)

    outcome_policy_block = _target_block(text, "outcome-provenance-gate-policy")
    case.assertIn("outcome-provenance-gate-policy: outcome-metrics routing-provenance-aggregate", text)
    case.assertIn(
        '$(PYTHON) -m ops.scripts.outcome_provenance_gate_policy --vault "$(VAULT)" --out "$(OUTCOME_PROVENANCE_GATE_POLICY_CANDIDATE_OUT)"',
        outcome_policy_block,
    )
    case.assertIn("--schema ops/schemas/outcome-provenance-gate-policy.schema.json", outcome_policy_block)
    case.assertIn("--expected-artifact-kind outcome_provenance_gate_policy", outcome_policy_block)
    case.assertIn("--expected-producer ops.scripts.outcome_provenance_gate_policy", outcome_policy_block)

    promotion_trends_block = _target_block(text, "promotion-decision-trends")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.promotion_decision_trends --vault "$(VAULT)" --recent-window "$(PROMOTION_DECISION_TRENDS_RECENT_WINDOW)"',
        promotion_trends_block,
    )


def _assert_external_report_action_matrix_target(case: unittest.TestCase, text: str) -> None:
    external_action_block = _target_block(text, "external-report-action-matrix")
    case.assertIn(
        '$(PYTHON) -m ops.scripts.external_report_action_matrix --vault "$(VAULT)" --out "$(EXTERNAL_REPORT_ACTION_MATRIX_OUT)"',
        external_action_block,
    )
    case.assertIn("compatibility aggregate", _target_block(text, "refresh-generated"))


class MakefileStaticGateTests(unittest.TestCase):
    def test_root_makefile_keeps_only_common_variables_and_aggregate_aliases(self) -> None:
        root_text = MAKEFILE.read_text(encoding="utf-8")
        allowed_assignments = {
            "VENV_DIR",
            "VENV_PYTHON",
            "PYTHON",
            "BOOTSTRAP_PYTHON",
            "VAULT",
            "EXECUTION_LANE_POLICY",
        }
        assignment_names = {
            match.group(1)
            for match in re.finditer(r"^([A-Z0-9_]+)\s*(?:\?|:)?=", root_text, flags=re.MULTILINE)
        }

        self.assertEqual(assignment_names, allowed_assignments)
        for mk_file in (
            "mk/core.mk",
            "mk/static.mk",
            "mk/test.mk",
            "mk/eval.mk",
            "mk/artifact.mk",
            "mk/registry.mk",
            "mk/mechanism.mk",
            "mk/release.mk",
            "mk/public.mk",
            "mk/supply_chain.mk",
        ):
            with self.subTest(mk_file=mk_file):
                self.assertIn(f"include {mk_file}", root_text)
                self.assertLess(root_text.index(f"include {mk_file}"), root_text.index(".PHONY: check"))
        self.assertLess(root_text.index("include mk/test.mk"), root_text.index("export PYTEST_DISABLE_PLUGIN_AUTOLOAD"))

    def test_help_target_indexes_operator_entrypoints(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "help")

        self.assertIn("help", _target_block(text, ".PHONY"))
        for heading in (
            "Setup:",
            "Source checks:",
            "Report contracts:",
            "Public mirror:",
            "Mechanism:",
            "Release:",
        ):
            self.assertIn(heading, block)
        for target in (
            "make dev-install",
            "make static",
            "make local-cache-clean",
            "make local-tool-state-clean",
            "make uv-cache-prune",
            "make strict-preview-audit",
            "make test-report-contract-core",
            "make external-report-lifecycle-refresh",
            "make sync-public-policy",
            "make goal-runtime-run-admission",
            "make release-auto-promotion-ready",
        ):
            self.assertIn(target, block)

    def test_check_targets_include_static_gate(self) -> None:
        text = _makefile_text()

        for target in ("check", "check-serial", "check-all", "check-all-serial"):
            with self.subTest(target=target):
                dependencies = _target_dependencies(text, target)
                self.assertEqual(dependencies[:2], ("uv-lock-check", "static"))
                self.assertIn("registry-preflight-check", dependencies)
                self.assertNotIn("registry-preflight", dependencies)
        self.assertEqual(_target_dependencies(text, "static"), ("uv-lock-check", "ruff", "typecheck"))
        self.assertEqual(
            _recipe_lines(text, "uv-lock-check"),
            ['UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) lock --check $(UV_LOCK_CHECK_INDEX_FLAGS)'],
        )
        self.assertIn("UV_CANONICAL_INDEX_URL ?= https://pypi.org/simple", text)
        self.assertIn(
            'UV_LOCK_CHECK_INDEX_FLAGS ?= --default-index "$(UV_CANONICAL_INDEX_URL)"',
            text,
        )
        self.assertIn("uv-lock-check", _target_block(text, ".PHONY"))

    def test_strict_targets_include_warning_budget_gate(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "check-strict: check warning-budget complexity-budget-touched-check", text
        )
        self.assertIn("check-conditional: check", text)
        self.assertIn(
            "check-clean: check-clean-lane-guard check-conditional warning-budget release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target check-clean',
            _target_block(text, "check-clean-lane-guard"),
        )
        self.assertIn("release-evidence-converge-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-evidence-converge',
            _target_block(text, "release-evidence-converge-lane-guard"),
        )
        self.assertIn("release-evidence-closeout-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            "release-evidence-closeout-lane-guard is a compatibility alias",
            _target_block(text, "release-evidence-closeout-lane-guard"),
        )
        self.assertIn("release-builder-full-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-builder-full',
            _target_block(text, "release-builder-full-lane-guard"),
        )
        self.assertIn("release-smoke-lane-guard", _target_block(text, ".PHONY"))
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-smoke',
            _target_block(text, "release-smoke-lane-guard"),
        )
        self.assertIn(
            "release-distribution-zip: release-distribution-zip-lane-guard",
            text,
        )
        self.assertIn(
            "release-distribution-zip-lane-guard", _target_block(text, ".PHONY")
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.execution_lane_guard --vault "$(VAULT)" --policy "$(EXECUTION_LANE_POLICY)" --target release-distribution-zip',
            _target_block(text, "release-distribution-zip-lane-guard"),
        )
        self.assertIn("release-conditional: release-evidence-refresh-fast", text)
        self.assertIn(
            "release-clean: release-check warning-budget release-evidence-converge release-evidence-cohort-check",
            text,
        )
        self.assertIn(
            "release-provenance-clean: release-clean supply-chain-check", text
        )
        self.assertIn(
            '$(PYTHON) -m ops.scripts.warning_budget --vault "$(VAULT)"',
            _target_block(text, "warning-budget"),
        )

    def test_static_gate_runs_ruff_and_full_ops_mypy_target(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("MYPY_TARGETS ?= ops/scripts", text)
        self.assertIn("TOOL_CACHE_ROOT ?= tmp/tool-cache", text)
        self.assertIn("TOOL_CACHE_PLATFORM ?=", text)
        self.assertIn("RUFF_CACHE_DIR ?= $(TOOL_CACHE_ROOT)/ruff/$(TOOL_CACHE_PLATFORM)", text)
        self.assertIn("MYPY_CACHE_DIR ?= $(TOOL_CACHE_ROOT)/mypy/$(TOOL_CACHE_PLATFORM)", text)
        self.assertIn("static: uv-lock-check ruff typecheck", text)
        self.assertIn(
            'UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) lock --check $(UV_LOCK_CHECK_INDEX_FLAGS)',
            _target_block(text, "uv-lock-check"),
        )
        self.assertIn(
            "$(PYTHON) -m ruff check $(RUFF_CACHE_FLAGS) $(RUFF_TARGETS)",
            _target_block(text, "ruff"),
        )
        self.assertIn(
            "$(PYTHON) -m mypy $(MYPY_CACHE_FLAGS) $(MYPY_TARGETS)",
            _target_block(text, "typecheck"),
        )

    def test_local_cache_clean_removes_only_regenerable_repo_caches(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "local-cache-clean")

        self.assertIn("local-cache-clean", _target_block(text, ".PHONY"))
        self.assertIn(
            "LOCAL_CACHE_CLEAN_PATHS ?= .pytest_cache .hypothesis .ruff_cache .mypy_cache $(TOOL_CACHE_ROOT)",
            text,
        )
        self.assertIn(
            "LOCAL_TOOL_STATE_CLEAN_PATHS ?= .agents .obsidian .serena .vscode .ouroboros .ouroboros_eval_artifact.md",
            text,
        )
        self.assertIn("LOCAL_CACHE_CLEAN_FIND_ROOTS ?= ops tests tools", text)
        self.assertIn("rm -rf $(LOCAL_CACHE_CLEAN_PATHS)", block)
        self.assertIn("find $(LOCAL_CACHE_CLEAN_FIND_ROOTS) -type d -name __pycache__", block)
        self.assertIn("find $(LOCAL_CACHE_CLEAN_FIND_ROOTS) -type f", block)
        self.assertNotIn("LOCAL_TOOL_STATE_CLEAN_PATHS", block)
        self.assertNotIn(".kiro", block)
        self.assertNotIn(".venv", block)
        self.assertNotIn("ops/reports", block)
        self.assertNotIn("build/release", block)

    def test_local_tool_state_clean_is_explicit_and_keeps_migration_state_out(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "local-tool-state-clean")

        self.assertIn("local-tool-state-clean", _target_block(text, ".PHONY"))
        self.assertIn("rm -rf $(LOCAL_TOOL_STATE_CLEAN_PATHS)", block)
        self.assertNotIn(".kiro", block)
        self.assertNotIn(".venv", block)
        self.assertNotIn("ops/reports", block)

    def test_uv_cache_prune_keeps_global_uv_cleanup_explicit_and_non_destructive(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "uv-cache-prune")

        self.assertIn("uv-cache-prune", _target_block(text, ".PHONY"))
        self.assertIn("UV_CACHE_PRUNE_FLAGS ?=", text)
        self.assertIn("$(UV) cache prune $(UV_CACHE_PRUNE_FLAGS)", block)
        self.assertNotIn("cache clean", block)
        self.assertNotIn("--force", block)

    def test_pytest_entrypoints_disable_third_party_plugin_autoload(self) -> None:
        text = _makefile_text()

        self.assertIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1", text)
        self.assertIn("export PYTEST_DISABLE_PLUGIN_AUTOLOAD", text)
        self.assertIn("LLMWIKI_MAKE_PYTEST_ENTRYPOINT ?= 1", text)
        self.assertIn("export LLMWIKI_MAKE_PYTEST_ENTRYPOINT", text)
        self.assertIn("PYTHONDONTWRITEBYTECODE ?= 1", text)
        self.assertIn("export PYTHONDONTWRITEBYTECODE", text)
        self.assertIn("PYTEST_XDIST_WORKERS ?= 4", text)
        self.assertIn("PYTEST_XDIST_MAXPROCESSES ?= 4", text)
        self.assertIn(
            "PYTEST_XDIST_MAXPROCESSES_FLAGS ?= --maxprocesses=$(PYTEST_XDIST_MAXPROCESSES)",
            text,
        )
        self.assertIn(
            "PYTEST_LOADFILE_FLAGS ?= -p xdist.plugin -n $(PYTEST_XDIST_WORKERS) $(PYTEST_XDIST_MAXPROCESSES_FLAGS) --dist=loadfile",
            text,
        )
        self.assertNotIn("-n auto --dist=loadfile", text)
        self.assertIn(
            "PYTEST_PARALLEL_FLAGS ?= $(PYTEST_LOADFILE_FLAGS)", text
        )
        self.assertIn("PYTEST_CACHE_ISOLATION_FLAGS ?= -p no:cacheprovider", text)
        self.assertIn(
            "PYTEST_FLAGS ?= $(PYTEST_PARALLEL_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)",
            text,
        )
        self.assertIn(
            "PYTEST_REPORT_CONTRACT_FLAGS ?= $(PYTEST_LOADFILE_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_SEALING_FLAGS ?= $(PYTEST_LOADFILE_FLAGS) $(PYTEST_CACHE_ISOLATION_FLAGS)",
            text,
        )

    def test_pytest_ini_declares_lane_markers(self) -> None:
        registry = _test_lane_registry()
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")
        marker_docs = _pytest_ini_marker_docs()

        self.assertEqual(set(marker_docs), authoritative_markers(registry))
        self.assertEqual(marker_docs, marker_semantics(registry))
        self.assertNotIn(
            "deprecated compatibility alias for artifact_finalization", pytest_ini_text
        )

    def test_registry_make_target_marker_expressions_match_makefile_variables(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        variable_by_target = {
            "test-slow": "PYTEST_SLOW_MARK_EXPR",
            "test-integration": "PYTEST_INTEGRATION_MARK_EXPR",
            "test-integration-heavy": "PYTEST_INTEGRATION_HEAVY_MARK_EXPR",
            "test-public": "PYTEST_PUBLIC_MARK_EXPR",
            "test-report-contract-all": "PYTEST_REPORT_CONTRACT_MARK_EXPR",
            "test-release-sealing-all": "PYTEST_RELEASE_SEALING_MARK_EXPR",
            "test-subprocess": "PYTEST_SUBPROCESS_MARK_EXPR",
        }

        for target, variable in variable_by_target.items():
            with self.subTest(target=target, variable=variable):
                self.assertEqual(
                    _normalize_whitespace(_makefile_assignment_value(text, variable)),
                    _normalize_whitespace(selection_by_make_target(registry)[target]),
                )

    def test_registry_explicit_selector_packs_match_makefile_variables(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        variable_by_pack = {
            "fast_smoke": "FAST_SMOKE_TESTS",
            "report_contract_core": "REPORT_CONTRACT_CORE_TESTS",
            "release_sealing_core": "RELEASE_SEALING_CORE_TESTS",
            "subprocess_checks": "SUBPROCESS_TESTS",
            "release_closeout_regression": "RELEASE_CLOSEOUT_REGRESSION_TESTS",
        }

        for pack_id, variable in variable_by_pack.items():
            with self.subTest(pack_id=pack_id, variable=variable):
                _assert_make_selector_variable_matches_pack(
                    self,
                    registry,
                    text,
                    variable=variable,
                    pack_id=pack_id,
                )

    def test_registry_make_target_compatibility_entries_exist_in_makefile(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        for target in compatibility_names(registry, "make_target"):
            with self.subTest(target=target):
                _target_block(text, target)

    def test_pyproject_does_not_define_conflicting_pytest_marker_block(self) -> None:
        pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertNotIn("[tool.pytest.ini_options]", pyproject_text)
        self.assertNotIn('"finalization: local artifact self-checks', pyproject_text)

    def test_readme_and_pytest_ini_pin_supported_pytest_entrypoints(self) -> None:
        registry = _test_lane_registry()
        readme_text = README.read_text(encoding="utf-8")
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        conftest_text = CONFTEST.read_text(encoding="utf-8")
        pytest_ini_text = PYTEST_INI.read_text(encoding="utf-8")
        normalized_readme_text = _normalize_whitespace(readme_text)
        normalized_development_text = _normalize_whitespace(development_text)

        self.assertIn("docs/development.md", readme_text)
        self.assertIn("make help", readme_text)
        self.assertIn("make help", development_text)
        self.assertIn("make uv-lock-check", development_text)
        self.assertIn("UV_CANONICAL_INDEX_URL", development_text)
        self.assertIn("uv.lock", development_text)
        self.assertIn(
            "For a full developer regression, use `make test-all`.",
            readme_text,
        )
        self.assertIn(
            "Bare `pytest` is not a supported entrypoint.",
            normalized_readme_text,
        )
        self.assertIn(
            "`make test-execution-summary-full-current-or-refresh`",
            development_text,
        )
        self.assertIn("`test-execution-summary-full-refresh-no-converge`", development_text)
        self.assertIn("`make test-all`", development_text)
        self.assertIn("focused `.venv/bin/python -m pytest tests/...`", development_text)
        self.assertIn("Bare `pytest` is unsupported.", normalized_development_text)
        self.assertIn("ops/test-lane-registry.json", development_text)
        self.assertIn("mk/test.mk", development_text)
        self.assertIn("Volatile counts and durations belong", development_text)
        self.assertNotRegex(
            development_text,
            r"\b(?:\d+\s+(?:tests|subtests|minutes)|20\d{2}-\d{2}-\d{2})\b",
        )
        self.assertIn("plain `pytest` is not a supported entrypoint", conftest_text)
        self.assertIn("selectorless `.venv/bin/python -m pytest`", conftest_text)
        self.assertIn("BARE_PYTEST_GUIDANCE", conftest_text)
        self.assertIn("SELECTORLESS_PYTEST_GUIDANCE", conftest_text)
        self.assertIn("LLMWIKI_MAKE_PYTEST_ENTRYPOINT", conftest_text)
        self.assertIn("make test-all", conftest_text)
        self.assertIn("make test-execution-summary-full-current-or-refresh", conftest_text)
        self.assertNotRegex(pytest_ini_text, r"(?im)^pythonpath\s*=")
        for entrypoint in (
            "make fast-smoke",
            "make test",
            "make test-all",
            "make release-run-ready",
            "make release-post-commit-finalize",
            "make release-authority-settle",
        ):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, development_text)
        for alias in (
            "make test-report-contract",
            "make report-contracts",
            "make report-contracts-core",
            "make report-contracts-all",
            "make report-contracts-extended",
            "make test-release-sealing",
        ):
            with self.subTest(alias=alias):
                self.assertNotIn(f"- `{alias}`", development_text)
                self.assertNotIn(alias, compatibility_names(registry, "documented_entrypoint"))

    def test_python_command_allows_interpreter_flags(self) -> None:
        text = _makefile_text()

        self.assertNotIn('"$(PYTHON)"', text)
        self.assertIn("PUBLIC_PYTHON ?= $(if $(wildcard $(firstword $(PYTHON)))", text)
        self.assertIn(
            "$(PYTHON) -m ruff check $(RUFF_CACHE_FLAGS) $(RUFF_TARGETS)",
            _target_block(text, "ruff"),
        )

    def test_repo_virtualenv_is_canonical_make_default(self) -> None:
        text = _makefile_text()

        self.assertIn("VENV_DIR ?= .venv", text)
        self.assertIn("VENV_PYTHON ?= $(VENV_DIR)/bin/python", text)
        self.assertIn(
            "PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python3)",
            text,
        )

    def test_fast_smoke_is_curated_developer_feedback_loop(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")
        block = _target_block(text, "fast-smoke")
        expected_tests = pack_selectors(registry, "fast_smoke")

        self.assertIn("fast-smoke", _target_block(text, ".PHONY"))
        self.assertIn(
            "PYTEST_FAST_SMOKE_MARK_EXPR ?= not slow and not integration_heavy", text
        )
        self.assertIn("FAST_SMOKE_TESTS ?=", text)
        self.assertIn(
            "`make fast-smoke`는 Subagent/developer precheck 전용 curated pytest slice다.",
            development_text,
        )
        for test_path in expected_tests:
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_SMOKE_MARK_EXPR)" $(FAST_SMOKE_TESTS) $(PYTEST_SERIAL_FLAGS)',
            block,
        )
        self.assertNotIn("lint", block)
        self.assertNotIn("eval", block)
        self.assertNotIn("stage2-eval", block)
        self.assertNotIn("release-smoke", block)
        self.assertNotIn("tests/test_report_generation_smoke.py", block)
        self.assertNotIn("tests/test_mutation_proposal.py \\", block)
        self.assertNotIn("tests/test_artifact_freshness_runtime.py \\", block)
        self.assertNotIn("tests/test_release_smoke.py \\", block)

    def test_fast_smoke_selectors_collect_via_supported_pytest_entrypoint(self) -> None:
        text = _makefile_text()
        selectors = _makefile_assignment_items(text, "FAST_SMOKE_TESTS")
        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                *selectors,
            ],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "FAST_SMOKE_TESTS contains an uncollectable pytest selector.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )

    def test_makefile_exposes_lane_targets_and_compatibility_aliases(self) -> None:
        text = _makefile_text()

        for target in (
            "test-fast",
            "test-report-contract-core",
            "test-report-contract-all",
            "test-release-sealing-core",
            "test-release-sealing-all",
            "test-subprocess",
            "release-source-package-smoke",
            "release-source-package-check",
            "release-run-ready",
            "release-run-ready-check",
            "release-sealed-run-ready",
            "release-sealed-run-ready-plan",
            "release-sealed-run-ready-check",
            "release-auto-promotion-goal-run-id-guard",
            "release-auto-promotion-preflight",
            "release-auto-promotion-preflight-check",
            "release-auto-promotion-safe-cleanup",
            "release-auto-promotion-preseal",
            "release-auto-promotion-preseal-check",
            "release-auto-promotion-ready",
            "release-auto-promotion-ready-plan",
            "release-auto-promotion-operator-summary",
            "release-auto-promotion-ready-check",
            "release-authority-settle",
            "release-builder-full",
        ):
            with self.subTest(target=target):
                self.assertIn(target, _target_block(text, ".PHONY"))
        phony_block = _target_block(text, ".PHONY")
        for removed_alias in (
            "report-contracts",
            "report-contracts-core",
            "report-contracts-all",
            "report-contracts-extended",
            "test-report-contract",
            "report-contract-summary",
            "test-release-sealing",
            "test-execution-summary-aggregate",
        ):
            with self.subTest(removed_alias=removed_alias):
                self.assertNotRegex(
                    phony_block,
                    rf"(?<![A-Za-z0-9_.-]){re.escape(removed_alias)}(?![A-Za-z0-9_.-])",
                )

        self.assertIn(
            "PYTEST_REPORT_CONTRACT_MARK_EXPR ?= report_contract",
            text,
        )
        self.assertIn(
            "PYTEST_RELEASE_CHECK_MARK_EXPR ?= not report_contract",
            text,
        )
        self.assertIn("PYTEST_RELEASE_SEALING_MARK_EXPR ?= release_sealing", text)
        self.assertIn("PYTEST_SUBPROCESS_MARK_EXPR ?= subprocess", text)
        self.assertIn("RELEASE_SEALING_CORE_TESTS ?=", text)
        self.assertIn("tests/test_release_auto_promotion_preflight.py", text)
        self.assertIn("RELEASE_SEALING_TESTS ?= $(RELEASE_SEALING_CORE_TESTS)", text)
        self.assertIn("SUBPROCESS_TESTS ?=", text)
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_FAST_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "test-fast"),
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(PYTEST_FLAGS)",
            _target_block(text, "unit-tests-all"),
        )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "unit-tests-release-check"),
        )
        self.assertIn("test: test-fast", text)
        self.assertIn("unit-tests: test-fast", text)
        self.assertIn(
            "release-builder-full: release-builder-full-lane-guard bootstrap-preflight static release-evidence-converge",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_SEALING_TESTS) $(PYTEST_RELEASE_SEALING_FLAGS)",
            _target_block(text, "test-release-sealing-core"),
        )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_SEALING_MARK_EXPR)" $(PYTEST_RELEASE_SEALING_FLAGS)',
            _target_block(text, "test-release-sealing-all"),
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(SUBPROCESS_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-subprocess"),
        )
        self.assertIn("RELEASE_CLOSEOUT_REGRESSION_TESTS ?=", text)
        self.assertIn(
            "RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT ?= tmp/release-closeout-regression-artifact-freshness-check.json",
            text,
        )
        self.assertIn(
            "RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT ?= tmp/release-closeout-fixed-point-cost-trend-ci.json",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(RELEASE_CLOSEOUT_REGRESSION_TESTS) $(PYTEST_SERIAL_FLAGS)",
            _target_block(text, "test-release-closeout-regression-pack"),
        )
        self.assertIn(
            "release-closeout-regression-dry-run",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-cost-evidence-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "release-closeout-post-check-finalizer-ci-artifact",
            _target_block(text, ".PHONY"),
        )
        regression_dry_run = _target_block(text, "release-closeout-regression-dry-run")
        self.assertIn("release-closeout-regression-dry-run: tmp-json-clean", text)
        self.assertIn(
            "$(MAKE) test-release-closeout-regression-pack", regression_dry_run
        )
        self.assertIn(
            '--out "$(RELEASE_CLOSEOUT_REGRESSION_FRESHNESS_CHECK_OUT)"',
            regression_dry_run,
        )
        self.assertIn("--fail-on-fail", regression_dry_run)
        self.assertIn("--verify", regression_dry_run)
        cost_artifact = _target_block(
            text, "release-closeout-cost-evidence-ci-artifact"
        )
        self.assertIn(
            "ops.scripts.release_closeout_fixed_point_cost_trend", cost_artifact
        )
        self.assertIn('--out "$(RELEASE_CLOSEOUT_COST_EVIDENCE_CI_OUT)"', cost_artifact)
        self.assertIn("--no-fail", cost_artifact)
        post_check_artifact = _target_block(
            text, "release-closeout-post-check-finalizer-ci-artifact"
        )
        self.assertIn("--recommended-targets-out", post_check_artifact)
        self.assertIn(
            '"$(RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_RECOMMENDED_TARGETS_OUT)"',
            post_check_artifact,
        )
        self.assertIn("--no-fail", post_check_artifact)

    def test_developer_full_suite_runs_full_pytest_without_marker_filter(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        release_check_expr = pack_mark_expr(registry, "release_check_unit_complement")

        _assert_assignment_exists(
            self,
            text,
            "PYTEST_RELEASE_CHECK_MARK_EXPR",
            release_check_expr,
        )
        self.assertEqual(release_check_expr, "not report_contract")
        for target, flags in (
            ("unit-tests-all", "$(PYTEST_FLAGS)"),
            ("unit-tests-all-serial", "$(PYTEST_SERIAL_FLAGS)"),
            ("unit-tests-all-parallel", "$(PYTEST_PARALLEL_FLAGS)"),
        ):
            with self.subTest(target=target):
                self.assertIn(
                    f"$(PYTHON) -m pytest {flags}",
                    _target_block(text, target),
                )
        self.assertIn(
            '$(PYTHON) -m pytest -m "$(PYTEST_RELEASE_CHECK_MARK_EXPR)" $(PYTEST_FLAGS)',
            _target_block(text, "unit-tests-release-check"),
        )

    def test_source_package_targets_pin_clean_extract_smoke_lane(self) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()

        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_ROOT",
            "build/source-package-smoke",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_OUT",
            "$(SOURCE_PACKAGE_SMOKE_ROOT)/source-package-smoke.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT",
            "$(SOURCE_PACKAGE_SMOKE_ROOT)/extract",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_SMOKE_PYTHON",
            "$(PUBLIC_PYTHON)",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_OUT",
            "ops/reports/source-package-clean-extract.json",
        )
        _assert_assignment_exists(
            self,
            text,
            "SOURCE_PACKAGE_CLEAN_EXTRACT_ROOT",
            "tmp/source-package-clean-extract",
        )
        self.assertIn("release-package-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-package-current-or-refresh", _target_block(text, ".PHONY"))
        self.assertIn("release-source-package-smoke-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-source-package-smoke-current-or-refresh", _target_block(text, ".PHONY"))
        self.assertIn("release-source-package-clean-extract", _target_block(text, ".PHONY"))
        self.assertIn("release-source-package-clean-extract-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-source-package-clean-extract-current-or-refresh", _target_block(text, ".PHONY"))
        self.assertIn("--reuse-if-current", _target_block(text, "release-package-current-check"))
        self.assertIn(
            '$(MAKE) release-package-current-check',
            _target_block(text, "release-package-current-or-refresh"),
        )
        self.assertIn(
            '$(MAKE) release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT="$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
            _target_block(text, "release-package-current-or-refresh"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-smoke-current-check",
            (
                "ops.scripts.source_package_smoke",
                '--source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
                '--extract-parent "$(SOURCE_PACKAGE_SMOKE_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)"',
                '--out "$(SOURCE_PACKAGE_SMOKE_OUT)"',
                "--reuse-if-current",
                "--reuse-only",
            ),
        )
        self.assertIn(
            '$(MAKE) release-source-package-smoke-current-check',
            _target_block(text, "release-source-package-smoke-current-or-refresh"),
        )
        _assert_recipe_contains_tokens(
            self,
            text,
            "release-source-package-clean-extract-current-check",
            (
                "ops.scripts.source_package_clean_extract",
                '--source-zip "$(RELEASE_CLOSEOUT_SEALED_DISTRIBUTION_ZIP)"',
                '--extract-parent "$(SOURCE_PACKAGE_CLEAN_EXTRACT_EXTRACT_PARENT)"',
                '--source-python "$(SOURCE_PACKAGE_SMOKE_PYTHON)"',
                '--test-summary-out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_TEST_SUMMARY_OUT)"',
                '--pytest-flags="$(SOURCE_PACKAGE_CLEAN_EXTRACT_PYTEST_FLAGS)"',
                '--zip-smoke-report "$(RELEASE_DISTRIBUTION_ZIP_SMOKE_OUT)"',
                '--out "$(SOURCE_PACKAGE_CLEAN_EXTRACT_OUT)"',
                "--reuse-if-current",
                "--reuse-only",
            ),
        )
        self.assertIn(
            '$(MAKE) release-source-package-clean-extract-current-check',
            _target_block(text, "release-source-package-clean-extract-current-or-refresh"),
        )
        self.assertEqual(pack_selectors(registry, "source_package"), ("release-source-package-smoke",))
        self.assertEqual(
            pack_summary_suite(registry, "source_package")["summary_target"],
            "build/source-package-smoke/source-package-smoke.json",
        )
        self.assertIn("$(MAKE) release-package-current-or-refresh", _target_block(text, "release-source-package-check"))
        self.assertIn("$(MAKE) release-source-package-smoke-current-or-refresh", _target_block(text, "release-source-package-check"))
        self.assertIn(
            "$(MAKE) release-source-package-clean-extract-current-or-refresh",
            _target_block(text, "release-source-package-check"),
        )

    def test_ci_matrix_runs_named_lane_targets(self) -> None:
        registry = _test_lane_registry()
        workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
        ci_map = compatibility_map(registry, "ci_tier")

        for tier, mapped_id in ci_map.items():
            with self.subTest(tier=tier, mapped_id=mapped_id):
                self.assertIn(f"- {tier}", workflow_text)
                if mapped_id in pack_by_id(registry):
                    expected_steps = pack_ci_steps(registry, mapped_id)
                    expected_entrypoint = pack_ci_entrypoint(registry, mapped_id)
                else:
                    expected_steps = lane_ci_steps(registry, mapped_id)
                    expected_entrypoint = lane_ci_entrypoint(registry, mapped_id)
                self.assertTrue(expected_steps)
                self.assertTrue(expected_entrypoint)
                self.assertIn(f"make {expected_entrypoint}", workflow_text)
                for step in expected_steps:
                    self.assertIn(step, workflow_text)
        self.assertIn("make release-authority-sealed-preflight", workflow_text)
        self.assertIn("make test-fast", workflow_text)

    def test_readme_ci_tier_summary_matches_current_workflow_shape(self) -> None:
        registry = _test_lane_registry()
        development_text = DOCS_DEVELOPMENT.read_text(encoding="utf-8")

        self.assertIn("CI splits registry-backed lanes into parallel jobs", development_text)
        self.assertIn(".github/workflows/ci.yml", development_text)
        self.assertIn("ops/test-lane-registry.json", development_text)
        self.assertIn("make help", development_text)
        for entrypoint in (
            "make test-fast",
            "make test-all",
            "make public-check",
            "make release-run-ready",
        ):
            with self.subTest(entrypoint=entrypoint):
                self.assertIn(entrypoint, development_text)
        for alias in (
            "make test-report-contract",
            "make report-contracts",
            "make report-contracts-core",
            "make report-contracts-all",
            "make report-contracts-extended",
            "make test-release-sealing",
        ):
            with self.subTest(alias=alias):
                self.assertNotIn(f"- `{alias}`", development_text)
                self.assertNotIn(alias, compatibility_names(registry, "documented_entrypoint"))

    def test_registry_documents_authority_boundary_for_lane_contract(self) -> None:
        registry = _test_lane_registry()

        self.assertEqual(
            documentation_authority(registry),
            ("README.md", "docs/development.md", "ops/README.md", ".github/workflows/ci.yml"),
        )
        self.assertEqual(
            documentation_out_of_scope(registry),
            ("ARCHITECTURE.md", ".github/workflows/release.yml"),
        )

    def test_architecture_public_surface_includes_github_workflows(self) -> None:
        architecture_text = Path("ARCHITECTURE.md").read_text(encoding="utf-8")

        self.assertIn("- `.github/`", architecture_text)
        self.assertIn("- `docs/`", architecture_text)

    def test_learning_readiness_signoff_make_targets_are_explicit_operator_ux(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("learning-readiness-signoff", _target_block(text, ".PHONY"))
        self.assertIn("learning-readiness-signoff-refresh", _target_block(text, ".PHONY"))
        self.assertIn("learning-readiness-signoff-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "learning-readiness-signoff-revalidation", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "learning-readiness-signoff-revalidation-check",
            _target_block(text, ".PHONY"),
        )
        self.assertIn(
            "learning-readiness-signoff-template", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_OUT ?= ops/reports/learning-readiness-signoff.json",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REUSE_FROM ?= $(LEARNING_READINESS_SIGNOFF_OUT)",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_OUT ?= ops/reports/learning-readiness-signoff-revalidation.json",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT ?= tmp/learning-readiness-signoff-revalidation-check.json",
            text,
        )
        self.assertIn("LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS ?= 7", text)
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND ?= make release-evidence-converge PYTHON=.venv/bin/python",
            text,
        )
        self.assertIn(
            "LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT ?= .venv clean release-builder",
            text,
        )
        self.assertIn("LEARNING_READINESS_SIGNOFF_ACCEPTED_BY ?=", text)
        self.assertIn("LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS ?= 14", text)
        block = _target_block(text, "learning-readiness-signoff")
        self.assertIn("ops.scripts.learning_readiness_signoff", block)
        self.assertIn(
            '--accepted-by "$(LEARNING_READINESS_SIGNOFF_ACCEPTED_BY)"', block
        )
        self.assertIn(
            '--expiry-days "$(LEARNING_READINESS_SIGNOFF_EXPIRY_DAYS)"', block
        )
        self.assertIn('--risk-owner "$(LEARNING_READINESS_SIGNOFF_RISK_OWNER)"', block)
        self.assertIn(
            '--revalidation-condition "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CONDITION)"',
            block,
        )
        self.assertIn(
            '--rollback-trigger "$(LEARNING_READINESS_SIGNOFF_ROLLBACK_TRIGGER)"', block
        )
        refresh_block = _target_block(text, "learning-readiness-signoff-refresh")
        self.assertIn("ops.scripts.learning_readiness_signoff_refresh", refresh_block)
        self.assertIn(
            '--reuse-from "$(LEARNING_READINESS_SIGNOFF_REUSE_FROM)"',
            refresh_block,
        )
        self.assertIn('--out "$(LEARNING_READINESS_SIGNOFF_OUT)"', refresh_block)
        self.assertNotIn("--accepted-by", refresh_block)
        self.assertIn(
            "tmp/learning-readiness-signoff-check-release-closeout-summary.json",
            _target_block(text, "learning-readiness-signoff-check"),
        )
        revalidation_block = _target_block(
            text, "learning-readiness-signoff-revalidation"
        )
        self.assertIn(
            "ops.scripts.learning_readiness_signoff_revalidation", revalidation_block
        )
        self.assertIn(
            '--window-days "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_WINDOW_DAYS)"',
            revalidation_block,
        )
        self.assertIn(
            '--required-command "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_COMMAND)"',
            revalidation_block,
        )
        self.assertIn(
            '--required-environment "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_ENVIRONMENT)"',
            revalidation_block,
        )
        self.assertIn(
            "--fail-on-due",
            _target_block(text, "learning-readiness-signoff-revalidation-check"),
        )
        self.assertIn(
            '--out "$(LEARNING_READINESS_SIGNOFF_REVALIDATION_CHECK_OUT)"',
            _target_block(text, "learning-readiness-signoff-revalidation-check"),
        )
        self.assertIn(
            "$(PYTHON) -m json.tool ops/templates/learning-readiness-signoff.json",
            _target_block(text, "learning-readiness-signoff-template"),
        )

    def test_learning_claim_bundle_delta_scoreboard_and_tmp_clean_alias_are_explicit(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("learning-claim-evidence-bundle", _target_block(text, ".PHONY"))
        self.assertIn(
            "learning-confirmed-legacy-reconstruction", _target_block(text, ".PHONY")
        )
        self.assertIn("public-check-summary", _target_block(text, ".PHONY"))
        self.assertIn(
            "PUBLIC_CHECK_SUMMARY_OUT ?= ops/reports/public-check-summary.json", text
        )
        self.assertIn(
            "LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT ?= ops/reports/learning-claim-evidence-bundle.json",
            text,
        )
        self.assertIn(
            "LEARNING_CONFIRMED_LEGACY_RECONSTRUCTION_OUT ?= ops/reports/learning-confirmed-legacy-reconstruction.json",
            text,
        )
        self.assertIn(
            "LEARNING_CONFIRMED_EVIDENCE_COHORT_OUT ?= ops/reports/learning-confirmed-evidence-cohort.json",
            text,
        )
        self.assertIn(
            "LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY ?= ops/policies/learning-claim-confirmed-improvement.json",
            text,
        )
        bundle_block = _target_block(text, "learning-claim-evidence-bundle")
        legacy_block = _target_block(text, "learning-confirmed-legacy-reconstruction")
        self.assertIn(
            "ops.scripts.learning_confirmed_legacy_reconstruction", legacy_block
        )
        self.assertIn(
            "ops/schemas/learning-confirmed-legacy-reconstruction.schema.json",
            legacy_block,
        )
        self.assertEqual(
            bundle_block.splitlines()[0],
            "learning-claim-evidence-bundle: learning-confirmed-legacy-reconstruction",
        )
        self.assertNotIn(
            "$(MAKE) learning-confirmed-legacy-reconstruction", bundle_block
        )
        self.assertIn("ops.scripts.learning_claim_evidence_bundle", bundle_block)
        self.assertIn(
            "ops/schemas/learning-claim-evidence-bundle.schema.json", bundle_block
        )
        cohort_block = _target_block(text, "learning-confirmed-evidence-cohort")
        self.assertEqual(
            cohort_block.splitlines()[0],
            "learning-confirmed-evidence-cohort: learning-claim-evidence-bundle",
        )
        self.assertIn("ops.scripts.learning_confirmed_evidence_cohort", cohort_block)
        self.assertIn(
            "ops/schemas/learning-confirmed-evidence-cohort.schema.json", cohort_block
        )
        self.assertIn(
            '--evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)"', cohort_block
        )
        self.assertIn(
            '--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"',
            cohort_block,
        )
        public_check_block = _target_block(text, "public-check-summary")
        self.assertIn("ops.scripts.public_check_summary", public_check_block)
        self.assertIn(
            "ops/schemas/public-check-summary.schema.json", public_check_block
        )
        self.assertIn("ops.scripts.canonical_artifact_promote", public_check_block)
        unlock_block = _target_block(text, "learning-claim-unlock-review")
        self.assertEqual(
            unlock_block.splitlines()[0],
            "learning-claim-unlock-review: learning-confirmed-evidence-cohort",
        )
        self.assertIn(
            '--evidence-bundle "$(LEARNING_CLAIM_EVIDENCE_BUNDLE_OUT)"', unlock_block
        )
        self.assertIn(
            '--confirmed-policy "$(LEARNING_CLAIM_CONFIRMED_IMPROVEMENT_POLICY)"',
            unlock_block,
        )
        self.assertIn("learning-delta-scoreboard", _target_block(text, ".PHONY"))
        self.assertIn("tmp-clean", _target_block(text, ".PHONY"))
        self.assertIn(
            "LEARNING_DELTA_SCOREBOARD_OUT ?= ops/reports/learning-delta-scoreboard.json",
            text,
        )
        self.assertIn(
            "LEARNING_CLAIM_ACTIVATION_REPORT_OUT ?= ops/reports/learning_claim_activation_report.json",
            text,
        )
        self.assertIn(
            "SESSION_SYNOPSIS_OUT ?= ops/reports/session-synopsis.json",
            text,
        )
        self.assertIn(
            "SELF_IMPROVEMENT_NEGATIVE_LESSONS_OUT ?= ops/reports/self-improvement-negative-lessons.json",
            text,
        )
        self.assertIn(
            "REMEDIATION_BACKLOG_OUT ?= ops/reports/remediation-backlog.json",
            text,
        )
        block = _target_block(text, "learning-delta-scoreboard")
        self.assertEqual(
            block.splitlines()[0],
            "learning-delta-scoreboard: learning-claim-unlock-review",
        )
        self.assertIn("ops.scripts.learning_delta_scoreboard", block)
        self.assertIn("ops/schemas/learning-delta-scoreboard.schema.json", block)
        activation_block = _target_block(text, "learning-claim-activation-report")
        self.assertEqual(
            activation_block.splitlines()[0],
            "learning-claim-activation-report: learning-delta-scoreboard",
        )
        self.assertIn("ops.scripts.learning_claim_activation_report", activation_block)
        self.assertIn(
            "ops/schemas/learning-claim-activation-report.schema.json",
            activation_block,
        )
        synopsis_block = _target_block(text, "session-synopsis")
        self.assertEqual(
            synopsis_block.splitlines()[0],
            "session-synopsis: learning-claim-activation-report",
        )
        self.assertIn("ops.scripts.session_synopsis", synopsis_block)
        self.assertIn("ops/schemas/session-synopsis.schema.json", synopsis_block)
        negative_lessons_block = _target_block(text, "self-improvement-negative-lessons")
        self.assertEqual(
            negative_lessons_block.splitlines()[0],
            "self-improvement-negative-lessons: session-synopsis",
        )
        self.assertIn("ops.scripts.self_improvement_negative_lessons", negative_lessons_block)
        self.assertIn(
            "ops/schemas/self-improvement-negative-lessons.schema.json",
            negative_lessons_block,
        )
        backlog_block = _target_block(text, "remediation-backlog")
        self.assertEqual(
            backlog_block.splitlines()[0],
            "remediation-backlog: self-improvement-negative-lessons session-synopsis",
        )
        self.assertIn("ops.scripts.remediation_backlog", backlog_block)
        self.assertIn("ops/schemas/remediation-backlog.schema.json", backlog_block)
        self.assertIn("tmp-clean: tmp-json-clean", text)
        tmp_json_clean_block = _target_block(text, "tmp-json-clean")
        self.assertIn("find tmp -mindepth 1 -delete", tmp_json_clean_block)
        self.assertNotIn("goal-worktree-guard.json", tmp_json_clean_block)

    def test_report_contract_targets_collect_schema_and_generated_artifact_checks(
        self,
    ) -> None:
        registry = _test_lane_registry()
        text = _makefile_text()
        core_block = _target_block(text, "test-report-contract-core")
        all_block = _target_block(text, "test-report-contract-all")
        expected_all_test_files = _report_contract_marked_test_files()

        self.assertIn("test-report-contract-core", _target_block(text, ".PHONY"))
        self.assertIn("test-report-contract-all", _target_block(text, ".PHONY"))
        self.assertIn("REPORT_CONTRACT_CORE_TESTS ?=", text)
        self.assertNotIn("REPORT_CONTRACT_EXTENDED_TESTS", text)
        self.assertIn("REPORT_CONTRACT_TESTS ?=", text)
        self.assertIn("REPORT_CONTRACT_TESTS ?= $(REPORT_CONTRACT_CORE_TESTS)", text)
        core_items = _assert_make_selector_variable_matches_pack(
            self,
            registry,
            text,
            variable="REPORT_CONTRACT_CORE_TESTS",
            pack_id="report_contract_core",
        )
        all_items = _makefile_assignment_items(text, "REPORT_CONTRACT_ALL_TESTS")
        self.assertEqual(
            all_items[:2],
            ("-m", '"$(PYTEST_REPORT_CONTRACT_MARK_EXPR)"'),
        )
        self.assertEqual(tuple(sorted(all_items[2:])), expected_all_test_files)
        core_files = {selector.split("::", 1)[0] for selector in core_items}
        self.assertTrue(core_files.issubset(set(all_items[2:])))
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            core_block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            all_block,
        )

    def test_report_contract_summary_uses_current_report_contract_lane(
        self,
    ) -> None:
        text = _makefile_text()
        core_block = _target_block(text, "test-report-contract-core")
        all_block = _target_block(text, "test-report-contract-all")

        self.assertIn("test-report-contract-core", _target_block(text, ".PHONY"))
        self.assertIn("test-report-contract-all", _target_block(text, ".PHONY"))
        phony_block = _target_block(text, ".PHONY")
        self.assertNotRegex(
            phony_block,
            r"(?<![A-Za-z0-9_.-])test-report-contract(?![A-Za-z0-9_.-])",
        )
        self.assertNotRegex(
            phony_block,
            r"(?<![A-Za-z0-9_.-])report-contract-summary(?![A-Za-z0-9_.-])",
        )
        self.assertIn(
            "REPORT_CONTRACT_SUMMARY_MARK_EXPR ?= $(PYTEST_REPORT_CONTRACT_MARK_EXPR)", text
        )
        self.assertIn(
            "REPORT_CONTRACT_SUMMARY_DESELECT_POLICY ?= ops/policies/report-contract-deselections.json",
            text,
        )
        self.assertIn(
            'REPORT_CONTRACT_SUMMARY_TESTS ?= -m "$(REPORT_CONTRACT_SUMMARY_MARK_EXPR)" $(REPORT_CONTRACT_TESTS)',
            text,
        )
        self.assertNotIn("--deselect=tests/test_", text)
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_SUMMARY_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            core_block,
        )
        self.assertIn(
            "$(PYTHON) -m pytest $(REPORT_CONTRACT_ALL_TESTS) $(PYTEST_REPORT_CONTRACT_FLAGS)",
            all_block,
        )
        self.assertNotIn("test-report-contract is a compatibility alias", text)
        self.assertNotIn("report-contract-summary:", text)

    def test_dev_install_creates_editable_environment(self) -> None:
        text = _makefile_text()

        block = _target_block(text, "dev-install")
        self.assertIn("DEV_LOCKED_REQUIREMENTS ?= tmp/locked-requirements.dev.txt", text)
        self.assertIn(
            "UV_EXPORT_DEV_REQUIREMENTS_FLAGS ?= --frozen --extra dev --format requirements-txt --no-hashes --no-emit-project",
            text,
        )
        self.assertIn(
            'UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) export $(UV_EXPORT_DEV_REQUIREMENTS_FLAGS) -o "$(DEV_LOCKED_REQUIREMENTS)"',
            block,
        )
        self.assertIn(
            'UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) pip install --python "$(VENV_PYTHON)" -r "$(DEV_LOCKED_REQUIREMENTS)"',
            block,
        )
        self.assertIn(
            'UV_DEFAULT_INDEX="$(UV_CANONICAL_INDEX_URL)" $(UV) pip install --python "$(VENV_PYTHON)" --no-deps -e .',
            block,
        )
        self.assertIn('"$(VENV_PYTHON)" -m pip install -e ".[dev]"', block)

    def test_legacy_root_requirements_files_are_retired(self) -> None:
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertIn("dev", pyproject["project"]["optional-dependencies"])
        self.assertFalse((REPO_ROOT / "requirements.txt").exists())
        self.assertFalse((REPO_ROOT / "requirements-dev.txt").exists())

    def test_bootstrap_preflight_target_writes_canonical_report_with_project_python(
        self,
    ) -> None:
        text = _makefile_text()

        self.assertIn("bootstrap-preflight", _target_block(text, ".PHONY"))
        self.assertIn(
            "BOOTSTRAP_PREFLIGHT_OUT ?= ops/reports/bootstrap-preflight-report.json",
            text,
        )
        self.assertIn("BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS ?= developer", text)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.bootstrap_preflight --vault "$(VAULT)" --dev --environment-class "$(BOOTSTRAP_PREFLIGHT_ENVIRONMENT_CLASS)" --out "$(BOOTSTRAP_PREFLIGHT_OUT)"',
            _target_block(text, "bootstrap-preflight"),
        )

    def test_refresh_generated_splits_core_outputs_from_observability_outputs(
        self,
    ) -> None:
        text = _makefile_text()

        _assert_refresh_generated_split_targets(self, text)
        _assert_observability_output_variables(self, text)
        _assert_script_surface_and_inventory_targets(self, text)
        _assert_workflow_dependency_planner_target(self, text)
        _assert_release_workflow_order_guard_target(self, text)
        _assert_function_budget_and_outcome_targets(self, text)
        _assert_external_report_action_matrix_target(self, text)

    def test_mechanism_run_linux_tmp_target_pins_native_temp_environment(self) -> None:
        text = _makefile_text()
        block = _target_block(text, "run-mechanism-experiment-linux-tmp")

        self.assertIn("MECHANISM_RUN_ARGS ?=", text)
        self.assertIn("run-mechanism-experiment-linux-tmp", _target_block(text, ".PHONY"))
        self.assertIn(
            'TMPDIR=/tmp TEMP=/tmp TMP=/tmp $(PYTHON) -m ops.scripts.run_mechanism_experiment --vault "$(VAULT)" $(MECHANISM_RUN_ARGS)',
            block,
        )

    def test_ruff_strict_preview_target_uses_full_scope_targets(self) -> None:
        text = _makefile_text()

        self.assertIn("RUFF_STRICT_PREVIEW_RULES ?= B,SIM,UP,I", text)
        self.assertIn("RUFF_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)", text)
        self.assertIn(
            '$(PYTHON) tools/ruff_strict_preview.py --vault "$(VAULT)" --targets "$(RUFF_STRICT_PREVIEW_TARGETS)" --select "$(RUFF_STRICT_PREVIEW_RULES)" --cache-dir "$(RUFF_CACHE_DIR)"',
            _target_block(text, "ruff-strict-preview"),
        )

    def test_strict_preview_audit_target_expands_all_public_runtime_targets(self) -> None:
        text = _makefile_text()

        self.assertIn("STRICT_PREVIEW_AUDIT_TARGETS ?= ops/scripts tests tools", text)
        self.assertIn("STRICT_PREVIEW_AUDIT_OUT ?= tmp/strict-preview-audit.json", text)
        block = _target_block(text, "strict-preview-audit")
        self.assertIn("tools/strict_preview_audit.py", block)
        self.assertIn('--targets "$(STRICT_PREVIEW_AUDIT_TARGETS)"', block)
        self.assertIn('--ruff-select "$(RUFF_STRICT_PREVIEW_RULES)"', block)
        self.assertIn('--ruff-cache-dir "$(RUFF_CACHE_DIR)"', block)
        self.assertIn('--mypy-flags "$(MYPY_CACHE_FLAGS) $(MYPY_STRICT_PREVIEW_FLAGS)"', block)
        self.assertNotIn("--fail-on-attention", block)

    def test_mypy_strict_preview_target_uses_full_scope_targets(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "MYPY_STRICT_PREVIEW_FLAGS ?= --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs",
            text,
        )
        self.assertIn(
            "MYPY_STRICT_PREVIEW_TARGETS ?= $(STRICT_PREVIEW_AUDIT_TARGETS)",
            text,
        )
        self.assertIn(
            "$(PYTHON) -m mypy --config-file pyproject.toml $(MYPY_CACHE_FLAGS) $(MYPY_STRICT_PREVIEW_FLAGS) $(MYPY_STRICT_PREVIEW_TARGETS)",
            _target_block(text, "mypy-strict-preview"),
        )

    def test_codebase_memory_mcp_targets_are_optional_public_export_sidecar(self) -> None:
        text = _makefile_text()
        phony = _target_block(text, ".PHONY")
        for target in (
            "cbm-require-bin",
            "cbm-export-public",
            "cbm-index-public",
            "cbm-list-projects-public",
            "cbm-schema-public",
            "cbm-architecture-public",
            "cbm-reset-local",
        ):
            with self.subTest(target=target):
                self.assertIn(target, phony)

        for assignment in (
            "CBM_BIN ?= codebase-memory-mcp",
            "CBM_CACHE_ROOT ?= $(if $(XDG_CACHE_HOME),$(XDG_CACHE_HOME),$(HOME)/.cache)",
            "CBM_PUBLIC_OUT ?= $(CBM_CACHE_ROOT)/llmwiki/codebase-memory-mcp/public-surface",
            "CBM_CACHE_DIR ?= $(CBM_CACHE_ROOT)/codebase-memory-mcp/llmwiki-public",
            "CBM_IGNORE_TEMPLATE ?= ops/templates/codebase-memory-mcp.cbmignore",
            "CBM_PROJECT_NAME ?= $(subst /,-,$(patsubst /%,%,$(CBM_PUBLIC_OUT)))",
        ):
            self.assertIn(assignment, text)

        export_block = _target_block(text, "cbm-export-public")
        for token in (
            "ops.scripts.cbm_public_export",
            '--vault "$(VAULT)"',
            '--out "$(CBM_PUBLIC_OUT)"',
            '--cbmignore-template "$(CBM_IGNORE_TEMPLATE)"',
        ):
            self.assertIn(token, export_block)

        self.assertEqual(
            _target_block(text, "cbm-index-public").splitlines()[0],
            "cbm-index-public: cbm-require-bin cbm-export-public",
        )
        self.assertIn(
            '\'{"project":"$(CBM_PROJECT_NAME)"}\'',
            _target_block(text, "cbm-schema-public"),
        )
        self.assertIn(
            '\'{"project":"$(CBM_PROJECT_NAME)"}\'',
            _target_block(text, "cbm-architecture-public"),
        )
        for release_gate in ("check", "check-finalized", "release-check", "release-source-ready"):
            with self.subTest(release_gate=release_gate):
                self.assertNotIn("cbm-", _target_block(text, release_gate))

    def test_codebase_memory_mcp_onboarding_is_documented_in_public_entrypoints(self) -> None:
        agents_text = Path("AGENTS.md").read_text(encoding="utf-8")
        readme_text = README.read_text(encoding="utf-8")
        ops_readme_text = Path("ops/README.md").read_text(encoding="utf-8")
        cbm_docs_text = DOCS_CBM.read_text(encoding="utf-8")

        for token in (
            "Optional codebase-memory-mcp sidecar",
            "make cbm-index-public",
            "cbm-schema-public",
            "cbm-architecture-public",
            "make cbm-index-public`로 재색인",
            "`CBM_PUBLIC_OUT` cache 경로",
            "candidate link, not proof",
            "assistant-specific workflow requirement",
        ):
            with self.subTest(surface="AGENTS.md", token=token):
                self.assertIn(token, agents_text)

        for token in (
            "code/ops 구조 탐색",
            "make cbm-index-public",
            "make cbm-schema-public",
            "make cbm-architecture-public",
            "graph-first/file-verified",
            "기존 `rg` / file read workflow",
        ):
            with self.subTest(surface="README.md", token=token):
                self.assertIn(token, readme_text)

        for token in (
            "Optional codebase-memory-mcp quickstart",
            "make cbm-index-public",
            "make cbm-schema-public",
            "make cbm-architecture-public",
            "graph-first/file-verified",
        ):
            with self.subTest(surface="ops/README.md", token=token):
                self.assertIn(token, ops_readme_text)

        for token in (
            "CBM_BIN=/path/to/codebase-memory-mcp",
            "not a dependency",
            "assistant-specific",
            "CBM-EXPORT-MANIFEST.json",
            "ops/reports/",
            "Re-run `make cbm-index-public` after repo edits",
            "cache export paths",
            "Map them back to the same relative path in the repo",
            "candidate links, not proof",
        ):
            with self.subTest(surface="docs/codebase-memory-mcp.md", token=token):
                self.assertIn(token, cbm_docs_text)

    def test_raw_intake_and_review_classification_targets_exist(self) -> None:
        text = _makefile_text()

        self.assertIn(
            "RAW_INTAKE_ABSORPTION_MATRIX ?= runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_ROUTE_PROPOSAL_OUT ?= tmp/raw-intake-route-proposal-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_SOURCE_QUALITY_OUT ?= tmp/raw-intake-source-quality-report.json",
            text,
        )
        self.assertIn(
            "RAW_INTAKE_ABSORPTION_CLOSEOUT_OUT ?= tmp/raw-intake-absorption-closeout-report.json",
            text,
        )
        self.assertIn(
            "WIKI_LINT_REVIEW_CLASSIFICATION_OUT ?= tmp/wiki-lint-review-classification.json",
            text,
        )
        self.assertIn("raw-intake-route-proposal", _target_block(text, ".PHONY"))
        self.assertIn("raw-intake-source-quality", _target_block(text, ".PHONY"))
        self.assertIn("raw-intake-absorption-closeout", _target_block(text, ".PHONY"))
        self.assertIn(
            "wiki-lint-review-classification", _target_block(text, ".PHONY")
        )
        self.assertIn(
            "ops.scripts.raw_intake_route_proposal",
            _target_block(text, "raw-intake-route-proposal"),
        )
        self.assertIn(
            "ops.scripts.raw_intake_source_quality",
            _target_block(text, "raw-intake-source-quality"),
        )
        self.assertIn(
            "--mode absorption_closeout --fail-on-fail",
            _target_block(text, "raw-intake-absorption-closeout"),
        )
        self.assertIn(
            "ops.scripts.wiki_lint_review_classification",
            _target_block(text, "wiki-lint-review-classification"),
        )

if __name__ == "__main__":  # pragma: no cover
    unittest.main()
