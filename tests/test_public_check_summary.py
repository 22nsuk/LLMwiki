from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager, redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import ops.scripts.public.public_check_summary as public_check_summary_module
from ops.scripts.core.command_runtime import ProcessCleanupError, TimedProcessResult
from ops.scripts.core.policy_runtime import LOCAL_CORPUS_POLICY_PATH
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.public.export_public_repo import public_export_session
from ops.scripts.public.public_check_summary import (
    PublicCheckRequest,
    _default_command_runner,
    _public_check_config_fingerprint,
    _public_export_negative_assertions,
    _public_pytest_summary_cache_path,
    _resolve_public_python,
    build_report,
    reusable_summary_diagnostics,
    write_report,
)
from ops.scripts.public.public_toolchain_runtime import public_toolchain_fingerprint
from ops.scripts.public.source_history_scan_runtime import scan_source_history
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "public-check-summary.schema.json"
PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH = Path(
    "ops/reports/test-execution-summary-public.json"
)


@pytest.fixture(autouse=True)
def selected_python_on_path(monkeypatch):
    # Bare "python" requests in command/config fixtures use this test environment.
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))


def _git(vault: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=vault,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _initialize_git_repository(vault: Path) -> None:
    _git(vault, "init", "-q")
    _git(vault, "config", "user.email", "public-history@example.test")
    _git(vault, "config", "user.name", "Public History Test")


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 5, 9, 9, 0, tzinfo=dt.UTC),
    )


def seed_public_policy_file(vault: Path) -> None:
    policy_path = vault / "ops" / "scripts" / "public" / "public_surface_policy.py"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text("PUBLIC_INCLUDE_PREFIXES = ()\n", encoding="utf-8")


def write_public_pytest_summary(
    cwd: Path,
    *,
    passed: int,
    failed: int,
    errors: int,
    skipped: int,
) -> None:
    summary_path = cwd / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "counts": {
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "skipped": skipped,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def fake_runner(
    argv: Sequence[str], cwd: Path, timeout_seconds: int
) -> TimedProcessResult:
    module = argv[2] if len(argv) > 2 else ""
    stdout = ""
    if module == "ops.scripts.test_execution_summary":
        write_public_pytest_summary(cwd, passed=217, failed=0, errors=0, skipped=5)
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=0,
        stdout=stdout,
        stderr="",
        timed_out=False,
        timeout_seconds=timeout_seconds,
        termination_reason="completed",
    )


@pytest.mark.parametrize("mode", ["default", "full"])
def test_cli_refresh_reuses_private_export_after_toolchain_miss(
    tmp_path: Path, monkeypatch, mode: str,
) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    monkeypatch.setenv("PYTHONPATH", ".:tools")
    monkeypatch.setenv("PYTHONSAFEPATH", "1")
    request = PublicCheckRequest(mode=mode, source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(tmp_path, report)
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    monkeypatch.setenv("PYTEST_ADDOPTS", "-q")
    exports: list[Path] = []

    @contextmanager
    def observed_export(vault, output):
        exports.append(output)
        with public_export_session(vault, output) as manifest:
            yield manifest

    with (
        patch.object(public_check_summary_module, "public_export_session", observed_export),
        patch.object(public_check_summary_module, "_default_command_runner", side_effect=lambda argv, cwd, timeout_seconds, **kwargs: fake_runner(argv, cwd, timeout_seconds)),
        redirect_stdout(io.StringIO()),
    ):
        assert public_check_summary_module.main([
            "--vault", str(tmp_path), "--mode", mode, "--out", "tmp/candidate.json",
            "--reuse-from", str(destination), "--reuse-if-current", "--skip-source-history-scan",
        ]) == 0
    assert len(exports) == 1
    assert not exports[0].exists()
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
    assert reusable_summary_diagnostics(tmp_path, "tmp/candidate.json", request)["reusable"]


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("outcome", ["hit", "source_miss", "history_miss", "reuse_only", "pass", "fail"])
def test_cli_session_preserves_publication_and_locking(
    tmp_path: Path, monkeypatch, retained: bool, outcome: str,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(public_out=str(tmp_path / "public") if retained else "", source_history_scan=False)
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    if outcome == "source_miss":
        report["source_tree_fingerprint"] = "0" * 64
    elif outcome == "history_miss":
        report["input_fingerprints"]["source_history_state"] = "0" * 64
    destination = write_report(vault, report)
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    candidate = vault / "tmp/candidate.json"
    candidate.parent.mkdir(exist_ok=True)
    candidate.write_text("stale candidate must never be promoted on a hit\n")
    candidate_before = candidate.read_bytes(), candidate.stat().st_mtime_ns
    if outcome in {"pass", "fail", "reuse_only"}:
        monkeypatch.setenv("PYTEST_ADDOPTS", "-q")
    commands: list[Path] = []
    exports: list[Path] = []

    @contextmanager
    def observed_export(source, output):
        exports.append(output)
        with public_export_session(source, output) as manifest:
            yield manifest

    def runner(argv, cwd, timeout_seconds, **kwargs):
        commands.append(cwd)
        # The reused private export remains owned by the invocation throughout validation.
        with pytest.raises(RuntimeError, match="output lock"), public_export_session(vault, cwd):
            pytest.fail("validation lost its output lock")
        result = fake_runner(argv, cwd, timeout_seconds)
        return replace(result, returncode=1) if outcome == "fail" else result

    with (
        patch.object(public_check_summary_module, "public_export_session", observed_export),
        patch.object(public_check_summary_module, "_default_command_runner", side_effect=runner),
        redirect_stdout(io.StringIO()),
    ):
        result = public_check_summary_module.main([
            "--vault", str(vault), "--out", str(candidate), "--promote-to", str(destination),
            "--reuse-from", str(destination), "--public-out", request.public_out,
            "--reuse-if-current", "--skip-source-history-scan",
            *(["--reuse-only"] if outcome == "reuse_only" else []),
        ])
    assert result == (1 if outcome in {"fail", "reuse_only"} else 0)
    executed = outcome not in {"hit", "reuse_only"}
    assert bool(commands) == executed
    assert len(exports) == (0 if retained and not executed else 1)
    assert all(path.exists() == retained for path in exports)
    if not executed:
        assert (candidate.read_bytes(), candidate.stat().st_mtime_ns) == candidate_before
    if outcome in {"hit", "reuse_only", "fail"}:
        assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
    else:
        assert reusable_summary_diagnostics(vault, destination, request)["reusable"]
    if outcome == "fail":
        assert json.loads(candidate.read_text())["status"] == "fail"


@pytest.mark.parametrize("change", ["source", "export", "probe_error"])
def test_cli_discards_unsafe_prepared_export(tmp_path: Path, monkeypatch, change: str) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    (tmp_path / "README.md").write_text("original source\n")
    request = PublicCheckRequest(source_history_scan=False)
    destination = write_report(tmp_path, build_report(
        tmp_path, request, context=fixed_context(), command_runner=fake_runner,
    ))
    original_readme = (tmp_path / "README.md").read_text()
    probes: list[Path] = []
    commands: list[Path] = []

    def probe(public_python, *, cwd, private_workspace):
        probes.append(cwd)
        if len(probes) == 1:
            if change == "probe_error":
                raise OSError("temporary probe failure")
            target = tmp_path if change == "source" else cwd
            (target / "README.md").write_text("changed during probe\n")
        return public_toolchain_fingerprint(public_python, cwd=cwd, private_workspace=private_workspace)

    def runner(argv, cwd, timeout_seconds, **kwargs):
        commands.append(cwd)
        expected = "changed during probe\n" if change == "source" else original_readme
        assert (cwd / "README.md").read_text() == expected
        return fake_runner(argv, cwd, timeout_seconds)

    with (
        patch.object(public_check_summary_module, "public_toolchain_fingerprint", side_effect=probe),
        patch.object(public_check_summary_module, "_default_command_runner", side_effect=runner),
        redirect_stdout(io.StringIO()),
    ):
        assert public_check_summary_module.main([
            "--vault", str(tmp_path), "--out", "tmp/candidate.json", "--reuse-from", str(destination),
            "--reuse-if-current", "--skip-source-history-scan",
        ]) == 0
    assert len(probes) == 3
    assert probes[0] != probes[1] == probes[2]
    assert set(commands) == {probes[1]}
    assert all(not path.exists() for path in probes)
    assert reusable_summary_diagnostics(tmp_path, "tmp/candidate.json", request)["reusable"]


@pytest.mark.parametrize("failure", ["probe_cleanup", "workspace_hit", "workspace_miss", "workspace_refresh"])
def test_cli_session_cleanup_failure_prevents_publication(tmp_path: Path, monkeypatch, failure: str) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(source_history_scan=False)
    destination = write_report(tmp_path, build_report(
        tmp_path, request, context=fixed_context(), command_runner=fake_runner,
    ))
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    candidate = tmp_path / "tmp/candidate.json"
    outputs: list[Path] = []
    if failure == "workspace_refresh":
        monkeypatch.setenv("PYTEST_ADDOPTS", "-q")

    @contextmanager
    def workspace(vault, requested):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "export"
            outputs.append(output)
            yield output
        if failure.startswith("workspace"):
            raise OSError("workspace cleanup failed")

    def probe(public_python, *, cwd, private_workspace):
        if failure == "probe_cleanup":
            raise ProcessCleanupError("probe cleanup failed")
        if failure == "workspace_miss":
            raise ValueError("probe unavailable")
        return public_toolchain_fingerprint(public_python, cwd=cwd, private_workspace=private_workspace)

    stdout = io.StringIO()
    with (
        patch.object(public_check_summary_module, "_public_check_output", workspace),
        patch.object(public_check_summary_module, "public_toolchain_fingerprint", side_effect=probe),
        patch.object(public_check_summary_module, "_default_command_runner", side_effect=lambda argv, cwd, timeout_seconds, **kwargs: fake_runner(argv, cwd, timeout_seconds)) as run,
        redirect_stdout(stdout),
        pytest.raises(ProcessCleanupError if failure == "probe_cleanup" else OSError, match="cleanup failed"),
    ):
        public_check_summary_module.main([
            "--vault", str(tmp_path), "--out", str(candidate), "--promote-to", str(destination),
            "--reuse-from", str(destination), "--reuse-if-current", "--skip-source-history-scan",
        ])
    assert bool(run.call_count) == (failure == "workspace_refresh")
    assert not candidate.exists()
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
    assert '"summary_mode": "reused"' not in stdout.getvalue()
    assert len(outputs) == 1 and not outputs[0].exists()


@pytest.mark.parametrize("changed", ["source", "export", "toolchain"])
def test_reused_session_rejects_drift_during_validation(tmp_path: Path, monkeypatch, changed: str) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(source_history_scan=False)
    destination = write_report(tmp_path, build_report(
        tmp_path, request, context=fixed_context(), command_runner=fake_runner,
    ))
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    monkeypatch.setenv("PYTEST_ADDOPTS", "-q")
    cache = _public_pytest_summary_cache_path(tmp_path, request)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"previous cache")
    outputs: list[Path] = []

    def runner(argv, cwd, timeout_seconds, **kwargs):
        outputs.append(cwd)
        if changed == "toolchain":
            monkeypatch.setenv("PYTEST_ADDOPTS", "-x")
        else:
            ((tmp_path if changed == "source" else cwd) / "README.md").write_text("changed\n")
        return fake_runner(argv, cwd, timeout_seconds)

    with (
        patch.object(public_check_summary_module, "_default_command_runner", side_effect=runner),
        redirect_stdout(io.StringIO()),
        pytest.raises(ValueError, match="changed during validation"),
    ):
        public_check_summary_module.main([
            "--vault", str(tmp_path), "--out", "tmp/candidate.json", "--promote-to", str(destination),
            "--reuse-from", str(destination), "--reuse-if-current", "--skip-source-history-scan",
        ])
    assert outputs and all(not path.exists() for path in outputs)
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
    assert not (tmp_path / "tmp/candidate.json").exists()
    assert cache.read_bytes() == b"previous cache"


def test_make_current_or_refresh_uses_one_cli_and_promotes_only_execution(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest()
    destination = write_report(vault, build_report(
        vault, request, context=fixed_context(), command_runner=fake_runner,
    ))
    candidate = vault / "tmp/candidate.json"
    candidate.parent.mkdir(exist_ok=True)
    candidate.write_text("stale candidate\n")
    shim = tmp_path / "invoke.py"
    invocations = tmp_path / "invocations"
    shim.write_text(
        "import sys\nfrom pathlib import Path\nfrom dataclasses import replace\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from tests.test_public_check_summary import fake_runner\n"
        "from ops.scripts.public import public_check_summary as module\n"
        f"with Path({str(invocations)!r}).open('a') as handle: handle.write('invoke\\n')\n"
        "def runner(argv, cwd, timeout_seconds, **kwargs):\n"
        "    result = fake_runner(argv, cwd, timeout_seconds)\n"
        "    return replace(result, returncode=1) if 'fail-check' in sys.argv else result\n"
        "module._default_command_runner = runner\n"
        "args = sys.argv[3:]\n"
        "raise SystemExit(module.main(args))\n"
    )
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        f"include {REPO_ROOT / 'mk/public.mk'}\n"
        "script-output-surfaces-check:\n\t@true\n"
    )
    command = [
        "make", "--no-print-directory", "-f", str(makefile), "public-check-summary-current-or-refresh",
        f"PYTHON={sys.executable} {shim}", f"VAULT={vault}", f"PUBLIC_PYTHON={sys.executable}",
        "RUFF_TARGETS=ops/scripts tests tools", "MYPY_TARGETS=ops/scripts", "PYTEST_PUBLIC_MARK_EXPR=public",
        "PYTEST_FLAGS=", "PUBLIC_OUT=", f"PUBLIC_CHECK_SUMMARY_OUT={destination}",
        f"PUBLIC_CHECK_SUMMARY_REUSE_FROM={destination}", f"PUBLIC_CHECK_SUMMARY_CANDIDATE_OUT={candidate}",
    ]
    for index, outcome in enumerate(("hit", "pass", "fail"), 1):
        before = destination.read_bytes(), destination.stat().st_mtime_ns
        if outcome != "hit":
            monkeypatch.setenv("PYTEST_ADDOPTS", "-q" if outcome == "pass" else "-x")
        actual = command + (["PYTEST_FLAGS=fail-check"] if outcome == "fail" else [])
        result = subprocess.run(actual, cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        assert (result.returncode == 0) == (outcome != "fail"), result.stdout + result.stderr
        assert invocations.read_text().splitlines() == ["invoke"] * index
        if outcome != "pass":
            assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
        if outcome == "hit":
            assert '"summary_mode": "reused"' in result.stdout
            assert candidate.read_text() == "stale candidate\n"
        elif outcome == "pass":
            assert reusable_summary_diagnostics(vault, destination, request)["reusable"]
        else:
            assert json.loads(candidate.read_text())["status"] == "fail"


def test_cli_promotion_rejects_candidate_alias_before_execution(tmp_path: Path) -> None:
    canonical = tmp_path / "ops/reports/public-check-summary.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("existing canonical\n")
    with (
        patch.object(public_check_summary_module, "build_report") as run,
        pytest.raises(ValueError, match="candidate and promotion destination must differ"),
    ):
        public_check_summary_module.main([
            "--vault", str(tmp_path), "--out", "ops/reports/../reports/public-check-summary.json",
            "--promote-to", str(canonical),
        ])
    run.assert_not_called()
    assert canonical.read_text() == "existing canonical\n"


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    ("change", "failed_check", "preflight"),
    [
        ("artifact_kind", "artifact_kind", True),
        ("producer", "producer", True),
        ("status", "status", True),
        ("summary_status", "public_check_status", True),
        ("missing_source", "source_tree_fingerprint", True),
        ("public_export_source", "public_export_source", True),
        ("public_python_toolchain", "public_python_toolchain", True),
        ("source_history_state", "source_history_state", True),
        ("public_check_config", "public_check_config", True),
        ("config", "public_check_config", True),
        ("mode", "source_command", True),
        ("local_policy", "local_corpus_policy", True),
        ("source", "source_tree_fingerprint", False),
        ("generated_source", "public_export_source", False),
    ],
)
def test_stale_reuse_stops_before_export_probe_and_history(
    tmp_path: Path, retained: bool, change: str, failed_check: str, preflight: bool,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(public_out=str(tmp_path / "public") if retained else "")
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    checked_request = request
    if change in {"artifact_kind", "producer", "status"}:
        report[change] = "invalid"
    elif change == "summary_status":
        report["summary"]["public_check_status"] = "fail"
    elif change == "missing_source":
        report.pop("source_tree_fingerprint")
    elif change in {
        "public_export_source", "public_python_toolchain", "source_history_state", "public_check_config",
    }:
        report["input_fingerprints"].pop(change)
    elif change == "config":
        checked_request = replace(request, pytest_flags="-q")
    elif change == "mode":
        checked_request = replace(request, mode="full", pytest_mark_expr="")
    elif change == "local_policy":
        (vault / LOCAL_CORPUS_POLICY_PATH).write_text('{"schema_version": 1, "overrides": {}}\n')
    elif change == "source":
        (vault / "README.md").write_text("# Changed public source\n")
    else:
        (vault / "ops/script-output-surfaces.json").write_text('{"version": 1}\n')
    destination = vault / "ops/reports/public-check-summary.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report))
    before = destination.read_bytes(), destination.stat().st_mtime_ns

    with ExitStack() as stack:
        observed = {
            name: stack.enter_context(patch.object(
                public_check_summary_module, name,
                wraps=getattr(public_check_summary_module, name),
            ))
            for name in (
                "release_source_tree_fingerprint", "_public_export_source_inputs",
                "_toolchain_workspace", "_export_toolchain_fingerprint", "source_history_state_fingerprint",
            )
        }
        diagnostics = reusable_summary_diagnostics(vault, destination, checked_request)

    assert not diagnostics["reusable"]
    assert diagnostics["checks"][failed_check] is False
    assert failed_check in diagnostics["reason"]
    for name in ("_toolchain_workspace", "_export_toolchain_fingerprint", "source_history_state_fingerprint"):
        observed[name].assert_not_called()
    if preflight:
        observed["release_source_tree_fingerprint"].assert_not_called()
        observed["_public_export_source_inputs"].assert_not_called()
    else:
        observed["release_source_tree_fingerprint"].assert_called_once()
        observed["_public_export_source_inputs"].assert_called_once()
    # Deferred checks are absent, not reported as successful observations.
    for key in ("retained_export", "public_python_toolchain", "source_history_state"):
        assert diagnostics["checks"].get(key) is not True
    if change in {"config", "mode", "public_check_config"}:
        assert diagnostics["expected_public_check_config_fingerprint"] != diagnostics["observed_public_check_config_fingerprint"]
        assert "expected_source_command" in diagnostics
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before


@pytest.mark.parametrize("retained", [False, True])
def test_current_reuse_still_checks_live_export_toolchain_and_history(tmp_path: Path, retained: bool) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(public_out=str(tmp_path / "public") if retained else "")
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(vault, report)
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    with ExitStack() as stack:
        observed = {
            name: stack.enter_context(patch.object(
                public_check_summary_module, name,
                wraps=getattr(public_check_summary_module, name),
            ))
            for name in (
                "release_source_tree_fingerprint", "_public_export_source_inputs",
                "_export_toolchain_fingerprint", "source_history_state_fingerprint",
                "_retained_export_is_current",
            )
        }
        assert reusable_summary_diagnostics(vault, destination, request)["reusable"]
    observed["_export_toolchain_fingerprint"].assert_called_once()
    observed["source_history_state_fingerprint"].assert_called_once()
    assert observed["release_source_tree_fingerprint"].call_count == 2
    assert observed["_public_export_source_inputs"].call_count == 2
    assert observed["_retained_export_is_current"].call_count == (2 if retained else 0)
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before


@pytest.mark.parametrize("change", ["toolchain", "retained_export"])
def test_reuse_skips_history_after_environment_rejection(tmp_path: Path, monkeypatch, change: str) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    output = tmp_path / "public"
    request = PublicCheckRequest(public_out=str(output) if change == "retained_export" else "")
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(vault, report)
    if change == "toolchain":
        monkeypatch.setenv("PYTEST_ADDOPTS", "-k changed")
    else:
        (output / "README.md").write_text("# Changed export\n")
    with patch.object(
        public_check_summary_module, "source_history_state_fingerprint",
        wraps=public_check_summary_module.source_history_state_fingerprint,
    ) as history:
        diagnostics = reusable_summary_diagnostics(vault, destination, request)
    assert not diagnostics["reusable"]
    assert diagnostics["checks"]["public_python_toolchain"] is False
    assert "source_history_state" not in diagnostics["checks"]
    history.assert_not_called()


@pytest.mark.parametrize("reuse_only", [False, True])
def test_cli_early_rejection_preserves_refresh_and_reuse_only(tmp_path: Path, reuse_only: bool) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(tmp_path, report)
    before = destination.read_bytes(), destination.stat().st_mtime_ns
    candidate = tmp_path / "tmp/candidate.json"

    def refresh(vault: Path, requested: PublicCheckRequest) -> dict[str, Any]:
        return build_report(vault, requested, context=fixed_context(), command_runner=fake_runner)

    stdout = io.StringIO()
    with (
        patch.object(public_check_summary_module, "build_report", side_effect=refresh) as run,
        patch.object(public_check_summary_module, "_toolchain_workspace", wraps=public_check_summary_module._toolchain_workspace) as workspace,
        redirect_stdout(stdout),
    ):
        exit_code = public_check_summary_module.main([
            "--vault", str(tmp_path), "--out", str(candidate), "--reuse-from", str(destination),
            "--reuse-if-current", "--skip-source-history-scan", "--pytest-flags=-q",
            *(["--reuse-only"] if reuse_only else []),
        ])
    diagnostics = json.JSONDecoder().raw_decode(stdout.getvalue())[0]["reuse_diagnostics"]
    assert "public_check_config" in diagnostics["reason"]
    assert "public_python_toolchain" not in diagnostics["checks"]
    workspace.assert_not_called()
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
    if reuse_only:
        assert exit_code == 1
        assert not candidate.exists()
        run.assert_not_called()
    else:
        assert exit_code == 0
        run.assert_called_once()
        assert json.loads(candidate.read_text())["status"] == "pass"
        assert reusable_summary_diagnostics(tmp_path, candidate, replace(request, pytest_flags="-q"))["reusable"]


def test_public_check_reuse_accepts_same_interpreter_alias(tmp_path: Path) -> None:
    executable = Path(sys.executable)
    alias = next((
        path for name in ("python", "python3")
        if (path := executable.with_name(name)) != executable
        and path.exists() and path.resolve() == executable.resolve()
    ), None)
    if alias is None:
        pytest.skip("test interpreter has no equivalent launcher alias")
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(public_python=str(alias), source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(tmp_path, report)
    assert reusable_summary_diagnostics(tmp_path, destination)["reusable"]
    assert reusable_summary_diagnostics(tmp_path, destination, request)["reusable"]


@pytest.mark.parametrize("pythonpath", ["", ".", "..", "plugins", os.pathsep.join([".", "", "plugins"])])
@pytest.mark.parametrize("safe_path", ["", "1"])
def test_public_check_reuse_with_relative_pythonpath(
    tmp_path: Path, monkeypatch, pythonpath: str, safe_path: str,
) -> None:
    monkeypatch.setenv("PYTHONPATH", pythonpath)
    monkeypatch.setenv("PYTHONSAFEPATH", safe_path)
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(tmp_path, report)
    cache = _public_pytest_summary_cache_path(tmp_path, request)
    assert cache.is_file()
    assert reusable_summary_diagnostics(tmp_path, destination, request)["reusable"]
    assert _public_pytest_summary_cache_path(tmp_path, request) == cache
    monkeypatch.setenv("PYTHONPATH", pythonpath + os.pathsep + "other-plugins")
    assert not reusable_summary_diagnostics(tmp_path, destination, request)["reusable"]
    assert _public_pytest_summary_cache_path(tmp_path, request) != cache


def test_public_toolchain_accepts_relative_path_launcher(monkeypatch) -> None:
    executable = Path(sys.executable)
    monkeypatch.chdir(executable.parent)
    monkeypatch.setenv("PATH", ".")
    assert public_toolchain_fingerprint(executable.name, cwd=executable.parent) == public_toolchain_fingerprint(str(executable), cwd=executable.parent)


def test_toolchain_probe_parses_each_distribution_metadata_once(tmp_path: Path, monkeypatch, capsys) -> None:
    import importlib.metadata

    from ops.scripts.public import public_toolchain_runtime

    # Include duplicate names using both supported metadata layouts. Discovery
    # and the validation tools' independent version resolution remain native.
    for suffix, filename, version in (
        ("dist-info", "METADATA", "1.0"), ("egg-info", "PKG-INFO", "2.0"),
    ):
        directory = tmp_path / f"probe_copy-{version}.{suffix}"
        directory.mkdir()
        (directory / filename).write_text(f"Name: Probe_Copy\nVersion: {version}\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["probe", "retained"])
    native_distributions = importlib.metadata.distributions
    native_metadata = importlib.metadata.Distribution.metadata.fget
    enumerated: list[Any] = []
    reads: dict[int, int] = {}

    def distributions(**kwargs):
        enumerated.extend(native_distributions(**kwargs))
        return iter(enumerated)

    def metadata(distribution):
        identity = id(distribution)
        reads[identity] = reads.get(identity, 0) + 1
        return native_metadata(distribution)

    monkeypatch.setattr(importlib.metadata, "distributions", distributions)
    monkeypatch.setattr(importlib.metadata.Distribution, "metadata", property(metadata))
    namespace: dict[str, Any] = {}
    exec(compile(public_toolchain_runtime._PROBE, "<public toolchain probe>", "exec"), namespace)
    assert enumerated
    assert [reads[id(distribution)] for distribution in enumerated] == [1] * len(enumerated)
    packages = [item for item in namespace["payload"]["packages"] if item[0] == "Probe_Copy"]
    assert [item[1] for item in packages] == ["1.0", "2.0"]
    for name in ("pytest", "ruff", "mypy"):
        assert namespace["payload"]["tools"][name][0] == importlib.metadata.version(name)
    assert capsys.readouterr().out.strip() == hashlib.sha256(
        json.dumps(namespace["payload"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@pytest.mark.parametrize("metadata_file", ["METADATA", "PKG-INFO", "RECORD", "direct_url.json"])
def test_toolchain_metadata_content_changes_invalidate_fingerprint(tmp_path: Path, monkeypatch, metadata_file: str) -> None:
    suffix = "egg-info" if metadata_file == "PKG-INFO" else "dist-info"
    directory = tmp_path / f"probe_copy-1.0.{suffix}"
    directory.mkdir()
    package_metadata = directory / ("PKG-INFO" if suffix == "egg-info" else "METADATA")
    package_metadata.write_text("Name: probe-copy\nVersion: 1.0\nSummary: original\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    before = public_toolchain_fingerprint(sys.executable, cwd=tmp_path)
    if metadata_file == "METADATA":
        # Raw metadata bytes still matter even when Name and Version are unchanged.
        package_metadata.write_text("Name: probe-copy\nVersion: 1.0\nSummary: changed\n")
    elif metadata_file == "PKG-INFO":
        package_metadata.write_text("Name: probe-copy\nVersion: 2.0\nSummary: original\n")
    elif metadata_file == "RECORD":
        (directory / metadata_file).write_text("module.py,sha256=changed,42\n")
    else:
        (directory / metadata_file).write_text('{"url":"https://example.invalid/changed.whl"}\n')
    assert public_toolchain_fingerprint(sys.executable, cwd=tmp_path) != before


def test_public_toolchain_distinguishes_virtualenvs(tmp_path: Path) -> None:
    import sysconfig

    environment = tmp_path / "environment"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(environment)],
        check=True, capture_output=True, timeout=30,
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    result = subprocess.run(
        [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    # Reuse installed test dependencies; the environment prefix must still differ.
    (Path(result.stdout.strip()) / "test-dependencies.pth").write_text(
        sysconfig.get_path("purelib") + "\n", encoding="utf-8",
    )
    assert public_toolchain_fingerprint(str(python), cwd=tmp_path) != public_toolchain_fingerprint(sys.executable, cwd=tmp_path)


def _native_public_validation(vault: Path, *, public_out: str, python: str) -> PublicCheckRequest:
    # Use the real summary wrapper and all three validation tools on one small test.
    with public_export_session(REPO_ROOT, vault):
        pass
    target = "tests/test_public_check_summary.py"
    (vault / target).write_text(
        "import pytest\n\npytestmark = pytest.mark.public\n\n\n"
        "def test_native_validation() -> None:\n    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    return PublicCheckRequest(
        public_out=public_out, public_python=python, source_history_scan=False,
        ruff_targets=target, mypy_targets=target, pytest_flags=f"{target} -o addopts= -q",
        timeout_seconds=60, heartbeat_interval_seconds=0,
    )


@pytest.mark.parametrize("bare_launcher", [False, True])
def test_public_check_uses_relative_external_validation_dependencies(
    tmp_path: Path, monkeypatch, bare_launcher: bool,
) -> None:
    import sysconfig

    environment = tmp_path / "environment"
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(environment)],
        check=True, capture_output=True, timeout=30,
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    dependencies = tmp_path / "validation-packages"
    try:
        dependencies.symlink_to(sysconfig.get_path("purelib"), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"dependency directory symlink unavailable: {exc}")
    metadata = tmp_path / "metadata" / "validation_environment-1.0.dist-info"
    metadata.mkdir(parents=True)
    metadata_file = metadata / "METADATA"
    metadata_file.write_text("Name: validation-environment\nVersion: 1.0\n")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(["../validation-packages", "../metadata"]))
    if bare_launcher:
        monkeypatch.setenv("PATH", os.pathsep.join([
            os.path.join("..", "environment", python.parent.name), os.environ.get("PATH", ""),
        ]))
    vault, output = tmp_path / "source", tmp_path / "public"
    request = _native_public_validation(
        vault, public_out=str(output), python=python.name if bare_launcher else str(python),
    )
    # Independently establish that the real tools are available in this layout.
    subprocess.run(
        [str(python), "-c", "import pytest, ruff, mypy"], cwd=vault,
        check=True, capture_output=True, timeout=15,
    )
    report = build_report(vault, request, context=fixed_context())
    assert report["status"] == "pass", json.dumps(report["commands"], indent=2)
    assert report["summary"]["pytest_passed"] == 1
    destination = write_report(vault, report)
    cache = _public_pytest_summary_cache_path(vault, request)
    assert cache.is_file()
    assert reusable_summary_diagnostics(vault, destination, request)["reusable"]
    metadata_file.write_text("Name: validation-environment\nVersion: 2.0\n")
    assert not reusable_summary_diagnostics(vault, destination, request)["reusable"]
    assert _public_pytest_summary_cache_path(vault, request) != cache


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("exported_launcher", [False, True])
def test_public_check_probes_exported_imports(
    tmp_path: Path, monkeypatch, retained: bool, exported_launcher: bool,
) -> None:
    if exported_launcher and os.name == "nt":
        pytest.skip("exported POSIX shell launcher")
    vault = tmp_path / "source"
    request = _native_public_validation(
        vault, public_out=str(tmp_path / "public") if retained else "",
        python="python-launcher" if exported_launcher else sys.executable,
    )
    if exported_launcher:
        launcher = vault / "tools/python-launcher"
        launcher.write_text('#!/bin/sh\nexec "$VALIDATION_PYTHON" "$@"\n')
        launcher.chmod(0o755)
        monkeypatch.setenv("VALIDATION_PYTHON", sys.executable)
        monkeypatch.setenv("PATH", os.pathsep.join(["tools", os.environ.get("PATH", "")]))
    packages = vault / "tools" / "validation_plugins"
    packages.mkdir()
    (packages / "validation_plugin.py").write_text("VALUE = 1\n")
    metadata = packages / "validation_plugin-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: validation-plugin\nVersion: 1.0\n")
    target = vault / "tests/test_public_check_summary.py"
    target.write_text(
        "import pytest\nimport validation_plugin\n\npytestmark = pytest.mark.public\n\n\n"
        "def test_native_validation() -> None:\n    assert validation_plugin.VALUE == 1\n",
    )
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([".", "tools/validation_plugins"]))
    monkeypatch.setenv("PYTHONSAFEPATH", "1")
    report = build_report(vault, request, context=fixed_context())
    assert report["status"] == "pass", json.dumps(report["commands"], indent=2)
    assert report["summary"]["pytest_passed"] == 1
    destination = write_report(vault, report)
    cache = _public_pytest_summary_cache_path(vault, request)
    assert cache.is_file()
    assert reusable_summary_diagnostics(vault, destination, request)["reusable"]
    assert _public_pytest_summary_cache_path(vault, request) == cache


@pytest.mark.parametrize("change", ["missing", "replaced", "metadata", "flags", "legacy"])
def test_public_check_reuse_binds_live_toolchain(tmp_path: Path, monkeypatch, change: str) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    if change == "metadata":
        packages = tmp_path / "packages"
        packages.mkdir()
        monkeypatch.setenv("PYTHONPATH", str(packages))
    python = sys.executable
    launcher = tmp_path / "python-launcher"
    if change in {"missing", "replaced"}:
        if os.name == "nt":
            pytest.skip("POSIX executable launcher replacement; metadata probe is cross-platform")
        import shlex

        launcher.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
        launcher.chmod(0o755)
        python = str(launcher)
    request = PublicCheckRequest(public_python=python, source_history_scan=False)
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(vault, report)
    cache = _public_pytest_summary_cache_path(vault, request)
    assert reusable_summary_diagnostics(vault, destination, request)["reusable"]
    if change == "missing":
        launcher.unlink()
    elif change == "replaced":
        launcher.write_text(launcher.read_text() + "# replaced launcher\n")
    elif change == "metadata":
        metadata = tmp_path / "packages" / "pytest-999.0.dist-info"
        metadata.mkdir(parents=True)
        (metadata / "METADATA").write_text("Metadata-Version: 2.1\nName: pytest\nVersion: 999.0\n")
    elif change == "flags":
        monkeypatch.setenv("PYTEST_ADDOPTS", "-k synthetic")
    else:
        report["input_fingerprints"].pop("public_python_toolchain", None)
        destination.write_text(json.dumps(report))
    diagnostic = reusable_summary_diagnostics(vault, destination, request)
    assert not diagnostic["reusable"]
    assert "public_python_toolchain" in diagnostic["reason"]
    if change in {"replaced", "metadata", "flags"}:
        assert _public_pytest_summary_cache_path(vault, request) != cache
    with redirect_stdout(io.StringIO()):
        assert public_check_summary_module.main([
            "--vault", str(vault), "--public-python", python, "--skip-source-history-scan",
            "--reuse-if-current", "--reuse-only", "--reuse-from", str(destination),
        ]) == 1


def test_public_check_does_not_publish_cache_after_toolchain_changes(tmp_path: Path) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    cache = tmp_path / "tmp" / "previous-cache.json"
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(b"previous")
    with (
        patch.object(public_check_summary_module, "public_toolchain_fingerprint", side_effect=["a" * 64, "b" * 64]),
        patch.object(public_check_summary_module, "_public_pytest_summary_cache_path", return_value=cache),
        pytest.raises(ValueError, match="toolchain"),
    ):
        build_report(tmp_path, context=fixed_context(), command_runner=fake_runner)
    assert cache.read_bytes() == b"previous"


@pytest.mark.parametrize("failure", ["timeout", "invalid", "nonzero"])
def test_public_toolchain_probe_failure_cannot_reuse_summary(tmp_path: Path, failure: str) -> None:
    from ops.scripts.public import public_toolchain_runtime

    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(public_python=sys.executable, source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(tmp_path, report)
    result = TimedProcessResult(
        args=[], returncode=1 if failure == "nonzero" else 0,
        stdout="invalid" if failure == "invalid" else "a" * 64, stderr="",
        timed_out=failure == "timeout", timeout_seconds=15,
        termination_reason="timeout" if failure == "timeout" else "completed",
    )
    with patch.object(public_toolchain_runtime, "run_with_timeout", return_value=result):
        assert not reusable_summary_diagnostics(tmp_path, destination, request)["reusable"]
        with pytest.raises(ValueError, match="probe"):
            build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)


def test_public_toolchain_cleanup_failure_propagates(tmp_path: Path) -> None:
    from ops.scripts.public import public_toolchain_runtime

    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(tmp_path, report)
    with patch.object(public_toolchain_runtime, "run_with_timeout", side_effect=ProcessCleanupError("cleanup failed")):
        with pytest.raises(ProcessCleanupError):
            reusable_summary_diagnostics(tmp_path, destination, request)
        with pytest.raises(ProcessCleanupError):
            build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("changed", ["source", "export"])
def test_reuse_rejects_changes_during_toolchain_probe(
    tmp_path: Path, monkeypatch, retained: bool, changed: str,
) -> None:
    vault = tmp_path / "source"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(
        public_out=str(tmp_path / "public") if retained else "", source_history_scan=False,
    )
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    destination = write_report(vault, report)

    def mutating_probe(public_python: str, *, cwd: Path, private_workspace: bool) -> str:
        result = public_toolchain_fingerprint(public_python, cwd=cwd, private_workspace=private_workspace)
        target = vault if changed == "source" else cwd
        (target / "README.md").write_text("changed during probe\n")
        return result

    monkeypatch.setattr(public_check_summary_module, "public_toolchain_fingerprint", mutating_probe)
    diagnostics = reusable_summary_diagnostics(vault, destination, request)
    assert not diagnostics["reusable"]
    if changed == "source":
        assert not diagnostics["checks"]["public_export_source"]
    elif retained:
        assert not diagnostics["checks"]["retained_export"]
    else:
        assert "changed during toolchain probe" in diagnostics["toolchain_error"]


def test_default_public_checks_have_independent_workspaces_and_caches(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)
    directories: list[Path] = []
    requests = PublicCheckRequest(source_history_scan=False)
    vaults = [tmp_path / name for name in ("a", "b")]
    for vault in vaults:
        vault.mkdir()
        seed_minimal_vault(vault)
        seed_public_policy_file(vault)
        (vault / "README.md").write_text(vault.name, encoding="utf-8")

    def check(vault: Path) -> dict[str, Any]:
        def runner(argv: Sequence[str], cwd: Path, timeout: int) -> TimedProcessResult:
            if argv[2] == "ruff":
                directories.append(cwd)
                barrier.wait(timeout=15)
            read = subprocess.run([sys.executable, "-I", "-c", "from pathlib import Path; print(Path('README.md').read_text())"], cwd=cwd, capture_output=True, text=True, check=True, timeout=10)
            assert read.stdout.strip() == vault.name
            return fake_runner(argv, cwd, timeout)
        return build_report(vault, requests, context=fixed_context(), command_runner=runner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(check, vaults))
    assert all(report["status"] == "pass" for report in reports)
    assert len(set(directories)) == 2
    assert all(not path.exists() for path in directories)
    assert _public_pytest_summary_cache_path(vaults[0], requests) != _public_pytest_summary_cache_path(vaults[1], requests)
    assert reports[0]["public_export"]["output_dir"] == "<tmp>/invocation-private/export"


@pytest.mark.parametrize("mode", ["default", "full"])
@pytest.mark.parametrize("retained", [False, True])
def test_public_check_reuses_initial_source_identities_for_cache_key(
    tmp_path: Path, mode: str, retained: bool,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(
        mode=mode, public_out=str(tmp_path / "public") if retained else "", source_history_scan=False,
    )
    with (
        patch.object(public_check_summary_module, "release_source_tree_fingerprint", wraps=public_check_summary_module.release_source_tree_fingerprint) as tree,
        patch.object(public_check_summary_module, "_public_export_source_inputs", wraps=public_check_summary_module._public_export_source_inputs) as public_inputs,
        patch.object(public_check_summary_module, "_persist_public_pytest_summary", wraps=public_check_summary_module._persist_public_pytest_summary) as persist,
    ):
        def runner(argv: Sequence[str], cwd: Path, timeout: int) -> TimedProcessResult:
            # Cache-key construction must not repeat either pre-command source scan.
            assert tree.call_count == 1
            assert public_inputs.call_count == 1
            return fake_runner(argv, cwd, timeout)

        report = build_report(vault, request, context=fixed_context(), command_runner=runner)
        # The independent post-command drift checks must still read current sources.
        assert tree.call_count == 2
        assert public_inputs.call_count == 2
        persist.assert_called_once()
        written_cache = persist.call_args.args[1]

    assert report["status"] == "pass"
    # Independent inspection still computes current identities and finds the same cache.
    assert written_cache == _public_pytest_summary_cache_path(vault, request)
    assert json.loads(written_cache.read_text())["counts"]["passed"] == 217


@pytest.mark.parametrize("changed", ["source", "export"])
@pytest.mark.parametrize("relative", ["README.md", "ops/script-output-surfaces.json"])
@pytest.mark.parametrize("existing_cache", [False, True])
def test_public_check_rejects_input_changes_during_validation(
    tmp_path: Path, changed: str, relative: str, existing_cache: bool
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    (vault / relative).write_text("original input\n", encoding="utf-8")

    def runner(argv: Sequence[str], cwd: Path, timeout: int) -> TimedProcessResult:
        if argv[2] == "ruff":
            target = vault if changed == "source" else cwd
            (target / relative).write_text("changed after snapshot\n", encoding="utf-8")
        return fake_runner(argv, cwd, timeout)

    request = PublicCheckRequest(source_history_scan=False)
    cache = _public_pytest_summary_cache_path(vault, request)
    if existing_cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text('{"prior": "cache"}\n', encoding="utf-8")
    original = cache.read_bytes() if existing_cache else None
    with pytest.raises(ValueError, match="inputs changed"):
        build_report(vault, request, context=fixed_context(), command_runner=runner)
    assert (cache.read_bytes() if cache.exists() else None) == original


@pytest.mark.parametrize("mode", ["default", "full"])
@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize("change", ["create", "edit", "remove", "rename", "rewrite", "excluded"])
def test_public_source_inputs_bind_summary_reuse_and_pytest_cache(
    tmp_path: Path, mode: str, retained: bool, change: str
) -> None:
    vault, output = tmp_path / "vault", tmp_path / "public"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    source = vault / "ops/script-output-surfaces.json"
    if change != "create":
        source.write_text('{"version": 1}\n', encoding="utf-8")
    request = PublicCheckRequest(
        mode=mode, public_out=str(output) if retained else "", source_history_scan=False,
    )
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    summary = write_report(vault, report)
    saved = summary.read_bytes(), summary.stat().st_mtime_ns
    cache = _public_pytest_summary_cache_path(vault, request)
    assert cache.is_file()
    assert reusable_summary_diagnostics(vault, summary, request)["reusable"] is True

    if change == "remove":
        source.unlink()
    elif change == "rename":
        source.rename(source.with_name("renamed-output-surfaces.json"))
    elif change == "rewrite":
        source.write_bytes(source.read_bytes())
    elif change == "excluded":
        generated = vault / "ops/reports/generated.json"
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("{}\n", encoding="utf-8")
    else:
        source.write_text("{}\n", encoding="utf-8")

    unchanged = change in {"rewrite", "excluded"}
    for checked_request in (None, request):
        diagnostics = reusable_summary_diagnostics(vault, summary, checked_request)
        assert diagnostics["reusable"] is unchanged
        if not unchanged:
            assert diagnostics["checks"]["public_export_source"] is False
    with redirect_stdout(io.StringIO()):
        exit_code = public_check_summary_module.main([
            "--vault", str(vault), "--out", str(summary), "--mode", mode,
            "--public-out", request.public_out, "--skip-source-history-scan", "--reuse-only",
        ])
    assert exit_code == (0 if unchanged else 1)
    assert (_public_pytest_summary_cache_path(vault, request) == cache) is unchanged
    assert (summary.read_bytes(), summary.stat().st_mtime_ns) == saved


def test_public_summary_without_export_source_identity_requires_refresh(tmp_path: Path) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    request = PublicCheckRequest(source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    report["input_fingerprints"].pop("public_export_source", None)
    summary = write_report(tmp_path, report)
    diagnostics = reusable_summary_diagnostics(tmp_path, summary, request)
    assert diagnostics["reusable"] is False
    assert diagnostics["checks"]["public_export_source"] is False


def test_public_source_read_failure_cannot_prove_currentness(tmp_path: Path) -> None:
    seed_minimal_vault(tmp_path)
    seed_public_policy_file(tmp_path)
    source = tmp_path / "ops/script-output-surfaces.json"
    source.write_text("{}\n", encoding="utf-8")
    request = PublicCheckRequest(source_history_scan=False)
    report = build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)
    summary = write_report(tmp_path, report)
    original_read = Path.read_bytes

    def unreadable(path: Path) -> bytes:
        if path == source:
            raise PermissionError("synthetic public input read failure")
        return original_read(path)

    with patch.object(Path, "read_bytes", unreadable):
        diagnostics = reusable_summary_diagnostics(tmp_path, summary, request)
        assert diagnostics["reusable"] is False
        assert diagnostics["reason"] == "public_export_source_unavailable:PermissionError"
        with pytest.raises(PermissionError, match="public input read failure"):
            build_report(tmp_path, request, context=fixed_context(), command_runner=fake_runner)


def test_explicit_export_lock_excludes_other_processes(tmp_path: Path) -> None:
    vault, output = tmp_path / "vault", tmp_path / "public"
    vault.mkdir()
    (vault / "README.md").write_text("source\n", encoding="utf-8")
    code = "from pathlib import Path; from ops.scripts.public.export_public_repo import export_public_repo; import sys; export_public_repo(Path(sys.argv[1]), Path(sys.argv[2]))"
    command = [sys.executable, "-c", code, str(vault), str(output)]
    with public_export_session(vault, output):
        result = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=20, check=False)
        assert result.returncode != 0
        assert "output lock" in result.stderr
        assert (output / "README.md").read_text() == "source\n"
    subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=20, check=True)


def test_reuse_rejects_retained_export_content_drift(tmp_path: Path) -> None:
    vault, output = tmp_path / "vault", tmp_path / "public"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(public_out=str(output), source_history_scan=False)
    report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
    path = write_report(vault, report)
    assert reusable_summary_diagnostics(vault, path, request)["reusable"] is True
    (output / "README.md").write_text("replaced by another invocation\n", encoding="utf-8")
    diagnostics = reusable_summary_diagnostics(vault, path, request)
    assert diagnostics["reusable"] is False
    assert diagnostics["checks"]["retained_export"] is False


def _add_export_entry(output: Path, relative: str, kind: str) -> None:
    path = output / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "directory":
        path.mkdir()
    elif kind == "file":
        path.write_text("synthetic extra content\n", encoding="utf-8")
    else:
        if path.exists():
            path.unlink()
        target = output / "README.md" if kind == "internal_link" else output.parent / "outside"
        if kind == "external_link":
            target.write_text("synthetic external content\n", encoding="utf-8")
        try:
            path.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")


@pytest.mark.parametrize("boundary", ["during_validation", "reuse"])
@pytest.mark.parametrize(
    ("relative", "kind"),
    [
        ("raw/synthetic-private.md", "file"),
        ("wiki", "directory"),
        ("ops/policies/wiki-maintainer-policy.local.yaml", "file"),
        ("ops/reports/unexpected.json", "file"),
        (".git/config", "file"),
        (".venv", "directory"),
        ("unexpected.txt", "file"),
        ("docs/added.md", "file"),
        ("docs/added.md", "external_link"),
        ("docs/added.md", "internal_link"),
        ("docs/added.md", "dangling_link"),
        ("PUBLIC-EXPORT-MANIFEST.json", "internal_link"),
        ("README.md", "internal_link"),
        (".pytest_cache/added", "external_link"),
        (".mypy_cache", "dangling_link"),
    ],
)
def test_public_check_rejects_unexpected_physical_entries(
    tmp_path: Path, boundary: str, relative: str, kind: str
) -> None:
    vault, output = tmp_path / "vault", tmp_path / "public"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(public_out=str(output), source_history_scan=False)

    def runner(argv: Sequence[str], cwd: Path, timeout: int) -> TimedProcessResult:
        result = fake_runner(argv, cwd, timeout)
        if argv[2] == "ops.scripts.test_execution_summary":
            _add_export_entry(cwd, relative, kind)
        return result

    if boundary == "during_validation":
        with pytest.raises(ValueError, match="inputs changed"):
            build_report(vault, request, context=fixed_context(), command_runner=runner)
    else:
        report = build_report(vault, request, context=fixed_context(), command_runner=fake_runner)
        summary = write_report(vault, report)
        original = summary.read_bytes(), summary.stat().st_mtime_ns
        assert reusable_summary_diagnostics(vault, summary, request)["reusable"] is True
        _add_export_entry(output, relative, kind)
        diagnostics = reusable_summary_diagnostics(vault, summary, request)
        assert diagnostics["reusable"] is False
        assert diagnostics["checks"]["retained_export"] is False
        assert (summary.read_bytes(), summary.stat().st_mtime_ns) == original


def test_public_check_allows_validation_caches_at_both_boundaries(tmp_path: Path) -> None:
    vault, output = tmp_path / "vault", tmp_path / "public"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    request = PublicCheckRequest(public_out=str(output), source_history_scan=False)

    def runner(argv: Sequence[str], cwd: Path, timeout: int) -> TimedProcessResult:
        for relative in (
            ".ruff_cache/version/entry", ".mypy_cache/version/entry",
            ".pytest_cache/v/cache/nodeids", ".hypothesis/constants/entry",
            "ops/scripts/public/__pycache__/public_surface_policy.cpython-312.pyc",
        ):
            _add_export_entry(cwd, relative, "file")
        return fake_runner(argv, cwd, timeout)

    report = build_report(vault, request, context=fixed_context(), command_runner=runner)
    assert report["status"] == "pass"
    summary = write_report(vault, report)
    assert reusable_summary_diagnostics(vault, summary, request)["reusable"] is True


def failing_pytest_runner(
    argv: Sequence[str], cwd: Path, timeout_seconds: int
) -> TimedProcessResult:
    module = argv[2] if len(argv) > 2 else ""
    if module == "ops.scripts.test_execution_summary":
        write_public_pytest_summary(cwd, passed=216, failed=1, errors=0, skipped=0)
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=1 if module == "ops.scripts.test_execution_summary" else 0,
        stdout="",
        stderr="",
        timed_out=False,
        timeout_seconds=timeout_seconds,
        termination_reason="completed",
    )


def timeout_pytest_runner(
    argv: Sequence[str], cwd: Path, timeout_seconds: int
) -> TimedProcessResult:
    module = argv[2] if len(argv) > 2 else ""
    timed_out = module == "ops.scripts.test_execution_summary"
    return TimedProcessResult(
        args=[str(item) for item in argv],
        returncode=-9 if timed_out else 0,
        stdout="",
        stderr="",
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
        termination_reason="execution_timeout" if timed_out else "completed",
        signal_sent="sigkill" if timed_out else "none",
        final_state_observed="drain_after_kill" if timed_out else "communicate",
        heartbeat_count=3 if timed_out else 0,
        heartbeat_interval_seconds=10 if timed_out else 0,
        quiet_seconds=30 if timed_out else 0,
        observation_mode="process_heartbeat" if timed_out else "communicate",
    )


@pytest.mark.parametrize("mode", ["default", "full"])
@pytest.mark.parametrize(
    "transition",
    ["absent", "unchanged", "create", "edit", "remove", "unreadable"],
)
def test_public_summary_reuse_tracks_local_policy(
    tmp_path: Path, mode: str, transition: str
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    seed_minimal_vault(vault)
    seed_public_policy_file(vault)
    local_policy = vault / LOCAL_CORPUS_POLICY_PATH
    local_text = '{"schema_version": 1, "overrides": {}}\n'
    if transition in {"unchanged", "edit", "remove"}:
        local_policy.write_text(local_text, encoding="utf-8")
    request = PublicCheckRequest(
        mode=mode, public_out=str(tmp_path / "public"), public_python="python"
    )
    report = build_report(
        vault, request, context=fixed_context(), command_runner=fake_runner
    )
    suffix = "-full" if mode == "full" else ""
    destination = write_report(
        vault, report, f"ops/reports/public-check-summary{suffix}.json"
    )
    before = (destination.read_bytes(), destination.stat().st_mtime_ns)
    assert reusable_summary_diagnostics(vault, destination, request)["reusable"]

    if transition == "create":
        local_policy.write_text(local_text, encoding="utf-8")
    elif transition == "edit":
        local_policy.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "overrides": {
                        "page_shape": {
                            "special_page_required_sections": {
                                "system/system-index.md": ["Summary", "Synthetic section"]
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
    elif transition == "remove":
        local_policy.unlink()
    elif transition == "unreadable":
        local_policy.mkdir()

    expected_current = transition in {"absent", "unchanged"}
    for selector in (None, request):
        diagnostics = reusable_summary_diagnostics(vault, destination, selector)
        assert diagnostics["reusable"] == expected_current
        if not expected_current:
            assert diagnostics["reason"] == "not_current:local_corpus_policy"

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = public_check_summary_module.main(
            [
                "--vault", str(vault),
                "--mode", mode,
                "--reuse-only",
                "--reuse-from", str(destination),
                "--public-out", request.public_out,
                "--public-python", "python",
            ]
        )
    assert exit_code == (0 if expected_current else 1)
    assert (destination.read_bytes(), destination.stat().st_mtime_ns) == before
    if not expected_current:
        assert json.loads(stdout.getvalue())["reuse_diagnostics"]["reason"] == (
            "not_current:local_corpus_policy"
        )
        if transition != "unreadable":
            refreshed = build_report(
                vault, request, context=fixed_context(), command_runner=fake_runner
            )
            write_report(vault, refreshed, str(destination))
            assert reusable_summary_diagnostics(vault, destination, request)["reusable"]


class PublicCheckSummaryTests(unittest.TestCase):
    def _build_report_with_exported_text(
        self,
        temp_dir: str,
        rel_path: str,
        text: str,
    ) -> dict[str, Any]:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        seed_public_policy_file(vault)
        target = vault / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return build_report(
            vault,
            PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="python",
                pytest_flags="-q",
            ),
            context=fixed_context(),
            command_runner=fake_runner,
        )

    def test_default_runner_exports_public_python_for_nested_make_entrypoints(
        self,
    ) -> None:
        captured_env: dict[str, str] = {}

        def fake_run_with_timeout(
            argv: Sequence[str],
            *,
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str] | None = None,
            heartbeat_interval_seconds: int | None = None,
            heartbeat_callback: object | None = None,
        ) -> TimedProcessResult:
            captured_env.update(dict(env or {}))
            return TimedProcessResult(
                args=[str(item) for item in argv],
                returncode=0,
                stdout="",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="completed",
                heartbeat_interval_seconds=heartbeat_interval_seconds or 0,
            )

        with patch(
            "ops.scripts.public.public_check_summary.run_with_timeout",
            fake_run_with_timeout,
        ):
            _default_command_runner(
                ["python", "-m", "pytest"],
                Path(),
                30,
                public_python="/workspace/.venv/bin/python",
                heartbeat_interval_seconds=0,
            )

        self.assertEqual(captured_env["PYTHON"], "/workspace/.venv/bin/python")
        self.assertEqual(captured_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")

    @patch("ops.scripts.public.public_check_summary.public_toolchain_fingerprint", return_value="a" * 64)
    def test_build_report_default_runner_exports_resolved_public_python_to_all_commands(
        self, _probe,
    ) -> None:
        captured_envs: list[dict[str, str]] = []

        def fake_run_with_timeout(
            argv: Sequence[str],
            *,
            cwd: Path,
            timeout_seconds: int,
            env: Mapping[str, str] | None = None,
            heartbeat_interval_seconds: int | None = None,
            heartbeat_callback: object | None = None,
        ) -> TimedProcessResult:
            captured_envs.append(dict(env or {}))
            module = argv[2] if len(argv) > 2 else ""
            if module == "ops.scripts.test_execution_summary":
                write_public_pytest_summary(
                    cwd, passed=3, failed=0, errors=0, skipped=0
                )
            return TimedProcessResult(
                args=[str(item) for item in argv],
                returncode=0,
                stdout="",
                stderr="",
                timed_out=False,
                timeout_seconds=timeout_seconds,
                termination_reason="completed",
                heartbeat_interval_seconds=heartbeat_interval_seconds or 0,
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            with patch(
                "ops.scripts.public.public_check_summary.run_with_timeout",
                fake_run_with_timeout,
            ):
                report = build_report(
                    vault,
                    PublicCheckRequest(
                        public_out=str(Path(temp_dir) / "public"),
                        public_python=".venv/bin/python",
                    ),
                    context=fixed_context(),
                )

        expected_python = str((vault / ".venv/bin/python").absolute())
        self.assertEqual(report["status"], "pass")
        self.assertEqual(len(captured_envs), 3)
        self.assertEqual({env["PYTHON"] for env in captured_envs}, {expected_python})
        self.assertEqual(
            {env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] for env in captured_envs}, {"1"}
        )

    def test_public_check_summary_schema_passes_and_records_export_fingerprint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(public_out),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            self.assertTrue(destination.exists())
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["public_check_status"], "pass")
            self.assertEqual(report["summary"]["negative_assertion_fail_count"], 0)
            self.assertEqual(report["summary"]["physical_repo_split_status"], "pass")
            self.assertEqual(
                report["summary"]["export_git_metadata_absence_status"], "pass"
            )
            self.assertFalse(report["public_export"]["git_metadata_present"])
            self.assertEqual(
                report["summary"]["source_history_evaluation_status"],
                "insufficient_history",
            )
            self.assertEqual(report["summary"]["source_history_status"], "unknown")
            self.assertEqual(report["summary"]["source_history_violation_count"], 0)
            self.assertEqual(
                report["source_history_scan"]["ref_scope"],
                "all_refs_and_head",
            )
            self.assertIsNone(report["source_history_scan"]["shallow_repository"])
            self.assertEqual(report["summary"]["pytest_passed"], 217)
            self.assertEqual(report["summary"]["pytest_skipped"], 5)
            self.assertEqual(report["summary"]["timeout_command_count"], 0)
            self.assertEqual(report["summary"]["max_command_heartbeat_count"], 0)
            self.assertEqual(report["summary"]["max_command_quiet_seconds"], 0)
            self.assertEqual(report["summary"]["public_pytest_heartbeat_count"], 0)
            self.assertEqual(report["summary"]["public_pytest_quiet_seconds"], 0)
            self.assertEqual(
                report["summary"]["public_pytest_termination_reason"], "completed"
            )
            self.assertEqual(report["summary"]["public_pytest_signal_sent"], "none")
            self.assertEqual(
                report["summary"]["public_pytest_final_state_observed"], "unknown"
            )
            self.assertEqual(
                {command["observation_mode"] for command in report["commands"]},
                {"communicate"},
            )
            self.assertEqual(
                {
                    command["heartbeat_interval_seconds"]
                    for command in report["commands"]
                },
                {0},
            )
            self.assertIn(
                "ops.scripts.test_execution_summary", report["commands"][-1]["command"]
            )
            self.assertIn("--reuse-if-current", report["commands"][-1]["command"])
            self.assertEqual(
                {command["signal_sent"] for command in report["commands"]}, {"none"}
            )
            self.assertEqual(
                {command["final_state_observed"] for command in report["commands"]},
                {"unknown"},
            )
            self.assertRegex(
                report["summary"]["export_root_fingerprint"], r"^[a-f0-9]{64}$"
            )
            self.assertRegex(
                report["summary"]["public_surface_policy_sha256"], r"^[a-f0-9]{64}$"
            )
            self.assertRegex(
                report["summary"]["public_check_config_fingerprint"],
                r"^[a-f0-9]{64}$",
            )
            self.assertEqual(
                report["summary"]["public_check_config_fingerprint"],
                report["input_fingerprints"]["public_check_config"],
            )
            self.assertEqual(
                report["source_command"],
                "python -m ops.scripts.public_check_summary --vault .",
            )
            self.assertTrue(report["public_export"]["output_dir"].startswith("<tmp>/"))
            self.assertTrue(
                report["public_export"]["output_dir"].endswith(f"/{public_out.name}")
            )
            self.assertTrue(_public_pytest_summary_cache_path(vault, PublicCheckRequest(
                public_out=str(public_out), public_python="python", pytest_flags="-q"
            )).exists())
            self.assertFalse(
                (public_out / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH).exists()
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["excluded_prefix_absence"][
                    "status"
                ],
                "pass",
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "status"
                ],
                "pass",
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["private_pattern_absence"][
                    "status"
                ],
                "pass",
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

            legacy = json.loads(json.dumps(report))
            legacy["summary"]["private_surface_history_absence_status"] = legacy[
                "summary"
            ].pop("export_git_metadata_absence_status")
            self.assertNotEqual(
                validate_with_schema(legacy, load_schema(SCHEMA_PATH)),
                [],
            )

            not_requested = json.loads(json.dumps(report))
            not_requested["source_history_scan"] = scan_source_history(
                vault,
                requested=False,
            )
            not_requested["summary"]["source_history_evaluation_status"] = (
                "not_requested"
            )
            not_requested["summary"]["source_history_status"] = "unknown"
            self.assertEqual(
                validate_with_schema(not_requested, load_schema(SCHEMA_PATH)),
                [],
            )

            contradictory_evaluated = json.loads(json.dumps(report))
            contradictory_evaluated["source_history_scan"].update(
                {
                    "evaluation_status": "evaluated",
                    "status": "pass",
                    "head_present": True,
                    "shallow_repository": False,
                    "legacy_grafts_present": False,
                    "object_enumeration_complete": True,
                    "missing_object_count": 1,
                    "scan_command": (
                        "git --no-replace-objects log --format= --raw --root "
                        "--no-renames --ignore-submodules=none -m -r -z "
                        "--no-abbrev --all HEAD"
                    ),
                }
            )
            self.assertNotEqual(
                validate_with_schema(
                    contradictory_evaluated,
                    load_schema(SCHEMA_PATH),
                ),
                [],
            )

            contradictory_not_requested = json.loads(json.dumps(not_requested))
            contradictory_not_requested["source_history_scan"]["ref_count"] = 1
            self.assertNotEqual(
                validate_with_schema(
                    contradictory_not_requested,
                    load_schema(SCHEMA_PATH),
                ),
                [],
            )

    def test_source_history_scan_fails_for_deleted_private_path_in_reachable_commit(
        self,
    ) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            (vault / "README.md").write_text("# Public\n", encoding="utf-8")
            _git(vault, "add", "README.md")
            _git(vault, "commit", "-m", "public baseline")

            private_path = vault / "raw" / "private.txt"
            private_path.parent.mkdir()
            private_payload = "private payload retained only in history\n"
            private_path.write_text(private_payload, encoding="utf-8")
            _git(vault, "add", "raw/private.txt")
            _git(vault, "commit", "-m", "add private history")
            _git(vault, "rm", "raw/private.txt")
            _git(vault, "commit", "-m", "delete private path")
            self.assertFalse(private_path.exists())

            scan = scan_source_history(vault)

        self.assertEqual(scan["evaluation_status"], "evaluated")
        self.assertEqual(scan["status"], "fail")
        self.assertFalse(scan["shallow_repository"])
        self.assertGreater(scan["violation_count"], 0)
        self.assertGreaterEqual(
            scan["violation_bytes"], len(private_payload.encode("utf-8"))
        )
        self.assertIn("raw/private.txt", scan["sample_paths"])

    def test_source_history_scan_preserves_excluded_alias_for_shared_blob(
        self,
    ) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            shared_payload = "same bytes at public and private paths\n"
            (vault / "README.md").write_text(shared_payload, encoding="utf-8")
            private_path = vault / "ops" / "manifest.json"
            private_path.parent.mkdir()
            private_path.write_text(shared_payload, encoding="utf-8")
            _git(vault, "add", "README.md", "ops/manifest.json")
            _git(vault, "commit", "-m", "add aliased private history")
            _git(vault, "rm", "ops/manifest.json")
            _git(vault, "commit", "-m", "delete private alias")
            self.assertFalse(private_path.exists())

            scan = scan_source_history(vault)

        self.assertEqual(scan["evaluation_status"], "evaluated")
        self.assertEqual(scan["status"], "fail")
        self.assertEqual(scan["violation_count"], 1)
        self.assertGreaterEqual(
            scan["violation_bytes"],
            len(shared_payload.encode("utf-8")),
        )
        self.assertIn("ops/manifest.json", scan["sample_paths"])

    def test_source_history_scan_ignores_git_replacement_objects(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            (vault / "README.md").write_text("# Public\n", encoding="utf-8")
            _git(vault, "add", "README.md")
            _git(vault, "commit", "-m", "clean public baseline")
            clean_commit = _git(vault, "rev-parse", "HEAD")

            private_path = vault / "raw" / "private.txt"
            private_path.parent.mkdir()
            private_path.write_text("private replacement payload\n", encoding="utf-8")
            _git(vault, "add", "raw/private.txt")
            _git(vault, "commit", "-m", "add private history")
            private_commit = _git(vault, "rev-parse", "HEAD")
            _git(vault, "replace", private_commit, clean_commit)

            scan = scan_source_history(vault)

        self.assertEqual(scan["evaluation_status"], "evaluated")
        self.assertEqual(scan["status"], "fail")
        self.assertIn("raw/private.txt", scan["sample_paths"])
        self.assertTrue(scan["scan_command"].startswith("git --no-replace-objects "))

    def test_source_history_scan_never_passes_with_legacy_grafts(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            (vault / "README.md").write_text("# Public\n", encoding="utf-8")
            _git(vault, "add", "README.md")
            _git(vault, "commit", "-m", "clean public baseline")

            private_path = vault / "raw" / "private.txt"
            private_path.parent.mkdir()
            private_path.write_text("private graft payload\n", encoding="utf-8")
            _git(vault, "add", "raw/private.txt")
            _git(vault, "commit", "-m", "add private history")
            _git(vault, "rm", "raw/private.txt")
            _git(vault, "commit", "-m", "delete private path")

            graft_path_text = _git(vault, "rev-parse", "--git-path", "info/grafts")
            graft_path = Path(graft_path_text)
            if not graft_path.is_absolute():
                graft_path = vault / graft_path
            graft_path.parent.mkdir(parents=True, exist_ok=True)
            graft_path.write_text(_git(vault, "rev-parse", "HEAD") + "\n")

            grafted_scan = scan_source_history(vault)
            graft_path.unlink()
            ungrafted_scan = scan_source_history(vault)

        self.assertTrue(grafted_scan["legacy_grafts_present"])
        self.assertEqual(
            grafted_scan["evaluation_status"],
            "insufficient_history",
        )
        self.assertEqual(grafted_scan["status"], "unknown")
        self.assertEqual(grafted_scan["reason"], "legacy_grafts_present")
        self.assertNotEqual(
            grafted_scan["ref_fingerprint"],
            ungrafted_scan["ref_fingerprint"],
        )
        self.assertFalse(ungrafted_scan["legacy_grafts_present"])
        self.assertEqual(ungrafted_scan["evaluation_status"], "evaluated")
        self.assertEqual(ungrafted_scan["status"], "fail")
        self.assertIn("raw/private.txt", ungrafted_scan["sample_paths"])

    def test_source_history_scan_ignores_ambient_repository_overrides(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            private_path = vault / "raw" / "private.txt"
            private_path.parent.mkdir()
            private_path.write_text("private environment payload\n", encoding="utf-8")
            _git(vault, "add", "raw/private.txt")
            _git(vault, "commit", "-m", "add private history")

            clean_repo = Path(temp_dir) / "clean"
            clean_repo.mkdir()
            _initialize_git_repository(clean_repo)
            (clean_repo / "README.md").write_text("# Clean\n", encoding="utf-8")
            _git(clean_repo, "add", "README.md")
            _git(clean_repo, "commit", "-m", "clean baseline")

            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(clean_repo / ".git"),
                    "GIT_WORK_TREE": str(vault),
                },
            ):
                scan = scan_source_history(vault)

        self.assertEqual(scan["evaluation_status"], "evaluated")
        self.assertEqual(scan["status"], "fail")
        self.assertIn("raw/private.txt", scan["sample_paths"])

    def test_source_history_scan_includes_gitlinks_ignored_by_config(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            _git(vault, "commit", "--allow-empty", "-m", "public baseline")
            target_oid = _git(vault, "rev-parse", "HEAD")
            _git(
                vault,
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{target_oid},raw/private-link",
            )
            _git(vault, "commit", "-m", "add private gitlink")

            _git(vault, "config", "diff.ignoreSubmodules", "all")
            local_config_scan = scan_source_history(vault)
            _git(vault, "config", "--unset", "diff.ignoreSubmodules")

            global_config = Path(temp_dir) / "global.gitconfig"
            global_config.write_text(
                "[diff]\n\tignoreSubmodules = all\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"GIT_CONFIG_GLOBAL": str(global_config)},
            ):
                ambient_config_scan = scan_source_history(vault)

        for scan in (local_config_scan, ambient_config_scan):
            self.assertEqual(scan["evaluation_status"], "evaluated")
            self.assertEqual(scan["status"], "fail")
            self.assertEqual(scan["violation_count"], 1)
            self.assertIn("raw/private-link", scan["sample_paths"])
            self.assertIn("--ignore-submodules=none", scan["scan_command"])

    def test_source_history_scan_enumerates_direct_tree_refs(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            _initialize_git_repository(vault)
            (vault / "README.md").write_text("# Public\n", encoding="utf-8")
            _git(vault, "add", "README.md")
            _git(vault, "commit", "-m", "clean public baseline")

            private_path = vault / "raw" / "private.txt"
            private_path.parent.mkdir()
            private_path.write_text("private tree-ref payload\n", encoding="utf-8")
            private_blob_oid = _git(vault, "hash-object", "-w", "raw/private.txt")

            def write_tree(specification: str) -> str:
                result = subprocess.run(
                    ["git", "mktree"],
                    cwd=vault,
                    input=specification,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                return result.stdout.strip()

            raw_tree_oid = write_tree(f"100644 blob {private_blob_oid}\tprivate.txt\n")
            root_tree_oid = write_tree(f"040000 tree {raw_tree_oid}\traw\n")
            _git(vault, "update-ref", "refs/tags/private-tree", root_tree_oid)
            private_path.unlink()
            private_path.parent.rmdir()

            scan = scan_source_history(vault)

        self.assertEqual(scan["evaluation_status"], "evaluated")
        self.assertEqual(scan["status"], "fail")
        self.assertEqual(scan["violation_count"], 1)
        self.assertIn("raw/private.txt", scan["sample_paths"])
        self.assertIn("ls-tree", scan["scan_command"])

    def test_source_history_scan_checks_non_head_refs_and_invalidates_reuse(
        self,
    ) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            _initialize_git_repository(vault)
            _git(vault, "add", ".")
            _git(vault, "commit", "-m", "clean public baseline")
            primary_branch = _git(vault, "branch", "--show-current")
            request = PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="python",
                pytest_flags="-q",
            )
            report = build_report(
                vault,
                request,
                context=fixed_context(),
                command_runner=fake_runner,
            )
            stored = Path(temp_dir) / "public-check-summary.json"
            stored.write_text(json.dumps(report), encoding="utf-8")
            self.assertTrue(
                reusable_summary_diagnostics(vault, stored, request)["reusable"]
            )

            _git(vault, "switch", "-q", "-c", "private-history")
            private_path = vault / "external-reports" / "review.md"
            private_path.parent.mkdir()
            private_path.write_text("private review\n", encoding="utf-8")
            _git(vault, "add", "-f", "external-reports/review.md")
            _git(vault, "commit", "-m", "private non-head history")
            _git(vault, "switch", "-q", primary_branch)

            scan = scan_source_history(vault)
            reuse = reusable_summary_diagnostics(vault, stored, request)

        self.assertEqual(scan["status"], "fail")
        self.assertIn("external-reports/review.md", scan["sample_paths"])
        self.assertFalse(reuse["reusable"])
        self.assertIn("source_history_state", reuse["reason"])

    def test_source_history_reuse_rechecks_object_graph_completeness(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            _initialize_git_repository(vault)
            _git(vault, "add", ".")
            _git(vault, "commit", "-m", "clean public baseline")
            (vault / "PUBLIC.md").write_text("public tip\n", encoding="utf-8")
            _git(vault, "add", "PUBLIC.md")
            _git(vault, "commit", "-m", "public tip")
            request = PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="python",
                pytest_flags="-q",
            )
            report = build_report(
                vault,
                request,
                context=fixed_context(),
                command_runner=fake_runner,
            )
            stored = Path(temp_dir) / "public-check-summary.json"
            stored.write_text(json.dumps(report), encoding="utf-8")
            self.assertTrue(
                reusable_summary_diagnostics(vault, stored, request)["reusable"]
            )

            before_scan = scan_source_history(vault)
            parent_oid = _git(vault, "rev-parse", "HEAD^")
            parent_object = vault / ".git" / "objects" / parent_oid[:2] / parent_oid[2:]
            self.assertTrue(parent_object.exists())
            parent_object.unlink()

            after_scan = scan_source_history(vault)
            reuse = reusable_summary_diagnostics(vault, stored, request)

        self.assertEqual(after_scan["evaluation_status"], "insufficient_history")
        self.assertEqual(after_scan["status"], "unknown")
        self.assertEqual(
            before_scan["ref_fingerprint"],
            after_scan["ref_fingerprint"],
        )
        self.assertNotEqual(
            before_scan["history_state_fingerprint"],
            after_scan["history_state_fingerprint"],
        )
        self.assertFalse(reuse["reusable"])
        self.assertIn("source_history_state", reuse["reason"])

    def test_source_history_scan_distinguishes_shallow_and_not_requested(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is required for source history probes")
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "source"
            source.mkdir()
            _initialize_git_repository(source)
            (source / "README.md").write_text("# Public\n", encoding="utf-8")
            _git(source, "add", "README.md")
            _git(source, "commit", "-m", "clean public baseline")
            shallow = Path(temp_dir) / "shallow"
            subprocess.run(
                ["git", "clone", "-q", "--depth=1", source.as_uri(), str(shallow)],
                check=True,
                text=True,
                capture_output=True,
            )

            shallow_scan = scan_source_history(shallow)
            skipped_scan = scan_source_history(source, requested=False)

        self.assertTrue(shallow_scan["shallow_repository"])
        self.assertEqual(shallow_scan["evaluation_status"], "insufficient_history")
        self.assertEqual(shallow_scan["status"], "unknown")
        self.assertEqual(skipped_scan["evaluation_status"], "not_requested")
        self.assertEqual(skipped_scan["status"], "unknown")
        self.assertEqual(skipped_scan["ref_scope"], "none")

    def test_public_check_summary_fails_on_exported_local_path_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            (vault / "README.md").write_text(
                f"Do not export local path {vault.resolve()}.\n",
                encoding="utf-8",
            )

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["negative_assertion_fail_count"], 1)
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "status"
                ],
                "fail",
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "violations"
                ],
                ["README.md"],
            )
            self.assertEqual(
                [
                    cause["id"]
                    for cause in report["failure_causes"]
                    if cause["kind"] == "negative_assertion_failure"
                ],
                ["negative_assertion:local_path_absence"],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_fails_on_exported_foreign_local_path_leak(
        self,
    ) -> None:
        for leaked_path in (
            "/workspace/LLMwiki/repo",
            "/Users/alice/work/repo",
            "/private/var/folders/ab/tmp/repo",
            "/" + "tmp/run-123-workspace/vault/wiki/page.md",
            "/" + "var/tmp/run-123/vault",
            "/" + "private/tmp/run-123/vault",
            "workspace:/home/alice/work/repo",
            "file:///" + "home/alice/work/repo",
            "vscode://file/" + "home/alice/work/repo",
            "c" + r":\temp\repo",
            "d" + ":/a/project",
        ):
            with (
                self.subTest(leaked_path=leaked_path),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                report = self._build_report_with_exported_text(
                    temp_dir,
                    "README.md",
                    f"Do not export local path {leaked_path}.\n",
                )

                self.assertEqual(report["status"], "fail")
                self.assertEqual(
                    report["public_export_negative_assertions"]["local_path_absence"][
                        "violations"
                    ],
                    ["README.md"],
                )

    def test_public_check_summary_allows_exported_api_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build_report_with_exported_text(
                temp_dir,
                "README.md",
                "GET /users/{id}\n",
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "violations"
                ],
                [],
            )

    def test_public_check_summary_allows_url_containing_current_vault_text(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            public_out = Path(temp_dir) / "public"
            rel_path = "tests/test_public_surface_policy.py"
            exported_file = public_out / rel_path
            exported_file.parent.mkdir(parents=True)
            exported_file.write_text(
                'URL = "https://example.com/workspace/LLMwiki"\n',
                encoding="utf-8",
            )

            assertions = _public_export_negative_assertions(
                public_out,
                {},
                [{"path": rel_path}],
                source_vault=Path("/", "workspace", "LLMwiki"),
            )

            self.assertEqual(
                assertions["local_path_absence"]["violations"],
                [],
            )

    def test_public_check_summary_rejects_foreign_paths_in_unregistered_source_files(
        self,
    ) -> None:
        for rel_path in (
            "ops/scripts/leak.py",
            "tests/leak.py",
            "tools/leak.py",
        ):
            with (
                self.subTest(rel_path=rel_path),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                report = self._build_report_with_exported_text(
                    temp_dir,
                    rel_path,
                    'DEV_ROOT = "/Users/alice/work/repo"\n',
                )

                self.assertEqual(report["status"], "fail")
                self.assertEqual(
                    report["public_export_negative_assertions"]["local_path_absence"][
                        "violations"
                    ],
                    [rel_path],
                )

    def test_public_check_summary_allows_registered_source_path_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/test_public_check_summary.py",
                'FIXTURE_ROOT = "/workspace/example"\n',
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "violations"
                ],
                [],
            )

    def test_public_check_summary_rejects_longer_path_with_allowed_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            longer_path = "/" + "workspace/example-secret/private"
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/test_public_check_summary.py",
                f'DEV_ROOT = "{longer_path}"\n',
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "violations"
                ],
                ["tests/test_public_check_summary.py"],
            )

    def test_public_check_summary_allows_registered_fixture_containing_current_vault(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_vault = Path("/", "workspace", "LLMwiki")
            public_out = Path(temp_dir) / "public"
            fixture_path = public_out / "tests" / "test_public_check_summary.py"
            fixture_path.parent.mkdir(parents=True)
            fixture_path.write_text(
                f'FIXTURE_ROOT = "{source_vault}/repo"\n',
                encoding="utf-8",
            )
            assertions = _public_export_negative_assertions(
                public_out,
                {},
                [{"path": "tests/test_public_check_summary.py"}],
                source_vault=source_vault,
            )

            self.assertEqual(
                assertions["local_path_absence"]["violations"],
                [],
            )

    def test_public_check_summary_rejects_unregistered_path_beside_allowed_fixture(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            allowed_fixture = "/" + "workspace/example"
            unexpected_path = "/" + "Users/real-user/private-repo"
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/test_public_check_summary.py",
                f'FIXTURE_ROOT = "{allowed_fixture}"\nDEV_ROOT = "{unexpected_path}"\n',
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "violations"
                ],
                ["tests/test_public_check_summary.py"],
            )

    def test_public_check_summary_rejects_current_vault_in_unregistered_source_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_vault = (Path(temp_dir) / "vault").resolve()
            report = self._build_report_with_exported_text(
                temp_dir,
                "tests/leak.py",
                f'DEV_ROOT = "{source_vault}/repo"\n',
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(
                report["public_export_negative_assertions"]["local_path_absence"][
                    "violations"
                ],
                ["tests/leak.py"],
            )

    def test_generated_report_files_are_excluded_without_private_export_violations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            for rel_path in (
                "ops/operator/operator-release-summary.json",
                "ops/reports/goal-worktree-guard.json",
                "ops/reports/release-workflow-order-guard.json",
                "ops/reports/workflow-dependency-planner.json",
            ):
                path = vault / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["negative_assertion_fail_count"], 0)
            self.assertEqual(
                report["public_export_negative_assertions"]["excluded_prefix_absence"][
                    "violations"
                ],
                [],
            )
            self.assertEqual(
                report["public_export_negative_assertions"]["private_pattern_absence"][
                    "violations"
                ],
                [],
            )
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_fails_when_public_pytest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                ),
                context=fixed_context(),
                command_runner=failing_pytest_runner,
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["command_fail_count"], 1)
            self.assertEqual(report["summary"]["pytest_failed"], 1)
            self.assertEqual(len(report["failure_causes"]), 1)
            cause = report["failure_causes"][0]
            self.assertEqual(cause["kind"], "command_failure")
            self.assertEqual(cause["id"], "command:pytest_public")
            self.assertEqual(cause["command_id"], "pytest_public")
            self.assertEqual(cause["returncode"], 1)
            self.assertEqual(cause["pytest_counts"]["failed"], 1)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_cli_prints_compact_failure_summary(self) -> None:
        fake_report = {
            "status": "fail",
            "summary": {
                "public_check_status": "fail",
                "command_fail_count": 1,
                "negative_assertion_fail_count": 0,
            },
            "failure_causes": [
                {
                    "severity": "error",
                    "kind": "command_failure",
                    "id": "command:pytest_public",
                    "message": "public check command pytest_public failed",
                    "command_id": "pytest_public",
                    "status": "fail",
                    "returncode": 1,
                    "timed_out": False,
                    "termination_reason": "completed",
                }
            ],
        }

        def fake_write_report(
            vault: Path, report: dict[str, object], out_path: str
        ) -> Path:
            destination = vault / out_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report), encoding="utf-8")
            return destination

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()

            with (
                patch.object(
                    public_check_summary_module,
                    "build_report",
                    return_value=fake_report,
                ),
                patch.object(
                    public_check_summary_module,
                    "write_report",
                    side_effect=fake_write_report,
                ),
            ):
                completed = invoke_cli_main(
                    public_check_summary_module.main,
                    [
                        "--vault",
                        str(vault),
                        "--out",
                        "tmp/public-check-summary.candidate.json",
                    ],
                    cwd=launcher,
                )

        stdout_lines = completed.stdout.splitlines()
        self.assertEqual(stdout_lines[0], "tmp/public-check-summary.candidate.json")
        payload = json.loads("\n".join(stdout_lines[1:]))
        self.assertEqual(payload["status"], "fail")
        self.assertEqual(payload["failure_causes"][0]["id"], "command:pytest_public")

    def test_public_check_summary_exposes_public_pytest_timeout_cleanup_diagnostics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    heartbeat_interval_seconds=10,
                    timeout_seconds=30,
                ),
                context=fixed_context(),
                command_runner=timeout_pytest_runner,
            )

            pytest_command = report["commands"][-1]
            self.assertEqual(report["status"], "timeout")
            self.assertEqual(report["summary"]["public_check_status"], "timeout")
            self.assertEqual(report["summary"]["command_fail_count"], 1)
            self.assertEqual(report["summary"]["timeout_command_count"], 1)
            self.assertEqual(report["summary"]["max_command_heartbeat_count"], 3)
            self.assertEqual(report["summary"]["max_command_quiet_seconds"], 30)
            self.assertEqual(report["summary"]["public_pytest_heartbeat_count"], 3)
            self.assertEqual(report["summary"]["public_pytest_quiet_seconds"], 30)
            self.assertEqual(
                report["summary"]["public_pytest_termination_reason"],
                "execution_timeout",
            )
            self.assertEqual(report["summary"]["public_pytest_signal_sent"], "sigkill")
            self.assertEqual(
                report["summary"]["public_pytest_final_state_observed"],
                "drain_after_kill",
            )
            self.assertTrue(pytest_command["timed_out"])
            self.assertEqual(pytest_command["signal_sent"], "sigkill")
            self.assertEqual(pytest_command["final_state_observed"], "drain_after_kill")
            self.assertEqual(pytest_command["heartbeat_count"], 3)
            self.assertEqual(pytest_command["quiet_seconds"], 30)
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_public_check_summary_reuses_external_public_pytest_cache_without_exporting_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache" / "test-execution-summary-public.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(
                    {"counts": {"passed": 9, "failed": 0, "errors": 0, "skipped": 1}}
                ),
                encoding="utf-8",
            )
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            def reuse_only_runner(
                argv: Sequence[str],
                cwd: Path,
                timeout_seconds: int,
            ) -> TimedProcessResult:
                module = argv[2] if len(argv) > 2 else ""
                if module == "ops.scripts.test_execution_summary":
                    self.assertIn("--reuse-if-current", argv)
                    self.assertIn("--reuse-from", argv)
                    self.assertIn(cache_path.as_posix(), argv)
                    write_public_pytest_summary(
                        cwd, passed=9, failed=0, errors=0, skipped=1
                    )
                return TimedProcessResult(
                    args=[str(item) for item in argv],
                    returncode=0,
                    stdout="",
                    stderr="",
                    timed_out=False,
                    timeout_seconds=timeout_seconds,
                    termination_reason="completed",
                )

            with patch(
                "ops.scripts.public.public_check_summary._public_pytest_summary_cache_path",
                return_value=cache_path,
            ):
                report = build_report(
                    vault,
                    PublicCheckRequest(
                        public_out=str(public_out),
                        public_python="python",
                    ),
                    context=fixed_context(),
                    command_runner=reuse_only_runner,
                )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["summary"]["pytest_passed"], 9)
            self.assertEqual(report["summary"]["pytest_skipped"], 1)
            self.assertFalse(
                (public_out / PUBLIC_PYTEST_SUMMARY_RELATIVE_PATH).exists()
            )

    def test_reusable_summary_requires_current_source_tree_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="python",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            reusable = reusable_summary_diagnostics(vault, destination)
            self.assertTrue(reusable["reusable"])
            self.assertEqual(reusable["reason"], "current_passing_public_check_summary")

            (vault / "README.md").write_text(
                "# Test\n\nChanged after public check.\n", encoding="utf-8"
            )
            stale = reusable_summary_diagnostics(vault, destination)

            self.assertFalse(stale["reusable"])
            self.assertIn("source_tree_fingerprint", stale["reason"])
            self.assertNotEqual(
                stale["current_source_tree_fingerprint"],
                json.loads(destination.read_text(encoding="utf-8"))[
                    "source_tree_fingerprint"
                ],
            )

    @patch("ops.scripts.public.public_check_summary.public_toolchain_fingerprint", return_value="a" * 64)
    def test_reusable_summary_requires_matching_public_check_config_fingerprint(
        self, _probe,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            original_request = PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="/home/alice/.venv/bin/python",
                ruff_targets="ops/scripts tests",
                mypy_targets="ops/scripts",
                pytest_mark_expr="public",
                pytest_flags="-q",
                timeout_seconds=90,
                heartbeat_interval_seconds=10,
            )

            report = build_report(
                vault,
                original_request,
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            matching = reusable_summary_diagnostics(
                vault, destination, original_request
            )
            self.assertTrue(matching["reusable"])
            self.assertEqual(
                matching["public_check_config_fingerprint"],
                report["input_fingerprints"]["public_check_config"],
            )

            mismatched_python = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="/home/bob/.venv/bin/python",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_python["reusable"])
            self.assertIn("public_check_config", mismatched_python["reason"])
            self.assertNotEqual(
                mismatched_python["expected_public_check_config_fingerprint"],
                mismatched_python["observed_public_check_config_fingerprint"],
            )

            mismatched_public_out = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out="tmp/public",
                    public_python="/home/alice/.venv/bin/python",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_public_out["reusable"])
            self.assertIn("public_check_config", mismatched_public_out["reason"])

            mismatched_pytest = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="/home/alice/.venv/bin/python",
                    ruff_targets="ops/scripts tests",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_pytest["reusable"])
            self.assertIn("public_check_config", mismatched_pytest["reason"])

            mismatched_ruff = reusable_summary_diagnostics(
                vault,
                destination,
                PublicCheckRequest(
                    public_out=str(Path(temp_dir) / "public"),
                    public_python="/home/alice/.venv/bin/python",
                    ruff_targets="ops/scripts",
                    mypy_targets="ops/scripts",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                    timeout_seconds=90,
                    heartbeat_interval_seconds=10,
                ),
            )
            self.assertFalse(mismatched_ruff["reusable"])
            self.assertIn("public_check_config", mismatched_ruff["reason"])

    def test_public_check_config_fingerprint_excludes_internal_pytest_cache_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            request = PublicCheckRequest(
                public_out=str(Path(temp_dir) / "public"),
                public_python="python",
                pytest_flags="-q",
            )

            with patch(
                "ops.scripts.public.public_check_summary._public_pytest_summary_cache_path",
                return_value=Path(temp_dir)
                / "cache-a"
                / "test-execution-summary-public.json",
            ):
                left = _public_check_config_fingerprint(vault, request)

            with patch(
                "ops.scripts.public.public_check_summary._public_pytest_summary_cache_path",
                return_value=Path(temp_dir)
                / "cache-b"
                / "test-execution-summary-public.json",
            ):
                right = _public_check_config_fingerprint(vault, request)

            self.assertEqual(left, right)

    def test_cli_reuse_only_rejects_mismatched_public_check_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"
            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(public_out),
                    public_python="python",
                    pytest_mark_expr="public",
                    pytest_flags="-q",
                ),
                context=fixed_context(),
                command_runner=fake_runner,
            )
            destination = write_report(vault, report)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = public_check_summary_module.main(
                    [
                        "--vault",
                        str(vault),
                        "--reuse-only",
                        "--reuse-from",
                        str(destination),
                        "--public-out",
                        str(public_out),
                        "--public-python",
                        "python",
                        "--pytest-mark-expr",
                        "",
                        "--pytest-flags=-q",
                    ]
                )

            self.assertEqual(exit_code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["summary_mode"], "executed")
            self.assertIn("public_check_config", payload["reuse_diagnostics"]["reason"])

    def test_exact_current_cli_check_does_not_rewrite_canonical_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"
            request = PublicCheckRequest(
                public_out=str(public_out), public_python="python", pytest_flags="-q"
            )
            report = build_report(
                vault, request, context=fixed_context(), command_runner=fake_runner
            )
            destination = write_report(vault, report)
            before_sha256 = hashlib.sha256(destination.read_bytes()).hexdigest()
            before_mtime_ns = destination.stat().st_mtime_ns

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = public_check_summary_module.main(
                    [
                        "--vault",
                        str(vault),
                        "--reuse-only",
                        "--reuse-from",
                        str(destination),
                        "--public-out",
                        str(public_out),
                        "--public-python",
                        "python",
                        "--pytest-flags=-q",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["summary_mode"], "reused")
            self.assertEqual(
                hashlib.sha256(destination.read_bytes()).hexdigest(), before_sha256
            )
            self.assertEqual(destination.stat().st_mtime_ns, before_mtime_ns)

    def test_default_then_full_execution_preserves_both_canonical_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            def execute(mode: str, selector: str, out_path: str) -> Path:
                report = build_report(
                    vault,
                    PublicCheckRequest(
                        mode=mode,
                        public_out=str(public_out),
                        public_python="python",
                        pytest_mark_expr=selector,
                    ),
                    context=fixed_context(),
                    command_runner=fake_runner,
                )
                return write_report(vault, report, out_path)

            default_path = execute(
                "default", "public", "ops/reports/public-check-summary.json"
            )
            default_sha256 = hashlib.sha256(default_path.read_bytes()).hexdigest()
            full_path = execute(
                "full", "", "ops/reports/public-check-summary-full.json"
            )

            self.assertTrue(default_path.is_file())
            self.assertTrue(full_path.is_file())
            self.assertEqual(
                hashlib.sha256(default_path.read_bytes()).hexdigest(), default_sha256
            )
            self.assertEqual(
                json.loads(full_path.read_text(encoding="utf-8"))["source_command"],
                "python -m ops.scripts.public_check_summary --vault . --mode full",
            )

    def test_cli_mode_defaults_make_full_selectorless(self) -> None:
        default_args = public_check_summary_module.parse_args([])
        full_args = public_check_summary_module.parse_args(["--mode", "full"])
        skipped_history_args = public_check_summary_module.parse_args(
            ["--skip-source-history-scan"]
        )
        explicit_empty = public_check_summary_module.parse_args(
            ["--mode", "full", "--pytest-mark-expr", ""]
        )

        self.assertEqual(default_args.pytest_mark_expr, "public")
        self.assertEqual(full_args.pytest_mark_expr, "")
        self.assertEqual(explicit_empty.pytest_mark_expr, "")
        self.assertTrue(skipped_history_args.skip_source_history_scan)
        with self.assertRaises(SystemExit):
            public_check_summary_module.parse_args(
                ["--mode", "full", "--pytest-mark-expr", "public"]
            )

    def test_programmatic_full_mode_is_selectorless_and_rejects_marker_filters(
        self,
    ) -> None:
        request = PublicCheckRequest(mode="full")

        command, _summary_path = (
            public_check_summary_module._pytest_public_summary_command(
                public_python="python",
                request=request,
                reuse_from=Path("ops/reports/test-execution-summary-public.json"),
            )
        )

        self.assertEqual(request.pytest_mark_expr, "")
        self.assertEqual(command[-3:], ["python", "-m", "pytest"])
        self.assertNotIn("public", command)
        with self.assertRaisesRegex(
            ValueError, "full mode requires an empty pytest marker expression"
        ):
            PublicCheckRequest(mode="full", pytest_mark_expr="public")

    def test_cross_mode_reuse_is_rejected_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"
            requests = {
                "default": PublicCheckRequest(
                    mode="default", public_out=str(public_out), public_python="python"
                ),
                "full": PublicCheckRequest(
                    mode="full",
                    public_out=str(public_out),
                    public_python="python",
                    pytest_mark_expr="",
                ),
            }
            paths = {}
            for mode, request in requests.items():
                report = build_report(
                    vault, request, context=fixed_context(), command_runner=fake_runner
                )
                suffix = "-full" if mode == "full" else ""
                paths[mode] = write_report(
                    vault, report, f"ops/reports/public-check-summary{suffix}.json"
                )

            for expected_mode, artifact_mode in (
                ("default", "full"),
                ("full", "default"),
            ):
                diagnostics = reusable_summary_diagnostics(
                    vault, paths[artifact_mode], requests[expected_mode]
                )
                self.assertFalse(diagnostics["reusable"])
                self.assertIn("source_command", diagnostics["reason"])
                self.assertIn("public_check_config", diagnostics["reason"])

    @patch("ops.scripts.public.public_check_summary.public_toolchain_fingerprint", return_value="a" * 64)
    def test_relative_public_python_resolves_against_source_vault(self, _probe) -> None:
        captured_argv: list[list[str]] = []
        captured_cwd: list[Path] = []

        def recording_runner(
            argv: Sequence[str],
            cwd: Path,
            timeout_seconds: int,
        ) -> TimedProcessResult:
            captured_argv.append([str(item) for item in argv])
            captured_cwd.append(cwd)
            return fake_runner(argv, cwd, timeout_seconds)

        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            seed_public_policy_file(vault)
            public_out = Path(temp_dir) / "public"

            report = build_report(
                vault,
                PublicCheckRequest(
                    public_out=str(public_out),
                    public_python=".venv/bin/python",
                ),
                context=fixed_context(),
                command_runner=recording_runner,
            )

            expected_python = str((vault / ".venv/bin/python").absolute())
            self.assertEqual(report["status"], "pass")
            self.assertEqual({argv[0] for argv in captured_argv}, {expected_python})
            self.assertEqual(set(captured_cwd), {public_out.resolve()})
            self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_unresolved_home_public_python_preserves_previous_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()

            with patch.object(
                Path, "expanduser", side_effect=RuntimeError("home unavailable")
            ):
                resolved = _resolve_public_python(vault, "~/bin/python")

            self.assertEqual(resolved, str((vault / "~/bin/python").absolute()))


if __name__ == "__main__":
    unittest.main()
