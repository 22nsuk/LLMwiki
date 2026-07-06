from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.release.release_workflow_order_guard import (
    build_report,
    check_report,
    write_report,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public

SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-workflow-order-guard.schema.json"
SPEC_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "release-workflow-order-guard-spec.schema.json"
SPEC_PATH = REPO_ROOT / "ops" / "policies" / "release-workflow-order-guard.json"
CRITICAL_GUARD_ARRAYS = (
    "recipe_command_roles",
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


def _role_overrides() -> dict[str, str]:
    spec = _workflow_order_spec()
    return {
        str(override["role"]): f"{override['target']} {override['raw_args_contains']}"
        for override in spec["role_overrides"]
        if isinstance(override, dict)
    }


def _recipe_command_roles() -> dict[str, dict[str, object]]:
    spec = _workflow_order_spec()
    return {
        str(command_role["role"]): {
            "target": str(command_role["target"]),
            "raw_line_contains": str(command_role["raw_line_contains"]),
            "argv_equals": [
                str(arg) for arg in command_role.get("argv_equals", [])
            ],
        }
        for command_role in spec["recipe_command_roles"]
        if isinstance(command_role, dict)
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
    override = _role_overrides().get(role)
    if override is not None:
        return f"\t$(MAKE) {override}\n"
    command_role = _recipe_command_roles().get(role)
    if command_role is not None:
        command_lines = {
            "release-post-commit-finalizer-snapshot": (
                '$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" '
                '--mode snapshot --out "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"'
            ),
            "release-post-commit-finalizer-verify": (
                '$(PYTHON) -m ops.scripts.release.release_post_commit_finalizer --vault "$(VAULT)" '
                '--mode verify --previous "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)" '
                '--out "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)" --fail-on-attention'
            ),
        }
        line = command_lines.get(role)
        if line is None:
            raise AssertionError(f"missing fixture recipe line for command role: {role}")
        if str(command_role["raw_line_contains"]) not in line:
            raise AssertionError(f"fixture line does not match command role: {role}")
        return f"\t{line}\n"
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


def _repetition_forbidden_targets(check_id: str) -> set[str]:
    for entry in _workflow_order_spec()["repetition_budgets"]:
        if isinstance(entry, dict) and entry.get("id") == check_id:
            return {str(target) for target in entry.get("forbidden_targets", [])}
    raise AssertionError(f"missing repetition budget: {check_id}")


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
RELEASE_CONVERGE_ALL_LINES = _make_recipe(
    "release-converge",
    "sync-public-policy",
    "public-check-all",
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
RELEASE_WORKFLOW_ORDER_PHONY_TARGETS = (
    "check",
    "check-finalized",
    "release-evidence-converge",
    "release-evidence-closeout",
    "release-finality-resettle",
    "release-terminal-finality",
    "release-authority-post-ready-finality",
    "release-authority-settle",
    "release-authority-sealed-preflight",
    "release-finality-resettle-current-or-refresh",
    "release-auto-promotion-goal-run-id-verified-check",
    "release-auto-promotion-preflight",
    "release-run-ready",
    "release-auto-promotion-preseal",
    "release-sealed-run-ready",
    "release-auto-promotion-ready",
    "release-authority-archive-candidate-gate",
    "release-authority-post-ready-finality-current-or-refresh",
    "release-converge-preflight",
    "release-source-ready",
    "release-source-ready-snapshot",
    "release-source-ready-prepare",
    "release-source-ready-commit",
    "release-post-commit-finalize",
    "release-source-ready-post-verify",
    "release-source-ready-status",
    "release-converge-all-surfaces",
    "release-converge",
    "release-converge-post",
    "script-output-surfaces-check",
    "release-smoke-fast-current-check",
    "test-execution-summary-current-check",
    "test-execution-summary-full-current-check",
    "sync-public-policy-check",
    "public-check-summary-current-check",
    "artifact-freshness-check",
    "release-check-all-surfaces",
    "sync-public-policy",
    "public-check-summary",
    "public-check-all",
    "goal-runtime-local-evidence-refresh",
    "auto-improve-readiness-worktree-guard",
    "remediation-backlog",
    "generated-artifact-converge",
    "generated-artifact-script-output",
    "generated-artifact-finality-suffix",
    "generated-artifact-index",
    "generated-artifact-index-body",
    "artifact-freshness",
    "release-closeout-summary",
    "release-evidence-dashboard-report",
    "release-lane-summary",
    "release-clean-blocker-ledger",
    "auto-improve-readiness-report-body",
    "release-closeout-summary-report",
    "script-output-surfaces",
    "external-report-action-matrix",
    "release-closeout-post-check-finalizer-dry-run",
    "release-closeout-fixed-point",
    "release-closeout-batch-manifest-promote",
    "release-closeout-batch-manifest-replay-verify",
    "artifact-freshness-refresh-check",
    "operator-release-summary",
    "tmp-json-clean",
    "release-closeout-finality-verify",
)
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
    "\t$(MAKE) release-closeout-fixed-point\n"
    "\t$(MAKE) release-closeout-post-check-finalizer-dry-run RELEASE_CLOSEOUT_POST_CHECK_FINALIZER_FLAGS=--fail-on-refresh-required\n"
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
    "release-auto-promotion-preflight:\n"
    "\t@true\n"
    "release-run-ready:\n"
    "\t@true\n"
    "release-auto-promotion-preseal:\n"
    "\t@true\n"
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
    "test-execution-summary-current-check:\n"
    "\t@true\n"
    "test-execution-summary-full-current-check:\n"
    "\t@true\n"
    "sync-public-policy-check:\n"
    "\t@true\n"
    "public-check-summary-current-check:\n"
    "\t@true\n"
    "artifact-freshness-check:\n"
    "\t@true\n"
    "goal-runtime-local-evidence-refresh:\n"
    "\t@true\n"
    "auto-improve-readiness-worktree-guard:\n"
    "\t@true\n"
    "remediation-backlog:\n"
    "\t@true\n"
    "generated-artifact-converge:\n"
    "\t$(MAKE) generated-artifact-finality-suffix\n"
    "generated-artifact-script-output:\n"
    "\t$(MAKE) script-output-surfaces\n"
    "generated-artifact-finality-suffix:\n"
    "\t$(MAKE) artifact-freshness\n"
    "\t$(MAKE) external-report-action-matrix\n"
    "\t$(MAKE) generated-artifact-index\n"
    "\t$(MAKE) artifact-freshness\n"
    "\t$(MAKE) external-report-action-matrix\n"
    "\t$(MAKE) generated-artifact-index-body\n"
    "\t$(MAKE) artifact-freshness\n"
    "script-output-surfaces:\n"
    "\t@true\n"
    "external-report-action-matrix:\n"
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
        release_post_commit_finalize_lines=RELEASE_POST_COMMIT_FINALIZE_LINES,
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
                "expensive_prerequisites_once": ["release-risk-taxonomy-matrix"],
            },
            {
                "name": "artifact-freshness",
                "target": "artifact-freshness",
                "produces": ["ops/reports/artifact-freshness-report.json"],
                "depends_on": ["generated-artifact-index-body"],
                "expensive_prerequisites_once": [],
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
    ) -> None:
        self.vault.joinpath("Makefile").write_text(
            _workflow_order_guard_makefile_text(
                misorder_check_finalized=misorder_check_finalized,
                misorder_release_source_ready=misorder_release_source_ready,
                misorder_release_source_ready_post_verify=misorder_release_source_ready_post_verify,
                misorder_release_converge_preflight=misorder_release_converge_preflight,
            ),
            encoding="utf-8",
        )

    def test_spec_keeps_critical_release_safety_roles(self) -> None:
        spec = _workflow_order_spec()
        role_overrides = {
            str(entry["role"]): str(entry["target"])
            for entry in spec["role_overrides"]
            if isinstance(entry, dict)
        }

        self.assertEqual(
            role_overrides["release-closeout-post-check-finalizer-strict-dry-run"],
            "release-closeout-post-check-finalizer-dry-run",
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
        self.assertEqual(
            _recipe_command_roles()["release-post-commit-finalizer-verify"]["target"],
            "release-post-commit-finalize",
        )
        self.assertEqual(
            _recipe_command_roles()["release-post-commit-finalizer-snapshot"]["target"],
            "release-post-commit-finalize",
        )
        self.assertIn(
            '--out "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
            str(
                _recipe_command_roles()["release-post-commit-finalizer-snapshot"][
                    "raw_line_contains"
                ]
            ),
        )
        self.assertIn(
            '--previous "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
            str(
                _recipe_command_roles()["release-post-commit-finalizer-verify"][
                    "raw_line_contains"
                ]
            ),
        )
        self.assertEqual(
            _recipe_command_roles()["release-post-commit-finalizer-snapshot"][
                "argv_equals"
            ],
            [
                "$(PYTHON)",
                "-m",
                "ops.scripts.release.release_post_commit_finalizer",
                "--vault",
                "$(VAULT)",
                "--mode",
                "snapshot",
                "--out",
                "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)",
            ],
        )
        self.assertEqual(
            _recipe_command_roles()["release-post-commit-finalizer-verify"][
                "argv_equals"
            ],
            [
                "$(PYTHON)",
                "-m",
                "ops.scripts.release.release_post_commit_finalizer",
                "--vault",
                "$(VAULT)",
                "--mode",
                "verify",
                "--previous",
                "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)",
                "--out",
                "$(RELEASE_POST_COMMIT_FINALIZATION_OUT)",
                "--fail-on-attention",
            ],
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
        self.assertIn(
            "raw-recipe-command",
            _repetition_forbidden_targets(
                "release_post_commit_finalizer_repetition_budget"
            ),
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

    def test_guard_rejects_spec_with_empty_critical_guard_array(self) -> None:
        spec = _cloned_workflow_order_spec()
        spec["terminal_checks"] = []
        self._write_workflow_order_spec(spec)

        with self.assertRaisesRegex(
            ValueError,
            r"invalid release workflow order spec.*\$\.terminal_checks: expected at least 1 item",
        ):
            build_report(self.vault, context=fixed_context())

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
        post_commit_budget = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        self.assertEqual(post_commit_budget["status"], "pass")
        preflight_check = next(item for item in report["checks"] if item["id"] == "release_converge_preflight_sequence")
        self.assertEqual(preflight_check["status"], "pass")
        self.assertIn("release-finality-resettle", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-terminal-finality", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-post-commit-finalize", {item["target"] for item in report["target_recipes"]})
        self.assertIn("release-converge-preflight", {item["target"] for item in report["target_recipes"]})
        self.assertTrue(write_report(self.vault, report).exists())

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
        self.assertEqual(
            check["violations"][0]["reason"],
            "finality_verify_must_be_terminal",
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

    def test_guard_fails_when_post_commit_finalizer_reintroduces_full_refresh(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) test-execution-summary-full-current-check\n",
                "\t$(MAKE) test-execution-summary-full-current-or-refresh\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][0]["reason"],
            "forbidden_post_commit_target",
        )

    def test_guard_fails_when_post_commit_finalizer_repeats_writer_cluster(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) artifact-freshness-check\n",
                "\t$(MAKE) artifact-freshness-check\n"
                "\t$(MAKE) artifact-freshness-check\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["violations"][0]["target"], "artifact-freshness-check")
        self.assertEqual(
            check["violations"][0]["reason"],
            "unexpected_repeated_post_commit_target",
        )

    def test_guard_fails_when_post_commit_snapshot_runs_after_currentness_checks(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
        first_currentness_line = "\t$(MAKE) script-output-surfaces-check\n"
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                snapshot_line + first_currentness_line,
                first_currentness_line + snapshot_line,
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][0]["expected_role"],
            "script-output-surfaces-check",
        )

    def test_guard_fails_when_post_commit_snapshot_is_not_first_invocation(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n",
                "release-post-commit-finalize:\n"
                "\t$(MAKE) release-check-all-surfaces\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            check["violations"],
        )

    def test_guard_fails_when_raw_command_runs_before_post_commit_snapshot(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n",
                "release-post-commit-finalize:\n"
                '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
                '--stored "ops/script-output-surfaces.json" --check\n',
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"][0]["role"], "raw-recipe-command")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            check["violations"],
        )

    def test_guard_fails_when_post_commit_prerequisite_runs_raw_command(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8")
            .replace(
                "release-post-commit-finalize:\n",
                "release-post-commit-finalize: release-post-commit-prerequisite\n",
            )
            .replace(
                "release-source-ready-status:\n",
                "release-post-commit-prerequisite:\n"
                '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
                '--stored "ops/script-output-surfaces.json" --check\n'
                "release-source-ready-status:\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        sequence_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"][0]["role"], "raw-recipe-command")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            sequence_check["violations"],
        )
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_fails_when_post_commit_snapshot_writes_noncanonical_path(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                snapshot_line,
                snapshot_line.replace(
                    '"$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
                    '"tmp/wrong-release-post-commit-finalization.snapshot.json"',
                ),
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "missing_or_out_of_order",
            },
            check["violations"],
        )

    def test_guard_fails_when_post_commit_snapshot_output_is_overridden(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                snapshot_line,
                snapshot_line.replace(
                    "\n",
                    ' --out "tmp/wrong-release-post-commit-finalization.snapshot.json"\n',
                ),
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"][0]["role"], "raw-recipe-command")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            check["violations"],
        )

    def test_guard_fails_when_raw_command_runs_after_post_commit_snapshot(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                snapshot_line,
                snapshot_line
                + '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
                '--stored "ops/script-output-surfaces.json" --check\n',
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(budget_check["status"], "fail")
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_fails_when_raw_fragment_shares_post_commit_make_invocation_line(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check; "
                'rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"\n',
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            [item["role"] for item in post_commit_recipe["invocations"][:3]],
            [
                "release-post-commit-finalizer-snapshot",
                "script-output-surfaces-check",
                "raw-recipe-command",
            ],
        )
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_fails_when_inline_post_commit_recipe_runs_before_snapshot(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n",
                'release-post-commit-finalize: ; rm "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"\n',
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        sequence_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"][0]["role"], "raw-recipe-command")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            sequence_check["violations"],
        )
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_models_duplicate_post_commit_recipe_override(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
        post_commit_tail = _make_recipe(
            *_sequence_roles("release_post_commit_finalizer_sequence")[1:]
        )
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n" + RELEASE_POST_COMMIT_FINALIZE_LINES,
                "release-post-commit-finalize:\n"
                f"{snapshot_line}"
                "release-post-commit-finalize:\n"
                f"{post_commit_tail}",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            post_commit_recipe["invocations"][0]["role"],
            "script-output-surfaces-check",
        )
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            check["violations"],
        )

    def test_guard_models_empty_inline_post_commit_recipe_override(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n" + RELEASE_POST_COMMIT_FINALIZE_LINES,
                "release-post-commit-finalize:\n"
                f"{RELEASE_POST_COMMIT_FINALIZE_LINES}"
                "release-post-commit-finalize: ;\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"], [])
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "missing_or_out_of_order",
            },
            check["violations"],
        )

    def test_guard_fails_when_make_invocation_redirects_snapshot_output(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "\t$(MAKE) script-output-surfaces-check\n",
                "\t$(MAKE) script-output-surfaces-check "
                '> "$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"\n',
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            [item["role"] for item in post_commit_recipe["invocations"][:3]],
            [
                "release-post-commit-finalizer-snapshot",
                "script-output-surfaces-check",
                "raw-recipe-command",
            ],
        )
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_rejects_make_target_spoofing_command_only_snapshot_role(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        snapshot_line = _recipe_line_for_role("release-post-commit-finalizer-snapshot")
        makefile.write_text(
            makefile.read_text(encoding="utf-8")
            .replace(
                snapshot_line,
                "\t$(MAKE) release-post-commit-finalizer-snapshot\n",
            )
            .replace(
                "release-source-ready-status:\n",
                "release-post-commit-finalizer-snapshot:\n"
                "\t@true\n"
                "release-source-ready-status:\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        sequence_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"][0]["role"], "raw-recipe-command")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            sequence_check["violations"],
        )
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_preserves_double_colon_post_commit_recipe_order(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n" + RELEASE_POST_COMMIT_FINALIZE_LINES,
                "release-post-commit-finalize::\n"
                '\t$(PYTHON) -m ops.scripts.script_output_surfaces --vault "$(VAULT)" '
                '--stored "ops/script-output-surfaces.json" --check\n'
                "release-post-commit-finalize::\n"
                f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        sequence_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        budget_check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        post_commit_recipe = next(
            item
            for item in report["target_recipes"]
            if item["target"] == "release-post-commit-finalize"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(post_commit_recipe["invocations"][0]["role"], "raw-recipe-command")
        self.assertEqual(
            post_commit_recipe["invocations"][1]["role"],
            "release-post-commit-finalizer-snapshot",
        )
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-snapshot",
                "reason": "snapshot_must_start_post_commit_finalize",
            },
            sequence_check["violations"],
        )
        self.assertIn(
            {
                "target": "raw-recipe-command",
                "count": 1,
                "reason": "forbidden_post_commit_target",
            },
            budget_check["violations"],
        )

    def test_guard_fails_when_post_commit_mixes_single_and_double_colon_rules(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n" + RELEASE_POST_COMMIT_FINALIZE_LINES,
                "release-post-commit-finalize:\n"
                f"{RELEASE_POST_COMMIT_FINALIZE_LINES}"
                "release-post-commit-finalize::\n"
                f"{RELEASE_POST_COMMIT_FINALIZE_LINES}",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item for item in report["checks"] if item["id"] == "make_target_rule_kind_conflicts"
        )
        post_commit_sequence = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(post_commit_sequence["status"], "pass")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            {
                "target": "release-post-commit-finalize",
                "reason": "mixed_single_and_double_colon_rules",
            },
            check["violations"],
        )

    def test_guard_fails_when_post_commit_verify_runs_before_currentness_checks(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        freshness_line = "\t$(MAKE) artifact-freshness-check\n"
        verify_line = _recipe_line_for_role("release-post-commit-finalizer-verify")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                freshness_line + verify_line,
                verify_line + freshness_line,
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][0]["expected_role"],
            "release-post-commit-finalizer-verify",
        )

    def test_guard_fails_when_post_commit_verify_reads_noncanonical_snapshot(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        verify_line = _recipe_line_for_role("release-post-commit-finalizer-verify")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                verify_line,
                verify_line.replace(
                    '"$(RELEASE_POST_COMMIT_FINALIZATION_SNAPSHOT_OUT)"',
                    '"tmp/wrong-release-post-commit-finalization.snapshot.json"',
                ),
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_sequence"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertIn(
            {
                "expected_role": "release-post-commit-finalizer-verify",
                "reason": "missing_or_out_of_order",
            },
            check["violations"],
        )

    def test_guard_fails_when_post_commit_finalizer_calls_authority_cleanup(
        self,
    ) -> None:
        makefile = self.vault.joinpath("Makefile")
        makefile.write_text(
            makefile.read_text(encoding="utf-8").replace(
                "release-post-commit-finalize:\n",
                "release-post-commit-finalize:\n"
                "\t$(MAKE) release-auto-promotion-ready-invalidate\n",
            ),
            encoding="utf-8",
        )

        report = build_report(self.vault, context=fixed_context())

        check = next(
            item
            for item in report["checks"]
            if item["id"] == "release_post_commit_finalizer_repetition_budget"
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(check["status"], "fail")
        self.assertEqual(
            check["violations"][0]["reason"],
            "forbidden_post_commit_target",
        )

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


if __name__ == "__main__":
    unittest.main()
