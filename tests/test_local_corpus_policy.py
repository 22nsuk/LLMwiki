from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from ops.scripts.core.artifact_envelope_runtime import artifact_input_fingerprints
from ops.scripts.core.policy_runtime import (
    DEFAULT_POLICY_PATH,
    LOCAL_CORPUS_POLICY_PATH,
    load_policy,
    write_local_corpus_policy,
)
from ops.scripts.core.source_tree_fingerprint_runtime import (
    release_source_tree_fingerprint,
)
from ops.scripts.core.yaml_runtime import parse_simple_yaml
from ops.scripts.mechanism.mechanism_run_workspace_runtime import (
    _prepare_workspace_copy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_SHARD = "system/system-raw-registry/wiki/local-test-shard.md"


class LocalCorpusPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name)
        self.base_path = self.vault / DEFAULT_POLICY_PATH
        self.base_path.parent.mkdir(parents=True)
        self.base_bytes = (REPO_ROOT / DEFAULT_POLICY_PATH).read_bytes()
        self.base_path.write_bytes(self.base_bytes)
        self.base = parse_simple_yaml(self.base_bytes.decode("utf-8"))
        self.local_path = self.vault / LOCAL_CORPUS_POLICY_PATH

    def _effective_policy(self) -> dict:
        policy = copy.deepcopy(self.base)
        policy["page_shape"]["special_page_required_sections"][SYNTHETIC_SHARD] = [
            "Summary", "Source trace"
        ]
        policy["frontmatter_contract"]["special_pages"][SYNTHETIC_SHARD] = {
            "required": ["special_role"],
            "expected": {
                "page_type": "registry-shard",
                "corpus": "system",
                "special_role": "raw-registry-shard",
            },
        }
        policy["registry_contract"]["raw_registry_shard_pages"].append(SYNTHETIC_SHARD)
        policy["registry_contract"]["raw_registry_entry_page_corpus"][SYNTHETIC_SHARD] = "wiki"
        return policy

    def _write_payload(self, overrides: dict) -> None:
        self.local_path.write_text(
            yaml.safe_dump({"schema_version": 1, "overrides": overrides}),
            encoding="utf-8",
        )

    def _fingerprints(self, path: Path | None = None) -> dict[str, str]:
        return artifact_input_fingerprints(
            self.vault,
            resolved_policy_path=path or self.base_path,
            schema_path="ops/schemas/wiki-maintainer-policy.schema.json",
        )

    def test_absent_local_file_preserves_public_policy_and_fingerprints(self) -> None:
        policy, resolved = load_policy(self.vault)
        self.assertEqual(policy, self.base)
        self.assertEqual(resolved, self.base_path)
        self.assertNotIn("local_corpus_policy", self._fingerprints())

    def test_default_relative_and_absolute_paths_load_the_same_effective_policy(self) -> None:
        expected = self._effective_policy()
        self.assertEqual(write_local_corpus_policy(self.vault, expected), self.local_path)
        for selector in (None, DEFAULT_POLICY_PATH, str(self.base_path)):
            with self.subTest(selector=selector):
                policy, resolved = load_policy(self.vault, selector)
                self.assertEqual(policy, expected)
                self.assertEqual(resolved, self.base_path)
        self.assertEqual(self.base_path.read_bytes(), self.base_bytes)
        first = self.local_path.read_bytes()
        write_local_corpus_policy(self.vault, expected)
        self.assertEqual(self.local_path.read_bytes(), first)

    def test_custom_policy_does_not_load_default_local_overrides(self) -> None:
        custom = self.vault / "custom-policy.yaml"
        custom.write_bytes(self.base_bytes)
        self.local_path.write_text("invalid: [", encoding="utf-8")
        policy, resolved = load_policy(self.vault, "custom-policy.yaml")
        self.assertEqual(policy, self.base)
        self.assertEqual(resolved, custom)
        self.assertNotIn("local_corpus_policy", self._fingerprints(custom))

    def test_unreadable_overlay_is_not_treated_as_absent(self) -> None:
        expected = self._effective_policy()
        write_local_corpus_policy(self.vault, expected)
        self.assertEqual(load_policy(self.vault)[0], expected)
        custom = self.vault / "custom-policy.yaml"
        custom.write_bytes(self.base_bytes)
        original_stat = os.stat
        original_open = Path.open

        def denied_stat(
            path: Any, *, dir_fd: int | None = None, follow_symlinks: bool = True
        ) -> os.stat_result:
            if path == self.local_path or path == str(self.local_path):
                raise PermissionError("synthetic overlay access denied")
            return original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

        def denied_open(path: Path, *args: Any, **kwargs: Any) -> Any:
            if path == self.local_path:
                raise PermissionError("synthetic overlay access denied")
            return original_open(path, *args, **kwargs)

        # Python 3.14 hides stat errors in exists()/is_file(). Keep parsing and
        # schema validation real, and inject only the inaccessible input.
        with patch.object(os, "stat", denied_stat), patch.object(Path, "open", denied_open):
            for selector in (None, DEFAULT_POLICY_PATH, str(self.base_path)):
                with self.subTest(selector=selector), self.assertRaises(PermissionError):
                    load_policy(self.vault, selector)
            with self.subTest(consumer="fingerprints"), self.assertRaises(PermissionError):
                self._fingerprints()
            with (
                tempfile.TemporaryDirectory() as workspace,
                self.subTest(consumer="sparse-workspace"),
                self.assertRaises(PermissionError),
            ):
                _prepare_workspace_copy(
                    self.vault, run_id="synthetic-local-policy", workspace_root=workspace,
                    mode="sparse_manifest", allowed_apply_roots=[DEFAULT_POLICY_PATH],
                )
            self.assertEqual(load_policy(self.vault, str(custom))[0], self.base)
            self.assertNotIn("local_corpus_policy", self._fingerprints(custom))

    def test_overlay_directory_is_rejected_by_policy_consumers(self) -> None:
        self.local_path.mkdir()
        with self.subTest(consumer="loader"), self.assertRaises(IsADirectoryError):
            load_policy(self.vault)
        with self.subTest(consumer="fingerprints"), self.assertRaises(IsADirectoryError):
            self._fingerprints()
        with (
            tempfile.TemporaryDirectory() as workspace,
            self.subTest(consumer="sparse-workspace"),
            self.assertRaises(IsADirectoryError),
        ):
            _prepare_workspace_copy(
                self.vault, run_id="synthetic-local-policy", workspace_root=workspace,
                mode="sparse_manifest", allowed_apply_roots=[DEFAULT_POLICY_PATH],
            )

    def test_local_file_does_not_shadow_unrelated_public_policy_updates(self) -> None:
        write_local_corpus_policy(self.vault, self._effective_policy())
        updated = copy.deepcopy(self.base)
        updated["runtime_defaults"]["display_timezone"] = {"label": "UTC", "utc_offset": "+00:00"}
        self.base_path.write_text(yaml.safe_dump(updated, sort_keys=False), encoding="utf-8")
        effective, _ = load_policy(self.vault)
        self.assertEqual(effective["runtime_defaults"], updated["runtime_defaults"])
        self.assertIn(SYNTHETIC_SHARD, effective["registry_contract"]["raw_registry_shard_pages"])

    def test_local_removal_of_shard_entries_leaves_public_file_intact(self) -> None:
        effective = self._effective_policy()
        removed = effective["registry_contract"]["raw_registry_shard_pages"].pop(0)
        effective["registry_contract"]["raw_registry_entry_page_corpus"].pop(removed, None)
        effective["frontmatter_contract"]["special_pages"].pop(removed, None)
        effective["page_shape"]["special_page_required_sections"].pop(removed, None)
        write_local_corpus_policy(self.vault, effective)
        self.assertEqual(load_policy(self.vault)[0], effective)
        self.assertEqual(self.base_path.read_bytes(), self.base_bytes)

    def test_invalid_local_overrides_fail_without_changing_public_file(self) -> None:
        for overrides in (
            {"subagent_routing_policy": {"default_rung": 4}},
            {"registry_contract": {"raw_registry_shard_pages": "not-a-list"}},
            {"frontmatter_contract": {"special_pages": {SYNTHETIC_SHARD: {"required": 1}}}},
        ):
            with self.subTest(overrides=overrides):
                self._write_payload(overrides)
                with self.assertRaises(ValueError):
                    load_policy(self.vault)
                self.assertEqual(self.base_path.read_bytes(), self.base_bytes)

    def test_writer_rejects_non_corpus_changes_without_replacing_local_file(self) -> None:
        effective = self._effective_policy()
        write_local_corpus_policy(self.vault, effective)
        before = self.local_path.read_bytes()
        effective["runtime_defaults"]["display_timezone"]["label"] = "private-label"
        with self.assertRaisesRegex(ValueError, "non-corpus"):
            write_local_corpus_policy(self.vault, effective)
        self.assertEqual(self.local_path.read_bytes(), before)
        self.assertEqual(self.base_path.read_bytes(), self.base_bytes)

    def test_null_entries_are_removed_even_inside_new_mapping_entries(self) -> None:
        self._write_payload({
            "frontmatter_contract": {"special_pages": {SYNTHETIC_SHARD: {
                "required": None,
                "expected": {"absent": None, "page_type": "registry-shard"},
            }}}
        })
        effective, _ = load_policy(self.vault)
        self.assertEqual(effective["frontmatter_contract"]["special_pages"][SYNTHETIC_SHARD], {
            "expected": {"page_type": "registry-shard"}
        })

    def test_local_updates_invalidate_inputs_without_changing_public_source_identity(self) -> None:
        public_tree = release_source_tree_fingerprint(self.vault)
        before = self._fingerprints()
        write_local_corpus_policy(self.vault, self._effective_policy())
        created = self._fingerprints()
        self.assertNotEqual(created["policy"], before["policy"])
        self.assertIn("local_corpus_policy", created)
        self.local_path.write_text(self.local_path.read_text() + "# operator edit\n", encoding="utf-8")
        staging = self.local_path.with_name(f".{self.local_path.name}.synthetic.tmp")
        staging.write_text("private-staging-sentinel\n", encoding="utf-8")
        changed = self._fingerprints()
        self.assertNotEqual(created["local_corpus_policy"], changed["local_corpus_policy"])
        self.assertEqual(public_tree, release_source_tree_fingerprint(self.vault))
        self.local_path.unlink()
        self.assertEqual(self._fingerprints(), before)

    def test_full_and_sparse_workspaces_preserve_effective_policy(self) -> None:
        expected = self._effective_policy()
        write_local_corpus_policy(self.vault, expected)
        local_bytes = self.local_path.read_bytes()
        unrelated_link = self.base_path.with_name("unrelated-link.yaml")
        unrelated_link.symlink_to(self.local_path)
        with tempfile.TemporaryDirectory() as external:
            # The internal target is intentionally excluded from full copies;
            # both workspace modes must carry an independent policy snapshot.
            for form, target in (
                ("regular", None),
                ("internal-link", self.vault / ".llmwiki" / "corpus.yaml"),
                ("external-link", Path(external) / "corpus.yaml"),
            ):
                if target is not None:
                    self.local_path.unlink()
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(local_bytes)
                    target.chmod(0o600)
                    link_target = os.path.relpath(target, self.local_path.parent) if form == "internal-link" else str(target)
                    self.local_path.symlink_to(link_target)
                for source_mode in (0o600, 0o400):
                    self.local_path.chmod(source_mode)
                    self.base_path.chmod(source_mode)
                    for mode, roots in (
                        ("full_copy", [DEFAULT_POLICY_PATH]),
                        ("sparse_manifest", [DEFAULT_POLICY_PATH]),
                        ("sparse_manifest", ["ops/policies/"]),
                        ("sparse_manifest", ["ops/policies/", LOCAL_CORPUS_POLICY_PATH, DEFAULT_POLICY_PATH]),
                        ("sparse_manifest", [LOCAL_CORPUS_POLICY_PATH, "ops/policies/"]),
                    ):
                        with (
                            self.subTest(form=form, source_mode=oct(source_mode), mode=mode, roots=roots),
                            tempfile.TemporaryDirectory() as workspace,
                        ):
                            prepared = _prepare_workspace_copy(
                                self.vault,
                                run_id="synthetic-local-policy",
                                workspace_root=workspace,
                                mode=mode,
                                allowed_apply_roots=roots,
                            )
                            copied = prepared.workspace_vault / LOCAL_CORPUS_POLICY_PATH
                            self.assertEqual(load_policy(prepared.workspace_vault)[0], expected)
                            self.assertFalse(copied.is_symlink())
                            self.assertEqual(copied.read_bytes(), local_bytes)
                            self.assertEqual(copied.stat().st_mode & 0o777, source_mode)
                            if mode == "sparse_manifest":
                                self.assertFalse((copied.parent / unrelated_link.name).exists())
                            # Candidate-owned copies can change permissions and
                            # bytes without mutating either source input.
                            copied.chmod(0o600)
                            copied.write_bytes(local_bytes + b"# candidate-only edit\n")
                            self.assertEqual(self.local_path.read_bytes(), local_bytes)
                            self.assertEqual(self.local_path.stat().st_mode & 0o777, source_mode)
                            self.assertEqual(self.base_path.read_bytes(), self.base_bytes)

    def test_built_wheel_and_sdist_exclude_local_policy_bytes(self) -> None:
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            shutil.copy2(REPO_ROOT / name, self.vault / name)
        (self.vault / "ops/__init__.py").write_text("", encoding="utf-8")
        sentinel = b"private-corpus-build-sentinel"
        self.local_path.write_bytes(sentinel)
        for directory in ("reports", "operator"):
            private_module = self.vault / "ops" / directory / "private_diagnostic.py"
            private_module.parent.mkdir(parents=True, exist_ok=True)
            private_module.write_bytes(b"# " + sentinel + b"\n")
        result = subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", "--sdist", "--wheel"],
            cwd=self.vault,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        wheel = next((self.vault / "dist").glob("*.whl"))
        sdist = next((self.vault / "dist").glob("*.tar.gz"))
        with zipfile.ZipFile(wheel) as archive:
            self.assertIn(DEFAULT_POLICY_PATH, archive.namelist())
            for name in archive.namelist():
                self.assertNotIn(LOCAL_CORPUS_POLICY_PATH, name)
                self.assertNotIn(sentinel, archive.read(name))
        with tarfile.open(sdist) as archive:
            self.assertTrue(any(item.name.endswith(DEFAULT_POLICY_PATH) for item in archive.getmembers()))
            for item in archive.getmembers():
                self.assertNotIn(LOCAL_CORPUS_POLICY_PATH, item.name)
                if item.isfile():
                    stream = archive.extractfile(item)
                    assert stream is not None
                    self.assertNotIn(sentinel, stream.read())
