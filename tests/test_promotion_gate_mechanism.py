from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ops.scripts.mechanism import promotion_gate_mechanism_state_runtime as runtime
from ops.scripts.mechanism.promotion_gate_common_runtime import PromotionGateUsageError
from ops.scripts.mechanism.promotion_gate_mechanism_runtime import (
    MechanismGateInputRequest,
    collect_mechanism_gate_inputs,
)

pytestmark = pytest.mark.public


def _patch_artifact_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_validate_json_artifact(vault: Path, rel_path: str, schema_path: Path) -> tuple[dict[str, Any], str]:
        report: dict[str, Any] = {"schema_path": str(schema_path), "vault": str(vault)}
        if rel_path.endswith("mechanism-contract-eval.json"):
            report.update({"artifact_kind": runtime.MECHANISM_CONTRACT_EVAL_ARTIFACT_KIND})
            report["phase"] = "candidate" if "candidate" in rel_path else "baseline"
        return report, rel_path

    monkeypatch.setattr(runtime, "validate_json_artifact", fake_validate_json_artifact)


def _request() -> MechanismGateInputRequest:
    return MechanismGateInputRequest(
        vault=Path(),
        baseline_eval_path="runs/example/baseline-eval.json",
        candidate_eval_path="runs/example/candidate-eval.json",
        baseline_lint_path="runs/example/baseline-lint.json",
        candidate_lint_path="runs/example/candidate-lint.json",
        baseline_mechanism_path="runs/example/baseline-mechanism-assessment.json",
        candidate_mechanism_path="runs/example/candidate-mechanism-assessment.json",
        changed_files_manifest_path="runs/example/changed-files.json",
        run_ledger_path="runs/example/run-ledger.json",
        behavior_delta_path="runs/example/behavior-delta.json",
        baseline_mechanism_contract_eval_path="runs/example/baseline-mechanism-contract-eval.json",
        candidate_mechanism_contract_eval_path="runs/example/candidate-mechanism-contract-eval.json",
    )


def test_collect_mechanism_gate_inputs_accepts_request_object(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_artifact_validation(monkeypatch)

    inputs = collect_mechanism_gate_inputs(_request())

    assert inputs.baseline_eval_rel == "runs/example/baseline-eval.json"
    assert inputs.candidate_mechanism_contract_eval_rel == (
        "runs/example/candidate-mechanism-contract-eval.json"
    )
    assert inputs.behavior_delta_rel == "runs/example/behavior-delta.json"


def test_collect_mechanism_gate_inputs_keeps_legacy_positional_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_artifact_validation(monkeypatch)
    request = _request()

    inputs = collect_mechanism_gate_inputs(
        request.vault,
        request.baseline_eval_path,
        request.candidate_eval_path,
        request.baseline_lint_path,
        request.candidate_lint_path,
        request.baseline_mechanism_path,
        request.candidate_mechanism_path,
        request.changed_files_manifest_path,
        request.run_ledger_path,
        request.behavior_delta_path,
        baseline_mechanism_contract_eval_path=request.baseline_mechanism_contract_eval_path,
        candidate_mechanism_contract_eval_path=request.candidate_mechanism_contract_eval_path,
    )

    assert inputs.run_ledger_rel == request.run_ledger_path
    assert inputs.baseline_mechanism_contract_eval_rel == (
        "runs/example/baseline-mechanism-contract-eval.json"
    )


def test_collect_mechanism_gate_inputs_rejects_mixed_request_and_legacy_fields() -> None:
    with pytest.raises(TypeError, match="either a request object or legacy fields"):
        collect_mechanism_gate_inputs(_request(), baseline_eval_path="other.json")


def test_collect_mechanism_gate_inputs_requires_contract_eval_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_artifact_validation(monkeypatch)
    request = _request()
    request = MechanismGateInputRequest(
        **{
            **request.__dict__,
            "candidate_mechanism_contract_eval_path": None,
        }
    )

    with pytest.raises(PromotionGateUsageError, match="requires both baseline and candidate"):
        collect_mechanism_gate_inputs(request)
