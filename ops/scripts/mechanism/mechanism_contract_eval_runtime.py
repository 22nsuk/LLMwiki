from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_envelope_runtime import build_canonical_report_envelope
from ops.scripts.core.policy_runtime import report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_constants_runtime import (
    BEHAVIOR_DELTA_SCHEMA_PATH,
    CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    EVAL_REPORT_SCHEMA_PATH,
    LINT_REPORT_SCHEMA_PATH,
    MECHANISM_ASSESSMENT_SCHEMA_PATH,
    RUN_LEDGER_SCHEMA_PATH,
)
from ops.scripts.core.schema_runtime import load_schema, validate_or_raise

from .mechanism_run_common_runtime import write_json
from .mechanism_run_ledger_runtime import run_rel
from .mechanism_run_validation_runtime import path_in_declared_scope

PRODUCER = "ops.scripts.mechanism.mechanism_contract_eval_runtime"
SOURCE_COMMAND = "python -m ops.scripts.mechanism.mechanism_contract_eval"
ARTIFACT_KIND = "mechanism_contract_eval_report"


@dataclass(frozen=True)
class MechanismContractEvalRequest:
    vault: Path
    run_id: str
    policy: dict[str, Any]
    resolved_policy_path: Path
    policy_path_text: str
    changed_files_manifest_path: str = ""
    behavior_delta_path: str = ""
    context: RuntimeContext | None = None


@dataclass(frozen=True)
class ArtifactState:
    rel_path: str
    payload: dict[str, Any]
    status: str
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


INPUT_SCHEMA_BY_KEY = {
    "baseline_eval_report": EVAL_REPORT_SCHEMA_PATH,
    "candidate_eval_report": EVAL_REPORT_SCHEMA_PATH,
    "baseline_lint_report": LINT_REPORT_SCHEMA_PATH,
    "candidate_lint_report": LINT_REPORT_SCHEMA_PATH,
    "baseline_mechanism_report": MECHANISM_ASSESSMENT_SCHEMA_PATH,
    "candidate_mechanism_report": MECHANISM_ASSESSMENT_SCHEMA_PATH,
    "changed_files_manifest": CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    "behavior_delta": BEHAVIOR_DELTA_SCHEMA_PATH,
    "run_ledger": RUN_LEDGER_SCHEMA_PATH,
}
PHASES = ("baseline", "candidate")


def default_changed_files_manifest_path(run_id: str) -> str:
    return run_rel(run_id, "changed-files-manifest.json")


def default_behavior_delta_path(run_id: str) -> str:
    return run_rel(run_id, "behavior-delta.json")


def default_mechanism_contract_eval_path(run_id: str, phase: str) -> str:
    return run_rel(run_id, f"{phase}-mechanism-contract-eval.json")


def _runtime_context(request: MechanismContractEvalRequest) -> RuntimeContext:
    return request.context or RuntimeContext.from_policy(request.policy)


def _input_paths(request: MechanismContractEvalRequest) -> dict[str, str]:
    changed_files_manifest = (
        request.changed_files_manifest_path or default_changed_files_manifest_path(request.run_id)
    )
    behavior_delta = request.behavior_delta_path or default_behavior_delta_path(request.run_id)
    return {
        "baseline_eval_report": run_rel(request.run_id, "baseline-eval.json"),
        "candidate_eval_report": run_rel(request.run_id, "candidate-eval.json"),
        "baseline_lint_report": run_rel(request.run_id, "baseline-lint.json"),
        "candidate_lint_report": run_rel(request.run_id, "candidate-lint.json"),
        "baseline_mechanism_report": run_rel(request.run_id, "baseline-mechanism-assessment.json"),
        "candidate_mechanism_report": run_rel(request.run_id, "candidate-mechanism-assessment.json"),
        "changed_files_manifest": changed_files_manifest,
        "behavior_delta": behavior_delta,
        "run_ledger": run_rel(request.run_id, "run-ledger.json"),
    }


def _load_artifact(vault: Path, rel_path: str, schema_rel_path: str) -> ArtifactState:
    if not rel_path:
        return ArtifactState(rel_path="", payload={}, status="missing", message="path is empty")
    path = vault / rel_path
    if not path.is_file():
        return ArtifactState(rel_path=rel_path, payload={}, status="missing", message="file does not exist")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ArtifactState(
            rel_path=rel_path,
            payload={},
            status="invalid_json",
            message=f"line {exc.lineno} column {exc.colno}: {exc.msg}",
        )
    except OSError as exc:
        return ArtifactState(
            rel_path=rel_path,
            payload={},
            status="read_error",
            message=f"{exc.__class__.__name__}: {exc}",
        )
    if not isinstance(payload, dict):
        return ArtifactState(
            rel_path=rel_path,
            payload={},
            status="invalid_json",
            message="JSON root is not an object",
        )
    try:
        schema = load_schema(vault / schema_rel_path)
        validate_or_raise(
            payload,
            schema,
            context=f"schema validation failed for {rel_path}",
        )
    except FileNotFoundError as exc:
        return ArtifactState(
            rel_path=rel_path,
            payload=payload,
            status="schema_missing",
            message=f"{schema_rel_path}: {exc}",
        )
    except ValueError as exc:
        return ArtifactState(
            rel_path=rel_path,
            payload=payload,
            status="schema_invalid",
            message=str(exc),
        )
    return ArtifactState(rel_path=rel_path, payload=payload, status="ok")


def _artifact_states(request: MechanismContractEvalRequest) -> dict[str, ArtifactState]:
    return {
        key: _load_artifact(request.vault, rel_path, INPUT_SCHEMA_BY_KEY[key])
        for key, rel_path in _input_paths(request).items()
    }


def _schema_matches(state: ArtifactState, expected_schema: str) -> bool:
    return state.ok and state.payload.get("$schema") == expected_schema


def _state_detail(states: Mapping[str, ArtifactState], keys: list[str]) -> dict[str, Any]:
    return {
        key: {
            "path": states[key].rel_path,
            "status": states[key].status,
            **({"message": states[key].message} if states[key].message else {}),
        }
        for key in keys
    }


def _result(eval_id: str, passed: bool, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "eval": eval_id,
        "pass": passed,
        "detail": detail,
    }


def _list_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _int_field(payload: Mapping[str, Any], field: str) -> int:
    value = payload.get(field)
    return value if isinstance(value, int) else 0


def _event_types(run_ledger: dict[str, Any]) -> list[str]:
    events = run_ledger.get("events")
    if not isinstance(events, list):
        return []
    return [
        event_type
        for event in events
        if isinstance(event, dict)
        if isinstance(event_type := event.get("type"), str)
    ]


def _baseline_changed_targets_result(states: Mapping[str, ArtifactState]) -> dict[str, Any]:
    state = states["changed_files_manifest"]
    return _result(
        "changed_targets_contract",
        False,
        {
            "phase": "baseline",
            "reason": "changed targets are candidate-run evidence and are intentionally not credited to the baseline phase",
            "candidate_evidence_path": state.rel_path,
            "candidate_evidence_status": state.status,
        },
    )


def _candidate_changed_targets_result(
    request: MechanismContractEvalRequest,
    states: Mapping[str, ArtifactState],
) -> dict[str, Any]:
    state = states["changed_files_manifest"]
    manifest = state.payload
    declared_targets = manifest.get("declared_targets") if state.ok else {}
    if not isinstance(declared_targets, dict):
        declared_targets = {}
    primary_targets = _list_strings(declared_targets.get("primary_targets"))
    supporting_targets = _list_strings(declared_targets.get("supporting_targets"))
    test_files = _list_strings(declared_targets.get("test_files"))
    declared_scope = [*primary_targets, *supporting_targets, *test_files]
    files = manifest.get("files") if state.ok else []
    changed_paths = [
        str(entry.get("path"))
        for entry in files
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    ] if isinstance(files, list) else []
    out_of_scope = [
        path for path in changed_paths if not path_in_declared_scope(path, declared_scope)
    ]
    primary_hits = [
        path for path in changed_paths if path_in_declared_scope(path, primary_targets)
    ]
    passed = (
        state.ok
        and _schema_matches(state, CHANGED_FILES_MANIFEST_SCHEMA_PATH)
        and manifest.get("run_id") == request.run_id
        and bool(changed_paths)
        and not out_of_scope
        and bool(primary_hits)
    )
    return _result(
        "changed_targets_contract",
        passed,
        {
            "phase": "candidate",
            "path": state.rel_path,
            "status": state.status,
            "schema_matches": _schema_matches(state, CHANGED_FILES_MANIFEST_SCHEMA_PATH),
            "run_id_matches": manifest.get("run_id") == request.run_id if state.ok else False,
            "changed_paths": changed_paths,
            "declared_scope": declared_scope,
            "primary_target_hits": primary_hits,
            "out_of_scope_changes": out_of_scope,
        },
    )


def _baseline_behavior_delta_result(states: Mapping[str, ArtifactState]) -> dict[str, Any]:
    state = states["behavior_delta"]
    return _result(
        "behavior_delta_contract",
        False,
        {
            "phase": "baseline",
            "reason": "behavior delta compares baseline to candidate and is intentionally not credited to the baseline phase",
            "candidate_evidence_path": state.rel_path,
            "candidate_evidence_status": state.status,
        },
    )


def _candidate_behavior_delta_result(
    request: MechanismContractEvalRequest,
    states: Mapping[str, ArtifactState],
) -> dict[str, Any]:
    state = states["behavior_delta"]
    behavior_delta = state.payload
    summary = behavior_delta.get("summary") if state.ok else {}
    if not isinstance(summary, dict):
        summary = {}
    inputs = behavior_delta.get("inputs") if state.ok else {}
    if not isinstance(inputs, dict):
        inputs = {}
    regression_count = _int_field(summary, "regression_count")
    unexpected_change_count = _int_field(summary, "unexpected_change_count")
    coverage_gap_count = _int_field(summary, "coverage_gap_count")
    input_manifest_path = str(inputs.get("changed_files_manifest", ""))
    expected_manifest_path = states["changed_files_manifest"].rel_path
    passed = (
        state.ok
        and _schema_matches(state, BEHAVIOR_DELTA_SCHEMA_PATH)
        and behavior_delta.get("run_id") == request.run_id
        and input_manifest_path == expected_manifest_path
        and regression_count == 0
        and unexpected_change_count == 0
        and coverage_gap_count == 0
    )
    return _result(
        "behavior_delta_contract",
        passed,
        {
            "phase": "candidate",
            "path": state.rel_path,
            "status": state.status,
            "schema_matches": _schema_matches(state, BEHAVIOR_DELTA_SCHEMA_PATH),
            "run_id_matches": behavior_delta.get("run_id") == request.run_id if state.ok else False,
            "changed_files_manifest_input": input_manifest_path,
            "expected_changed_files_manifest": expected_manifest_path,
            "regression_count": regression_count,
            "unexpected_change_count": unexpected_change_count,
            "coverage_gap_count": coverage_gap_count,
        },
    )


def _promotion_gate_contract_result(
    phase: str,
    states: Mapping[str, ArtifactState],
) -> dict[str, Any]:
    required_keys = (
        ["baseline_eval_report", "baseline_lint_report", "baseline_mechanism_report", "run_ledger"]
        if phase == "baseline"
        else [
            "baseline_eval_report",
            "candidate_eval_report",
            "baseline_lint_report",
            "candidate_lint_report",
            "baseline_mechanism_report",
            "candidate_mechanism_report",
            "changed_files_manifest",
            "behavior_delta",
            "run_ledger",
        ]
    )
    missing_or_invalid = [key for key in required_keys if not states[key].ok]
    schema_mismatches = [
        key
        for key in required_keys
        if states[key].ok and not _schema_matches(states[key], INPUT_SCHEMA_BY_KEY[key])
    ]
    passed = not missing_or_invalid and not schema_mismatches
    return _result(
        "promotion_gate_contract",
        passed,
        {
            "phase": phase,
            "required_inputs": _state_detail(states, required_keys),
            "missing_or_invalid_inputs": missing_or_invalid,
            "schema_mismatches": schema_mismatches,
        },
    )


def _telemetry_schema_contract_result(
    phase: str,
    request: MechanismContractEvalRequest,
    states: Mapping[str, ArtifactState],
) -> dict[str, Any]:
    ledger_state = states["run_ledger"]
    events = _event_types(ledger_state.payload) if ledger_state.ok else []
    required_events = (
        ["baseline_captured"]
        if phase == "baseline"
        else ["baseline_captured", "candidate_captured", "repo_health_checked"]
    )
    missing_events = [event_type for event_type in required_events if event_type not in events]
    required_schema_keys = (
        ["baseline_eval_report", "baseline_lint_report", "baseline_mechanism_report", "run_ledger"]
        if phase == "baseline"
        else [
            "candidate_eval_report",
            "candidate_lint_report",
            "candidate_mechanism_report",
            "changed_files_manifest",
            "behavior_delta",
            "run_ledger",
        ]
    )
    schema_mismatches = [
        key
        for key in required_schema_keys
        if states[key].ok and not _schema_matches(states[key], INPUT_SCHEMA_BY_KEY[key])
    ]
    run_id_matches = ledger_state.ok and ledger_state.payload.get("run_id") == request.run_id
    passed = ledger_state.ok and run_id_matches and not missing_events and not schema_mismatches
    return _result(
        "telemetry_schema_contract",
        passed,
        {
            "phase": phase,
            "run_ledger": ledger_state.rel_path,
            "run_id_matches": run_id_matches,
            "required_events": required_events,
            "observed_events": events,
            "missing_events": missing_events,
            "schema_mismatches": schema_mismatches,
        },
    )


def _phase_results(
    phase: str,
    request: MechanismContractEvalRequest,
    states: Mapping[str, ArtifactState],
) -> list[dict[str, Any]]:
    if phase == "baseline":
        return [
            _baseline_changed_targets_result(states),
            _baseline_behavior_delta_result(states),
            _promotion_gate_contract_result(phase, states),
            _telemetry_schema_contract_result(phase, request, states),
        ]
    if phase == "candidate":
        return [
            _candidate_changed_targets_result(request, states),
            _candidate_behavior_delta_result(request, states),
            _promotion_gate_contract_result(phase, states),
            _telemetry_schema_contract_result(phase, request, states),
        ]
    raise ValueError(f"unsupported mechanism contract eval phase: {phase}")


def build_mechanism_contract_eval_report(
    request: MechanismContractEvalRequest,
    *,
    phase: str,
) -> dict[str, Any]:
    states = _artifact_states(request)
    runtime_context = _runtime_context(request)
    generated_at = runtime_context.isoformat_z()
    results = _phase_results(phase, request, states)
    score = sum(1 for result in results if result["pass"])
    max_score = len(results)
    input_paths = _input_paths(request)
    return {
        **build_canonical_report_envelope(
            request.vault,
            generated_at=generated_at,
            artifact_kind=ARTIFACT_KIND,
            producer=PRODUCER,
            source_command=f"{SOURCE_COMMAND} --run-id {request.run_id} --phase {phase}",
            resolved_policy_path=request.resolved_policy_path,
            schema_path=EVAL_REPORT_SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/mechanism_contract_eval_runtime.py",
                "ops/scripts/mechanism/mechanism_contract_eval.py",
                "ops/scripts/mechanism/mechanism_run_validation_runtime.py",
            ],
            file_inputs=input_paths,
            text_inputs={"phase": phase, "run_id": request.run_id},
        ),
        "vault": report_path(request.vault, request.vault),
        "run_id": request.run_id,
        "phase": phase,
        "inputs": input_paths,
        "policy": {
            "path": report_path(request.vault, request.resolved_policy_path),
            "version": request.policy.get("version"),
        },
        "status": "pass" if score == max_score else "fail",
        "max_score": max_score,
        "total_score": score,
        "pages": [
            {
                "page": f"runs/{request.run_id}/{phase}-mechanism-contract-eval",
                "score": score,
                "max_score": max_score,
                "results": results,
            }
        ],
    }


def write_mechanism_contract_eval_report(
    request: MechanismContractEvalRequest,
    *,
    phase: str,
) -> str:
    if phase not in PHASES:
        raise ValueError(f"unsupported mechanism contract eval phase: {phase}")
    rel_path = default_mechanism_contract_eval_path(request.run_id, phase)
    report = build_mechanism_contract_eval_report(request, phase=phase)
    write_json(request.vault, rel_path, report, EVAL_REPORT_SCHEMA_PATH)
    return rel_path


def write_mechanism_contract_eval_pair(request: MechanismContractEvalRequest) -> dict[str, str]:
    return {
        "baseline": write_mechanism_contract_eval_report(
            request,
            phase="baseline",
        ),
        "candidate": write_mechanism_contract_eval_report(
            request,
            phase="candidate",
        ),
    }
