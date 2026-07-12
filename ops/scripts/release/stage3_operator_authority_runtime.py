from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Stage3CountAudit:
    raw_count: int
    effective_count: int
    identity_count_mismatch: bool
    discounted_ids: tuple[str, ...]
    release_gate_discounted_ids: tuple[str, ...]
    advisory_discounted_ids: tuple[str, ...]

    def diagnostics(self, *, count_field: str) -> dict[str, Any]:
        return {
            count_field: self.effective_count,
            "raw_count": self.raw_count,
            "identity_count_mismatch": self.identity_count_mismatch,
            "discounted_ids": list(self.discounted_ids),
            "release_gate_discounted_ids": list(self.release_gate_discounted_ids),
            "advisory_discounted_ids": list(self.advisory_discounted_ids),
        }


def _string_ids(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def release_gate_blocker_ids(payload: Mapping[str, Any]) -> set[str]:
    blockers = payload.get("promotion_blockers")
    if not isinstance(blockers, list):
        return set()
    return {
        str(blocker.get("id", "")).strip()
        for blocker in blockers
        if (
            isinstance(blocker, dict)
            and str(blocker.get("scope", "")).strip() == "release_gate"
            and str(blocker.get("id", "")).strip()
        )
    }


def stage3_count_audit(
    raw_count: int,
    *,
    operator_ids: Any,
    release_gate_ids: Iterable[str],
    lower_authority_pass: bool,
    advisory_ids: Any = (),
) -> Stage3CountAudit:
    normalized_raw_count = max(0, raw_count)
    mapped_ids = _string_ids(operator_ids)
    identity_count_mismatch = len(mapped_ids) != normalized_raw_count
    release_matches = (
        mapped_ids.intersection(str(item).strip() for item in release_gate_ids)
        if lower_authority_pass and not identity_count_mismatch
        else set()
    )
    advisory_matches = (
        mapped_ids.intersection(_string_ids(advisory_ids))
        if not identity_count_mismatch
        else set()
    )
    matched_ids = release_matches | advisory_matches
    discounted = sorted(matched_ids)
    discounted_set = set(discounted)
    return Stage3CountAudit(
        raw_count=normalized_raw_count,
        effective_count=(
            max(normalized_raw_count, len(mapped_ids))
            if identity_count_mismatch
            else normalized_raw_count - len(discounted)
        ),
        identity_count_mismatch=identity_count_mismatch,
        discounted_ids=tuple(discounted),
        release_gate_discounted_ids=tuple(sorted(release_matches & discounted_set)),
        advisory_discounted_ids=tuple(sorted(advisory_matches & discounted_set)),
    )


def run_manifest_authority_pass(payload: Mapping[str, Any]) -> bool:
    if "release_authority_status" in payload:
        authority_status = str(payload.get("release_authority_status", "")).strip()
        if authority_status != "clean_pass":
            return False
        machine_allowed = payload.get("machine_release_allowed")
        if isinstance(machine_allowed, bool):
            return machine_allowed
        return True
    return str(payload.get("status", "")).strip() == "pass"


def sealed_manifest_authority_pass(payload: Mapping[str, Any]) -> bool:
    if "sealed_release_status" in payload:
        return str(payload.get("sealed_release_status", "")).strip() == "sealed_clean_pass"
    return str(payload.get("status", "")).strip() == "pass"


def current_lower_authority_pass(
    *,
    run_payload: Mapping[str, Any],
    sealed_payload: Mapping[str, Any],
    run_identity: Mapping[str, Any],
    sealed_identity: Mapping[str, Any],
    current_fingerprint: str,
    current_revision: str,
) -> bool:
    return (
        run_identity.get("load_status") == "ok"
        and run_identity.get("artifact_kind") == "release_run_manifest"
        and run_identity.get("source_tree_fingerprint") == current_fingerprint
        and run_identity.get("source_revision") == current_revision
        and run_manifest_authority_pass(run_payload)
        and sealed_identity.get("load_status") == "ok"
        and sealed_identity.get("artifact_kind") == "release_sealed_run_manifest"
        and sealed_identity.get("source_tree_fingerprint") == current_fingerprint
        and sealed_identity.get("source_revision") == current_revision
        and sealed_manifest_authority_pass(sealed_payload)
    )
