from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
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


DEFAULT_OUT = "ops/reports/learning_claim_activation_report.json"
PRODUCER = "ops.scripts.learning_claim_activation_report"
SCHEMA_PATH = "ops/schemas/learning-claim-activation-report.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.learning_claim_activation_report --vault ."
SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"
UNLOCK_REVIEW_PATH = "ops/reports/learning-claim-unlock-review.json"
EVIDENCE_BUNDLE_PATH = "ops/reports/learning-claim-evidence-bundle.json"
AUTO_IMPROVE_READINESS_PATH = "ops/reports/auto-improve-readiness.json"
RELEASE_CLEAN_BLOCKER_LEDGER_PATH = "ops/reports/release-clean-blocker-ledger.json"
SOURCE_PACKAGE_CLEAN_EXTRACT_PATH = "ops/reports/source-package-clean-extract.json"
POST_SEAL_ATTESTATION_PATH = "build/release/release-post-seal-attestation.json"
SOURCE_PATHS = [
    "ops/scripts/learning/learning_claim_activation_report.py",
    "ops/scripts/learning/learning_delta_scoreboard.py",
    "ops/scripts/learning/learning_claim_unlock_review.py",
    "ops/scripts/learning/learning_claim_evidence_bundle.py",
    "ops/scripts/learning/learning_claim_model.py",
]
ANTI_SLOP_AXES = [
    "claim_hygiene",
    "evidence_density",
    "reproducibility",
    "scope_discipline",
    "context_efficiency",
    "operator_override_pressure",
]
HEX_SAFE_RE = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class ActivationInputs:
    readiness: dict[str, Any]
    scoreboard: dict[str, Any]
    unlock_review: dict[str, Any]
    evidence_bundle: dict[str, Any]
    release_clean_blocker_ledger: dict[str, Any]
    source_package_clean_extract: dict[str, Any]
    post_seal_attestation: dict[str, Any]


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _bool_at(payload: dict[str, Any], path: tuple[str, ...]) -> bool:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return False
        value = value.get(key)
    return bool(value)


def _str_at(payload: dict[str, Any], path: tuple[str, ...], default: str = "") -> str:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    text = str(value or "").strip()
    return text or default


def _int_at(payload: dict[str, Any], path: tuple[str, ...], default: int = 0) -> int:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_at(payload: dict[str, Any], path: tuple[str, ...], default: float = 0.0) -> float:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_id(value: str) -> str:
    lowered = value.strip().lower().replace("-", "_")
    normalized = HEX_SAFE_RE.sub("_", lowered).strip("_")
    return normalized or "unknown"


def _evidence_digest(vault: Path, rel_path: str) -> dict[str, Any]:
    path = vault / rel_path
    exists = path.is_file()
    return {
        "path": rel_path,
        "exists": exists,
        "sha256": _sha256_file(path) if exists else "",
        "status": "present" if exists else "missing",
    }


def _post_seal_linkage(vault: Path, attestation: dict[str, Any]) -> dict[str, Any]:
    digest = _evidence_digest(vault, POST_SEAL_ATTESTATION_PATH)
    authority = attestation.get("learning_claim_authority")
    authority_payload = authority if isinstance(authority, dict) else {}
    return {
        **digest,
        "attestation_status": str(attestation.get("status", "missing" if not digest["exists"] else "")).strip(),
        "claim_level": str(authority_payload.get("claim_level", "")).strip(),
        "learning_claim_evidence_bundle_sha256": str(
            authority_payload.get("learning_claim_evidence_bundle_sha256", "")
        ).strip(),
        "post_seal_verified": digest["exists"] and str(attestation.get("status", "")).strip() == "pass",
    }


def _read_inputs(vault: Path) -> ActivationInputs:
    return ActivationInputs(
        readiness=load_optional_json_object(vault / AUTO_IMPROVE_READINESS_PATH),
        scoreboard=load_optional_json_object(vault / SCOREBOARD_PATH),
        unlock_review=load_optional_json_object(vault / UNLOCK_REVIEW_PATH),
        evidence_bundle=load_optional_json_object(vault / EVIDENCE_BUNDLE_PATH),
        release_clean_blocker_ledger=load_optional_json_object(vault / RELEASE_CLEAN_BLOCKER_LEDGER_PATH),
        source_package_clean_extract=load_optional_json_object(vault / SOURCE_PACKAGE_CLEAN_EXTRACT_PATH),
        post_seal_attestation=load_optional_json_object(vault / POST_SEAL_ATTESTATION_PATH),
    )


def _predicate_repair_target(predicate_id: str) -> str:
    repair_targets = {
        "auto_improve_can_promote_result": (
            "Clear release authority, sealed preflight, and promotion blockers before treating "
            "auto-improve learning as claimable."
        ),
        "learning_claim_blocker_absence": (
            "Resolve release-clean-blocker-ledger learning claim blockers or keep claim_level=none."
        ),
        "learning_claim_unlock_review_not_approved": (
            "Approve or auto-approve the unlock review only after evidence bundle, readiness, "
            "and review items are current and clean."
        ),
        "post_seal_learning_claim_linkage": (
            "Run release-post-seal-attestation after the candidate evidence is sealed and verify "
            "the learning claim authority binding."
        ),
    }
    return repair_targets.get(
        predicate_id,
        "Repair the predicate source evidence, rerun the owning report, and keep claim_level=none until it passes.",
    )


def _blocked_predicate(
    vault: Path,
    predicate: dict[str, Any],
    *,
    source: str,
    post_seal: dict[str, Any],
) -> dict[str, Any]:
    predicate_id = str(predicate.get("id", source)).strip() or source
    source_path = str(predicate.get("source_path", "")).strip()
    digest = _evidence_digest(vault, source_path) if source_path else {
        "path": "",
        "exists": False,
        "sha256": "",
        "status": "missing",
    }
    return {
        "id": predicate_id,
        "status": str(predicate.get("status", "fail")).strip() or "fail",
        "source": source,
        "source_path": source_path,
        "current": str(predicate.get("observed_value", predicate.get("current", ""))).strip(),
        "required": str(predicate.get("required_condition", predicate.get("required", ""))).strip(),
        "repair_target": _predicate_repair_target(predicate_id),
        "summary": str(predicate.get("summary", "")).strip(),
        "evidence_digest": digest,
        "post_seal_linkage": {
            "path": post_seal["path"],
            "sha256": post_seal["sha256"],
            "linked": bool(post_seal["post_seal_verified"]),
        },
    }


def _blocked_predicates(
    vault: Path,
    *,
    inputs: ActivationInputs,
    post_seal: dict[str, Any],
) -> list[dict[str, Any]]:
    predicates: list[dict[str, Any]] = []
    machine_policy = inputs.unlock_review.get("machine_policy_decision")
    machine_payload = machine_policy if isinstance(machine_policy, dict) else {}
    for source_name, rows in (
        ("learning_claim_unlock_review.machine_policy_decision", machine_payload.get("predicate_results")),
        ("learning_claim_unlock_review.confirmed_policy", machine_payload.get("confirmed_predicate_results")),
    ):
        for predicate in _list_of_dicts(rows):
            if str(predicate.get("status", "")).strip() == "pass":
                continue
            predicates.append(
                _blocked_predicate(
                    vault,
                    predicate,
                    source=source_name,
                    post_seal=post_seal,
                )
            )

    scoreboard_unlock = inputs.scoreboard.get("learning_claim_unlock_review")
    unlock_payload = scoreboard_unlock if isinstance(scoreboard_unlock, dict) else {}
    if unlock_payload and not bool(unlock_payload.get("approved")):
        predicates.append(
            _blocked_predicate(
                vault,
                {
                    "id": "learning_claim_unlock_review_not_approved",
                    "status": str(unlock_payload.get("status", "required")).strip() or "required",
                    "source_path": SCOREBOARD_PATH,
                    "observed_value": (
                        f"approved={bool(unlock_payload.get('approved'))}; "
                        f"status={str(unlock_payload.get('status', '')).strip()}"
                    ),
                    "required_condition": "learning_claim_unlock_review.approved == true",
                    "summary": str(unlock_payload.get("reason", "")).strip(),
                },
                source="learning_delta_scoreboard.learning_claim_unlock_review",
                post_seal=post_seal,
            )
        )

    if not bool(post_seal["post_seal_verified"]):
        predicates.append(
            _blocked_predicate(
                vault,
                {
                    "id": "post_seal_learning_claim_linkage",
                    "status": "fail",
                    "source_path": POST_SEAL_ATTESTATION_PATH,
                    "observed_value": f"post_seal_verified={bool(post_seal['post_seal_verified'])}",
                    "required_condition": "release_post_seal_attestation.status == pass",
                    "summary": "Post-seal learning claim authority is not verified for the current evidence set.",
                },
                source="release_post_seal_attestation",
                post_seal=post_seal,
            )
        )
    return predicates


def _claim_candidate(
    *,
    vault: Path,
    inputs: ActivationInputs,
    post_seal: dict[str, Any],
    blocked_predicates: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = inputs.scoreboard.get("summary")
    scoreboard_summary = summary if isinstance(summary, dict) else {}
    learning_likely = _bool_at(inputs.readiness, ("learning_readiness", "likely_to_learn"))
    claim_candidate = learning_likely or bool(scoreboard_summary.get("learning_likely"))
    learning_claim_allowed = bool(scoreboard_summary.get("learning_claim_allowed"))
    claim_level = str(scoreboard_summary.get("claim_level", "none")).strip() or "none"
    if learning_claim_allowed:
        status = "open"
    elif claim_candidate:
        status = "blocked"
    else:
        status = "not_candidate"
    first_repair = blocked_predicates[0]["repair_target"] if blocked_predicates else ""
    return {
        "status": status,
        "candidate": claim_candidate,
        "current": {
            "claim_level": claim_level,
            "learning_likely": learning_likely,
            "claims_learning_improved": bool(scoreboard_summary.get("claims_learning_improved")),
            "learning_claim_allowed": learning_claim_allowed,
            "bounded_learning_claim_allowed": bool(scoreboard_summary.get("bounded_learning_claim_allowed")),
            "confirmed_learning_improvement_allowed": bool(
                scoreboard_summary.get("confirmed_learning_improvement_allowed")
            ),
            "claim_wording_allowed": bool(scoreboard_summary.get("claim_wording_allowed")),
            "claim_wording_policy_status": str(
                scoreboard_summary.get("claim_wording_policy_status", "blocked")
            ).strip()
            or "blocked",
            "learning_claim_evidence_complete": bool(
                scoreboard_summary.get("learning_claim_evidence_complete")
            ),
        },
        "required": {
            "bounded_learning_likely": (
                "learning_claim_allowed == true with full same-eval reason, strict-secondary, "
                "behavior-delta digest, placeholder-free external report, and approved unlock review"
            ),
            "confirmed_learning_improvement": (
                "confirmed evidence cohort, active evidence bundle, clean full/public/revalidation "
                "evidence, no learning blockers, and post-seal attestation authority"
            ),
        },
        "repair_target": first_repair
        or "Keep claim_level=none until learning readiness, unlock review, and post-seal authority all pass.",
        "evidence_digest": _evidence_digest(vault, SCOREBOARD_PATH),
        "post_seal_linkage": {
            "path": post_seal["path"],
            "sha256": post_seal["sha256"],
            "post_seal_verified": bool(post_seal["post_seal_verified"]),
        },
    }


def _axis(axis: str, status: str, current: str, required: str, repair_target: str) -> dict[str, Any]:
    return {
        "axis": axis,
        "status": status,
        "current": current,
        "required": required,
        "repair_target": repair_target,
        "gate_effect": "none",
    }


def _anti_slop_preview_ledger(inputs: ActivationInputs, claim_candidate: dict[str, Any]) -> dict[str, Any]:
    summary = inputs.scoreboard.get("summary")
    scoreboard_summary = summary if isinstance(summary, dict) else {}
    anti_slop = inputs.scoreboard.get("anti_slop_score")
    anti_slop_payload = anti_slop if isinstance(anti_slop, dict) else {}
    bundle_summary = _dict_value(inputs.evidence_bundle.get("summary"))
    axes = [
        _axis(
            "claim_hygiene",
            "pass" if claim_candidate["current"]["claim_level"] == "none" or claim_candidate["current"]["claim_wording_allowed"] else "warn",
            (
                f"claim_level={claim_candidate['current']['claim_level']}; "
                f"claim_wording_allowed={claim_candidate['current']['claim_wording_allowed']}"
            ),
            "No learning-improvement wording unless the claim model allows it.",
            "Keep claim_level=none or complete the unlock and confirmed-claim predicates.",
        ),
        _axis(
            "evidence_density",
            "pass"
            if {
                str(scoreboard_summary.get("telemetry_coverage_status", "")),
                str(scoreboard_summary.get("same_eval_reason_coverage_status", "")),
                str(scoreboard_summary.get("strict_secondary_improvement_coverage_status", "")),
                str(scoreboard_summary.get("behavior_delta_digest_coverage_status", "")),
            }
            <= {"full", "not_applicable"}
            else "warn",
            (
                f"telemetry={scoreboard_summary.get('telemetry_coverage_status', '')}; "
                f"same_eval_reason={scoreboard_summary.get('same_eval_reason_coverage_status', '')}; "
                f"strict_secondary={scoreboard_summary.get('strict_secondary_improvement_coverage_status', '')}; "
                f"behavior_delta_digest={scoreboard_summary.get('behavior_delta_digest_coverage_status', '')}"
            ),
            "Same-eval learning claims require full telemetry, reason, strict-secondary, and digest coverage.",
            "Backfill missing telemetry or keep the claim closed.",
        ),
        _axis(
            "reproducibility",
            "pass"
            if str(inputs.source_package_clean_extract.get("status", "")).strip() == "pass"
            and str(bundle_summary.get("revocation_status", "")).strip() == "active"
            else "warn",
            (
                f"source_package_clean_extract={inputs.source_package_clean_extract.get('status', 'missing')}; "
                f"evidence_bundle_revocation={bundle_summary.get('revocation_status', 'missing')}"
            ),
            "Source package replay and active evidence bundle must remain reproducible.",
            "Rerun release-source-package-check and learning-claim-evidence-bundle.",
        ),
        _axis(
            "scope_discipline",
            "pass"
            if _int_at(inputs.readiness, ("queue", "runnable_proposal_count")) <= 1
            else "warn",
            (
                f"runnable_proposal_count={_int_at(inputs.readiness, ('queue', 'runnable_proposal_count'))}; "
                f"can_execute_trial={bool(inputs.readiness.get('can_execute_trial'))}"
            ),
            "Auto-improve learning probes should remain narrow, with at most one runnable proposal.",
            "Split or defer proposals until the active run has a single bounded target.",
        ),
        _axis(
            "context_efficiency",
            "warn",
            "no dedicated context-efficiency telemetry is bound to the learning claim lane",
            "Claim activation should expose context budget or synopsis reuse pressure before promotion authority uses it.",
            "Add context budget telemetry or a session synopsis digest before making this axis gating.",
        ),
        _axis(
            "operator_override_pressure",
            "pass"
            if str(inputs.unlock_review.get("review_status", "")).strip() in {"", "auto_approved"}
            else "warn",
            (
                f"unlock_review_status={inputs.unlock_review.get('review_status', 'missing')}; "
                f"approved={bool(inputs.unlock_review.get('approved'))}"
            ),
            "Manual override pressure should stay explicit and should not silently unlock claim wording.",
            "Keep review_status required until machine policy and operator signoff are clean.",
        ),
    ]
    status = "clean" if all(item["status"] == "pass" for item in axes) else "attention"
    return {
        "mode": "preview",
        "gate_effect": "none",
        "status": status,
        "scoreboard_anti_slop_status": str(anti_slop_payload.get("status", "unknown")).strip() or "unknown",
        "scoreboard_anti_slop_score": _int_at(anti_slop_payload, ("score",), 0),
        "axes": axes,
    }


def _pattern_digest(vault: Path, paths: list[str]) -> list[dict[str, Any]]:
    return [_evidence_digest(vault, path) for path in paths if path]


def _add_pattern(
    patterns: dict[str, dict[str, Any]],
    *,
    pattern_id: str,
    decision: str,
    run_id: str = "",
    evidence_paths: list[str] | None = None,
    repair_target: str,
) -> None:
    key = _safe_id(pattern_id)
    row = patterns.setdefault(
        key,
        {
            "pattern_id": key,
            "decisions": [],
            "run_ids": [],
            "occurrence_count": 0,
            "forbidden_repeat": "Do not repeat this run shape until the repair target is completed.",
            "repair_target": repair_target,
            "evidence_digests": [],
        },
    )
    if decision and decision not in row["decisions"]:
        row["decisions"].append(decision)
    if run_id and run_id not in row["run_ids"]:
        row["run_ids"].append(run_id)
    row["occurrence_count"] = int(row["occurrence_count"]) + 1
    for evidence_path in evidence_paths or []:
        if evidence_path and evidence_path not in [item["path"] for item in row["evidence_digests"]]:
            row["evidence_digests"].append({"path": evidence_path, "exists": False, "sha256": "", "status": "pending"})


def _is_outcome_only_rejection_reason(reason: str, decision: str) -> bool:
    normalized = reason.strip().lower()
    decision_value = decision.strip().lower()
    return normalized in {
        f"decision={decision_value}",
        f"decision = {decision_value}",
        decision_value,
    }


def _confirmed_rejection_pattern_suffix(
    *,
    decision: str,
    reasons: list[str],
    telemetry_reason: str | None,
) -> str | None:
    for reason in reasons:
        if not _is_outcome_only_rejection_reason(reason, decision):
            return reason
    if telemetry_reason:
        return None
    return "confirmed_evidence_rejected_without_specific_reason"


def _negative_learning_ledger(vault: Path, inputs: ActivationInputs) -> dict[str, Any]:
    patterns: dict[str, dict[str, Any]] = {}
    telemetry_reason_by_run_id: dict[str, str] = {}
    for telemetry_path in sorted((vault / "runs").glob("**/run-telemetry.json")):
        telemetry = load_optional_json_object(telemetry_path)
        decision = str(telemetry.get("decision", "")).strip()
        if decision not in {"HOLD", "DISCARD"}:
            continue
        run_id = str(telemetry.get("run_id", telemetry_path.parent.name)).strip()
        reason = str(telemetry.get("same_eval_reason_code", "unspecified")).strip() or "unspecified"
        if run_id:
            telemetry_reason_by_run_id[run_id] = reason
        rel_path = report_path(vault, telemetry_path)
        _add_pattern(
            patterns,
            pattern_id=f"{decision}_{reason}",
            decision=decision,
            run_id=run_id,
            evidence_paths=[rel_path],
            repair_target=(
                "Change the mechanism or evidence predicate before rerunning another "
                f"{decision} attempt with same_eval_reason_code={reason}."
            ),
        )

    scoreboard_summary = _dict_value(inputs.scoreboard.get("summary"))
    confirmed_summary = _dict_value(scoreboard_summary.get("confirmed_evidence_summary"))
    for diagnostic in _list_of_dicts(confirmed_summary.get("rejected_run_diagnostics")):
        decision = str(diagnostic.get("decision", "")).strip()
        if decision not in {"HOLD", "DISCARD"}:
            continue
        run_id = str(diagnostic.get("run_id", "")).strip()
        reasons = _string_list(diagnostic.get("reasons"))
        pattern_suffix = _confirmed_rejection_pattern_suffix(
            decision=decision,
            reasons=reasons,
            telemetry_reason=telemetry_reason_by_run_id.get(run_id),
        )
        if pattern_suffix is None:
            continue
        _add_pattern(
            patterns,
            pattern_id=f"{decision}_{pattern_suffix}",
            decision=decision,
            run_id=run_id,
            evidence_paths=[SCOREBOARD_PATH],
            repair_target="Repair the rejected confirmed-evidence run before using it as learning proof.",
        )

    for row in _list_of_dicts(inputs.readiness.get("queue", {}).get("blocked_reason_counts")):
        reason = str(row.get("reason", "unknown")).strip() or "unknown"
        count = _int_at(row, ("count",), 1)
        for _index in range(max(1, count)):
            _add_pattern(
                patterns,
                pattern_id=f"blocked_queue_{reason}",
                decision="BLOCKED",
                evidence_paths=[AUTO_IMPROVE_READINESS_PATH],
                repair_target=f"Resolve queue blocked reason {reason} before rerunning the same proposal lane.",
            )

    finalized = []
    for row in patterns.values():
        row["evidence_digests"] = _pattern_digest(vault, [item["path"] for item in row["evidence_digests"]])
        finalized.append(row)
    finalized.sort(key=lambda item: (str(item["pattern_id"]), str(item["decisions"])))
    return {
        "mode": "advisory",
        "gate_effect": "none",
        "status": "attention" if finalized else "clean",
        "pattern_count": len(finalized),
        "patterns": finalized,
    }


def _evidence_digests(vault: Path) -> list[dict[str, Any]]:
    return [
        _evidence_digest(vault, rel_path)
        for rel_path in [
            AUTO_IMPROVE_READINESS_PATH,
            SCOREBOARD_PATH,
            UNLOCK_REVIEW_PATH,
            EVIDENCE_BUNDLE_PATH,
            RELEASE_CLEAN_BLOCKER_LEDGER_PATH,
            SOURCE_PACKAGE_CLEAN_EXTRACT_PATH,
            POST_SEAL_ATTESTATION_PATH,
        ]
    ]


def _report_status(claim_candidate: dict[str, Any]) -> str:
    current = claim_candidate["current"]
    if current["claim_level"] == "none" and not current["claim_wording_allowed"]:
        return "pass"
    if claim_candidate["status"] == "open":
        return "pass"
    return "attention"


def build_report(
    vault: Path,
    *,
    out_path: str = DEFAULT_OUT,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> dict[str, Any]:
    del out_path
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    inputs = _read_inputs(vault)
    post_seal = _post_seal_linkage(vault, inputs.post_seal_attestation)
    blocked = _blocked_predicates(vault, inputs=inputs, post_seal=post_seal)
    claim_candidate = _claim_candidate(
        vault=vault,
        inputs=inputs,
        post_seal=post_seal,
        blocked_predicates=blocked,
    )
    anti_slop = _anti_slop_preview_ledger(inputs, claim_candidate)
    negative_learning = _negative_learning_ledger(vault, inputs)
    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=runtime_context.isoformat_z(),
            artifact_kind="learning_claim_activation_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=SOURCE_PATHS,
            path_group_inputs={
                "learning_claim_activation_inputs": [
                    AUTO_IMPROVE_READINESS_PATH,
                    SCOREBOARD_PATH,
                    UNLOCK_REVIEW_PATH,
                    EVIDENCE_BUNDLE_PATH,
                    RELEASE_CLEAN_BLOCKER_LEDGER_PATH,
                    SOURCE_PACKAGE_CLEAN_EXTRACT_PATH,
                    POST_SEAL_ATTESTATION_PATH,
                ]
            },
        ),
        "vault": report_path(vault, vault),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "status": _report_status(claim_candidate),
        "summary": {
            "activation_status": claim_candidate["status"],
            "claim_level": claim_candidate["current"]["claim_level"],
            "claim_wording_allowed": claim_candidate["current"]["claim_wording_allowed"],
            "blocked_predicate_count": len(blocked),
            "anti_slop_preview_status": anti_slop["status"],
            "negative_learning_pattern_count": negative_learning["pattern_count"],
            "gate_effect": "none",
        },
        "claim_candidate": claim_candidate,
        "blocked_predicates": blocked,
        "evidence_digests": _evidence_digests(vault),
        "post_seal_linkage": post_seal,
        "anti_slop_preview_ledger": anti_slop,
        "negative_learning_ledger": negative_learning,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str = DEFAULT_OUT) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="learning claim activation report schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build learning claim activation explanation report")
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
