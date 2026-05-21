from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import subprocess
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import SchemaBackedReportWriteRequest, write_schema_backed_report
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.source_tree_fingerprint_runtime import release_source_tree_fingerprint


DEFAULT_OUT = "tmp/goal-runtime-closeout-plan.json"
DEFAULT_CANDIDATE_ROOT = "runs/goal-auto-improve-trial/state/closeout"
PRODUCER = "ops.scripts.goal_runtime_closeout"
SCHEMA_PATH = "ops/schemas/goal-runtime-closeout-plan.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.goal_runtime_closeout --vault ."

CANDIDATE_SETUP_TARGETS = (
    "report-schema-samples-check",
    "goal-runtime-clean-transient",
    "goal-runtime-local-evidence-converge",
)
CANDIDATE_REPORT_TARGETS = (
    "goal-runtime-closeout-candidate-script-output-surfaces",
    "goal-runtime-closeout-candidate-generated-artifact-index",
    "goal-runtime-closeout-candidate-artifact-freshness",
)
GOAL_RUNTIME_CANDIDATE_CONVERGE_TARGET = "goal-runtime-closeout-candidate-converge"
GOAL_RUNTIME_PUBLISH_TARGET = "goal-runtime-closeout-publish"
GOAL_RUNTIME_FINALIZE_TARGET = "goal-runtime-closeout-finalize"
CANDIDATE_CONVERGE_TARGETS = (
    *CANDIDATE_SETUP_TARGETS,
    *CANDIDATE_REPORT_TARGETS,
)
PUBLISH_TARGETS = (
    "goal-runtime-closeout-publish-script-output-surfaces",
    "goal-runtime-publish-local-evidence",
    "goal-runtime-certificate",
    "generated-artifact-converge",
)
POST_PUBLISH_FINALIZATION_TARGETS = (
    "test-artifact-finalization",
    "goal-runtime-fixed-point-check",
)
GENERATED_DIRTY_PREFIXES = (
    "build/",
    "external-reports/",
    "ops/operator/",
    "ops/reports/",
    "runs/",
    "tmp/",
)
GENERATED_DIRTY_FILES = {
    "ops/manifest.json",
    "ops/raw-registry.json",
    "ops/script-output-surfaces.json",
}


@dataclass(frozen=True)
class EvidenceReport:
    phase_id: str
    path: str
    target: str
    expensive: bool
    requires_source_fingerprint: bool = True


@dataclass(frozen=True)
class GoalRuntimeCloseoutRequest:
    vault: Path
    out_path: str | None = None
    policy_path: str | None = None
    budget: str = "cheap"
    candidate_root: str = DEFAULT_CANDIDATE_ROOT
    context: RuntimeContext | None = None


EVIDENCE_REPORTS = (
    EvidenceReport(
        phase_id="release_smoke",
        path="ops/reports/release-smoke-report.json",
        target="release-smoke-full-reuse",
        expensive=True,
    ),
    EvidenceReport(
        phase_id="source_package",
        path="ops/reports/source-package-clean-extract.json",
        target="release-source-package-check",
        expensive=True,
    ),
    EvidenceReport(
        phase_id="public_check",
        path="ops/reports/public-check-summary.json",
        target="public-check-summary",
        expensive=True,
    ),
    EvidenceReport(
        phase_id="full_suite",
        path="ops/reports/test-execution-summary-full.json",
        target="test-execution-summary-full-refresh",
        expensive=True,
    ),
)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _git_status_entries(vault: Path) -> tuple[str, list[dict[str, str]]]:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
            cwd=vault,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return "unavailable", []
    if completed.returncode != 0:
        return "unavailable", []

    entries: list[dict[str, str]] = []
    for raw_line in completed.stdout.splitlines():
        if len(raw_line) < 4:
            continue
        status = raw_line[:2]
        raw_path = raw_line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        path = raw_path.replace("\\", "/")
        entries.append(
            {
                "path": path,
                "status": status.strip() or "modified",
                "category": _dirty_path_category(path),
            }
        )
    return ("clean" if not entries else "dirty"), entries


def _dirty_path_category(path: str) -> str:
    if path in GENERATED_DIRTY_FILES:
        return "generated"
    if any(path.startswith(prefix) for prefix in GENERATED_DIRTY_PREFIXES):
        return "generated"
    return "source"


def _report_is_pass(payload: dict[str, Any]) -> bool:
    return str(payload.get("status", "")).strip() == "pass"


def _report_is_current(payload: dict[str, Any], source_fingerprint: str, report: EvidenceReport) -> bool:
    if not _report_is_pass(payload):
        return False
    currentness = payload.get("currentness")
    if isinstance(currentness, dict) and currentness.get("status") != "current":
        return False
    if not report.requires_source_fingerprint:
        return True
    return str(payload.get("source_tree_fingerprint", "")).strip() == source_fingerprint


def _decision(
    phase_id: str,
    *,
    phase_group: str,
    decision: str,
    target: str,
    reason: str,
    budget_class: str,
    report_path: str = "",
    observed_status: str = "",
    observed_source_tree_fingerprint: str = "",
) -> dict[str, Any]:
    return {
        "phase_id": phase_id,
        "phase_group": phase_group,
        "decision": decision,
        "target": target,
        "reason": reason,
        "budget_class": budget_class,
        "report_path": report_path,
        "observed_status": observed_status,
        "observed_source_tree_fingerprint": observed_source_tree_fingerprint,
    }


def _phase_id(prefix: str, target: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in target.lower()).strip("_")
    return f"{prefix}_{normalized}"


def _candidate_root_path(candidate_root: str) -> str:
    normalized = Path(str(candidate_root).strip() or DEFAULT_CANDIDATE_ROOT).as_posix().strip("/")
    return normalized or DEFAULT_CANDIDATE_ROOT


def _candidate_outputs(candidate_root: str) -> dict[str, str]:
    root = _candidate_root_path(candidate_root)
    return {
        "script_output_surfaces": f"{root}/script-output-surfaces.json",
        "generated_artifact_index": f"{root}/generated-artifact-index.json",
        "artifact_freshness": f"{root}/artifact-freshness-report.json",
    }


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _evidence_decisions(
    vault: Path,
    *,
    source_fingerprint: str,
    budget: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    decisions: list[dict[str, Any]] = []
    targets: list[str] = []
    for report in EVIDENCE_REPORTS:
        payload = _load_json_object(vault / report.path)
        observed_status = str(payload.get("status", "")).strip()
        observed_source_tree_fingerprint = str(payload.get("source_tree_fingerprint", "")).strip()
        if _report_is_current(payload, source_fingerprint, report):
            decisions.append(
                _decision(
                    report.phase_id,
                    phase_group="expensive_evidence",
                    decision="reuse",
                    target=report.target,
                    reason="passing evidence already matches the current source fingerprint",
                    budget_class="expensive" if report.expensive else "cheap",
                    report_path=report.path,
                    observed_status=observed_status,
                    observed_source_tree_fingerprint=observed_source_tree_fingerprint,
                )
            )
            continue
        if report.expensive and budget != "full":
            decisions.append(
                _decision(
                    report.phase_id,
                    phase_group="expensive_evidence",
                    decision="blocked_by_budget",
                    target=report.target,
                    reason="expensive evidence is required but the cheap closeout budget forbids it",
                    budget_class="expensive",
                    report_path=report.path,
                    observed_status=observed_status,
                    observed_source_tree_fingerprint=observed_source_tree_fingerprint,
                )
            )
            continue
        decisions.append(
            _decision(
                report.phase_id,
                phase_group="expensive_evidence",
                decision="run",
                target=report.target,
                reason="evidence is missing, failing, stale, or tied to a different source fingerprint",
                budget_class="expensive" if report.expensive else "cheap",
                report_path=report.path,
                observed_status=observed_status,
                observed_source_tree_fingerprint=observed_source_tree_fingerprint,
            )
        )
        targets.append(report.target)
    return decisions, targets


def _summary(
    *,
    source_dirty_count: int,
    generated_dirty_count: int,
    decisions: list[dict[str, Any]],
    targets: list[str],
) -> dict[str, Any]:
    blocked_by_budget_count = sum(1 for item in decisions if item["decision"] == "blocked_by_budget")
    expensive_run_count = sum(
        1
        for item in decisions
        if item["decision"] == "run" and item["budget_class"] == "expensive"
    )
    reuse_count = sum(1 for item in decisions if item["decision"] == "reuse")
    return {
        "status": "attention" if blocked_by_budget_count else "pass",
        "target_count": len(targets),
        "run_target_count": sum(1 for item in decisions if item["decision"] == "run"),
        "reuse_count": reuse_count,
        "blocked_by_budget_count": blocked_by_budget_count,
        "expensive_run_count": expensive_run_count,
        "source_dirty_count": source_dirty_count,
        "generated_dirty_count": generated_dirty_count,
        "full_suite_required": any(
            item["phase_id"] == "full_suite" and item["decision"] in {"run", "blocked_by_budget"}
            for item in decisions
        ),
        "release_smoke_required": any(
            item["phase_id"] == "release_smoke" and item["decision"] in {"run", "blocked_by_budget"}
            for item in decisions
        ),
    }


def _has_budget_block(decisions: list[dict[str, Any]]) -> bool:
    return any(item["decision"] == "blocked_by_budget" for item in decisions)


def _transaction_contract(*, budget: str, candidate_root: str) -> dict[str, Any]:
    return {
        "mode": "run_local_candidate_then_publish_once",
        "candidate_root": _candidate_root_path(candidate_root),
        "candidate_outputs": _candidate_outputs(candidate_root),
        "candidate_convergence_target": GOAL_RUNTIME_CANDIDATE_CONVERGE_TARGET,
        "candidate_targets": list(CANDIDATE_CONVERGE_TARGETS),
        "expensive_evidence_budget": {
            "mode": budget,
            "allowed": budget == "full",
            "max_full_suite_runs_per_source_fingerprint": 1,
            "max_release_smoke_runs_per_source_fingerprint": 1,
        },
        "publish_boundary": {
            "target": GOAL_RUNTIME_PUBLISH_TARGET,
            "canonical_publish_targets": list(PUBLISH_TARGETS),
            "canonical_publish_count": 1,
            "after_phase_group": "expensive_evidence",
            "before_phase_group": "post_publish_finalization",
        },
        "post_publish_finalization_target": GOAL_RUNTIME_FINALIZE_TARGET,
        "post_publish_finalization_targets": list(POST_PUBLISH_FINALIZATION_TARGETS),
        "fixed_point": {
            "candidate_check_target": "goal-runtime-local-fixed-point-check",
            "canonical_check_target": "goal-runtime-fixed-point-check",
            "max_candidate_convergence_passes": 3,
        },
        "forbidden_default_targets": [
            "release-smoke-full",
            "release-smoke-full-reuse",
            "test-execution-summary-full-refresh",
        ]
        if budget == "cheap"
        else [],
    }


def build_report(request: GoalRuntimeCloseoutRequest) -> dict[str, Any]:
    vault = request.vault.resolve()
    policy, resolved_policy_path = load_policy(vault, request.policy_path)
    context = request.context or RuntimeContext.from_policy(policy)
    source_fingerprint = release_source_tree_fingerprint(vault)
    git_status, git_entries = _git_status_entries(vault)
    source_dirty_count = sum(1 for item in git_entries if item["category"] == "source")
    generated_dirty_count = sum(1 for item in git_entries if item["category"] == "generated")

    decisions: list[dict[str, Any]] = []
    decisions.extend(
        _decision(
            _phase_id("candidate_converge", target),
            phase_group="candidate_convergence",
            decision="run",
            target=target,
            reason=(
                "run-local candidate artifact convergence runs after transient cleanup and local evidence convergence"
                if target in CANDIDATE_REPORT_TARGETS
                else "run-local setup and goal/readiness/session/backlog evidence must converge before canonical publish"
            ),
            budget_class="cheap",
        )
        for target in CANDIDATE_CONVERGE_TARGETS
    )
    targets = [GOAL_RUNTIME_CANDIDATE_CONVERGE_TARGET]

    evidence_decisions, evidence_targets = _evidence_decisions(
        vault,
        source_fingerprint=source_fingerprint,
        budget=request.budget,
    )
    decisions.extend(evidence_decisions)
    targets.extend(evidence_targets)
    publish_ready = not _has_budget_block(evidence_decisions)
    if publish_ready:
        decisions.extend(
            _decision(
                _phase_id("publish", target),
                phase_group="canonical_publish",
                decision="run",
                target=target,
                reason="canonical reports are promoted after candidate convergence and any required expensive evidence",
                budget_class="cheap",
            )
            for target in PUBLISH_TARGETS
        )
        targets.append(GOAL_RUNTIME_PUBLISH_TARGET)
        decisions.extend(
            _decision(
                _phase_id("finalization", target),
                phase_group="post_publish_finalization",
                decision="run",
                target=target,
                reason="lightweight finalization closes generated/self-reference drift after the single publish boundary",
                budget_class="cheap",
            )
            for target in POST_PUBLISH_FINALIZATION_TARGETS
        )
        targets.append(GOAL_RUNTIME_FINALIZE_TARGET)
    else:
        decisions.extend(
            _decision(
                _phase_id("publish", target),
                phase_group="canonical_publish",
                decision="skip",
                target=target,
                reason="canonical publish is skipped until stale expensive evidence is refreshed with the full closeout budget",
                budget_class="cheap",
            )
            for target in PUBLISH_TARGETS
        )
        decisions.extend(
            _decision(
                _phase_id("finalization", target),
                phase_group="post_publish_finalization",
                decision="skip",
                target=target,
                reason="post-publish finalization is skipped because the publish boundary was not entered",
                budget_class="cheap",
            )
            for target in POST_PUBLISH_FINALIZATION_TARGETS
        )
    recommended_targets = _dedupe_preserve_order(targets)
    summary = _summary(
        source_dirty_count=source_dirty_count,
        generated_dirty_count=generated_dirty_count,
        decisions=decisions,
        targets=recommended_targets,
    )
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=context.isoformat_z(),
            artifact_kind="goal_runtime_closeout_plan",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/mechanism/goal_runtime_closeout.py",
                "ops/schemas/goal-runtime-closeout-plan.schema.json",
                "mk/mechanism.mk",
            ],
            file_inputs={
                report.phase_id: report.path
                for report in EVIDENCE_REPORTS
                if (vault / report.path).exists()
            },
            text_inputs={
                "budget": request.budget,
                "source_fingerprint": source_fingerprint,
            },
            source_tree_excluded_files=(request.out_path or DEFAULT_OUT,),
        ),
        "vault": report_path(vault, vault),
        "status": summary["status"],
        "budget": {
            "mode": request.budget,
            "full_suite_max_runs": 1,
            "expensive_evidence_allowed": request.budget == "full",
            "cheap_closeout_never_runs_full_suite": request.budget == "cheap",
        },
        "transaction": _transaction_contract(
            budget=request.budget,
            candidate_root=request.candidate_root,
        ),
        "source_snapshot": {
            "source_tree_fingerprint": source_fingerprint,
            "git_status": git_status,
            "source_dirty_count": source_dirty_count,
            "generated_dirty_count": generated_dirty_count,
            "generated_dirty_allowed_during_candidate_convergence": True,
            "dirty_entries": git_entries,
        },
        "summary": summary,
        "phase_decisions": decisions,
        "recommended_targets": recommended_targets,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="goal runtime closeout plan schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default=".", help="Repository/vault root.")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output plan path.")
    parser.add_argument("--policy-path", default=None, help="Policy path relative to the vault.")
    parser.add_argument("--budget", choices=("cheap", "full"), default="cheap")
    parser.add_argument("--candidate-root", default=DEFAULT_CANDIDATE_ROOT)
    parser.add_argument("--format", choices=("json", "targets"), default="json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        GoalRuntimeCloseoutRequest(
            vault=vault,
            out_path=args.out,
            policy_path=args.policy_path,
            budget=args.budget,
            candidate_root=args.candidate_root,
        )
    )
    if args.format == "targets":
        for target in report["recommended_targets"]:
            print(target)
        return 0
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
