from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact_io_runtime import write_vault_schema_validated_json
from .request_coercion_runtime import coerce_request_or_kwargs
from .run_artifact_envelope_runtime import maybe_embed_run_artifact_envelope
from .schema_constants_runtime import BEHAVIOR_DELTA_SCHEMA_PATH

_RISK_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_EXECUTION_SCRIPT_NAMES = {
    "auto_improve_loop.py",
    "auto_improve_runtime.py",
    "codex_exec_executor.py",
    "command_runtime.py",
    "executor_runtime.py",
    "run_mechanism_experiment.py",
    "run_mechanism_experiment_runtime.py",
}
_EXECUTION_SCRIPT_PREFIXES = (
    "mechanism_run_workspace",
    "mechanism_run_ledger",
    "experiment_telemetry",
)
_PROMOTION_GATE_PREFIXES = (
    "promotion_gate",
    "mechanism_run_promotion",
    "mechanism_run_validation",
)
_PLANNING_GATE_PREFIXES = (
    "planning_gate",
    "starter_bundle",
)
_TELEMETRY_CONTRACT_SCHEMA_NAMES = {
    "behavior-delta.schema.json",
    "executor-report.schema.json",
    "run-artifact-fingerprint.schema.json",
    "run-ledger.schema.json",
    "run-telemetry.schema.json",
    "timeout-failure.schema.json",
}


@dataclass(frozen=True)
class BehaviorDeltaRequest:
    baseline_root: Path
    candidate_root: Path
    run_id: str
    generated_at: str
    policy_path: str
    policy: dict[str, Any]
    primary_targets: list[str]
    supporting_targets: list[str]
    test_files: list[str]
    input_artifacts: dict[str, str]
    changed_files_manifest: dict[str, Any]


def _read_text(root: Path, rel_path: str) -> str | None:
    path = root / rel_path
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _python_symbols(source: str) -> tuple[set[str], str | None]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return set(), f"{exc.__class__.__name__}: {exc.msg}"

    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.add(f"{node.name}.{child.name}")
    return symbols, None


def classify_surface(rel_path: str) -> str:
    path = Path(rel_path)
    parts = path.parts
    name = path.name
    suffix = path.suffix

    if parts and parts[0] == "tests":
        return "test_surface"
    if name.startswith("test_") and suffix == ".py":
        return "test_surface"
    if parts[:2] == ("ops", "schemas") or name.endswith(".schema.json"):
        return "schema_surface"
    if parts[:2] == ("ops", "policies"):
        return "policy_surface"
    if suffix == ".md":
        return "documentation_surface"
    if parts[:2] == ("ops", "scripts"):
        return "runtime_surface"
    if suffix == ".py":
        return "python_api_surface"
    if suffix == ".json":
        return "artifact_contract"
    return "unknown"


def _classify_surface(rel_path: str) -> str:
    return classify_surface(rel_path)


def _script_stem_matches(name: str, prefixes: tuple[str, ...]) -> bool:
    stem = Path(name).stem
    return any(stem == prefix or stem.startswith(f"{prefix}_") for prefix in prefixes)


def contract_touches_for_path(rel_path: str, change_type: str | None = None) -> list[str]:
    path = Path(rel_path)
    parts = path.parts
    name = path.name
    surface = change_type or classify_surface(rel_path)
    touches: set[str] = set()

    if surface == "test_surface":
        touches.add("test_surface")
    if surface == "documentation_surface":
        touches.update({"documentation", "public_surface"})
    if surface == "schema_surface":
        touches.add("schema_contract")
        if name in _TELEMETRY_CONTRACT_SCHEMA_NAMES:
            touches.add("telemetry_contract")
    if surface == "policy_surface":
        touches.add("policy_contract")
    if surface == "artifact_contract" or (parts[:2] == ("ops", "templates")):
        touches.add("artifact_contract")
    if parts[:2] == ("ops", "scripts"):
        if name in _EXECUTION_SCRIPT_NAMES or _script_stem_matches(name, _EXECUTION_SCRIPT_PREFIXES):
            touches.add("runtime_execution")
        elif _script_stem_matches(name, _PROMOTION_GATE_PREFIXES):
            touches.add("promotion_gate")
        elif _script_stem_matches(name, _PLANNING_GATE_PREFIXES):
            touches.add("planning_gate")
        else:
            touches.add("runtime_logic")
    if not touches:
        touches.add("unknown")
    return sorted(touches)


def _risk_for(change_type: str, manifest_change_type: str) -> str:
    if manifest_change_type == "deleted":
        return "high"
    if change_type in {"schema_surface", "policy_surface"}:
        return "high"
    if change_type in {"artifact_contract", "python_api_surface", "runtime_surface"}:
        return "medium"
    return "low"


def _matches_declared_target(rel_path: str, targets: list[str]) -> bool:
    normalized = rel_path.rstrip("/")
    for target in targets:
        normalized_target = target.rstrip("/")
        if normalized == normalized_target or normalized.startswith(f"{normalized_target}/"):
            return True
    return False


def _intent_for(
    rel_path: str,
    *,
    primary_targets: list[str],
    supporting_targets: list[str],
    test_files: list[str],
) -> str:
    if _matches_declared_target(rel_path, [*primary_targets, *supporting_targets, *test_files]):
        return "intended"
    return "unexpected"


def _semantic_class(
    *,
    change_type: str,
    manifest_change_type: str,
    contract_touches: list[str],
    added_symbols: list[str],
    removed_symbols: list[str],
) -> str:
    if manifest_change_type == "deleted":
        return "contract_removed" if change_type in {"schema_surface", "policy_surface"} else "implementation_removed"
    if "promotion_gate" in contract_touches:
        return "promotion_gate_changed"
    if "planning_gate" in contract_touches:
        return "planning_gate_changed"
    if "runtime_execution" in contract_touches:
        return "execution_flow_changed"
    if "schema_contract" in contract_touches or "artifact_contract" in contract_touches:
        return "artifact_contract_changed"
    if "policy_contract" in contract_touches:
        return "policy_contract_changed"
    if change_type == "test_surface":
        return "test_expectation_changed"
    if change_type == "documentation_surface":
        return "documentation_only"
    if added_symbols or removed_symbols:
        return "api_surface_changed"
    if change_type in {"runtime_surface", "python_api_surface"}:
        return "implementation_changed"
    return "unknown"


def _expected_direction(contract_touches: list[str], change_type: str) -> str:
    if "test_surface" in contract_touches:
        return "test_guardrail_change"
    if "documentation" in contract_touches:
        return "documentation_change"
    if "promotion_gate" in contract_touches or "planning_gate" in contract_touches:
        return "gate_change"
    if "runtime_execution" in contract_touches:
        return "execution_change"
    if change_type in {"artifact_contract", "policy_surface", "schema_surface"}:
        return "contract_change"
    return "unknown"


def _coverage_status(change_type: str, test_files: list[str]) -> str:
    if change_type in {"documentation_surface", "test_surface"}:
        return "not_applicable"
    if test_files:
        return "covered"
    if change_type in {
        "artifact_contract",
        "policy_surface",
        "python_api_surface",
        "runtime_surface",
        "schema_surface",
    }:
        return "coverage_gap"
    return "unknown"


def _behavior_sentence(
    *,
    manifest_change_type: str,
    change_type: str,
    added_symbols: list[str],
    removed_symbols: list[str],
    parse_error: str | None,
) -> str:
    base = f"{manifest_change_type} {change_type} file"
    if parse_error:
        return f"{base}; Python syntax could not be parsed deterministically"
    if added_symbols or removed_symbols:
        fragments = []
        if added_symbols:
            fragments.append(f"added Python symbols: {', '.join(added_symbols)}")
        if removed_symbols:
            fragments.append(f"removed Python symbols: {', '.join(removed_symbols)}")
        return f"{base}; {'; '.join(fragments)}"
    return f"{base}; no deterministic Python symbol delta detected"


def _manifest_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    files = manifest.get("files")
    if isinstance(files, list):
        return [entry for entry in files if isinstance(entry, dict)]
    return []


def _summary_changed_file_count(manifest: dict[str, Any], files: list[dict[str, Any]]) -> int:
    summary = manifest.get("summary")
    if isinstance(summary, dict):
        for key in ("total_changed_files", "total"):
            total = summary.get(key)
            if isinstance(total, int):
                return total
    return len(files)


def _symbol_delta(
    *,
    baseline_text: str | None,
    candidate_text: str | None,
) -> tuple[list[str], list[str], str | None]:
    baseline_symbols: set[str] = set()
    candidate_symbols: set[str] = set()
    parse_error: str | None = None
    if baseline_text is not None:
        baseline_symbols, baseline_error = _python_symbols(baseline_text)
        parse_error = baseline_error or parse_error
    if candidate_text is not None:
        candidate_symbols, candidate_error = _python_symbols(candidate_text)
        parse_error = candidate_error or parse_error
    return (
        sorted(candidate_symbols - baseline_symbols),
        sorted(baseline_symbols - candidate_symbols),
        parse_error,
    )


def _manifest_change_type(entry: dict[str, Any], rel_path: str, skipped_files: list[dict[str, str]]) -> str:
    manifest_change_type = str(entry.get("change_type") or "modified")
    if manifest_change_type in {"added", "deleted", "modified"}:
        return manifest_change_type
    skipped_files.append(
        {
            "path": rel_path,
            "reason": "unknown manifest change_type",
            "detail": manifest_change_type,
        }
    )
    return "modified"


def _delta_details(
    *,
    rel_path: str,
    baseline_text: str | None,
    candidate_text: str | None,
    added_symbols: list[str],
    removed_symbols: list[str],
    parse_error: str | None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "file_exists_in_baseline": baseline_text is not None,
        "file_exists_in_candidate": candidate_text is not None,
    }
    if Path(rel_path).suffix == ".py":
        details.update(
            {
                "added_symbols": added_symbols,
                "removed_symbols": removed_symbols,
                "symbol_count_delta": len(added_symbols) - len(removed_symbols),
            }
        )
    if parse_error:
        details["parse_error"] = parse_error
    return details


def _file_delta(
    request: BehaviorDeltaRequest,
    entry: dict[str, Any],
    *,
    index: int,
    skipped_files: list[dict[str, str]],
) -> dict[str, Any] | None:
    rel_path = str(entry.get("path") or "")
    if not rel_path:
        skipped_files.append({"path": "<missing>", "reason": "missing path"})
        return None
    manifest_change_type = _manifest_change_type(entry, rel_path, skipped_files)
    change_type = _classify_surface(rel_path)
    contract_touches = contract_touches_for_path(rel_path, change_type)
    baseline_text = _read_text(request.baseline_root, rel_path)
    candidate_text = _read_text(request.candidate_root, rel_path)
    added_symbols: list[str] = []
    removed_symbols: list[str] = []
    parse_error: str | None = None

    if Path(rel_path).suffix == ".py":
        added_symbols, removed_symbols, parse_error = _symbol_delta(
            baseline_text=baseline_text,
            candidate_text=candidate_text,
        )

    coverage_status = _coverage_status(change_type, request.test_files)
    evidence = [request.input_artifacts["changed_files_manifest"]]
    if coverage_status == "covered":
        evidence.extend(request.test_files)

    return {
        "id": f"behavior-delta-{index:03d}",
        "target": rel_path,
        "change_type": change_type,
        "manifest_change_type": manifest_change_type,
        "intent": _intent_for(
            rel_path,
            primary_targets=request.primary_targets,
            supporting_targets=request.supporting_targets,
            test_files=request.test_files,
        ),
        "semantic_class": _semantic_class(
            change_type=change_type,
            manifest_change_type=manifest_change_type,
            contract_touches=contract_touches,
            added_symbols=added_symbols,
            removed_symbols=removed_symbols,
        ),
        "expected_direction": _expected_direction(contract_touches, change_type),
        "contract_touches": contract_touches,
        "behavior": _behavior_sentence(
            manifest_change_type=manifest_change_type,
            change_type=change_type,
            added_symbols=added_symbols,
            removed_symbols=removed_symbols,
            parse_error=parse_error,
        ),
        "evidence": evidence,
        "coverage_status": coverage_status,
        "risk": _risk_for(change_type, manifest_change_type),
        "details": _delta_details(
            rel_path=rel_path,
            baseline_text=baseline_text,
            candidate_text=candidate_text,
            added_symbols=added_symbols,
            removed_symbols=removed_symbols,
            parse_error=parse_error,
        ),
    }


def _risk_level(deltas: list[dict[str, Any]]) -> str:
    risk_level = "none"
    for delta in deltas:
        if _RISK_ORDER[delta["risk"]] > _RISK_ORDER[risk_level]:
            risk_level = delta["risk"]
    return risk_level


def _report_summary(
    changed_files_manifest: dict[str, Any],
    files: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "behavior_changed": bool(deltas),
        "changed_file_count": _summary_changed_file_count(changed_files_manifest, files),
        "delta_count": len(deltas),
        "intended_change_count": sum(1 for delta in deltas if delta["intent"] == "intended"),
        "unexpected_change_count": sum(1 for delta in deltas if delta["intent"] == "unexpected"),
        "unknown_intent_count": sum(1 for delta in deltas if delta["intent"] == "unknown"),
        "coverage_gap_count": sum(
            1 for delta in deltas if delta["coverage_status"] == "coverage_gap"
        ),
        "contract_touch_count": sum(
            1 for delta in deltas
            if any(touch not in {"documentation", "test_surface", "unknown"} for touch in delta["contract_touches"])
        ),
        "high_risk_delta_count": sum(1 for delta in deltas if delta["risk"] == "high"),
        "regression_count": 0,
        "risk_level": _risk_level(deltas),
    }


def build_behavior_delta_report(
    request: BehaviorDeltaRequest | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    request = coerce_request_or_kwargs(
        request=request,
        legacy_kwargs=kwargs,
        request_type=BehaviorDeltaRequest,
    )
    files = _manifest_files(request.changed_files_manifest)
    skipped_files: list[dict[str, str]] = []
    deltas = [
        delta
        for index, entry in enumerate(files, start=1)
        if (delta := _file_delta(request, entry, index=index, skipped_files=skipped_files)) is not None
    ]
    summary = _report_summary(request.changed_files_manifest, files, deltas)
    return {
        "$schema": BEHAVIOR_DELTA_SCHEMA_PATH,
        "run_id": request.run_id,
        "generated_at": request.generated_at,
        "policy": {
            "path": request.policy_path,
            "version": request.policy.get("version", "unknown"),
        },
        "primary_targets": sorted(request.primary_targets),
        "supporting_targets": sorted(request.supporting_targets),
        "test_files": sorted(request.test_files),
        "inputs": {
            "baseline_eval_report": request.input_artifacts["baseline_eval_report"],
            "candidate_eval_report": request.input_artifacts["candidate_eval_report"],
            "baseline_lint_report": request.input_artifacts["baseline_lint_report"],
            "candidate_lint_report": request.input_artifacts["candidate_lint_report"],
            "baseline_mechanism_report": request.input_artifacts["baseline_mechanism_report"],
            "candidate_mechanism_report": request.input_artifacts["candidate_mechanism_report"],
            "changed_files_manifest": request.input_artifacts["changed_files_manifest"],
        },
        "summary": summary,
        "deltas": deltas,
        "diagnostics": {
            "notes": [
                "v2-v4 behavior delta remains deterministic: intent is derived from declared run scope, contract touches from path policy, and regression_count is only populated by explicit future policy annotations."
            ],
            "skipped_files": skipped_files,
        },
    }


def write_behavior_delta_report(
    *,
    vault: Path,
    report_path: str,
    report: dict[str, Any],
) -> str:
    report = maybe_embed_run_artifact_envelope(
        vault,
        report_path,
        report,
        schema_path=BEHAVIOR_DELTA_SCHEMA_PATH,
    )
    write_vault_schema_validated_json(
        vault,
        report_path,
        report,
        BEHAVIOR_DELTA_SCHEMA_PATH,
        context=f"schema validation failed for {report_path}",
    )
    return report_path
