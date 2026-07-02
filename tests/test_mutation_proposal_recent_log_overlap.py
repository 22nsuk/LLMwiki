from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.mutation_proposal_runtime import build_report
from tests.mutation_proposal_test_runtime import (
    fixed_context,
    mechanism_review_report,
    seed_vault,
    write_json,
)

pytestmark = pytest.mark.runtime_hotspot_smoke


class MutationProposalRecentLogOverlapTest(unittest.TestCase):
    def test_all_recent_log_overlap_blocked_queue_emits_runnable_rotation_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(
                vault / "ops" / "reports" / "mechanism-review-candidates.json",
                mechanism_review_report(),
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(policy),
            )
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 4)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 4,
                    "selected_proposal_count": 4,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 1,
                    "blocked_available_count": 3,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 3,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3}
                    ],
                },
            )
            self.assertEqual(
                proposal_report["diagnostics"]["recent_log_overlap"]["matches"][0][
                    "matched_marker"
                ],
                "ops/scripts/promotion_gate.py",
            )

            rotation = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "recent_log_overlap_queue_blocked"
            )
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(
                rotation["source_candidate_type"],
                "mechanism_recent_log_overlap_queue_unblock_candidate",
            )
            self.assertEqual(
                rotation["primary_targets"],
                ["ops/scripts/mechanism/mutation_proposal_runtime.py"],
            )
            self.assertEqual(
                rotation["must_change_tests"],
                [
                    "tests/test_mutation_proposal_build_report.py",
                    "tests/test_mutation_proposal_promotion.py",
                ],
            )
            self.assertIn(
                "`tests/test_mutation_proposal_build_report.py`",
                rotation["single_mechanism_scope"],
            )
            self.assertEqual(rotation["blocked_by"], [])
            self.assertEqual(
                rotation["must_change_budget_signal"],
                {
                    "signal": "mutation_proposal.queue_selection.runnable_available_count",
                    "expected_change": "greater_than_zero",
                },
            )

            limited_report = build_report(
                vault,
                policy,
                policy_path,
                max_proposals=1,
                context=fixed_context(policy),
            )
            self.assertEqual(limited_report["summary"]["proposals_emitted"], 1)
            self.assertEqual(limited_report["summary"]["blocked_proposals"], 0)
            self.assertEqual(
                limited_report["proposals"][0]["failure_mode"],
                "recent_log_overlap_queue_blocked",
            )
            self.assertEqual(
                limited_report["diagnostics"]["queue_selection"]["selected_runnable_count"],
                1,
            )

    def test_recent_log_overlap_rotation_uses_non_overlapping_secondary_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(
                vault / "ops" / "reports" / "mechanism-review-candidates.json",
                mechanism_review_report(),
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n"
                "- `ops/scripts/mechanism/mutation_proposal_runtime.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(policy),
            )
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "pass")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 4)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"],
                {
                    "available_proposal_count": 4,
                    "selected_proposal_count": 4,
                    "selection_mode": "standard",
                    "repair_priority_suppressed_count": 0,
                    "runnable_available_count": 1,
                    "blocked_available_count": 3,
                    "selected_runnable_count": 1,
                    "selected_blocked_count": 3,
                    "blocked_reason_counts": [
                        {"reason": "recent_log_overlap", "count": 3}
                    ],
                },
            )

            rotation = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "recent_log_overlap_queue_blocked"
            )
            self.assertEqual(rotation["failure_mode"], "recent_log_overlap_queue_blocked")
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(
                rotation["primary_targets"],
                ["ops/scripts/mechanism/mechanism_run_validation_runtime.py"],
            )
            self.assertEqual(
                rotation["must_change_tests"],
                ["tests/test_mechanism_run_validation_runtime.py"],
            )
            self.assertEqual(rotation["blocked_by"], [])

    def test_recent_log_overlap_rotation_respects_failure_mode_policy_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            write_json(
                vault / "ops" / "reports" / "mechanism-review-candidates.json",
                mechanism_review_report(),
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            policy["mutation_proposal"]["allowed_failure_modes"] = [
                failure_mode
                for failure_mode in policy["mutation_proposal"]["allowed_failure_modes"]
                if failure_mode != "recent_log_overlap_queue_blocked"
            ]
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(policy),
            )
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            self.assertEqual(proposal_report["status"], "attention")
            self.assertEqual(proposal_report["summary"]["proposals_emitted"], 3)
            self.assertEqual(proposal_report["summary"]["blocked_proposals"], 3)
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["runnable_available_count"],
                0,
            )
            self.assertFalse(
                any(
                    proposal["failure_mode"] == "recent_log_overlap_queue_blocked"
                    for proposal in proposal_report["proposals"]
                )
            )

    def test_recent_log_overlap_rotation_skips_over_budget_primary_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            mutation_target = vault / "ops" / "scripts" / "mechanism" / "mutation_proposal_runtime.py"
            mutation_target.parent.mkdir(parents=True, exist_ok=True)
            mutation_target.write_text(
                "\n".join(f"VALUE_{index} = {index}" for index in range(901)) + "\n",
                encoding="utf-8",
            )
            validation_target = (
                vault
                / "ops"
                / "scripts"
                / "mechanism"
                / "mechanism_run_validation_runtime.py"
            )
            validation_target.write_text(
                "def validate_run() -> bool:\n    return True\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_mutation_proposal.py").write_text(
                "def test_mutation_proposal_runtime() -> None:\n    assert True\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_report_generation_smoke.py").write_text(
                "def test_smoke() -> None:\n    assert True\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_mechanism_run_validation_runtime.py").write_text(
                "def test_validation_runtime() -> None:\n    assert True\n",
                encoding="utf-8",
            )
            write_json(
                vault / "ops" / "reports" / "mechanism-review-candidates.json",
                mechanism_review_report(),
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(policy),
            )
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            rotation = next(
                proposal
                for proposal in proposal_report["proposals"]
                if proposal["failure_mode"] == "recent_log_overlap_queue_blocked"
            )
            self.assertEqual(
                rotation["proposal_id"],
                "recent_log_overlap_queue_blocked__mechanism-run-validation-runtime",
            )
            self.assertEqual(
                rotation["primary_targets"],
                ["ops/scripts/mechanism/mechanism_run_validation_runtime.py"],
            )
            self.assertEqual(rotation["blocked_by"], [])
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["runnable_available_count"],
                1,
            )

    def test_recent_log_overlap_rotation_skips_retired_readiness_queue_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_vault(vault)
            retired_target = (
                vault
                / "ops"
                / "scripts"
                / "mechanism"
                / "auto_improve_readiness_queue_runtime.py"
            )
            retired_target.parent.mkdir(parents=True, exist_ok=True)
            retired_target.write_text(
                "def retired_readiness_queue_runtime() -> None:\n    return None\n",
                encoding="utf-8",
            )
            (vault / "tests" / "test_auto_improve_readiness_queue_runtime.py").write_text(
                "def test_retired_readiness_queue_runtime() -> None:\n    assert True\n",
                encoding="utf-8",
            )
            write_json(
                vault / "ops" / "reports" / "mechanism-review-candidates.json",
                mechanism_review_report(),
            )
            write_json(
                vault / "ops" / "reports" / "outcome-metrics.json",
                {
                    "recent_attempts": [
                        {
                            "run_id": "mutation-proposal-rerun-2",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__mutation-proposal-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                        {
                            "run_id": "mechanism-validation-rerun-2",
                            "proposal_id": (
                                "recent_log_overlap_queue_blocked__"
                                "mechanism-run-validation-runtime"
                            ),
                            "outcome": "validation_blocked",
                            "decision": "HOLD",
                        },
                    ],
                },
            )
            (vault / "system" / "system-log.md").write_text(
                "# System Log\n\n"
                "## [2026-04-14 00:00] decision | prior overlapping experiments\n\n"
                "### Artifacts\n"
                "- `ops/scripts/promotion_gate.py`\n"
                "- `ops/scripts/wiki_lint.py`\n"
                "- `ops/scripts/mechanism_assess.py`\n"
                "- `ops/scripts/mechanism/mutation_proposal_runtime.py`\n"
                "- `ops/scripts/mechanism/mechanism_run_validation_runtime.py`\n",
                encoding="utf-8",
            )

            policy, policy_path = load_policy(vault)
            proposal_report = build_report(
                vault,
                policy,
                policy_path,
                context=fixed_context(policy),
            )
            schema = load_schema(vault / "ops" / "schemas" / "mutation-proposals.schema.json")

            self.assertEqual(validate_with_schema(proposal_report, schema), [])
            for proposal in proposal_report["proposals"]:
                self.assertNotIn(
                    "ops/scripts/mechanism/auto_improve_readiness_queue_runtime.py",
                    proposal["primary_targets"],
                )
            self.assertEqual(
                proposal_report["diagnostics"]["queue_selection"]["runnable_available_count"],
                0,
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
