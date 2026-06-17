from __future__ import annotations

import unittest

from ops.scripts.mechanism import (
    auto_improve_learning_preflight_runtime,
    auto_improve_runtime,
)
from ops.scripts.mechanism.goal_runtime_run_admission import (
    _contract_authorizes_learning_uncertain,
)


def _readiness_report(*, recommended_next_step: str = "review first") -> dict:
    return {
        "learning_readiness": {
            "status": "learning_uncertain",
            "gate_effect": "operator_review_required",
            "recommended_next_step": recommended_next_step,
        }
    }


def _session_with_learning_policy(policy: dict) -> dict:
    return {"goal_contract": {"execution_policy": {"learning_uncertain": policy}}}


class AutoImproveLearningPreflightRuntimeTests(unittest.TestCase):
    def test_auto_improve_runtime_learning_preflight_exports_point_to_helper(self) -> None:
        self.assertIs(
            auto_improve_runtime._learning_uncertain_contract_authorization,
            auto_improve_learning_preflight_runtime._learning_uncertain_contract_authorization,
        )

    def test_decision_blocks_learning_review_without_authorization(self) -> None:
        decision = auto_improve_learning_preflight_runtime.build_learning_preflight_decision(
            {},
            _readiness_report(recommended_next_step="bounded review required"),
            allow_learning_uncertain=False,
        )

        self.assertTrue(decision.review_required)
        self.assertTrue(decision.blocked)
        self.assertEqual(decision.recommended_next_step, "bounded review required")
        self.assertEqual(
            decision.learning_mode,
            {
                "allow_learning_uncertain": False,
                "bounded_trial": False,
                "authorization_source": "",
                "contract_authorized": False,
                "command_flag": "",
            },
        )

    def test_decision_prefers_command_flag_over_contract_authorization_source(self) -> None:
        session = _session_with_learning_policy(
            {
                "allow_bounded_trial": True,
                "requires_explicit_authorization": True,
                "authorization_source": "codex_goal_contract",
                "command_flag": "--allow-learning-uncertain",
            }
        )

        decision = auto_improve_learning_preflight_runtime.build_learning_preflight_decision(
            session,
            _readiness_report(),
            allow_learning_uncertain=True,
        )

        self.assertFalse(decision.blocked)
        self.assertEqual(
            decision.learning_mode,
            {
                "allow_learning_uncertain": True,
                "bounded_trial": True,
                "authorization_source": "command_flag",
                "contract_authorized": True,
                "command_flag": "--allow-learning-uncertain",
            },
        )

    def test_goal_admission_uses_same_contract_authorization_rule(self) -> None:
        contract = {
            "execution_policy": {
                "learning_uncertain": {
                    "allow_bounded_trial": True,
                    "requires_explicit_authorization": True,
                    "authorization_source": "codex_goal_contract",
                }
            }
        }
        stringly_contract = {
            "execution_policy": {
                "learning_uncertain": {
                    "allow_bounded_trial": "true",
                    "requires_explicit_authorization": True,
                    "authorization_source": "codex_goal_contract",
                }
            }
        }

        self.assertTrue(
            auto_improve_learning_preflight_runtime.goal_contract_authorizes_learning_uncertain(
                contract
            )
        )
        self.assertTrue(_contract_authorizes_learning_uncertain(contract))
        self.assertFalse(
            auto_improve_learning_preflight_runtime.goal_contract_authorizes_learning_uncertain(
                stringly_contract
            )
        )
        self.assertFalse(_contract_authorizes_learning_uncertain(stringly_contract))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
