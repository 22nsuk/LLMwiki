from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.core.trusted_candidate_runner import (
    TrustedCandidateRunRequest,
    build_trusted_candidate_env,
    resolve_trusted_repo_health_argv,
    rewrite_argv_trusted_python,
    run_trusted_candidate_command,
)
from ops.scripts.core.workspace_python_identity_runtime import (
    build_workspace_python_identity,
    verify_workspace_python_shim,
    write_workspace_python_identity,
)
from tests.minimal_vault_runtime import REPO_ROOT


class TrustedCandidateRunnerTests(unittest.TestCase):
    def test_build_trusted_candidate_env_strips_workspace_python_contamination(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {
                "PYTHONPATH": "/evil",
                "VIRTUAL_ENV": "/tmp/evil",
                "PYTHONHOME": "/tmp/evil",
                "HOME": "/home/tester",
            },
            clear=False,
        ):
            env = build_trusted_candidate_env(trusted_python=Path("/trusted/python"))
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("VIRTUAL_ENV", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["PYTHON"], "/trusted/python")

    def test_resolve_trusted_repo_health_argv_uses_trusted_make_for_external_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            trusted = Path(temp_dir) / "trusted"
            workspace = Path(temp_dir) / "workspace"
            trusted.mkdir()
            workspace.mkdir()
            (trusted / "Makefile").write_text("check:\n\t@echo ok\n", encoding="utf-8")
            argv = resolve_trusted_repo_health_argv(
                test_files=[],
                workspace_mode="full_copy",
                workspace_root=workspace,
                trusted_vault_root=trusted,
                trusted_python=Path("/trusted/python"),
            )
            self.assertEqual(Path(argv[0]).name, "make")
            self.assertEqual(argv[1], "-C")
            self.assertEqual(argv[2], str(trusted))
            self.assertTrue(any(str(token).startswith("VAULT=") for token in argv))
            self.assertTrue(any(str(token).startswith("PYTHON=") for token in argv))

    def test_run_trusted_candidate_command_writes_audit_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            audit_rel = "runs/run-audit/test.audit.json"

            def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                argv = list(args[0]) if args else list(kwargs.get("args", []))
                return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

            with mock.patch(
                "ops.scripts.core.trusted_candidate_runner.subprocess.run",
                side_effect=fake_run,
            ):
                outcome = run_trusted_candidate_command(
                    TrustedCandidateRunRequest(
                        purpose="test",
                        argv=["echo", "ok"],
                        workspace_root=vault,
                        trusted_vault_root=vault,
                        trusted_python=Path("/trusted/python"),
                        timeout_seconds=5,
                        audit_rel_path=audit_rel,
                    )
                )
            self.assertEqual(outcome.returncode, 0)
            audit = json.loads((vault / audit_rel).read_text(encoding="utf-8"))
            self.assertEqual(audit["purpose"], "test")

    def test_rewrite_preserves_workspace_python_when_caller_trusts_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            workspace_python = workspace / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            workspace_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            argv = [str(workspace_python), "-I", "-B", "-c", "pass"]

            rewritten = rewrite_argv_trusted_python(
                argv,
                workspace_root=workspace,
                trusted_python=workspace_python,
            )

            self.assertEqual(rewritten, argv)

    def test_rewrite_replaces_workspace_python_when_trusted_python_differs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            workspace_python = workspace / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            workspace_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            trusted_python = Path(temp_dir) / "trusted-python"
            trusted_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            argv = [str(workspace_python), "-I", "-B", "-c", "pass"]

            rewritten = rewrite_argv_trusted_python(
                argv,
                workspace_root=workspace,
                trusted_python=trusted_python,
            )

            self.assertEqual(rewritten[0], str(trusted_python.resolve()))
            self.assertEqual(rewritten[1:], argv[1:])

    def test_rewrite_preserves_trusted_python_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            workspace_python = workspace / ".venv" / "bin" / "python"
            workspace_python.parent.mkdir(parents=True)
            trusted_target = Path(temp_dir) / "trusted-python-target"
            trusted_target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            trusted_target.chmod(0o755)
            trusted_python = Path(temp_dir) / "trusted-bin" / "python"
            trusted_python.parent.mkdir()
            try:
                trusted_python.symlink_to(trusted_target)
            except OSError as exc:
                self.skipTest(f"symlink setup unavailable: {exc}")
            workspace_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            argv = [str(workspace_python), "-I", "-B", "-c", "pass"]

            rewritten = rewrite_argv_trusted_python(
                argv,
                workspace_root=workspace,
                trusted_python=trusted_python,
            )

            self.assertEqual(rewritten[0], str(trusted_python.absolute()))
            self.assertNotEqual(rewritten[0], str(trusted_target))
            self.assertEqual(rewritten[1:], argv[1:])

    def test_run_trusted_candidate_command_blocks_trusted_python_symlink_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            first_target = Path(temp_dir) / "first-python"
            second_target = Path(temp_dir) / "second-python"
            for target in (first_target, second_target):
                target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                target.chmod(0o755)
            trusted_python = workspace / ".venv" / "bin" / "python"
            trusted_python.parent.mkdir(parents=True)
            try:
                trusted_python.symlink_to(first_target)
            except OSError as exc:
                self.skipTest(f"symlink setup unavailable: {exc}")
            expected_realpath = trusted_python.resolve(strict=True)
            trusted_python.unlink()
            trusted_python.symlink_to(second_target)

            with mock.patch("ops.scripts.core.trusted_candidate_runner.subprocess.run") as run:
                outcome = run_trusted_candidate_command(
                    TrustedCandidateRunRequest(
                        purpose="test",
                        argv=[str(trusted_python), "-c", "pass"],
                        workspace_root=workspace,
                        trusted_vault_root=workspace,
                        trusted_python=trusted_python,
                        trusted_python_realpath=expected_realpath,
                        timeout_seconds=5,
                    )
                )

            run.assert_not_called()
            self.assertEqual(outcome.returncode, 126)
            self.assertIn("trusted python symlink target changed", outcome.stderr)

    def test_workspace_python_identity_blocks_modified_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "base-python"
            source.write_text("#!/bin/sh\n", encoding="utf-8")
            shim = workspace / ".venv" / "bin" / "python"
            shim.parent.mkdir(parents=True)
            content = f"#!/bin/sh\nexec {source} \"$@\"\n"
            shim.write_text(content, encoding="utf-8")
            write_workspace_python_identity(
                workspace,
                build_workspace_python_identity(source_python=source, shim_content=content),
            )
            shim.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
            issue = verify_workspace_python_shim(workspace, workspace_python=shim)
            self.assertIn("shim", issue)

    def test_workspace_python_identity_requires_manifest_for_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            source = workspace / "base-python"
            source.write_text("#!/bin/sh\n", encoding="utf-8")
            shim = workspace / ".venv" / "bin" / "python"
            shim.parent.mkdir(parents=True)
            shim.write_text(f"#!/bin/sh\nexec {source} \"$@\"\n", encoding="utf-8")
            issue = verify_workspace_python_shim(workspace, workspace_python=shim)
            self.assertEqual(issue, "missing workspace python identity manifest")


class TrustedCandidateInvariantTests(unittest.TestCase):
    def test_automated_codex_argv_never_includes_dangerous_bypass_flag(self) -> None:
        from ops.scripts.core.codex_exec_executor import _codex_exec_argv

        argv = _codex_exec_argv(
            workspace_root=REPO_ROOT,
            routing_report={
                "routing_decision": {
                    "sandbox_mode": "read-only",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                }
            },
            output_last_message_rel="runs/test/validator-last-message.json",
        )
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
