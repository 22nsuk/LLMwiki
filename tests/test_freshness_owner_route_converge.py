from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.release.freshness_owner_route_converge import build_plan, run_converge


def _report(
    routes: list[dict[str, object]],
    classification: str = "source_identity_only",
    currentness_status: str = "current",
) -> dict[str, object]:
    return {
        "status": "attention" if classification != "clean" else "pass",
        "currentness": {
            "status": currentness_status,
            "checked_at": "2026-06-17T00:00:00Z",
        },
        "stale_routing": {
            "classification": classification,
            "source_identity_owner_routes": routes,
        }
    }


def _current_report(vault: Path, routes: list[dict[str, object]], **kwargs: object) -> dict[str, object]:
    payload = _report(routes, **kwargs)
    payload["source_tree_fingerprint"] = release_source_tree_fingerprint(vault)
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class FreshnessOwnerRouteConvergeTests(unittest.TestCase):
    def test_build_plan_selects_owner_targets_and_defers_generic_suffix_targets(self) -> None:
        plan = build_plan(
            _report(
                [
                    {
                        "route_id": "ops_reports_maintainability",
                        "recommended_targets": [
                            "function-budget-refactor-proposals",
                            "lint-uplift-plan",
                        ],
                    },
                    {
                        "route_id": "ops_reports_release_finality",
                        "recommended_targets": [
                            "release-finality-resettle-current-or-refresh"
                        ],
                    },
                    {
                        "route_id": "ops_reports_source_identity_resettle",
                        "recommended_targets": ["freshness-source-identity-converge"],
                    },
                    {
                        "route_id": "ops_reports_promotion_decision_trends",
                        "recommended_targets": ["promotion-decision-trends"],
                    },
                ]
            )
        )

        self.assertEqual(plan["status"], "owner_targets_available")
        self.assertEqual(
            plan["selected_targets"],
            [
                "function-budget-refactor-proposals",
                "lint-uplift-plan",
                "promotion-decision-trends",
            ],
        )
        skipped_reasons = {item["reason"] for item in plan["skipped_targets"]}
        self.assertIn("deferred_to_terminal_suffix", skipped_reasons)
        self.assertIn("generic_source_identity_recursion", skipped_reasons)

    def test_build_plan_blocks_unallowed_owner_route_targets(self) -> None:
        plan = build_plan(
            _report(
                [
                    {
                        "route_id": "external_reports_reference_manifest",
                        "recommended_targets": ["release-run-ready"],
                    },
                ]
            )
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["selected_targets"], [])
        self.assertEqual(
            plan["blocked_targets"][0]["reason"],
            "owner_route_target_not_allowed",
        )

    def test_build_plan_materializes_goal_runtime_targets_when_run_id_is_bound(self) -> None:
        plan = build_plan(
            _report(
                [
                    {
                        "route_id": "ops_reports_goal_runtime",
                        "recommended_targets": [
                            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-status-finalize",
                            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate",
                        ],
                    }
                ]
            ),
            env={"GOAL_RUN_ID": "completed-run-1"},
        )

        self.assertEqual(plan["status"], "owner_targets_available")
        self.assertEqual(
            plan["selected_targets"],
            ["goal-runtime-status-finalize", "goal-runtime-certificate"],
        )
        self.assertEqual(plan["blocked_targets"], [])

    def test_build_plan_blocks_unresolved_goal_runtime_placeholders(self) -> None:
        plan = build_plan(
            _report(
                [
                    {
                        "route_id": "ops_reports_goal_runtime",
                        "recommended_targets": [
                            "GOAL_RUN_ID=<completed-run-id> make goal-runtime-certificate"
                        ],
                    }
                ]
            ),
            env={},
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["selected_targets"], [])
        self.assertEqual(plan["blocked_targets"][0]["reason"], "goal_run_id_required")

    def test_build_plan_noops_when_freshness_is_clean(self) -> None:
        plan = build_plan(_report([], classification="clean"))

        self.assertEqual(plan["status"], "clean")
        self.assertEqual(plan["selected_targets"], [])
        self.assertEqual(
            plan["terminal_suffix_targets"][-1],
            "release-finality-resettle-current-or-refresh",
        )

    def test_run_converge_reuses_current_clean_report_without_initial_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            report_path = vault / "ops/reports/artifact-freshness-report.json"
            plan_path = vault / "tmp/plan.json"
            marker_path = vault / "make-called.txt"
            make_path = vault / "fake-make"
            make_path.write_text(
                f"#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> {marker_path}\n",
                encoding="utf-8",
            )
            os.chmod(make_path, 0o755)
            _write_json(report_path, _current_report(vault, [], classification="clean"))

            code = run_converge(
                vault=vault,
                report_path="ops/reports/artifact-freshness-report.json",
                plan_out="tmp/plan.json",
                make_bin=make_path.as_posix(),
                python="python",
                env={},
                dry_run=False,
            )

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertFalse(marker_path.exists())
            self.assertEqual(plan["status"], "clean")
            self.assertEqual(plan["initial_refresh"]["status"], "skipped")
            self.assertEqual(plan["initial_refresh"]["reason"], "existing_report_current")

    def test_run_converge_refreshes_when_current_report_has_stale_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            report_path = vault / "ops/reports/artifact-freshness-report.json"
            plan_path = vault / "tmp/plan.json"
            command_log_path = vault / "make-targets.txt"
            make_path = vault / "fake-make"
            make_path.write_text(
                f"#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> {command_log_path}\n",
                encoding="utf-8",
            )
            os.chmod(make_path, 0o755)
            payload = _current_report(vault, [], classification="clean")
            payload["source_tree_fingerprint"] = "stale"
            _write_json(report_path, payload)

            code = run_converge(
                vault=vault,
                report_path="ops/reports/artifact-freshness-report.json",
                plan_out="tmp/plan.json",
                make_bin=make_path.as_posix(),
                python="python",
                env={},
                dry_run=False,
            )

            command_log = command_log_path.read_text(encoding="utf-8").splitlines()
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertEqual(command_log, ["artifact-freshness-refresh-check"])
            self.assertEqual(plan["status"], "source_report_not_current")

    def test_run_converge_runs_owner_targets_before_terminal_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            report_path = vault / "ops/reports/artifact-freshness-report.json"
            plan_path = vault / "tmp/plan.json"
            command_log_path = vault / "make-targets.txt"
            make_path = vault / "fake-make"
            make_path.write_text(
                f"#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> {command_log_path}\n",
                encoding="utf-8",
            )
            os.chmod(make_path, 0o755)
            _write_json(
                report_path,
                _current_report(
                    vault,
                    [
                        {
                            "route_id": "external_reports_reference_manifest",
                            "recommended_targets": [
                                "external-report-reference-manifest-settle"
                            ],
                        }
                    ],
                ),
            )

            code = run_converge(
                vault=vault,
                report_path="ops/reports/artifact-freshness-report.json",
                plan_out="tmp/plan.json",
                make_bin=make_path.as_posix(),
                python="python",
                env={},
                dry_run=False,
            )

            command_log = command_log_path.read_text(encoding="utf-8").splitlines()
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(
                command_log,
                [
                    "external-report-reference-manifest-settle",
                    "artifact-freshness-refresh-check",
                    "generated-artifact-index",
                    "artifact-freshness-refresh-check",
                    "release-finality-resettle-current-or-refresh",
                ],
            )
            self.assertEqual(plan["status"], "pass")
            self.assertEqual(plan["initial_refresh"]["status"], "skipped")
            command_json = json.dumps(
                [result["command"] for result in plan["command_results"]]
            )
            self.assertNotIn(vault.as_posix(), command_json)
            self.assertIn("VAULT=.", command_json)

    def test_run_converge_stops_when_refreshed_report_is_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            report_path = vault / "ops/reports/artifact-freshness-report.json"
            plan_path = vault / "tmp/plan.json"
            command_log_path = vault / "make-targets.txt"
            make_path = vault / "fake-make"
            make_path.write_text(
                f"#!/usr/bin/env bash\nprintf '%s\\n' \"$1\" >> {command_log_path}\n",
                encoding="utf-8",
            )
            os.chmod(make_path, 0o755)
            _write_json(
                report_path,
                _report(
                    [
                        {
                            "route_id": "external_reports_reference_manifest",
                            "recommended_targets": [
                                "external-report-reference-manifest-settle"
                            ],
                        }
                    ],
                    currentness_status="stale",
                ),
            )

            code = run_converge(
                vault=vault,
                report_path="ops/reports/artifact-freshness-report.json",
                plan_out="tmp/plan.json",
                make_bin=make_path.as_posix(),
                python="python",
                env={},
                dry_run=False,
            )

            command_log = command_log_path.read_text(encoding="utf-8").splitlines()
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 2)
            self.assertEqual(command_log, ["artifact-freshness-refresh-check"])
            self.assertEqual(plan["status"], "source_report_not_current")


if __name__ == "__main__":
    unittest.main()
