from __future__ import annotations

import hashlib
from pathlib import Path

from .observability_artifacts_shared_runtime import (
    load_optional_json,
    run_dir_candidates,
    run_rel,
    write_schema_backed_json,
)
from .policy_runtime import report_path
from .run_artifact_envelope_runtime import maybe_embed_run_artifact_envelope
from .runtime_context import RuntimeContext
from .schema_constants_runtime import (
    BEHAVIOR_DELTA_SCHEMA_PATH,
    CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH,
    CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    COMMAND_LOG_SUMMARY_SCHEMA_PATH,
    EVAL_REPORT_SCHEMA_PATH,
    EXECUTOR_REPORT_SCHEMA_PATH,
    GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH,
    IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH,
    LINT_REPORT_SCHEMA_PATH,
    MECHANISM_ASSESSMENT_SCHEMA_PATH,
    PLANNING_VALIDATION_SCHEMA_PATH,
    PROMOTION_REPORT_SCHEMA_PATH,
    PROPOSAL_SCOPE_SCHEMA_PATH,
    PROPOSAL_SNAPSHOT_SCHEMA_PATH,
    ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
    RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH,
    RUN_LEDGER_SCHEMA_PATH,
    RUN_TELEMETRY_SCHEMA_PATH,
    SEED_SCHEMA_PATH,
    SHADOW_APPLY_REPORT_SCHEMA_PATH,
    STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
    SUBAGENT_ROUTING_SCHEMA_PATH,
    TIMEOUT_FAILURE_SCHEMA_PATH,
)

RUN_ARTIFACT_FINGERPRINT = RUN_ARTIFACT_FINGERPRINT_SCHEMA_PATH

RUN_FILE_SCHEMAS = {
    "seed.yaml": SEED_SCHEMA_PATH,
    "planning-validation.json": PLANNING_VALIDATION_SCHEMA_PATH,
    "run-ledger.json": RUN_LEDGER_SCHEMA_PATH,
    "promotion-report.json": PROMOTION_REPORT_SCHEMA_PATH,
    "proposal-snapshot.json": PROPOSAL_SNAPSHOT_SCHEMA_PATH,
    "improvement-observations.json": IMPROVEMENT_OBSERVATIONS_SCHEMA_PATH,
    "changed-files-manifest.json": CHANGED_FILES_MANIFEST_SCHEMA_PATH,
    "candidate-changed-files-snapshot.json": CANDIDATE_CHANGED_FILES_SNAPSHOT_SCHEMA_PATH,
    "shadow-apply-report.json": SHADOW_APPLY_REPORT_SCHEMA_PATH,
    "rollback-rehearsal-report.json": ROLLBACK_REHEARSAL_REPORT_SCHEMA_PATH,
    "behavior-delta.json": BEHAVIOR_DELTA_SCHEMA_PATH,
    "structural-complexity-budget.json": STRUCTURAL_COMPLEXITY_BUDGET_REPORT_SCHEMA_PATH,
    "generated-artifact-convergence.json": GENERATED_ARTIFACT_CONVERGENCE_SCHEMA_PATH,
    "baseline-eval.json": EVAL_REPORT_SCHEMA_PATH,
    "candidate-eval.json": EVAL_REPORT_SCHEMA_PATH,
    "baseline-lint.json": LINT_REPORT_SCHEMA_PATH,
    "candidate-lint.json": LINT_REPORT_SCHEMA_PATH,
    "baseline-mechanism-assessment.json": MECHANISM_ASSESSMENT_SCHEMA_PATH,
    "candidate-mechanism-assessment.json": MECHANISM_ASSESSMENT_SCHEMA_PATH,
    "scope-freeze.json": PROPOSAL_SCOPE_SCHEMA_PATH,
    "run-telemetry.json": RUN_TELEMETRY_SCHEMA_PATH,
    "command-log-summary.json": COMMAND_LOG_SUMMARY_SCHEMA_PATH,
}


def _artifact_schema(rel_path: str) -> str:
    filename = Path(rel_path).name
    if filename in RUN_FILE_SCHEMAS:
        return RUN_FILE_SCHEMAS[filename]
    if filename.startswith("subagent-routing.") and filename.endswith(".json"):
        return SUBAGENT_ROUTING_SCHEMA_PATH
    if filename.endswith("-executor-report.json"):
        return EXECUTOR_REPORT_SCHEMA_PATH
    if filename.endswith("-timeout-failure.json"):
        return TIMEOUT_FAILURE_SCHEMA_PATH
    return ""


def _artifact_role(rel_path: str) -> str:
    filename = Path(rel_path).name
    if filename.endswith(".stdout.txt"):
        return "command_stdout"
    if filename.endswith(".stderr.txt"):
        return "command_stderr"
    if filename.endswith("-trace.txt"):
        return "command_log_trace"
    if filename == "command-log-summary.json":
        return "command_log_summary"
    if filename.startswith("subagent-routing.") and filename.endswith(".json"):
        return "subagent_routing_report"
    if filename.endswith("-executor-report.json"):
        return "executor_report"
    if filename.endswith("-timeout-failure.json"):
        return "timeout_failure"
    role = filename.removesuffix(".json").removesuffix(".yaml").removesuffix(".md")
    return role.replace("-", "_") or "artifact"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_dir(vault: Path, run_id: str, *, run_root_rel: str | None = None) -> Path:
    if run_root_rel:
        return vault / run_root_rel.strip("/")
    candidates = run_dir_candidates(vault, run_id)
    if candidates:
        return candidates[0]
    return vault / "runs" / run_id


def _run_artifact_fingerprint_rel_path(
    vault: Path,
    run_id: str,
    *,
    run_root_rel: str | None = None,
) -> str:
    run_dir = _run_dir(vault, run_id, run_root_rel=run_root_rel)
    return report_path(vault, run_dir / "run-artifact-fingerprint.json") or run_rel(
        run_id, "run-artifact-fingerprint.json"
    )


def _is_archived_run_dir(vault: Path, run_dir: Path) -> bool:
    try:
        run_dir.resolve().relative_to((vault / "runs" / "archive").resolve())
    except ValueError:
        return False
    return True


def _empty_provenance_snapshot() -> dict[str, object]:
    return {
        "report_path": "ops/reports/supply-chain-provenance.json",
        "report_sha256": "",
        "report_generated_at": "",
        "report_status": "",
        "exists_at_run_start": False,
    }


def build_run_artifact_fingerprint(
    vault: Path,
    run_id: str,
    *,
    context: RuntimeContext,
    run_root_rel: str | None = None,
) -> dict:
    run_dir = _run_dir(vault, run_id, run_root_rel=run_root_rel)
    fingerprint_rel_path = _run_artifact_fingerprint_rel_path(
        vault,
        run_id,
        run_root_rel=run_root_rel,
    )
    artifacts = []
    total_size = 0
    schema_backed_count = 0
    if run_dir.exists():
        for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
            rel_path = report_path(vault, path)
            if rel_path == fingerprint_rel_path:
                continue
            schema_rel = _artifact_schema(rel_path)
            size = path.stat().st_size
            total_size += size
            if schema_rel:
                schema_backed_count += 1
            artifacts.append(
                {
                    "path": rel_path,
                    "artifact_role": _artifact_role(rel_path),
                    "schema": schema_rel,
                    "size_bytes": size,
                    "sha256": _sha256(path),
                }
            )

    provenance_path = vault / "ops" / "reports" / "supply-chain-provenance.json"
    provenance_snapshot = _empty_provenance_snapshot()
    if not _is_archived_run_dir(vault, run_dir) and provenance_path.exists():
        provenance_payload = load_optional_json(provenance_path) or {}
        provenance_snapshot["report_sha256"] = _sha256(provenance_path)
        provenance_snapshot["report_generated_at"] = str(provenance_payload.get("generated_at", ""))
        provenance_snapshot["report_status"] = str(provenance_payload.get("status", ""))
        provenance_snapshot["exists_at_run_start"] = True

    return {
        "$schema": RUN_ARTIFACT_FINGERPRINT,
        "scope": "run",
        "run_id": run_id,
        "generated_at": context.isoformat_z(),
        "repo_provenance_snapshot": provenance_snapshot,
        "summary": {
            "artifact_count": len(artifacts),
            "schema_backed_count": schema_backed_count,
            "total_size_bytes": total_size,
        },
        "artifacts": artifacts,
    }


def write_run_artifact_fingerprint(
    vault: Path,
    run_id: str,
    *,
    context: RuntimeContext,
    run_root_rel: str | None = None,
) -> str:
    payload = build_run_artifact_fingerprint(
        vault,
        run_id,
        context=context,
        run_root_rel=run_root_rel,
    )
    rel_path = _run_artifact_fingerprint_rel_path(
        vault,
        run_id,
        run_root_rel=run_root_rel,
    )
    payload = maybe_embed_run_artifact_envelope(
        vault,
        rel_path,
        payload,
        schema_path=RUN_ARTIFACT_FINGERPRINT,
    )
    return write_schema_backed_json(
        vault,
        rel_path,
        payload,
        RUN_ARTIFACT_FINGERPRINT,
        context=f"schema validation failed for {rel_path}",
    )
