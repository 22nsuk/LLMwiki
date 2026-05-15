#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.promotion_gate_common_runtime import (
        PROMOTION_REPORT_SCHEMA,
        PromotionGateArtifactDecodeError,
        PromotionGateArtifactMissingError,
        PromotionGateArtifactSchemaError,
        PromotionGateError,
        PromotionGateInternalError,
        PromotionGatePolicyError,
        PromotionGateReportWriteError,
        PromotionGateUsageError,
        build_log,
        build_signoff,
        ensure_log_args_consistent,
        repo_relative_path,
    )
    from ops.scripts.promotion_decision_registry_runtime import decision_record_from_report
    from ops.scripts.promotion_gate_mechanism_runtime import (
        MechanismPromotionReportRequest,
        collect_mechanism_gate_inputs,
        mechanism_class_report as build_mechanism_class_report,
    )
    from ops.scripts.promotion_gate_page_runtime import (
        PageClassReportRequest,
        collect_page_gate_inputs,
        evaluate_stage2,
        evaluate_wiki,
        lint_wiki,
        page_class_report as build_page_class_report,
    )
else:
    from ops.scripts.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.policy_runtime import load_policy, report_path
    from .promotion_gate_common_runtime import (
        PROMOTION_REPORT_SCHEMA,
        PromotionGateArtifactDecodeError,
        PromotionGateArtifactMissingError,
        PromotionGateArtifactSchemaError,
        PromotionGateError,
        PromotionGateInternalError,
        PromotionGatePolicyError,
        PromotionGateReportWriteError,
        PromotionGateUsageError,
        build_log,
        build_signoff,
        ensure_log_args_consistent,
        repo_relative_path,
    )
    from ops.scripts.promotion_decision_registry_runtime import decision_record_from_report
    from .promotion_gate_mechanism_runtime import (
        MechanismPromotionReportRequest,
        collect_mechanism_gate_inputs,
        mechanism_class_report as build_mechanism_class_report,
    )
    from .promotion_gate_page_runtime import (
        PageClassReportRequest,
        collect_page_gate_inputs,
        evaluate_stage2,
        evaluate_wiki,
        lint_wiki,
        page_class_report as build_page_class_report,
    )

__all__ = [
    "PromotionGateArtifactDecodeError",
    "PromotionGateArtifactMissingError",
    "PromotionGateArtifactSchemaError",
    "build_log",
    "build_signoff",
    "main",
    "mechanism_class_report",
    "MechanismClassReportRequest",
    "page_class_report",
]


@dataclass(frozen=True)
class MechanismClassReportRequest:
    vault: Path
    run_id: str
    policy: dict
    resolved_policy_path: Path
    artifact_class: str
    primary_targets: list[str]
    supporting_targets: list[str]
    signoff: dict
    log: dict
    baseline_eval_path: str
    candidate_eval_path: str
    baseline_lint_path: str
    candidate_lint_path: str
    baseline_mechanism_path: str
    candidate_mechanism_path: str
    changed_files_manifest_path: str
    run_ledger_path: str
    behavior_delta_path: str | None = None
    auto_improve_run: bool = False


_MECHANISM_CLASS_REPORT_POSITIONAL_FIELDS = (
    "run_id",
    "policy",
    "resolved_policy_path",
    "artifact_class",
    "primary_targets",
    "supporting_targets",
    "signoff",
    "log",
    "baseline_eval_path",
    "candidate_eval_path",
    "baseline_lint_path",
    "candidate_lint_path",
    "baseline_mechanism_path",
    "candidate_mechanism_path",
    "changed_files_manifest_path",
    "run_ledger_path",
    "behavior_delta_path",
    "auto_improve_run",
)


def page_class_report(
    vault: Path,
    run_id: str,
    policy_path: str | None,
    policy: dict,
    resolved_policy_path: Path,
    artifact_class: str,
    primary_targets: list[str],
    supporting_targets: list[str],
    signoff: dict,
    log: dict,
) -> dict:
    lint_report = lint_wiki(vault, policy_path)
    eval_report = evaluate_wiki(vault, policy_path)
    stage2_report = evaluate_stage2(vault, policy_path)
    return build_page_class_report(
        PageClassReportRequest(
            vault=vault,
            run_id=run_id,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            artifact_class=artifact_class,
            primary_targets=primary_targets,
            supporting_targets=supporting_targets,
            signoff=signoff,
            log=log,
            lint_report=lint_report,
            eval_report=eval_report,
            stage2_report=stage2_report,
        )
    )


def _mechanism_class_report_request(
    vault_or_request: Path | MechanismClassReportRequest,
    legacy_args: tuple[Any, ...],
    legacy_fields: dict[str, Any],
) -> MechanismClassReportRequest:
    if isinstance(vault_or_request, MechanismClassReportRequest):
        if legacy_args or legacy_fields:
            raise TypeError("mechanism_class_report accepts either a request object or legacy arguments")
        return vault_or_request
    if len(legacy_args) > len(_MECHANISM_CLASS_REPORT_POSITIONAL_FIELDS):
        raise TypeError("too many positional arguments for mechanism_class_report")
    fields = dict(legacy_fields)
    for name, value in zip(_MECHANISM_CLASS_REPORT_POSITIONAL_FIELDS, legacy_args, strict=False):
        if name in fields:
            raise TypeError(f"mechanism_class_report got multiple values for argument '{name}'")
        fields[name] = value
    return MechanismClassReportRequest(vault=vault_or_request, **fields)


def _mechanism_gate_inputs(request: MechanismClassReportRequest):
    return collect_mechanism_gate_inputs(
        request.vault,
        request.baseline_eval_path,
        request.candidate_eval_path,
        request.baseline_lint_path,
        request.candidate_lint_path,
        request.baseline_mechanism_path,
        request.candidate_mechanism_path,
        request.changed_files_manifest_path,
        request.run_ledger_path,
        behavior_delta_path=request.behavior_delta_path,
    )


def mechanism_class_report(
    vault_or_request: Path | MechanismClassReportRequest,
    *legacy_args: Any,
    **legacy_fields: Any,
) -> dict:
    request = _mechanism_class_report_request(vault_or_request, legacy_args, legacy_fields)
    return build_mechanism_class_report(
        request=MechanismPromotionReportRequest(
            vault=request.vault,
            run_id=request.run_id,
            policy=request.policy,
            resolved_policy_path=request.resolved_policy_path,
            artifact_class=request.artifact_class,
            primary_targets=request.primary_targets,
            supporting_targets=request.supporting_targets,
            signoff=request.signoff,
            log=request.log,
            inputs=_mechanism_gate_inputs(request),
            auto_improve_run=request.auto_improve_run,
        )
    )


def write_report(vault: Path, report: dict, out_path: str | None) -> Path:
    try:
        if not (vault / PROMOTION_REPORT_SCHEMA).is_file():
            raise FileNotFoundError(PROMOTION_REPORT_SCHEMA)
        if "decision_record" in report:
            decision_record_from_report(report, require_record=True)
        return write_schema_backed_report(
            SchemaBackedReportWriteRequest(
                vault=vault,
                payload=report,
                schema_path=PROMOTION_REPORT_SCHEMA,
                out_path=out_path,
                default_relative_path=f"runs/{report['run_id']}/promotion-report.json",
                context="promotion report schema validation failed",
                trailing_newline=False,
            )
        )
    except FileNotFoundError as exc:
        raise PromotionGateReportWriteError(
            f"missing schema for promotion report validation: {PROMOTION_REPORT_SCHEMA}"
        ) from exc
    except ValueError as exc:
        raise PromotionGateReportWriteError(str(exc)) from exc
    except OSError as exc:
        raise PromotionGateReportWriteError(f"failed to write promotion report: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument(
        "--artifact-class",
        required=True,
        choices=[
            "wiki_source",
            "wiki_concept",
            "wiki_synthesis",
            "wiki_query",
            "system_page",
            "system_mechanism",
        ],
    )
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--primary-target", action="append", required=True)
    ap.add_argument("--supporting-target", action="append", default=[])
    ap.add_argument("--log-summary", required=True)
    ap.add_argument("--out")
    ap.add_argument("--require-signoff", action="store_true")
    ap.add_argument(
        "--signoff-status",
        choices=["pending", "approved", "rejected", "not_required"],
    )
    ap.add_argument("--signoff-by")
    ap.add_argument("--signoff-ts")
    ap.add_argument("--log-recorded", action="store_true")
    ap.add_argument("--log-entry-ref")
    ap.add_argument("--baseline-eval-report")
    ap.add_argument("--candidate-eval-report")
    ap.add_argument("--baseline-lint-report")
    ap.add_argument("--candidate-lint-report")
    ap.add_argument("--baseline-mechanism-report")
    ap.add_argument("--candidate-mechanism-report")
    ap.add_argument("--changed-files-manifest")
    ap.add_argument("--behavior-delta")
    ap.add_argument("--auto-improve-run", action="store_true")
    ap.add_argument("--run-ledger")
    return ap.parse_args(argv)


def _load_policy_or_raise(vault: Path, policy_path: str | None) -> tuple[dict, Path]:
    try:
        return load_policy(vault, policy_path)
    except FileNotFoundError as exc:
        missing_path = policy_path or "ops/policies/wiki-maintainer-policy.yaml"
        raise PromotionGatePolicyError(f"missing policy: {missing_path}") from exc
    except ValueError as exc:
        raise PromotionGatePolicyError(str(exc)) from exc


def _required_mechanism_args(args: argparse.Namespace) -> tuple[str, str, str, str, str, str, str]:
    missing_args = [
        name for name, value in (
            ("--baseline-eval-report", args.baseline_eval_report),
            ("--candidate-eval-report", args.candidate_eval_report),
            ("--baseline-lint-report", args.baseline_lint_report),
            ("--candidate-lint-report", args.candidate_lint_report),
            ("--baseline-mechanism-report", args.baseline_mechanism_report),
            ("--candidate-mechanism-report", args.candidate_mechanism_report),
            ("--changed-files-manifest", args.changed_files_manifest),
        )
        if not value
    ]
    if missing_args:
        raise PromotionGateUsageError(
            "missing required arguments for system_mechanism: "
            + ", ".join(missing_args)
        )
    return (
        args.baseline_eval_report,
        args.candidate_eval_report,
        args.baseline_lint_report,
        args.candidate_lint_report,
        args.baseline_mechanism_report,
        args.candidate_mechanism_report,
        args.changed_files_manifest,
    )


def _build_report(args: argparse.Namespace) -> tuple[Path, dict]:
    vault = Path(args.vault).resolve()
    ensure_log_args_consistent(args)
    policy, resolved_policy_path = _load_policy_or_raise(vault, args.policy)
    signoff = build_signoff(policy, args.artifact_class, args)
    log = build_log(policy, args)
    primary_targets = [repo_relative_path(vault, target) for target in args.primary_target]
    supporting_targets = [repo_relative_path(vault, target) for target in args.supporting_target]
    artifact_kind = policy["promotion_policy"]["artifact_classes"][args.artifact_class]["kind"]

    if artifact_kind == "page":
        lint_report, eval_report, stage2_report = collect_page_gate_inputs(vault, args.policy)
        report = build_page_class_report(
            PageClassReportRequest(
                vault=vault,
                run_id=args.run_id,
                policy=policy,
                resolved_policy_path=resolved_policy_path,
                artifact_class=args.artifact_class,
                primary_targets=primary_targets,
                supporting_targets=supporting_targets,
                signoff=signoff,
                log=log,
                lint_report=lint_report,
                eval_report=eval_report,
                stage2_report=stage2_report,
            )
        )
        return vault, report

    (
        baseline_eval_path,
        candidate_eval_path,
        baseline_lint_path,
        candidate_lint_path,
        baseline_mechanism_path,
        candidate_mechanism_path,
        changed_files_manifest_path,
    ) = _required_mechanism_args(args)
    run_ledger_path = args.run_ledger or f"runs/{args.run_id}/run-ledger.json"
    inputs = collect_mechanism_gate_inputs(
        vault,
        baseline_eval_path,
        candidate_eval_path,
        baseline_lint_path,
        candidate_lint_path,
        baseline_mechanism_path,
        candidate_mechanism_path,
        changed_files_manifest_path,
        run_ledger_path,
        behavior_delta_path=args.behavior_delta,
    )
    report = build_mechanism_class_report(
        request=MechanismPromotionReportRequest(
            vault=vault,
            run_id=args.run_id,
            policy=policy,
            resolved_policy_path=resolved_policy_path,
            artifact_class=args.artifact_class,
            primary_targets=primary_targets,
            supporting_targets=supporting_targets,
            signoff=signoff,
            log=log,
            inputs=inputs,
            auto_improve_run=args.auto_improve_run,
        )
    )
    return vault, report


def _print_error_and_exit(exc: PromotionGateError) -> None:
    print(str(exc), file=sys.stderr)
    raise SystemExit(exc.exit_code)


def main(argv: list[str] | None = None) -> None:
    try:
        args = parse_args(argv)
        vault, report = _build_report(args)
        destination = write_report(vault, report, args.out)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\nwritten_to={report_path(vault, destination)}")
    except PromotionGateError as exc:
        _print_error_and_exit(exc)
    except Exception as exc:  # broad-exception: cli_boundary
        _print_error_and_exit(PromotionGateInternalError(str(exc)))


if __name__ == "__main__":
    main()
