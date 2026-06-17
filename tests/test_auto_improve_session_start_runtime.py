from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.codex_goal_client import set_goal
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.mechanism import (
    auto_improve_error_runtime,
    auto_improve_runtime,
    auto_improve_session_start_runtime,
    auto_improve_value_runtime,
)
from tests.run_mechanism_experiment_test_utils import seed_wrapper_vault
from tests.test_codex_goal_contract import sample_goal_contract


class AutoImproveSessionStartRuntimeTests(unittest.TestCase):
    def test_auto_improve_runtime_start_exports_point_to_helpers(self) -> None:
        self.assertIs(
            auto_improve_runtime.AutoImproveError,
            auto_improve_error_runtime.AutoImproveError,
        )
        self.assertIs(
            auto_improve_runtime.AutoImproveUsageError,
            auto_improve_error_runtime.AutoImproveUsageError,
        )
        self.assertIs(
            auto_improve_runtime.AutoImproveLearningReviewRequiredError,
            auto_improve_error_runtime.AutoImproveLearningReviewRequiredError,
        )
        self.assertIs(
            auto_improve_runtime.AutoImproveSessionRequest,
            auto_improve_session_start_runtime.AutoImproveSessionRequest,
        )
        self.assertIs(
            auto_improve_runtime.AutoImproveSessionStart,
            auto_improve_session_start_runtime.AutoImproveSessionStart,
        )
        self.assertIs(
            auto_improve_runtime._coerce_auto_improve_session_request,
            auto_improve_session_start_runtime._coerce_auto_improve_session_request,
        )
        self.assertIs(
            auto_improve_runtime._start_auto_improve_session,
            auto_improve_session_start_runtime._start_auto_improve_session,
        )
        self.assertIs(
            auto_improve_runtime._new_auto_improve_session,
            auto_improve_session_start_runtime._new_auto_improve_session,
        )
        self.assertIs(
            auto_improve_runtime._attach_goal_contract_snapshot,
            auto_improve_session_start_runtime._attach_goal_contract_snapshot,
        )
        self.assertIs(auto_improve_runtime._int_value, auto_improve_value_runtime._int_value)
        self.assertIs(
            auto_improve_runtime._mapping_value,
            auto_improve_value_runtime._mapping_value,
        )
        self.assertIs(auto_improve_runtime._list_text, auto_improve_value_runtime._list_text)

    def test_request_object_coercion_resolves_vault_and_rejects_mixed_legacy_kwargs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            request = auto_improve_session_start_runtime.AutoImproveSessionRequest(
                vault=Path(temp_dir) / "vault",
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
            )

            resolved = auto_improve_session_start_runtime._coerce_auto_improve_session_request(
                request,
                {},
            )

            self.assertEqual(resolved.vault, request.vault.resolve())
            with self.assertRaisesRegex(TypeError, "unexpected legacy session arguments"):
                auto_improve_session_start_runtime._coerce_auto_improve_session_request(
                    request,
                    {"policy_path": "ops/policies/wiki-maintainer-policy.yaml"},
                )

    def test_start_auto_improve_session_attaches_goal_contract_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_wrapper_vault(vault)
            contract = sample_goal_contract()
            set_goal(contract, vault=vault)
            request = auto_improve_session_start_runtime.AutoImproveSessionRequest(
                vault=vault,
                policy_path="ops/policies/wiki-maintainer-policy.yaml",
                session_id="auto-session-start-contract",
                goal_contract_path="ops/reports/codex-goal-contract.json",
                max_proposals=1,
                max_minutes=30,
                max_consecutive_failures=1,
                executor_name="codex_exec",
                context=RuntimeContext(
                    display_timezone=dt.UTC,
                    clock=lambda: dt.datetime(2026, 4, 15, tzinfo=dt.UTC),
                    executor_id="codex_exec",
                ),
            )

            start = auto_improve_session_start_runtime._start_auto_improve_session(request)

            self.assertEqual(start.session_id, "auto-session-start-contract")
            self.assertEqual(start.session["budget"]["max_proposals"], 1)
            self.assertEqual(
                start.session["goal_contract"]["requested_path"],
                "ops/reports/codex-goal-contract.json",
            )
            self.assertEqual(
                start.session["goal_contract"]["promotion_blockers"],
                contract["promotion_guard"]["promotion_blockers"],
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
