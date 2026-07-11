from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.core.artifact_io_runtime import (
    load_optional_json_object_with_diagnostics,
)
from ops.scripts.core.release_authority_state_runtime import (
    release_status_v2_view_with_readiness_fallback,
)
from ops.scripts.core.release_currentness_state_runtime import currentness_field
from ops.scripts.core.request_coercion_runtime import coerce_request_or_kwargs
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.source_revision_runtime import resolve_source_revision
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.learning.learning_readiness_signoff_state import (
    learning_readiness_signoff_summary,
)
from ops.scripts.release.release_run_manifest import remote_sync as read_remote_sync

STATUS_KEYS = (
    "source_closeout",
    "sealed_run",
    "public_summary",
    "lockfile_freshness",
    "learning_signoff",
    "goal_runtime_certificate",
    "remote_sync",
)
STATUS_AXIS_SOURCE_CLOSEOUT = "source_closeout"
STATUS_AXIS_SEALED_RUN = "sealed_run"
STATUS_VALUE_SYNCED = "synced"
STATUS_VALUE_NOT_SYNCED = "not_synced"
STATUS_VALUE_PASS = "pass"
STATUS_VALUE_FAIL = "fail"
STATUS_VALUE_CURRENT = "current"
STATUS_VALUE_STALE = "stale"
STATUS_VALUE_UNKNOWN = "unknown"
STATUS_VALUE_REQUIRES_FULL_VAULT = "requires_full_vault"
TOOLCHAIN_ALIGNMENT_ALIGNED = "aligned"
TOOLCHAIN_ALIGNMENT_BASELINE_NEEDS_NORMALIZATION = "baseline_environment_needs_normalization"
TOOLCHAIN_ALIGNMENT_CANONICAL_FAILED = "canonical_lock_check_failed"
TOOLCHAIN_ALIGNMENT_POLICY_EVIDENCE_NOT_ENFORCED = "policy_evidence_not_enforced"
VAULT_COMPLETENESS_FULL = "full_vault"
VAULT_COMPLETENESS_PUBLIC = "public_mirror"
FRESHNESS_DISPLAY_VALUES = {"none", "advisory", "blocking"}
UV_CANONICAL_INDEX_URL = "https://pypi.org/simple"

DEFAULT_CLOSEOUT = "ops/reports/release-closeout-summary.json"
DEFAULT_SEALED_RUN = "build/release/release-sealed-run-manifest.json"
DEFAULT_OPERATOR_SUMMARY = "ops/operator/operator-release-summary.json"
DEFAULT_PUBLIC_SUMMARY = "ops/reports/public-check-summary.json"
DEFAULT_SUPPLY_CHAIN_PROVENANCE = "ops/reports/supply-chain-provenance.json"
DEFAULT_LEARNING_SIGNOFF = "ops/reports/learning-readiness-signoff.json"
DEFAULT_GOAL_RUNTIME_CERTIFICATE = "ops/reports/goal-runtime-certificate.json"
DEFAULT_RELEASE_RUN_MANIFEST = "build/release/release-run-manifest.json"
DEFAULT_REMOTE_SYNC_LIVE_EVIDENCE = "git:live-remote-sync"
SOURCE_COMMAND = "python -m ops.scripts.release.release_status_surface --vault ."

LockCheckRunner = Callable[[Path], dict[str, Any]]
RemoteSyncReader = Callable[[Path], dict[str, Any]]


@dataclass(frozen=True)
class StatusSurfaceSignals:
    generated_at: str
    vault_completeness: str
    source_closeout_status: str
    sealed_run_status: str
    public_summary_status: str
    lock_check_status: str
    uv_lock_check_passed: bool
    learning_signoff_status: str
    goal_runtime_certificate_status: str
    remote_sync_signal: dict[str, Any]
    artifact_freshness_display: str
    canonical_uv_lock_check_passed: bool | None = None
    source_closeout_evidence_path: str = DEFAULT_CLOSEOUT
    sealed_run_evidence_path: str = DEFAULT_SEALED_RUN
    public_summary_evidence_path: str = DEFAULT_PUBLIC_SUMMARY
    lockfile_evidence_path: str = DEFAULT_SUPPLY_CHAIN_PROVENANCE
    learning_signoff_evidence_path: str = DEFAULT_LEARNING_SIGNOFF
    goal_runtime_certificate_evidence_path: str = DEFAULT_GOAL_RUNTIME_CERTIFICATE
    remote_sync_evidence_path: str = DEFAULT_REMOTE_SYNC_LIVE_EVIDENCE
    source_closeout_currentness_detail: str = "evidence_currentness=unknown"
    public_summary_currentness_detail: str = "evidence_currentness=unknown"


def remote_sync_display_status(remote_signal: dict[str, Any]) -> str:
    upstream = str(remote_signal.get("upstream", "")).strip()
    try:
        ahead = int(remote_signal.get("ahead", 0) or 0)
        behind = int(remote_signal.get("behind", 0) or 0)
    except (TypeError, ValueError):
        return STATUS_VALUE_NOT_SYNCED
    if (
        upstream
        and ahead == 0
        and behind == 0
        and str(remote_signal.get("status", "")).strip() == STATUS_VALUE_PASS
    ):
        return STATUS_VALUE_SYNCED
    return STATUS_VALUE_NOT_SYNCED


def lockfile_freshness_display_status(
    *,
    lock_check_status: str,
    uv_lock_check_passed: bool,
) -> str:
    if lock_check_status == "enforced" and uv_lock_check_passed:
        return STATUS_VALUE_PASS
    return STATUS_VALUE_FAIL


def _pass_fail(passed: bool) -> str:
    return STATUS_VALUE_PASS if passed else STATUS_VALUE_FAIL


def _dependency_normalization_status(
    *,
    lock_check_status: str,
    baseline_uv_lock_check_passed: bool,
    canonical_uv_lock_check_passed: bool,
) -> dict[str, str]:
    baseline_status = _pass_fail(baseline_uv_lock_check_passed)
    canonical_status = _pass_fail(canonical_uv_lock_check_passed)
    if canonical_status != STATUS_VALUE_PASS:
        alignment_status = TOOLCHAIN_ALIGNMENT_CANONICAL_FAILED
        recommended_step = "make uv-lock-check"
    elif baseline_status != canonical_status:
        alignment_status = TOOLCHAIN_ALIGNMENT_BASELINE_NEEDS_NORMALIZATION
        recommended_step = (
            "set UV_CANONICAL_INDEX_URL=https://pypi.org/simple and rerun make uv-lock-check"
        )
    elif lock_check_status != "enforced":
        alignment_status = TOOLCHAIN_ALIGNMENT_POLICY_EVIDENCE_NOT_ENFORCED
        recommended_step = "refresh supply-chain provenance evidence"
    else:
        alignment_status = TOOLCHAIN_ALIGNMENT_ALIGNED
        recommended_step = "none"
    return {
        "baseline_environment_lock_check_status": baseline_status,
        "canonical_lock_check_status": canonical_status,
        "toolchain_alignment_status": alignment_status,
        "recommended_normalization_step": recommended_step,
    }


def _load_optional(vault: Path, rel_path: str) -> tuple[dict[str, Any], str]:
    payload, diagnostics = load_optional_json_object_with_diagnostics(vault / rel_path)
    status = str(diagnostics.get("status", STATUS_VALUE_UNKNOWN)).strip()
    return payload, status or STATUS_VALUE_UNKNOWN


def _status_from_payload(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = str(value.get("result", "")).strip()
            if nested:
                return nested
        else:
            text = str(value or "").strip()
            if text:
                return text
    return ""


def _comparison_status(observed: str, expected: str) -> str:
    if not observed or not expected:
        return STATUS_VALUE_UNKNOWN
    return STATUS_VALUE_CURRENT if observed == expected else STATUS_VALUE_STALE


def _evidence_currentness_detail(
    payload: dict[str, Any],
    load_status: str,
    *,
    current_source_revision: str,
    current_source_tree_fingerprint: str,
    binding_mode: str,
) -> str:
    if load_status != "ok":
        return (
            "evidence_currentness=unknown; "
            "self_declared_currentness=unknown; "
            "artifact_status=unknown; "
            "source_revision=unknown; "
            "source_tree_fingerprint=unknown; "
            f"currentness_reason=load_status:{load_status or STATUS_VALUE_UNKNOWN}"
        )
    self_declared_currentness = currentness_field(payload, "status") or STATUS_VALUE_UNKNOWN
    artifact_status = str(payload.get("artifact_status", "")).strip() or STATUS_VALUE_UNKNOWN
    source_revision_status = _comparison_status(
        str(payload.get("source_revision", "")).strip(),
        current_source_revision,
    )
    source_tree_fingerprint_status = _comparison_status(
        str(payload.get("source_tree_fingerprint", "")).strip(),
        current_source_tree_fingerprint,
    )
    if (
        binding_mode == "content"
        and source_revision_status == STATUS_VALUE_STALE
        and source_tree_fingerprint_status == STATUS_VALUE_CURRENT
    ):
        source_revision_status = "provenance_only"
    reasons: list[str] = []
    if self_declared_currentness != STATUS_VALUE_CURRENT:
        reasons.append(f"self_declared_currentness:{self_declared_currentness}")
    if artifact_status != STATUS_VALUE_CURRENT:
        reasons.append(f"artifact_status:{artifact_status}")
    if source_revision_status not in {STATUS_VALUE_CURRENT, "provenance_only"}:
        reasons.append(f"source_revision:{source_revision_status}")
    if source_tree_fingerprint_status != STATUS_VALUE_CURRENT:
        reasons.append(f"source_tree_fingerprint:{source_tree_fingerprint_status}")
    evidence_currentness = STATUS_VALUE_CURRENT if not reasons else STATUS_VALUE_STALE
    reason = ",".join(reasons) if reasons else STATUS_VALUE_CURRENT
    return (
        f"evidence_currentness={evidence_currentness}; "
        f"self_declared_currentness={self_declared_currentness}; "
        f"artifact_status={artifact_status}; "
        f"source_revision={source_revision_status}; "
        f"source_tree_fingerprint={source_tree_fingerprint_status}; "
        f"currentness_reason={reason}"
    )


def _artifact_freshness_display(closeout: dict[str, Any]) -> str:
    gate = closeout.get("artifact_freshness_gate")
    gate = gate if isinstance(gate, dict) else {}
    display_effect = str(gate.get("display_effect", "")).strip()
    if display_effect in FRESHNESS_DISPLAY_VALUES:
        return display_effect
    if bool(gate.get("blocking")):
        return "blocking"
    gate_effect = str(gate.get("gate_effect", "")).strip()
    if gate_effect == "advisory":
        return "advisory"
    if gate_effect in {"blocks_promotion", "blocks_execution"}:
        return "blocking"
    return "none"


def _source_closeout_status(closeout: dict[str, Any], load_status: str) -> tuple[str, str]:
    if load_status != "ok":
        return STATUS_VALUE_UNKNOWN, "none"
    view = release_status_v2_view_with_readiness_fallback(closeout)
    return (
        str(view.get("release_authority_status", STATUS_VALUE_UNKNOWN)).strip()
        or STATUS_VALUE_UNKNOWN,
        _artifact_freshness_display(closeout),
    )


def _sealed_run_status(
    sealed_run: dict[str, Any],
    sealed_load_status: str,
    operator_summary: dict[str, Any],
    operator_load_status: str,
) -> tuple[str, str]:
    if sealed_load_status == "ok":
        view = release_status_v2_view_with_readiness_fallback(sealed_run)
        status = (
            str(view.get("sealed_release_status", "")).strip()
            or _status_from_payload(sealed_run, "sealed_release_status", "status")
            or STATUS_VALUE_UNKNOWN
        )
        return status, DEFAULT_SEALED_RUN
    if operator_load_status == "ok":
        return (
            _status_from_payload(operator_summary, "sealed_release_status", "status")
            or STATUS_VALUE_UNKNOWN,
            DEFAULT_OPERATOR_SUMMARY,
        )
    return STATUS_VALUE_UNKNOWN, DEFAULT_SEALED_RUN


def _vault_completeness(vault: Path) -> str:
    full_vault_paths = ("raw", "wiki", "system", "runs", "external-reports")
    if all((vault / path).exists() for path in full_vault_paths):
        return VAULT_COMPLETENESS_FULL
    return VAULT_COMPLETENESS_PUBLIC


def _unverified_status(value: str, *, vault_completeness: str) -> str:
    if value:
        return value
    if vault_completeness == VAULT_COMPLETENESS_PUBLIC:
        return STATUS_VALUE_REQUIRES_FULL_VAULT
    return STATUS_VALUE_UNKNOWN


def _status_line(
    *,
    key: str,
    status: str,
    axis: str | None,
    detail: str,
    evidence_path: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "axis": axis,
        "detail": detail,
        "evidence_path": evidence_path,
    }


def _coerce_status_surface_signals(
    signals: StatusSurfaceSignals | None,
    legacy_kwargs: dict[str, Any],
) -> StatusSurfaceSignals:
    return coerce_request_or_kwargs(
        request=signals,
        legacy_kwargs=legacy_kwargs,
        request_type=StatusSurfaceSignals,
        mixed_error_prefix="signals cannot be combined with legacy keyword arguments",
    )


def _normalized_freshness_display(signals: StatusSurfaceSignals) -> str:
    if signals.artifact_freshness_display in FRESHNESS_DISPLAY_VALUES:
        return signals.artifact_freshness_display
    return "none"


def _canonical_uv_lock_passed(signals: StatusSurfaceSignals) -> bool:
    if signals.canonical_uv_lock_check_passed is None:
        return signals.uv_lock_check_passed
    return signals.canonical_uv_lock_check_passed


def _source_closeout_line(signals: StatusSurfaceSignals, freshness: str) -> dict[str, Any]:
    return _status_line(
        key="source_closeout",
        status=signals.source_closeout_status or STATUS_VALUE_UNKNOWN,
        axis=STATUS_AXIS_SOURCE_CLOSEOUT,
        detail=f"freshness={freshness}; {signals.source_closeout_currentness_detail}",
        evidence_path=signals.source_closeout_evidence_path,
    )


def _sealed_run_line(signals: StatusSurfaceSignals) -> dict[str, Any]:
    return _status_line(
        key="sealed_run",
        status=signals.sealed_run_status or STATUS_VALUE_UNKNOWN,
        axis=STATUS_AXIS_SEALED_RUN,
        detail="axis=sealed_run_authority",
        evidence_path=signals.sealed_run_evidence_path,
    )


def _public_summary_line(signals: StatusSurfaceSignals) -> dict[str, Any]:
    return _status_line(
        key="public_summary",
        status=signals.public_summary_status or STATUS_VALUE_UNKNOWN,
        axis=None,
        detail=f"public mirror contract evidence; {signals.public_summary_currentness_detail}",
        evidence_path=signals.public_summary_evidence_path,
    )


def _lockfile_freshness_line(
    signals: StatusSurfaceSignals,
    *,
    lock_status: str,
    dependency_normalization: dict[str, str],
) -> dict[str, Any]:
    return _status_line(
        key="lockfile_freshness",
        status=lock_status,
        axis=None,
        detail=(
            f"lock_check_status={signals.lock_check_status or STATUS_VALUE_UNKNOWN}; "
            f"baseline_environment_lock_check={dependency_normalization['baseline_environment_lock_check_status']}; "
            f"canonical_lock_check={dependency_normalization['canonical_lock_check_status']}; "
            f"toolchain_alignment={dependency_normalization['toolchain_alignment_status']}; "
            f"recommended_normalization_step={dependency_normalization['recommended_normalization_step']}"
        ),
        evidence_path=signals.lockfile_evidence_path,
    )


def _learning_signoff_line(signals: StatusSurfaceSignals) -> dict[str, Any]:
    return _status_line(
        key="learning_signoff",
        status=_unverified_status(
            signals.learning_signoff_status,
            vault_completeness=signals.vault_completeness,
        ),
        axis=None,
        detail="learning readiness signoff evidence",
        evidence_path=signals.learning_signoff_evidence_path,
    )


def _goal_runtime_certificate_line(signals: StatusSurfaceSignals) -> dict[str, Any]:
    return _status_line(
        key="goal_runtime_certificate",
        status=_unverified_status(
            signals.goal_runtime_certificate_status,
            vault_completeness=signals.vault_completeness,
        ),
        axis=None,
        detail="goal runtime certificate evidence",
        evidence_path=signals.goal_runtime_certificate_evidence_path,
    )


def _remote_sync_line(signals: StatusSurfaceSignals, remote_status: str) -> dict[str, Any]:
    return _status_line(
        key="remote_sync",
        status=remote_status,
        axis=None,
        detail=(
            "source=live_git_remote_state; "
            f"upstream={str(signals.remote_sync_signal.get('upstream', '')).strip() or 'none'}; "
            f"ahead={signals.remote_sync_signal.get('ahead', 0)}; "
            f"behind={signals.remote_sync_signal.get('behind', 0)}"
        ),
        evidence_path=signals.remote_sync_evidence_path,
    )


def _status_surface_lines(
    signals: StatusSurfaceSignals,
    *,
    freshness: str,
    lock_status: str,
    dependency_normalization: dict[str, str],
    remote_status: str,
) -> list[dict[str, Any]]:
    return [
        _source_closeout_line(signals, freshness),
        _sealed_run_line(signals),
        _public_summary_line(signals),
        _lockfile_freshness_line(
            signals,
            lock_status=lock_status,
            dependency_normalization=dependency_normalization,
        ),
        _learning_signoff_line(signals),
        _goal_runtime_certificate_line(signals),
        _remote_sync_line(signals, remote_status),
    ]


def status_surface_from_signals(
    signals: StatusSurfaceSignals | None = None,
    **legacy_kwargs: Any,
) -> dict[str, Any]:
    signals = _coerce_status_surface_signals(signals, legacy_kwargs)
    canonical_uv_lock_check_passed = _canonical_uv_lock_passed(signals)
    lock_status = lockfile_freshness_display_status(
        lock_check_status=signals.lock_check_status,
        uv_lock_check_passed=canonical_uv_lock_check_passed,
    )
    dependency_normalization = _dependency_normalization_status(
        lock_check_status=signals.lock_check_status,
        baseline_uv_lock_check_passed=signals.uv_lock_check_passed,
        canonical_uv_lock_check_passed=canonical_uv_lock_check_passed,
    )
    return {
        "generated_at": signals.generated_at,
        "producer": "ops.scripts.release_status_surface",
        "source_command": SOURCE_COMMAND,
        "vault_completeness": signals.vault_completeness,
        "lines": _status_surface_lines(
            signals,
            freshness=_normalized_freshness_display(signals),
            lock_status=lock_status,
            dependency_normalization=dependency_normalization,
            remote_status=remote_sync_display_status(signals.remote_sync_signal),
        ),
        "axes": {
            "source_closeout_axis": STATUS_AXIS_SOURCE_CLOSEOUT,
            "sealed_run_axis": STATUS_AXIS_SEALED_RUN,
        },
        **dependency_normalization,
    }


def _run_uv_lock_check(vault: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["uv", "lock", "--check"],
            cwd=vault,
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": STATUS_VALUE_FAIL,
            "returncode": 127,
            "error": str(exc),
        }
    return {
        "status": STATUS_VALUE_PASS if completed.returncode == 0 else STATUS_VALUE_FAIL,
        "returncode": completed.returncode,
    }


def _run_canonical_uv_lock_check(vault: Path) -> dict[str, Any]:
    env = {
        **os.environ,
        "UV_DEFAULT_INDEX": UV_CANONICAL_INDEX_URL,
    }
    try:
        completed = subprocess.run(
            ["uv", "lock", "--check", "--default-index", UV_CANONICAL_INDEX_URL],
            cwd=vault,
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": STATUS_VALUE_FAIL,
            "returncode": 127,
            "error": str(exc),
        }
    return {
        "status": STATUS_VALUE_PASS if completed.returncode == 0 else STATUS_VALUE_FAIL,
        "returncode": completed.returncode,
    }


def _skipped_lock_check(_vault: Path) -> dict[str, Any]:
    return {
        "status": STATUS_VALUE_FAIL,
        "returncode": None,
        "reason": "skipped",
    }


def _lock_check_status_from_provenance(provenance: dict[str, Any]) -> str:
    lock_evidence = provenance.get("lock_evidence")
    lock_evidence = lock_evidence if isinstance(lock_evidence, dict) else {}
    return str(lock_evidence.get("lock_check_status", STATUS_VALUE_UNKNOWN)).strip() or STATUS_VALUE_UNKNOWN


def _learning_signoff_status(
    payload: dict[str, Any],
    *,
    load_status: str,
    generated_at: str,
) -> str:
    if load_status != "ok":
        return ""
    explicit_status = _status_from_payload(
        payload,
        "signoff_status",
        "readiness_status",
        "status",
    )
    if explicit_status:
        return explicit_status
    summary = learning_readiness_signoff_summary(payload, generated_at=generated_at)
    return str(summary.get("signoff_status", "")).strip()


def _remote_sync_signal(
    vault: Path,
    run_manifest: dict[str, Any],
    run_manifest_load_status: str,
    remote_sync_reader: RemoteSyncReader,
) -> dict[str, Any]:
    _ = (run_manifest, run_manifest_load_status)
    return remote_sync_reader(vault)


def build_status_surface(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    lock_check_runner: LockCheckRunner = _run_uv_lock_check,
    canonical_lock_check_runner: LockCheckRunner | None = None,
    remote_sync_reader: RemoteSyncReader = read_remote_sync,
) -> dict[str, Any]:
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    generated_at = runtime_context.isoformat_z()
    closeout, closeout_load_status = _load_optional(vault, DEFAULT_CLOSEOUT)
    sealed_run, sealed_load_status = _load_optional(vault, DEFAULT_SEALED_RUN)
    operator_summary, operator_load_status = _load_optional(vault, DEFAULT_OPERATOR_SUMMARY)
    public_summary, public_load_status = _load_optional(vault, DEFAULT_PUBLIC_SUMMARY)
    provenance, _provenance_load_status = _load_optional(vault, DEFAULT_SUPPLY_CHAIN_PROVENANCE)
    learning_signoff, learning_load_status = _load_optional(vault, DEFAULT_LEARNING_SIGNOFF)
    goal_certificate, goal_load_status = _load_optional(vault, DEFAULT_GOAL_RUNTIME_CERTIFICATE)
    run_manifest, run_manifest_load_status = _load_optional(vault, DEFAULT_RELEASE_RUN_MANIFEST)
    current_source_revision = resolve_source_revision(vault).revision
    current_source_tree_fingerprint = release_source_tree_fingerprint(vault)

    source_status, freshness = _source_closeout_status(closeout, closeout_load_status)
    sealed_status, sealed_evidence_path = _sealed_run_status(
        sealed_run,
        sealed_load_status,
        operator_summary,
        operator_load_status,
    )
    public_status = (
        _status_from_payload(public_summary, "status", "result")
        if public_load_status == "ok"
        else STATUS_VALUE_UNKNOWN
    )
    learning_status = _learning_signoff_status(
        learning_signoff,
        load_status=learning_load_status,
        generated_at=generated_at,
    )
    goal_status = (
        _status_from_payload(goal_certificate, "status", "certificate_status", "result")
        if goal_load_status == "ok"
        else ""
    )
    selected_canonical_lock_check_runner = (
        _run_canonical_uv_lock_check
        if canonical_lock_check_runner is None and lock_check_runner is _run_uv_lock_check
        else canonical_lock_check_runner or lock_check_runner
    )
    lock_check = lock_check_runner(vault)
    canonical_lock_check = selected_canonical_lock_check_runner(vault)
    remote_signal = _remote_sync_signal(
        vault,
        run_manifest,
        run_manifest_load_status,
        remote_sync_reader,
    )
    return status_surface_from_signals(
        generated_at=generated_at,
        vault_completeness=_vault_completeness(vault),
        source_closeout_status=source_status,
        sealed_run_status=sealed_status,
        public_summary_status=public_status,
        lock_check_status=_lock_check_status_from_provenance(provenance),
        uv_lock_check_passed=str(lock_check.get("status", "")).strip() == STATUS_VALUE_PASS,
        canonical_uv_lock_check_passed=(
            str(canonical_lock_check.get("status", "")).strip() == STATUS_VALUE_PASS
        ),
        learning_signoff_status=learning_status,
        goal_runtime_certificate_status=goal_status,
        remote_sync_signal=remote_signal,
        artifact_freshness_display=freshness,
        sealed_run_evidence_path=sealed_evidence_path,
        source_closeout_currentness_detail=_evidence_currentness_detail(
            closeout,
            closeout_load_status,
            current_source_revision=current_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            binding_mode="revision",
        ),
        public_summary_currentness_detail=_evidence_currentness_detail(
            public_summary,
            public_load_status,
            current_source_revision=current_source_revision,
            current_source_tree_fingerprint=current_source_tree_fingerprint,
            binding_mode="content",
        ),
    )


def render_status_surface_text(surface: dict[str, Any]) -> str:
    rows: list[str] = []
    for line in surface.get("lines", []):
        if not isinstance(line, dict):
            continue
        axis = str(line.get("axis") or "none")
        rows.append(
            f"{line.get('key')}: {line.get('status')} | axis={axis} | "
            f"evidence={line.get('evidence_path')} | {line.get('detail')}"
        )
    return "\n".join(rows) + ("\n" if rows else "")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the LLMwiki operator status surface.")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument(
        "--skip-lock-check",
        action="store_true",
        help="Do not run uv lock --check; render lock freshness as fail/unknown.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    lock_runner = _skipped_lock_check if args.skip_lock_check else _run_uv_lock_check
    canonical_lock_runner = (
        _skipped_lock_check if args.skip_lock_check else _run_canonical_uv_lock_check
    )
    surface = build_status_surface(
        vault,
        lock_check_runner=lock_runner,
        canonical_lock_check_runner=canonical_lock_runner,
    )
    if args.format == "json":
        print(json.dumps(surface, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        sys.stdout.write(render_status_surface_text(surface))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
