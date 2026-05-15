from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ops.scripts.filesystem_runtime import (
    AtomicTextUpdate,
    FilesystemTransactionError,
    apply_manifest_transaction,
    atomic_multi_write,
    build_atomic_text_updates,
    plan_manifest_apply_transaction,
    rehearse_manifest_apply_rollback,
)


class FilesystemRuntimeTests(unittest.TestCase):
    def test_build_atomic_text_updates_normalizes_specs_and_rejects_duplicate_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alpha = root / "alpha.txt"
            beta = root / "beta.txt"
            (root / "nested").mkdir()
            alpha_alias = root / "nested" / ".." / "alpha.txt"

            updates = build_atomic_text_updates(
                [
                    (alpha, "alpha\n"),
                    {"path": beta, "text": "beta\n"},
                ]
            )

            self.assertEqual(
                updates,
                [
                    AtomicTextUpdate(path=alpha, text="alpha\n"),
                    AtomicTextUpdate(path=beta, text="beta\n"),
                ],
            )
            with self.assertRaisesRegex(
                FilesystemTransactionError,
                "atomic_multi_write received duplicate target paths: .*alpha.txt",
            ):
                build_atomic_text_updates(
                    [
                        (alpha, "first-alpha\n"),
                        (alpha_alias, "second-alpha\n"),
                    ]
                )

    def test_atomic_multi_write_rejects_duplicate_alias_targets_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alpha = root / "alpha.txt"
            (root / "nested").mkdir()
            alpha_alias = root / "nested" / ".." / "alpha.txt"
            alpha.write_text("original-alpha\n", encoding="utf-8")

            with self.assertRaisesRegex(
                FilesystemTransactionError,
                "atomic_multi_write received duplicate target paths: .*alpha.txt",
            ):
                atomic_multi_write(
                    [
                        AtomicTextUpdate(path=alpha, text="first-alpha\n"),
                        {"path": alpha_alias, "text": "second-alpha\n"},
                    ]
                )

            self.assertEqual(alpha.read_text(encoding="utf-8"), "original-alpha\n")

    def test_atomic_multi_write_rolls_back_committed_files_on_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alpha = root / "alpha.txt"
            beta = root / "nested" / "beta.txt"
            alpha.write_text("original-alpha\n", encoding="utf-8")

            real_replace = __import__("os").replace
            call_count = {"value": 0}

            def flaky_replace(src: str | Path, dst: str | Path) -> None:
                call_count["value"] += 1
                if call_count["value"] == 2:
                    raise OSError("replace failed")
                real_replace(src, dst)

            with mock.patch("ops.scripts.filesystem_runtime.os.replace", side_effect=flaky_replace):
                with self.assertRaises(FilesystemTransactionError):
                    atomic_multi_write(
                        [
                            AtomicTextUpdate(path=alpha, text="updated-alpha\n"),
                            AtomicTextUpdate(path=beta, text="new-beta\n"),
                        ]
                    )

            self.assertEqual(alpha.read_text(encoding="utf-8"), "original-alpha\n")
            self.assertFalse(beta.exists())

    def test_apply_manifest_transaction_rolls_back_partial_workspace_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            live_root.mkdir()
            workspace_root.mkdir()

            (live_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (live_root / "ops" / "scripts" / "example.py").write_text(
                "print('live')\n",
                encoding="utf-8",
            )
            (workspace_root / "ops" / "scripts" / "example.py").write_text(
                "print('workspace')\n",
                encoding="utf-8",
            )
            (workspace_root / "ops" / "scripts" / "new_module.py").write_text(
                "print('new')\n",
                encoding="utf-8",
            )

            manifest = {
                "files": [
                    {"path": "ops/scripts/example.py", "change_type": "modified"},
                    {"path": "ops/scripts/new_module.py", "change_type": "added"},
                ]
            }

            real_replace = __import__("os").replace
            call_count = {"value": 0}

            def flaky_replace(src: str | Path, dst: str | Path) -> None:
                call_count["value"] += 1
                if call_count["value"] == 2:
                    raise OSError("workspace apply failed")
                real_replace(src, dst)

            with mock.patch("ops.scripts.filesystem_runtime.os.replace", side_effect=flaky_replace):
                with self.assertRaises(FilesystemTransactionError):
                    apply_manifest_transaction(
                        live_root,
                        workspace_root,
                        manifest,
                        allowed_apply_roots=["ops/"],
                    )

            self.assertEqual(
                (live_root / "ops" / "scripts" / "example.py").read_text(encoding="utf-8"),
                "print('live')\n",
            )
            self.assertFalse((live_root / "ops" / "scripts" / "new_module.py").exists())

    def test_apply_manifest_transaction_writes_shadow_report_before_live_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            live_root.mkdir()
            workspace_root.mkdir()

            (live_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (live_root / "ops" / "scripts" / "example.py").write_text(
                "print('live')\n",
                encoding="utf-8",
            )
            (workspace_root / "ops" / "scripts" / "example.py").write_text(
                "print('workspace')\n",
                encoding="utf-8",
            )
            (workspace_root / "ops" / "scripts" / "new_module.py").write_text(
                "print('new')\n",
                encoding="utf-8",
            )
            (live_root / "ops" / "scripts" / "old_module.py").write_text(
                "print('old')\n",
                encoding="utf-8",
            )

            manifest = {
                "$schema": "ops/schemas/changed-files-manifest.schema.json",
                "run_id": "run-shadow-apply",
                "files": [
                    {"path": "ops/scripts/example.py", "change_type": "modified"},
                    {"path": "ops/scripts/new_module.py", "change_type": "added"},
                    {"path": "ops/scripts/old_module.py", "change_type": "deleted"},
                ],
            }
            shadow_report_path = live_root / "runs" / "run-shadow-apply" / "shadow-apply-report.json"
            real_replace = __import__("os").replace
            live_example_suffix = "/ops/scripts/example.py"

            def fail_first_live_apply(src: str | Path, dst: str | Path) -> None:
                normalized_dst = str(dst).replace("\\", "/").casefold()
                if normalized_dst.endswith(live_example_suffix):
                    raise OSError("live apply failed")
                real_replace(src, dst)

            with mock.patch("ops.scripts.filesystem_runtime.os.replace", side_effect=fail_first_live_apply):
                with self.assertRaisesRegex(FilesystemTransactionError, "live apply failed"):
                    apply_manifest_transaction(
                        live_root,
                        workspace_root,
                        manifest,
                        allowed_apply_roots=["ops/"],
                        shadow_report_path=shadow_report_path,
                        shadow_report_generated_at="2026-04-15T03:45:00Z",
                    )

            shadow_report = json.loads(shadow_report_path.read_text(encoding="utf-8"))
            self.assertEqual(shadow_report["mode"], "shadow")
            self.assertEqual(shadow_report["status"], "ready_for_live_apply")
            self.assertEqual(shadow_report["source_manifest"]["run_id"], "run-shadow-apply")
            self.assertEqual(shadow_report["guard"]["allowed_apply_roots"], ["ops/"])
            self.assertEqual(shadow_report["summary"]["total_changed_files"], 3)
            self.assertEqual(shadow_report["summary"]["added"], 1)
            self.assertEqual(shadow_report["summary"]["modified"], 1)
            self.assertEqual(shadow_report["summary"]["deleted"], 1)
            self.assertEqual(
                [item["path"] for item in shadow_report["files"]],
                [
                    "ops/scripts/example.py",
                    "ops/scripts/new_module.py",
                    "ops/scripts/old_module.py",
                ],
            )
            self.assertEqual(
                (live_root / "ops" / "scripts" / "example.py").read_text(encoding="utf-8"),
                "print('live')\n",
            )
            self.assertFalse((live_root / "ops" / "scripts" / "new_module.py").exists())
            self.assertTrue((live_root / "ops" / "scripts" / "old_module.py").exists())

    def test_plan_manifest_apply_transaction_writes_shadow_report_without_live_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            live_root.mkdir()
            workspace_root.mkdir()
            (live_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (live_root / "ops" / "scripts" / "example.py").write_text("before\n", encoding="utf-8")
            (workspace_root / "ops" / "scripts" / "example.py").write_text("after\n", encoding="utf-8")

            shadow_report_path = live_root / "runs" / "run-canary" / "shadow-apply-report.json"
            changed_paths = plan_manifest_apply_transaction(
                live_root,
                workspace_root,
                {
                    "$schema": "ops/schemas/changed-files-manifest.schema.json",
                    "run_id": "run-canary",
                    "files": [{"path": "ops/scripts/example.py", "change_type": "modified"}],
                },
                allowed_apply_roots=["ops/"],
                shadow_report_path=shadow_report_path,
                shadow_report_generated_at="2026-04-15T03:45:00Z",
            )

            shadow_report = json.loads(shadow_report_path.read_text(encoding="utf-8"))
            self.assertEqual(changed_paths, ["ops/scripts/example.py"])
            self.assertEqual(shadow_report["mode"], "shadow")
            self.assertEqual(shadow_report["status"], "ready_for_live_apply")
            self.assertEqual((live_root / "ops" / "scripts" / "example.py").read_text(encoding="utf-8"), "before\n")

    def test_rehearse_manifest_apply_rollback_writes_report_without_live_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            live_root.mkdir()
            workspace_root.mkdir()
            (live_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (live_root / "ops" / "scripts" / "example.py").write_text("before\n", encoding="utf-8")
            (workspace_root / "ops" / "scripts" / "example.py").write_text("after\n", encoding="utf-8")
            (workspace_root / "ops" / "scripts" / "new_module.py").write_text("new\n", encoding="utf-8")
            (live_root / "ops" / "scripts" / "old_module.py").write_text("old\n", encoding="utf-8")

            manifest = {
                "$schema": "ops/schemas/changed-files-manifest.schema.json",
                "run_id": "run-rehearsal",
                "files": [
                    {"path": "ops/scripts/example.py", "change_type": "modified"},
                    {"path": "ops/scripts/new_module.py", "change_type": "added"},
                    {"path": "ops/scripts/old_module.py", "change_type": "deleted"},
                ],
            }
            report_path = live_root / "runs" / "run-rehearsal" / "rollback-rehearsal-report.json"

            report = rehearse_manifest_apply_rollback(
                live_root,
                workspace_root,
                manifest,
                allowed_apply_roots=["ops/"],
                rollback_rehearsal_report_path=report_path,
                rollback_rehearsal_generated_at="2026-04-15T03:45:00Z",
                shadow_report_ref="runs/run-rehearsal/shadow-apply-report.json",
            )

            persisted = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report, persisted)
            self.assertEqual(report["mode"], "rollback_rehearsal")
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["source_shadow_apply_report"], "runs/run-rehearsal/shadow-apply-report.json")
            self.assertEqual(report["summary"]["total_changed_files"], 3)
            self.assertEqual(report["summary"]["apply_verified"], 3)
            self.assertEqual(report["summary"]["rollback_verified"], 3)
            self.assertEqual(report["summary"]["failed"], 0)
            self.assertEqual((live_root / "ops" / "scripts" / "example.py").read_text(encoding="utf-8"), "before\n")
            self.assertFalse((live_root / "ops" / "scripts" / "new_module.py").exists())
            self.assertTrue((live_root / "ops" / "scripts" / "old_module.py").exists())

    def test_rehearse_manifest_apply_rollback_reports_rollback_verification_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            live_root.mkdir()
            workspace_root.mkdir()
            (live_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            live_file = live_root / "ops" / "scripts" / "example.py"
            workspace_file = workspace_root / "ops" / "scripts" / "example.py"
            live_file.write_text("before\n", encoding="utf-8")
            workspace_file.write_text("after\n", encoding="utf-8")
            manifest = {
                "$schema": "ops/schemas/changed-files-manifest.schema.json",
                "run_id": "run-rehearsal-fail",
                "files": [{"path": "ops/scripts/example.py", "change_type": "modified"}],
            }
            report_path = live_root / "runs" / "run-rehearsal-fail" / "rollback-rehearsal-report.json"

            with mock.patch(
                "ops.scripts.filesystem_runtime._rollback_manifest_items",
                return_value=["ops/scripts/example.py: simulated rollback failure"],
            ):
                report = rehearse_manifest_apply_rollback(
                    live_root,
                    workspace_root,
                    manifest,
                    allowed_apply_roots=["ops/"],
                    rollback_rehearsal_report_path=report_path,
                    rollback_rehearsal_generated_at="2026-04-15T03:45:00Z",
                )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["summary"]["failed"], 1)
            self.assertIn("simulated rollback failure", report["diagnostics"][0])
            self.assertEqual(live_file.read_text(encoding="utf-8"), "before\n")

    def test_apply_manifest_transaction_rejects_paths_outside_allowed_apply_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            live_root.mkdir()
            workspace_root.mkdir()

            (live_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
            (workspace_root / "README.md").write_text("workspace readme\n", encoding="utf-8")
            (workspace_root / "ops" / "scripts" / "example.py").write_text(
                "print('workspace')\n",
                encoding="utf-8",
            )
            (live_root / "README.md").write_text("live readme\n", encoding="utf-8")
            (live_root / "ops" / "scripts" / "example.py").write_text(
                "print('live')\n",
                encoding="utf-8",
            )

            manifest = {
                "files": [
                    {"path": "README.md", "change_type": "modified"},
                    {"path": "ops/scripts/example.py", "change_type": "modified"},
                ]
            }

            with self.assertRaisesRegex(FilesystemTransactionError, "outside allowed_apply_roots: README.md"):
                apply_manifest_transaction(
                    live_root,
                    workspace_root,
                    manifest,
                    allowed_apply_roots=["ops/", "tests/", "system/system-log.md"],
                )

            self.assertEqual(
                (live_root / "README.md").read_text(encoding="utf-8"),
                "live readme\n",
            )
            self.assertEqual(
                (live_root / "ops" / "scripts" / "example.py").read_text(encoding="utf-8"),
                "print('live')\n",
            )

    def test_apply_manifest_transaction_rejects_live_symlink_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            outside_live = root / "outside-live"
            live_root.mkdir()
            workspace_root.mkdir()
            outside_live.mkdir()
            try:
                (live_root / "ops").symlink_to(outside_live, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation is unavailable in this environment")
            (workspace_root / "ops").mkdir(parents=True, exist_ok=True)
            (workspace_root / "ops" / "escape.txt").write_text("candidate\n", encoding="utf-8")

            manifest = {"files": [{"path": "ops/escape.txt", "change_type": "added"}]}

            with self.assertRaisesRegex(
                FilesystemTransactionError,
                "live path resolves through symlink segments for ops/escape.txt",
            ):
                apply_manifest_transaction(
                    live_root,
                    workspace_root,
                    manifest,
                    allowed_apply_roots=["ops/"],
                )

            self.assertFalse((outside_live / "escape.txt").exists())
            self.assertFalse((live_root / "ops" / "escape.txt").exists())

    def test_apply_manifest_transaction_rejects_workspace_symlink_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            live_root = root / "live"
            workspace_root = root / "workspace"
            outside_workspace = root / "outside-workspace"
            live_root.mkdir()
            workspace_root.mkdir()
            outside_workspace.mkdir()
            (live_root / "ops").mkdir(parents=True, exist_ok=True)
            try:
                (workspace_root / "ops").symlink_to(outside_workspace, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("symlink creation is unavailable in this environment")
            (outside_workspace / "escape.txt").write_text("candidate\n", encoding="utf-8")

            manifest = {"files": [{"path": "ops/escape.txt", "change_type": "added"}]}

            with self.assertRaisesRegex(
                FilesystemTransactionError,
                "workspace path resolves through symlink segments for ops/escape.txt",
            ):
                apply_manifest_transaction(
                    live_root,
                    workspace_root,
                    manifest,
                    allowed_apply_roots=["ops/"],
                )

            self.assertFalse((live_root / "ops" / "escape.txt").exists())
