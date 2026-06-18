from __future__ import annotations

import unittest

from ops.scripts.mechanism.promotion_gate_mechanism_report_runtime import (
    MechanismPromotionReportAssemblyRequest,
    assemble_mechanism_promotion_report,
    build_mechanism_report_inputs,
)
from ops.scripts.mechanism.promotion_gate_mechanism_state_runtime import (
    MechanismGateInputs,
)


def _gate_inputs(
    *,
    behavior_delta_rel: str = "",
    mechanism_contract_eval: bool = False,
) -> MechanismGateInputs:
    eval_report = {
        "status": "pass",
        "total_score": 10,
        "max_score": 10,
        "pages": [],
    }
    return MechanismGateInputs(
        baseline_eval_report=eval_report,
        baseline_eval_rel="artifacts/baseline-eval.json",
        candidate_eval_report=eval_report,
        candidate_eval_rel="artifacts/candidate-eval.json",
        baseline_lint_report={},
        baseline_lint_rel="artifacts/baseline-lint.json",
        candidate_lint_report={},
        candidate_lint_rel="artifacts/candidate-lint.json",
        baseline_mechanism_report={},
        baseline_mechanism_rel="artifacts/baseline-mechanism.json",
        candidate_mechanism_report={},
        candidate_mechanism_rel="artifacts/candidate-mechanism.json",
        changed_files_manifest_report={},
        changed_files_manifest_rel="artifacts/changed-files-manifest.json",
        run_ledger_report={},
        run_ledger_rel="runs/run-1/run-ledger.json",
        behavior_delta_report={} if behavior_delta_rel else None,
        behavior_delta_rel=behavior_delta_rel,
        baseline_mechanism_contract_eval_report=eval_report
        if mechanism_contract_eval
        else None,
        baseline_mechanism_contract_eval_rel=(
            "artifacts/baseline-mechanism-contract-eval.json"
            if mechanism_contract_eval
            else ""
        ),
        candidate_mechanism_contract_eval_report=eval_report
        if mechanism_contract_eval
        else None,
        candidate_mechanism_contract_eval_rel=(
            "artifacts/candidate-mechanism-contract-eval.json"
            if mechanism_contract_eval
            else ""
        ),
    )


class PromotionGateMechanismReportRuntimeTest(unittest.TestCase):
    def test_report_inputs_payload_omits_absent_behavior_delta(self) -> None:
        self.assertEqual(
            build_mechanism_report_inputs(_gate_inputs()),
            {
                "baseline_eval_report": "artifacts/baseline-eval.json",
                "candidate_eval_report": "artifacts/candidate-eval.json",
                "baseline_lint_report": "artifacts/baseline-lint.json",
                "candidate_lint_report": "artifacts/candidate-lint.json",
                "baseline_mechanism_report": "artifacts/baseline-mechanism.json",
                "candidate_mechanism_report": "artifacts/candidate-mechanism.json",
                "changed_files_manifest": "artifacts/changed-files-manifest.json",
                "run_ledger": "runs/run-1/run-ledger.json",
            },
        )

    def test_report_inputs_payload_preserves_behavior_delta_when_present(self) -> None:
        payload = build_mechanism_report_inputs(
            _gate_inputs(behavior_delta_rel="artifacts/behavior-delta.json")
        )

        self.assertEqual(payload["behavior_delta"], "artifacts/behavior-delta.json")

    def test_report_inputs_payload_preserves_mechanism_contract_eval_pair(self) -> None:
        payload = build_mechanism_report_inputs(_gate_inputs(mechanism_contract_eval=True))

        self.assertEqual(
            payload["baseline_mechanism_contract_eval_report"],
            "artifacts/baseline-mechanism-contract-eval.json",
        )
        self.assertEqual(
            payload["candidate_mechanism_contract_eval_report"],
            "artifacts/candidate-mechanism-contract-eval.json",
        )

    def test_assembled_report_uses_typed_inputs_payload_without_wire_drift(self) -> None:
        report = assemble_mechanism_promotion_report(
            request=MechanismPromotionReportAssemblyRequest(
                run_id="run-1",
                artifact_class="system_mechanism",
                primary_targets=["ops/scripts/example.py"],
                supporting_targets=[],
                signoff={"required": False, "status": "not_required"},
                log={"required": False, "summary": "typed payload fixture"},
                inputs=_gate_inputs(behavior_delta_rel="artifacts/behavior-delta.json"),
                checks=[],
                decision="PROMOTE",
            )
        )

        self.assertEqual(
            report["inputs"],
            {
                "baseline_eval_report": "artifacts/baseline-eval.json",
                "candidate_eval_report": "artifacts/candidate-eval.json",
                "baseline_lint_report": "artifacts/baseline-lint.json",
                "candidate_lint_report": "artifacts/candidate-lint.json",
                "baseline_mechanism_report": "artifacts/baseline-mechanism.json",
                "candidate_mechanism_report": "artifacts/candidate-mechanism.json",
                "changed_files_manifest": "artifacts/changed-files-manifest.json",
                "run_ledger": "runs/run-1/run-ledger.json",
                "behavior_delta": "artifacts/behavior-delta.json",
            },
        )


if __name__ == "__main__":
    unittest.main()
