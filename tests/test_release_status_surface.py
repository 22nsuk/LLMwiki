from __future__ import annotations

import datetime as dt
import json
import string
import subprocess
import tempfile
from pathlib import Path

import hypothesis.strategies as st
import pytest
from hypothesis import given
from ops.scripts.runtime_context import RuntimeContext

from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.release.release_status_surface import (
    DEFAULT_REMOTE_SYNC_LIVE_EVIDENCE,
    FRESHNESS_DISPLAY_VALUES,
    STATUS_KEYS,
    STATUS_VALUE_NOT_SYNCED,
    STATUS_VALUE_PASS,
    STATUS_VALUE_REQUIRES_FULL_VAULT,
    STATUS_VALUE_SYNCED,
    STATUS_VALUE_UNKNOWN,
    TOOLCHAIN_ALIGNMENT_ALIGNED,
    TOOLCHAIN_ALIGNMENT_BASELINE_NEEDS_NORMALIZATION,
    TOOLCHAIN_ALIGNMENT_CANONICAL_FAILED,
    TOOLCHAIN_ALIGNMENT_POLICY_EVIDENCE_NOT_ENFORCED,
    VAULT_COMPLETENESS_FULL,
    VAULT_COMPLETENESS_PUBLIC,
    StatusSurfaceSignals,
    build_status_surface,
    lockfile_freshness_display_status,
    remote_sync_display_status,
    render_status_surface_text,
    status_surface_from_signals,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAFE_TEXT = st.text(alphabet=string.ascii_lowercase + string.digits + "-_", min_size=1, max_size=20)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 31, 12, 0, tzinfo=dt.UTC),
    )


def _request_object_signals() -> StatusSurfaceSignals:
    return StatusSurfaceSignals(
        generated_at="2026-05-31T12:00:00Z",
        vault_completeness=VAULT_COMPLETENESS_PUBLIC,
        source_closeout_status="clean_pass",
        sealed_run_status="sealed_clean_pass",
        public_summary_status="pass",
        lock_check_status="enforced",
        uv_lock_check_passed=True,
        learning_signoff_status="",
        goal_runtime_certificate_status="",
        remote_sync_signal={
            "status": "pass",
            "upstream": "origin/feature",
            "ahead": 0,
            "behind": 0,
        },
        artifact_freshness_display="advisory",
    )


def _line_by_key(surface: dict[str, object], key: str) -> dict[str, object]:
    lines = surface["lines"]
    assert isinstance(lines, list)
    matches = [line for line in lines if isinstance(line, dict) and line.get("key") == key]
    assert len(matches) == 1
    return matches[0]


@given(
    upstream=st.one_of(st.just(""), SAFE_TEXT.map(lambda value: f"origin/{value}")),
    ahead=st.integers(min_value=0, max_value=5),
    behind=st.integers(min_value=0, max_value=5),
    status=st.sampled_from(["pass", "fail", "unknown", ""]),
)
def test_property_1_remote_sync_display_mapping_is_total_and_head_aware(
    upstream: str,
    ahead: int,
    behind: int,
    status: str,
) -> None:
    """Feature: release-evidence-sync, Property 1: remote-sync display mapping is total and HEAD-aware"""
    display = remote_sync_display_status(
        {
            "status": status,
            "upstream": upstream,
            "ahead": ahead,
            "behind": behind,
        }
    )

    assert display in {STATUS_VALUE_SYNCED, STATUS_VALUE_NOT_SYNCED}
    if upstream and ahead == 0 and behind == 0 and status == STATUS_VALUE_PASS:
        assert display == STATUS_VALUE_SYNCED
    else:
        assert display == STATUS_VALUE_NOT_SYNCED


@given(
    lock_check_status=st.sampled_from(
        ["enforced", "missing_ci_check", "missing_lockfile", "failed", "unknown", ""]
    ),
    uv_lock_check_passed=st.booleans(),
)
def test_property_2_lockfile_display_never_masks_a_failing_check(
    lock_check_status: str,
    uv_lock_check_passed: bool,
) -> None:
    """Feature: release-evidence-sync, Property 2: lockfile display never masks a failing check"""
    display = lockfile_freshness_display_status(
        lock_check_status=lock_check_status,
        uv_lock_check_passed=uv_lock_check_passed,
    )

    if lock_check_status == "enforced" and uv_lock_check_passed:
        assert display == STATUS_VALUE_PASS
    else:
        assert display != STATUS_VALUE_PASS


@given(
    vault_completeness=st.sampled_from([VAULT_COMPLETENESS_FULL, VAULT_COMPLETENESS_PUBLIC]),
    freshness=st.sampled_from(sorted(FRESHNESS_DISPLAY_VALUES)),
    learning_available=st.booleans(),
    goal_available=st.booleans(),
    lock_check_status=st.sampled_from(["enforced", "missing_ci_check", "missing_lockfile", "failed", "unknown"]),
    uv_lock_check_passed=st.booleans(),
)
def test_property_11_status_surface_shape_and_unverifiable_evidence_handling(
    vault_completeness: str,
    freshness: str,
    learning_available: bool,
    goal_available: bool,
    lock_check_status: str,
    uv_lock_check_passed: bool,
) -> None:
    """Feature: release-evidence-sync, Property 11: status surface shape and unverifiable-evidence handling"""
    surface = status_surface_from_signals(
        generated_at="2026-05-31T12:00:00Z",
        vault_completeness=vault_completeness,
        source_closeout_status="clean_pass",
        sealed_run_status="sealed_clean_pass",
        public_summary_status="pass",
        lock_check_status=lock_check_status,
        uv_lock_check_passed=uv_lock_check_passed,
        learning_signoff_status="pass" if learning_available else "",
        goal_runtime_certificate_status="pass" if goal_available else "",
        remote_sync_signal={
            "status": "pass",
            "upstream": "origin/feature",
            "ahead": 0,
            "behind": 0,
        },
        artifact_freshness_display=freshness,
    )

    lines = surface["lines"]
    assert isinstance(lines, list)
    assert len(lines) == len(STATUS_KEYS)
    assert [line["key"] for line in lines] == list(STATUS_KEYS)
    assert len({line["key"] for line in lines}) == len(STATUS_KEYS)
    assert f"freshness={freshness}" in str(_line_by_key(surface, "source_closeout")["detail"])
    lock_detail = str(_line_by_key(surface, "lockfile_freshness")["detail"])
    assert "baseline_environment_lock_check=" in lock_detail
    assert "canonical_lock_check=" in lock_detail
    assert "toolchain_alignment=" in lock_detail
    assert "recommended_normalization_step=" in lock_detail
    assert surface["baseline_environment_lock_check_status"] in {"pass", "fail"}
    assert surface["canonical_lock_check_status"] in {"pass", "fail"}
    assert str(surface["toolchain_alignment_status"])
    assert str(surface["recommended_normalization_step"])
    if vault_completeness == VAULT_COMPLETENESS_PUBLIC and not learning_available:
        assert _line_by_key(surface, "learning_signoff")["status"] == STATUS_VALUE_REQUIRES_FULL_VAULT
    if vault_completeness == VAULT_COMPLETENESS_PUBLIC and not goal_available:
        assert (
            _line_by_key(surface, "goal_runtime_certificate")["status"]
            == STATUS_VALUE_REQUIRES_FULL_VAULT
        )
    if not (lock_check_status == "enforced" and uv_lock_check_passed):
        assert _line_by_key(surface, "lockfile_freshness")["status"] != STATUS_VALUE_PASS


@given(
    source_status=st.sampled_from(["clean_pass", "conditional_pass", "failed", "semantic_clean_unsealed"]),
    sealed_status=st.sampled_from(
        ["sealed_clean_pass", "sealed_conditional_pass", "unsealed_missing_manifest", "unsealed_mismatch"]
    ),
)
def test_property_12_source_closeout_and_sealed_run_axes_are_independent(
    source_status: str,
    sealed_status: str,
) -> None:
    """Feature: release-evidence-sync, Property 12: source-closeout and sealed-run axes are independent"""
    surface = status_surface_from_signals(
        generated_at="2026-05-31T12:00:00Z",
        vault_completeness=VAULT_COMPLETENESS_FULL,
        source_closeout_status=source_status,
        sealed_run_status=sealed_status,
        public_summary_status="pass",
        lock_check_status="enforced",
        uv_lock_check_passed=True,
        learning_signoff_status="pass",
        goal_runtime_certificate_status="pass",
        remote_sync_signal={
            "status": "pass",
            "upstream": "origin/feature",
            "ahead": 0,
            "behind": 0,
        },
        artifact_freshness_display="none",
    )

    assert _line_by_key(surface, "source_closeout")["status"] == source_status
    assert _line_by_key(surface, "sealed_run")["status"] == sealed_status
    assert _line_by_key(surface, "source_closeout")["axis"] == "source_closeout"
    assert _line_by_key(surface, "sealed_run")["axis"] == "sealed_run"


def test_status_surface_accepts_signal_request_object() -> None:
    surface = status_surface_from_signals(_request_object_signals())

    assert _line_by_key(surface, "source_closeout")["status"] == "clean_pass"
    assert "freshness=advisory" in str(_line_by_key(surface, "source_closeout")["detail"])
    assert _line_by_key(surface, "remote_sync")["status"] == STATUS_VALUE_SYNCED


def test_status_surface_rejects_mixed_signal_request_object_and_legacy_kwargs() -> None:
    with pytest.raises(
        TypeError,
        match="signals cannot be combined with legacy keyword arguments: generated_at",
    ):
        status_surface_from_signals(_request_object_signals(), generated_at="override")


def test_status_surface_reads_existing_file_signals_without_writing_authority() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        closeout = vault / "ops" / "reports" / "release-closeout-summary.json"
        provenance = vault / "ops" / "reports" / "supply-chain-provenance.json"
        public_summary = vault / "ops" / "reports" / "public-check-summary.json"
        learning_signoff = vault / "ops" / "reports" / "learning-readiness-signoff.json"
        run_manifest = vault / "build" / "release" / "release-run-manifest.json"
        closeout.parent.mkdir(parents=True)
        run_manifest.parent.mkdir(parents=True)
        closeout.write_text(
            json.dumps(
                {
                    "release_authority_status": "clean_pass",
                    "machine_release_allowed": True,
                    "artifact_freshness_gate": {"display_effect": "advisory"},
                }
            ),
            encoding="utf-8",
        )
        public_summary.write_text(json.dumps({"status": "pass"}), encoding="utf-8")
        provenance.write_text(
            json.dumps({"lock_evidence": {"lock_check_status": "enforced"}}),
            encoding="utf-8",
        )
        learning_signoff.write_text(
            json.dumps(
                {
                    "artifact_kind": "learning_readiness_signoff",
                    "linked_blocker_id": "learning_blocked_by_review_required",
                    "accepted_by": "operator",
                    "risk_owner": "runtime-maintainer",
                    "expires_at": "2026-06-07T12:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        run_manifest.write_text(
            json.dumps(
                {
                    "remote_sync": {
                        "status": "fail",
                        "upstream": "origin/feature",
                        "ahead": 1,
                        "behind": 0,
                    }
                }
            ),
            encoding="utf-8",
        )

        surface = build_status_surface(
            vault,
            context=fixed_context(),
            lock_check_runner=lambda _vault: {"status": "pass", "returncode": 0},
            remote_sync_reader=lambda _vault: {
                "status": "pass",
                "upstream": "origin/feature",
                "ahead": 0,
                "behind": 0,
            },
        )

        assert _line_by_key(surface, "source_closeout")["status"] == "clean_pass"
        assert "freshness=advisory" in str(_line_by_key(surface, "source_closeout")["detail"])
        assert "evidence_currentness=stale" in str(
            _line_by_key(surface, "source_closeout")["detail"]
        )
        assert _line_by_key(surface, "public_summary")["status"] == "pass"
        assert "evidence_currentness=stale" in str(
            _line_by_key(surface, "public_summary")["detail"]
        )
        assert _line_by_key(surface, "lockfile_freshness")["status"] == "pass"
        assert _line_by_key(surface, "learning_signoff")["status"] == "active"
        assert _line_by_key(surface, "remote_sync")["status"] == STATUS_VALUE_SYNCED
        assert _line_by_key(surface, "remote_sync")["evidence_path"] == DEFAULT_REMOTE_SYNC_LIVE_EVIDENCE
        assert "source=live_git_remote_state" in str(_line_by_key(surface, "remote_sync")["detail"])
        assert surface["baseline_environment_lock_check_status"] == "pass"
        assert surface["canonical_lock_check_status"] == "pass"
        assert surface["toolchain_alignment_status"] == TOOLCHAIN_ALIGNMENT_ALIGNED
        assert surface["recommended_normalization_step"] == "none"
        assert not (vault / "ops" / "operator" / "operator-release-summary.json").exists()


def test_status_surface_displays_currentness_for_public_and_closeout_evidence() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        fingerprint = release_source_tree_fingerprint(vault)
        reports = vault / "ops" / "reports"
        reports.mkdir(parents=True)
        current_envelope = {
            "artifact_status": "current",
            "currentness": {"status": "current"},
            "source_revision": "source_package_without_git",
            "source_tree_fingerprint": fingerprint,
        }
        (reports / "release-closeout-summary.json").write_text(
            json.dumps(
                {
                    **current_envelope,
                    "status": "pass",
                    "release_authority_status": "clean_pass",
                    "machine_release_allowed": True,
                }
            ),
            encoding="utf-8",
        )
        (reports / "public-check-summary.json").write_text(
            json.dumps(
                {
                    **current_envelope,
                    "status": "pass",
                    "summary": {"public_check_status": "pass"},
                }
            ),
            encoding="utf-8",
        )

        surface = build_status_surface(
            vault,
            context=fixed_context(),
            lock_check_runner=lambda _vault: {"status": "pass", "returncode": 0},
            remote_sync_reader=lambda _vault: {
                "status": "unknown",
                "upstream": "",
                "ahead": 0,
                "behind": 0,
            },
        )

        assert "evidence_currentness=current" in str(
            _line_by_key(surface, "source_closeout")["detail"]
        )
        assert "evidence_currentness=current" in str(
            _line_by_key(surface, "public_summary")["detail"]
        )


def test_status_surface_keeps_self_declared_currentness_visible_when_evidence_is_stale() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        reports = vault / "ops" / "reports"
        reports.mkdir(parents=True)
        stale_envelope = {
            "artifact_status": "current",
            "currentness": {"status": "current"},
            "source_revision": "source_package_without_git",
            "source_tree_fingerprint": "old-source-tree",
        }
        (reports / "release-closeout-summary.json").write_text(
            json.dumps(
                {
                    **stale_envelope,
                    "status": "pass",
                    "release_authority_status": "clean_pass",
                    "machine_release_allowed": True,
                }
            ),
            encoding="utf-8",
        )
        (reports / "public-check-summary.json").write_text(
            json.dumps(
                {
                    **stale_envelope,
                    "status": "pass",
                    "summary": {"public_check_status": "pass"},
                }
            ),
            encoding="utf-8",
        )

        surface = build_status_surface(
            vault,
            context=fixed_context(),
            lock_check_runner=lambda _vault: {"status": "pass", "returncode": 0},
            remote_sync_reader=lambda _vault: {
                "status": "unknown",
                "upstream": "",
                "ahead": 0,
                "behind": 0,
            },
        )

        for key in ("source_closeout", "public_summary"):
            detail = str(_line_by_key(surface, key)["detail"])
            assert "evidence_currentness=stale" in detail
            assert "self_declared_currentness=current" in detail
            assert "source_tree_fingerprint=stale" in detail


def test_status_surface_distinguishes_ambient_from_canonical_lock_check() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        provenance = vault / "ops" / "reports" / "supply-chain-provenance.json"
        provenance.parent.mkdir(parents=True)
        provenance.write_text(
            json.dumps({"lock_evidence": {"lock_check_status": "enforced"}}),
            encoding="utf-8",
        )

        surface = build_status_surface(
            vault,
            context=fixed_context(),
            lock_check_runner=lambda _vault: {"status": "fail", "returncode": 1},
            canonical_lock_check_runner=lambda _vault: {"status": "pass", "returncode": 0},
            remote_sync_reader=lambda _vault: {
                "status": "unknown",
                "upstream": "",
                "ahead": 0,
                "behind": 0,
            },
        )

        lock_line = _line_by_key(surface, "lockfile_freshness")
        assert lock_line["status"] == STATUS_VALUE_PASS
        assert surface["baseline_environment_lock_check_status"] == "fail"
        assert surface["canonical_lock_check_status"] == "pass"
        assert surface["toolchain_alignment_status"] == TOOLCHAIN_ALIGNMENT_BASELINE_NEEDS_NORMALIZATION
        assert (
            surface["recommended_normalization_step"]
            == "set UV_CANONICAL_INDEX_URL=https://pypi.org/simple and rerun make uv-lock-check"
        )
        assert "baseline_environment_lock_check=fail" in str(lock_line["detail"])
        assert "canonical_lock_check=pass" in str(lock_line["detail"])


def test_status_surface_fails_lock_freshness_when_canonical_lock_check_fails() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        provenance = vault / "ops" / "reports" / "supply-chain-provenance.json"
        provenance.parent.mkdir(parents=True)
        provenance.write_text(
            json.dumps({"lock_evidence": {"lock_check_status": "enforced"}}),
            encoding="utf-8",
        )

        surface = build_status_surface(
            vault,
            context=fixed_context(),
            lock_check_runner=lambda _vault: {"status": "pass", "returncode": 0},
            canonical_lock_check_runner=lambda _vault: {"status": "fail", "returncode": 1},
            remote_sync_reader=lambda _vault: {
                "status": "unknown",
                "upstream": "",
                "ahead": 0,
                "behind": 0,
            },
        )

        lock_line = _line_by_key(surface, "lockfile_freshness")
        assert lock_line["status"] != STATUS_VALUE_PASS
        assert surface["baseline_environment_lock_check_status"] == "pass"
        assert surface["canonical_lock_check_status"] == "fail"
        assert surface["toolchain_alignment_status"] == TOOLCHAIN_ALIGNMENT_CANONICAL_FAILED
        assert surface["recommended_normalization_step"] == "make uv-lock-check"


def test_status_surface_requires_provenance_policy_even_when_canonical_lock_check_passes() -> None:
    surface = status_surface_from_signals(
        generated_at="2026-05-31T12:00:00Z",
        vault_completeness=VAULT_COMPLETENESS_PUBLIC,
        source_closeout_status=STATUS_VALUE_UNKNOWN,
        sealed_run_status=STATUS_VALUE_UNKNOWN,
        public_summary_status=STATUS_VALUE_UNKNOWN,
        lock_check_status="missing_ci_check",
        uv_lock_check_passed=True,
        canonical_uv_lock_check_passed=True,
        learning_signoff_status="",
        goal_runtime_certificate_status="",
        remote_sync_signal={"status": "unknown", "upstream": "", "ahead": 0, "behind": 0},
        artifact_freshness_display="none",
    )

    lock_line = _line_by_key(surface, "lockfile_freshness")
    assert lock_line["status"] != STATUS_VALUE_PASS
    assert surface["baseline_environment_lock_check_status"] == "pass"
    assert surface["canonical_lock_check_status"] == "pass"
    assert surface["toolchain_alignment_status"] == TOOLCHAIN_ALIGNMENT_POLICY_EVIDENCE_NOT_ENFORCED
    assert surface["recommended_normalization_step"] == "refresh supply-chain provenance evidence"


def test_status_surface_does_not_promote_stale_manifest_remote_sync_when_live_state_unknown() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        run_manifest = vault / "build" / "release" / "release-run-manifest.json"
        run_manifest.parent.mkdir(parents=True)
        run_manifest.write_text(
            json.dumps(
                {
                    "remote_sync": {
                        "status": "pass",
                        "upstream": "origin/main",
                        "ahead": 0,
                        "behind": 0,
                    }
                }
            ),
            encoding="utf-8",
        )

        surface = build_status_surface(
            vault,
            context=fixed_context(),
            lock_check_runner=lambda _vault: {"status": "pass", "returncode": 0},
            remote_sync_reader=lambda _vault: {
                "status": "unknown",
                "upstream": "",
                "ahead": 0,
                "behind": 0,
            },
        )

        assert _line_by_key(surface, "remote_sync")["status"] == STATUS_VALUE_NOT_SYNCED
        assert _line_by_key(surface, "remote_sync")["evidence_path"] == DEFAULT_REMOTE_SYNC_LIVE_EVIDENCE


def test_status_surface_text_renderer_outputs_exactly_seven_public_safe_lines() -> None:
    surface = status_surface_from_signals(
        generated_at="2026-05-31T12:00:00Z",
        vault_completeness=VAULT_COMPLETENESS_PUBLIC,
        source_closeout_status=STATUS_VALUE_UNKNOWN,
        sealed_run_status=STATUS_VALUE_UNKNOWN,
        public_summary_status=STATUS_VALUE_UNKNOWN,
        lock_check_status="unknown",
        uv_lock_check_passed=False,
        learning_signoff_status="",
        goal_runtime_certificate_status="",
        remote_sync_signal={"status": "unknown", "upstream": "", "ahead": 0, "behind": 0},
        artifact_freshness_display="none",
    )

    rendered = render_status_surface_text(surface)

    lines = rendered.strip().splitlines()
    assert len(lines) == len(STATUS_KEYS)
    assert [line.split(":", 1)[0] for line in lines] == list(STATUS_KEYS)
    assert not any(str(REPO_ROOT) in line for line in lines)


def test_status_entrypoint_make_aliases_render_the_same_seven_line_surface() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        status = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-s",
                "status",
                f"VAULT={vault}",
                "STATUS_FLAGS=--skip-lock-check",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        alias = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-s",
                "llm-wiki-status",
                f"VAULT={vault}",
                "STATUS_FLAGS=--skip-lock-check",
            ],
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

    assert status.stdout == alias.stdout
    lines = status.stdout.strip().splitlines()
    assert len(lines) == len(STATUS_KEYS)
    assert [line.split(":", 1)[0] for line in lines] == list(STATUS_KEYS)


def test_pyproject_registers_llm_wiki_status_console_script() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'llm-wiki-status = "ops.scripts.release.release_status_surface:main"' in pyproject
