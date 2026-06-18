from __future__ import annotations

import json
import unittest
from pathlib import Path

from ops.scripts.core.promotion_decision_registry_runtime import (
    DECISION_REDUCER_KEY,
    DECISION_STAGE,
    FINALIZABLE_DECISIONS,
    PROMOTION_DECISION_REGISTRY,
    PromotionDecisionRegistryError,
    decision_is_finalizable_by_default,
    decision_is_terminal,
    decision_ledger_event_type,
    decision_outcome,
    promotion_decision_values,
    reduce_decision_proposals,
    telemetry_decision_values,
    validate_decision_record,
)
from ops.scripts.core.rule_registry_runtime import (
    RuleMetadata,
    RuleSpec,
    evaluate_rule_registry,
)


class PromotionDecisionRegistryRuntimeTests(unittest.TestCase):
    def _contract(self, decision: str) -> dict:
        return reduce_decision_proposals(
            [{"rule_id": "test_rule", "decision": decision}],
            subject_id=f"run-{decision.lower()}",
            subject_kind="system_mechanism",
            policy_version=1,
            source_pass="system_mechanism",
            signoff={"required": False, "status": "not_required"},
        )

    def test_reducer_uses_registry_precedence(self) -> None:
        contract = reduce_decision_proposals(
            [
                {"rule_id": "eligible", "decision": "PROMOTE"},
                {"rule_id": "manual_review", "decision": "HOLD"},
                {"rule_id": "scope_violation", "decision": "DISCARD"},
            ],
            subject_id="run-precedence",
            subject_kind="system_mechanism",
            policy_version=1,
            source_pass="system_mechanism",
            signoff={"required": False, "status": "not_required"},
        )

        self.assertEqual(contract["decision"], "DISCARD")
        self.assertEqual(contract["decision_record"]["precedence_key"], "0100:DISCARD")
        self.assertEqual(
            PROMOTION_DECISION_REGISTRY[contract["decision"]]["precedence"],
            max(row["precedence"] for row in PROMOTION_DECISION_REGISTRY.values()),
        )

    def test_reducer_records_losing_proposals_in_supersedes_and_trace(self) -> None:
        contract = reduce_decision_proposals(
            [
                {"rule_id": "eligible", "decision": "PROMOTE"},
                {"rule_id": "manual_review", "decision": "HOLD"},
            ],
            subject_id="run-supersedes",
            subject_kind="system_mechanism",
            policy_version=1,
            source_pass="system_mechanism",
            signoff={"required": False, "status": "not_required"},
        )

        selected_id = contract["decision_reduction"]["selected_decision_id"]
        proposal_ids = [
            proposal["decision_id"]
            for proposal in contract["decision_reduction"]["proposals"]
        ]
        self.assertEqual(contract["decision"], "HOLD")
        self.assertIn(selected_id, proposal_ids)
        self.assertEqual(
            contract["decision_record"]["supersedes"],
            [proposal_id for proposal_id in proposal_ids if proposal_id != selected_id],
        )

    def test_unsupported_decision_proposal_fails_closed(self) -> None:
        with self.assertRaises(PromotionDecisionRegistryError):
            reduce_decision_proposals(
                [{"rule_id": "future_value", "decision": "ESCALATE"}],
                subject_id="run-unsupported",
                subject_kind="system_mechanism",
                policy_version=1,
                source_pass="system_mechanism",
                signoff={"required": False, "status": "not_required"},
            )

    def test_finalizable_decisions_are_closed_contract(self) -> None:
        self.assertEqual(FINALIZABLE_DECISIONS, frozenset({"PROMOTE", "DISCARD"}))

    def test_registry_helpers_expose_decision_semantics(self) -> None:
        self.assertEqual(promotion_decision_values(), ("PROMOTE", "HOLD", "DISCARD"))
        self.assertEqual(telemetry_decision_values(), ("", "PROMOTE", "HOLD", "DISCARD", "SKIPPED"))
        self.assertEqual(decision_outcome("PROMOTE"), "promoted")
        self.assertEqual(decision_outcome("DISCARD"), "discarded")
        self.assertEqual(decision_outcome("HOLD"), "hold")
        self.assertTrue(decision_is_terminal("PROMOTE"))
        self.assertTrue(decision_is_terminal("DISCARD"))
        self.assertFalse(decision_is_terminal("HOLD"))
        self.assertTrue(decision_is_finalizable_by_default("PROMOTE"))
        self.assertTrue(decision_is_finalizable_by_default("DISCARD"))
        self.assertFalse(decision_is_finalizable_by_default("HOLD"))
        self.assertEqual(decision_ledger_event_type("HOLD"), "promotion_evaluated")

    def test_decision_record_validation_rejects_registry_semantic_drift(self) -> None:
        record = dict(self._contract("PROMOTE")["decision_record"])
        record["is_terminal"] = False
        with self.assertRaisesRegex(PromotionDecisionRegistryError, "is_terminal"):
            validate_decision_record(record)

        record = dict(self._contract("PROMOTE")["decision_record"])
        record["ledger_event_type"] = "custom_event"
        with self.assertRaisesRegex(PromotionDecisionRegistryError, "ledger_event_type"):
            validate_decision_record(record)

        record = dict(self._contract("HOLD")["decision_record"])
        record["finalizable"] = True
        record["finalize_blockers"] = []
        with self.assertRaisesRegex(PromotionDecisionRegistryError, "finalizable"):
            validate_decision_record(record)

    def test_report_schemas_track_registry_decision_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        decisions = list(promotion_decision_values())
        telemetry_decisions = list(telemetry_decision_values())

        promotion_report = json.loads(
            (root / "ops/schemas/promotion-report.schema.json").read_text(encoding="utf-8")
        )
        trends = json.loads(
            (root / "ops/schemas/promotion-decision-trends.schema.json").read_text(
                encoding="utf-8"
            )
        )
        run_telemetry = json.loads(
            (root / "ops/schemas/run-telemetry.schema.json").read_text(encoding="utf-8")
        )

        self.assertEqual(promotion_report["$defs"]["promotion_decision"]["enum"], decisions)
        self.assertEqual(
            promotion_report["$defs"]["decision_record"]["properties"]["decision"]["$ref"],
            "#/$defs/promotion_decision",
        )
        self.assertEqual(
            promotion_report["$defs"]["decision_record"]["properties"]["decision_stage"]["enum"],
            [DECISION_STAGE],
        )
        self.assertEqual(
            promotion_report["$defs"]["decision_record"]["properties"]["reducer_key"]["enum"],
            [DECISION_REDUCER_KEY],
        )
        self.assertEqual(
            trends["$defs"]["recent_run"]["properties"]["decision"]["enum"],
            decisions,
        )
        self.assertEqual(
            trends["$defs"]["decision_record"]["properties"]["decision"]["enum"],
            decisions,
        )
        self.assertEqual(run_telemetry["properties"]["decision"]["enum"], telemetry_decisions)
        self.assertEqual(
            run_telemetry["$defs"]["decision_record"]["properties"]["decision"]["enum"],
            decisions,
        )


class RuleRegistryRuntimeTests(unittest.TestCase):
    def test_rule_metadata_summary_template_drives_decision_detail(self) -> None:
        metadata = RuleMetadata(
            rule_id="scope_gate",
            artifact_dependencies=("changed_files_manifest",),
            reducer="status_fail_discard",
            severity="blocker",
            summary_template="{rule_id} {severity} emitted {statuses}: {details}",
        )
        registry = {
            "scope_gate": RuleSpec(
                rule_id="scope_gate",
                build_checks=lambda: [
                    {
                        "id": "scope_check",
                        "status": "FAIL",
                        "detail": "path escaped declared target set",
                    }
                ],
                reduce_decision=lambda _checks: "DISCARD",
                metadata=metadata,
            )
        }

        _checks, decisions = evaluate_rule_registry(["scope_gate"], registry)

        self.assertEqual(
            decisions[0]["reason_detail"],
            "scope_gate blocker emitted FAIL: scope_check=FAIL: path escaped declared target set",
        )
        self.assertEqual(decisions[0]["evidence_refs"], ["scope_check"])


if __name__ == "__main__":
    unittest.main()
