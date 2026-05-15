from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    load_optional_json_object,
    write_schema_backed_report,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.runtime_context import RuntimeContext


DEFAULT_OUT = "ops/reports/learning-confirmed-legacy-reconstruction.json"
PRODUCER = "ops.scripts.learning_confirmed_legacy_reconstruction"
SCHEMA_PATH = "ops/schemas/learning-confirmed-legacy-reconstruction.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.learning_confirmed_legacy_reconstruction --vault ."
MECHANISM_REVIEW_CANDIDATES_PATH = "ops/reports/mechanism-review-candidates.json"
MUTATION_PROPOSALS_PATH = "ops/reports/mutation-proposals.json"
HEX_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")
SAME_EVAL_PROPOSAL_FAILURE_MODES = {
    "repeated_same_eval_or_discard",
    "repeated_same_eval_after_promote",
    "repeated_discard_runs",
}


def _sha256_file(path: Path | None) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path else ""
    except OSError:
        return ""


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _target_key(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _same_eval_proposals(mutation_proposals: dict[str, Any]) -> list[dict[str, Any]]:
    proposals = mutation_proposals.get("proposals", [])
    if not isinstance(proposals, list):
        return []
    return [
        proposal
        for proposal in proposals
        if isinstance(proposal, dict)
        and str(proposal.get("failure_mode", "")).strip() in SAME_EVAL_PROPOSAL_FAILURE_MODES
    ]


def _proposal_group_family(proposal: dict[str, Any]) -> str:
    family = str(proposal.get("family", "")).strip()
    if family:
        return family
    failure_mode = str(proposal.get("failure_mode", "")).strip()
    return failure_mode or str(proposal.get("expected_change", "unknown")).strip() or "unknown"


def _proposal_families(mutation_proposals: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for proposal in _same_eval_proposals(mutation_proposals):
        family = _proposal_group_family(proposal)
        if family not in families:
            families.append(family)
    return families


def _proposal_target_keys(mutation_proposals: dict[str, Any]) -> set[tuple[str, ...]]:
    return {
        key
        for proposal in _same_eval_proposals(mutation_proposals)
        for key in [_target_key(proposal.get("primary_targets"))]
        if key
    }


def _confirmed_run_family_map(
    mutation_proposals: dict[str, Any],
    mechanism_review: dict[str, Any],
) -> dict[str, list[str]]:
    active_families = set(_proposal_families(mutation_proposals))
    active_targets = _proposal_target_keys(mutation_proposals)
    mapping: dict[str, list[str]] = {}
    candidates = mechanism_review.get("candidates", [])
    if not isinstance(candidates, list):
        return mapping
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        family = str(candidate.get("family", "")).strip()
        primary_targets = _target_key(candidate.get("primary_targets"))
        if active_families and family not in active_families and primary_targets not in active_targets:
            continue
        if not family:
            family = "unknown"
        for run_id in _string_list(candidate.get("run_ids")):
            mapping.setdefault(run_id, [])
            if family not in mapping[run_id]:
                mapping[run_id].append(family)
    return mapping


def _run_file(vault: Path, run_id: str, filename: str) -> Path | None:
    candidates = [
        vault / "runs" / run_id / filename,
        vault / "runs" / "archive" / run_id / filename,
    ]
    for path in candidates:
        if path.is_file():
            return path
    matches = sorted((vault / "runs").glob(f"**/{run_id}/{filename}"))
    return matches[0] if matches else None


def _behavior_delta_path(telemetry: dict[str, Any], promotion_report: dict[str, Any]) -> str:
    telemetry_path = str(telemetry.get("behavior_delta", "")).strip()
    if telemetry_path:
        return telemetry_path
    inputs = promotion_report.get("inputs") if isinstance(promotion_report, dict) else {}
    if isinstance(inputs, dict):
        return str(inputs.get("behavior_delta", "")).strip()
    return ""


def _secondary_axes_from_text(value: str) -> list[str]:
    if "selected_axes=" not in value:
        return []
    tail = value.split("selected_axes=", 1)[1].strip()
    if tail.startswith("[") and "]" in tail:
        tail = tail[1 : tail.index("]")]
    else:
        tail = tail.split(",", 1)[0].strip()
    tail = tail.strip("[](){}")
    return [
        item.strip().strip("'\"")
        for item in tail.split(",")
        if item.strip().strip("'\"")
    ]


def _promotion_secondary_improvement(promotion_report: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    axes = _string_list(promotion_report.get("secondary_improvement_axes"))
    strict = bool(promotion_report.get("strict_secondary_improvement_present"))
    evidence = {
        "source": "promotion_report_fields" if (strict or axes) else "missing",
        "check_id": "",
        "detail": "",
        "strict_signal": strict,
        "axes": axes,
    }
    checks = promotion_report.get("checks", [])
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict) or check.get("id") != "equal_score_secondary_eligibility":
                continue
            detail = str(check.get("detail", ""))
            inferred_axes = _secondary_axes_from_text(detail)
            if inferred_axes and not axes:
                axes = inferred_axes
            if "selected_any_improvement=true" in detail:
                strict = True
            if inferred_axes or "selected_any_improvement=true" in detail:
                evidence = {
                    "source": "promotion_report_check_detail",
                    "check_id": "equal_score_secondary_eligibility",
                    "detail": detail,
                    "strict_signal": "selected_any_improvement=true" in detail,
                    "axes": axes,
                }
    if strict or axes:
        evidence["strict_signal"] = strict
        evidence["axes"] = axes
    return strict, axes, evidence


def _reconstruction_row(vault: Path, run_id: str, families: list[str]) -> dict[str, Any]:
    telemetry_path = _run_file(vault, run_id, "run-telemetry.json")
    promotion_path = _run_file(vault, run_id, "promotion-report.json")
    telemetry = load_optional_json_object(telemetry_path) if telemetry_path else {}
    promotion_report = load_optional_json_object(promotion_path) if promotion_path else {}
    behavior_delta_rel = _behavior_delta_path(telemetry, promotion_report)
    behavior_delta_path = vault / behavior_delta_rel if behavior_delta_rel else None
    behavior_delta_exists = bool(behavior_delta_path and behavior_delta_path.is_file())
    behavior_delta_sha256 = _sha256_file(behavior_delta_path) if behavior_delta_exists else ""
    telemetry_digest = str(telemetry.get("behavior_delta_digest", "")).strip()
    telemetry_digest_valid = bool(HEX_SHA256_RE.fullmatch(telemetry_digest))
    telemetry_axes = _string_list(telemetry.get("secondary_improvement_axes"))
    telemetry_strict = bool(telemetry.get("strict_secondary_improvement_present"))
    parsed_strict, parsed_axes, parsed_axis_evidence = _promotion_secondary_improvement(promotion_report)
    digest_reconstruction_needed = not telemetry_digest_valid
    secondary_reconstruction_needed = not telemetry_strict or not telemetry_axes
    reconstruction_needed = digest_reconstruction_needed or secondary_reconstruction_needed
    selection_reason = (
        "selected_from_mechanism_review_candidates_for_active_same_eval_family"
        f"; families={','.join(families) or 'unknown'}"
    )

    reasons: list[str] = []
    if not telemetry:
        reasons.append("run telemetry missing")
    if digest_reconstruction_needed:
        reasons.append("telemetry behavior_delta_digest missing or invalid")
    if secondary_reconstruction_needed:
        reasons.append("telemetry strict secondary improvement fields missing or incomplete")
    if digest_reconstruction_needed and not behavior_delta_sha256:
        reasons.append("behavior-delta artifact digest unavailable")
    if secondary_reconstruction_needed and (not parsed_strict or not parsed_axes):
        reasons.append("promotion report secondary-axis evidence unavailable")

    status = "not_needed"
    if not telemetry:
        status = "blocked"
    elif not reconstruction_needed:
        status = "not_needed"
    elif digest_reconstruction_needed and not behavior_delta_sha256:
        status = "blocked"
    elif secondary_reconstruction_needed and (not parsed_strict or not parsed_axes):
        status = "blocked"
    else:
        status = "reconstructed"

    return {
        "run_id": run_id,
        "families": families,
        "telemetry_path": report_path(vault, telemetry_path) if telemetry_path else "",
        "telemetry_sha256": _sha256_file(telemetry_path),
        "promotion_report_path": report_path(vault, promotion_path) if promotion_path else "",
        "promotion_report_sha256": _sha256_file(promotion_path),
        "behavior_delta_path": behavior_delta_rel,
        "behavior_delta_artifact_exists": behavior_delta_exists,
        "behavior_delta_artifact_sha256": behavior_delta_sha256,
        "telemetry_behavior_delta_digest": telemetry_digest.lower() if telemetry_digest_valid else telemetry_digest,
        "telemetry_behavior_delta_digest_valid": telemetry_digest_valid,
        "digest_reconstruction_needed": digest_reconstruction_needed,
        "secondary_reconstruction_needed": secondary_reconstruction_needed,
        "selection_reason": selection_reason,
        "parsed_strict_secondary_improvement_present": parsed_strict,
        "parsed_secondary_axes": parsed_axes,
        "parsed_secondary_axis_evidence": parsed_axis_evidence,
        "reconstruction_status": status,
        "reasons": reasons,
    }


def _operator_reconstruction_diagnostics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for row in rows:
        diagnostics.append(
            {
                "run_id": str(row.get("run_id", "")).strip(),
                "families": _string_list(row.get("families")),
                "reconstruction_status": str(row.get("reconstruction_status", "")).strip(),
                "reconstruction_needed": bool(row.get("digest_reconstruction_needed"))
                or bool(row.get("secondary_reconstruction_needed")),
                "selection_reason": str(row.get("selection_reason", "")).strip(),
                "reconstruction_reasons": _string_list(row.get("reasons")),
                "parsed_secondary_axes": _string_list(row.get("parsed_secondary_axes")),
                "parsed_secondary_axis_evidence": (
                    row.get("parsed_secondary_axis_evidence")
                    if isinstance(row.get("parsed_secondary_axis_evidence"), dict)
                    else {
                        "source": "missing",
                        "check_id": "",
                        "detail": "",
                        "strict_signal": False,
                        "axes": [],
                    }
                ),
            }
        )
    return diagnostics


def build_report(
    vault: Path,
    *,
    out_path: str = DEFAULT_OUT,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    mutation_proposals = load_optional_json_object(vault / MUTATION_PROPOSALS_PATH)
    mechanism_review = load_optional_json_object(vault / MECHANISM_REVIEW_CANDIDATES_PATH)
    run_families = _confirmed_run_family_map(mutation_proposals, mechanism_review)
    rows = [
        _reconstruction_row(vault, run_id, families)
        for run_id, families in run_families.items()
    ]
    reconstruction_digest = _canonical_sha256(
        {
            "payload_version": 1,
            "run_reconstructions": rows,
        }
    )
    blocked_rows = [row for row in rows if row["reconstruction_status"] == "blocked"]
    reconstruction_diagnostics = _operator_reconstruction_diagnostics(rows)
    input_paths = [
        MUTATION_PROPOSALS_PATH,
        MECHANISM_REVIEW_CANDIDATES_PATH,
        *[
            str(row["telemetry_path"])
            for row in rows
            if str(row.get("telemetry_path", "")).strip()
        ],
        *[
            str(row["promotion_report_path"])
            for row in rows
            if str(row.get("promotion_report_path", "")).strip()
        ],
        *[
            str(row["behavior_delta_path"])
            for row in rows
            if str(row.get("behavior_delta_path", "")).strip()
        ],
    ]
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="learning_confirmed_legacy_reconstruction",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=[
                "ops/scripts/learning/learning_confirmed_legacy_reconstruction.py",
                "ops/scripts/learning/learning_claim_evidence_bundle.py",
            ],
            path_group_inputs={"legacy_reconstruction_inputs": input_paths},
        ),
        "vault": report_path(vault, vault),
        "policy": {"path": report_path(vault, resolved_policy_path), "version": policy.get("version")},
        "status": "pass" if not blocked_rows else "fail",
        "summary": {
            "reconstruction_sha256": reconstruction_digest,
            "run_count": len(rows),
            "reconstruction_needed_count": sum(
                1
                for row in rows
                if bool(row["digest_reconstruction_needed"]) or bool(row["secondary_reconstruction_needed"])
            ),
            "reconstructed_run_count": sum(1 for row in rows if row["reconstruction_status"] == "reconstructed"),
            "not_needed_run_count": sum(1 for row in rows if row["reconstruction_status"] == "not_needed"),
            "blocked_run_count": len(blocked_rows),
            "historical_telemetry_mutation": False,
            "operator_reconstruction_diagnostics": reconstruction_diagnostics,
            "operator_summary": (
                f"legacy_reconstruction_runs={len(rows)}; "
                f"needed={sum(1 for row in reconstruction_diagnostics if row['reconstruction_needed'])}; "
                f"reconstructed={sum(1 for row in rows if row['reconstruction_status'] == 'reconstructed')}; "
                f"blocked={len(blocked_rows)}"
            ),
        },
        "reconstruction_identity": {
            "digest_algorithm": "sha256",
            "payload_version": 1,
            "reconstruction_digest": reconstruction_digest,
        },
        "run_reconstructions": rows,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="learning confirmed legacy reconstruction schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build learning confirmed legacy reconstruction evidence")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--out", default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, out_path=args.out)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
