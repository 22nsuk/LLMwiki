from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from ops.scripts.release_smoke import (
    ARCHIVE_SELF_DESCRIPTION_PATH,
    EPHEMERAL_REPORT_PREFIX,
    FAST_PROFILE,
    FAST_DEFAULT_REPORT_OUT,
    FULL_PROFILE,
    ReleaseArchiveBuildError,
    build_partial_report,
    build_release_archive,
    build_report,
    build_smoke_commands,
    compare_manifests,
    default_report_out,
    ensure_output_parent_preflight,
    extract_release_archive,
    main,
    output_parent_preflight,
    parse_args,
    release_smoke_reuse_diagnostics,
    run_smoke_commands,
    write_report,
    _archive_budget,
    _verify_release_archive,
)
from ops.scripts.review_archive import build_review_archive, write_report as write_review_archive_report
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.wiki_manifest import build_manifest
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.integration, pytest.mark.report_contract]


def sample_archive_class() -> dict:
    return {
        "name": "release_smoke_zip",
        "format": "zip",
        "compression": "ZIP_DEFLATED",
        "root_prefix": "LLMwiki",
        "member_path_template": "LLMwiki/<manifest path>",
        "path_encoding": "utf-8",
        "zip_create_system": 3,
        "manifest_exclusion_policy": {
            "name": "release_manifest_exclusions",
            "excluded_prefixes": [],
            "excluded_files": [],
            "excluded_cache_dirs": ["__pycache__", ".cache"],
            "excluded_dev_hidden_dirs": [".venv"],
            "excluded_suffixes": [".pyc", ".pyo"],
            "excluded_egg_info_dirs": True,
        },
    }


def sample_archive_budget(*, passed: bool = True) -> dict:
    status = "pass" if passed else "fail"
    return {
        "pass": passed,
        "zip_path_byte_budget": {"limit_bytes": 65535, "max_bytes": 16, "status": "pass"},
        "zip_component_byte_budget": {"limit_bytes": 255, "max_bytes": 9, "status": status},
        "posix_escape_expanded_filename_budget": {"limit_bytes": 255, "max_bytes": 9, "status": status},
        "blocking_budget_fail_count": 0 if passed else 1,
        "platform_warning_count": 0 if passed else 1,
        "platform_path_diagnostics": {
            "status": "pass" if passed else "warn",
            "blocker_count": 0 if passed else 1,
            "warning_count": 0 if passed else 1,
            "diagnostics": [
                {"id": "zip_path_byte_budget", "status": "pass", "severity": "blocker"},
                {"id": "zip_component_byte_budget", "status": status, "severity": "blocker"},
                {"id": "infozip_c_locale_escape_filename_budget", "status": status, "severity": "warn"},
            ],
        },
        "top_offenders": [
            {
                "path": "README.md",
                "archive_path": "LLMwiki/README.md",
                "size_bytes": 1,
                "zip_path_bytes": 15,
                "zip_component_bytes": 9,
                "python_unicode_escape_filename_bytes": 9,
                "posix_escape_expanded_filename_bytes": 9,
                "infozip_c_locale_escape_filename_bytes": 9,
                "max_budget_ratio": 0.04,
            }
        ],
    }


def sample_archive_reproducibility(*, status: str = "pass") -> dict:
    passed = status == "pass"
    archive_sha = "a" * 64 if passed else "b" * 64
    manifest_sha = "c" * 64 if passed else "d" * 64
    return {
        "status": status,
        "run_count": 2 if status != "not_run" else 0,
        "first_archive_sha256": "a" * 64 if status != "not_run" else "",
        "second_archive_sha256": archive_sha if status != "not_run" else "",
        "same_archive_sha256": passed,
        "first_source_manifest_digest": "c" * 64 if status != "not_run" else "",
        "second_source_manifest_digest": manifest_sha if status != "not_run" else "",
        "same_source_manifest_digest": passed,
        "summary": f"archive_reproducibility={status}",
    }


class ReleaseSmokeTest(unittest.TestCase):
    def test_review_archive_reuses_manifest_exclusions_without_running_smoke_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            (vault / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
            (vault / ".venv" / "bin" / "python").write_text("python", encoding="utf-8")
            (vault / ".pytest_cache").mkdir(exist_ok=True)
            (vault / ".pytest_cache" / "nodeids").write_text("cache", encoding="utf-8")
            (vault / ".obsidian").mkdir(exist_ok=True)
            (vault / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
            (vault / "dist").mkdir(exist_ok=True)
            (vault / "dist" / "artifact.whl").write_text("wheel", encoding="utf-8")
            (vault / "llm_wiki_vnext.egg-info").mkdir(exist_ok=True)
            (vault / "llm_wiki_vnext.egg-info" / "PKG-INFO").write_text("metadata", encoding="utf-8")
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "local.json").write_text("{}", encoding="utf-8")
            (vault / "AGENTS.local.md").write_text("# local\n", encoding="utf-8")
            (vault / "wiki").mkdir(exist_ok=True)
            (vault / "wiki" / "index.md").write_text("# private\n", encoding="utf-8")
            (vault / "raw").mkdir(exist_ok=True)
            (vault / "raw" / "source.pdf").write_text("pdf", encoding="utf-8")
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            archive_path = vault / "tmp" / "review.zip"
            report = build_review_archive(vault, archive_path, context=context)
            destination = write_review_archive_report(vault, report, "ops/reports/review-archive-report.json")

            with zipfile.ZipFile(archive_path) as zf:
                names = sorted(zf.namelist())

            self.assertIn("vault/README.md", names)
            self.assertNotIn("vault/.venv/bin/python", names)
            self.assertNotIn("vault/.pytest_cache/nodeids", names)
            self.assertNotIn("vault/.obsidian/workspace.json", names)
            self.assertNotIn("vault/dist/artifact.whl", names)
            self.assertNotIn("vault/llm_wiki_vnext.egg-info/PKG-INFO", names)
            self.assertNotIn("vault/ops/reports/local.json", names)
            self.assertNotIn("vault/AGENTS.local.md", names)
            self.assertNotIn("vault/wiki/index.md", names)
            self.assertNotIn("vault/raw/source.pdf", names)
            self.assertEqual(report["$schema"], "ops/schemas/review-archive-report.schema.json")
            self.assertEqual(report["artifact_kind"], "review_archive_report")
            self.assertEqual(report["profile"], "clean")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["currentness"], {"status": "current", "checked_at": "2026-04-15T03:45:00Z"})
            self.assertEqual(report["archive_path"], "tmp/review.zip")
            self.assertEqual(report["archive_file"]["path"], "tmp/review.zip")
            self.assertTrue(report["archive_file"]["exists"])
            self.assertEqual(len(report["archive_file"]["sha256"]), 64)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["policy"], {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 4})
            self.assertEqual(report["exclusion_policy"], "public_surface_policy")
            self.assertEqual(report["manifest_digest"], report["archive_manifest_digest"])
            self.assertEqual(report["current_snapshot_representativeness"]["status"], "representative")
            self.assertEqual(report["snapshot_hygiene"]["status"], "pass")
            self.assertTrue(report["snapshot_hygiene"]["enforced"])
            self.assertTrue(report["current_snapshot_representativeness"]["representative_of_current_tree"])
            self.assertTrue(any(entry["path"] == "README.md" for entry in report["manifest"]["files"]))
            self.assertTrue(any(entry["path"] == "README.md" for entry in report["archive_manifest"]["files"]))
            self.assertFalse(any(entry["path"].startswith("wiki/") for entry in report["manifest"]["files"]))
            self.assertEqual(destination, (vault / "ops" / "reports" / "review-archive-report.json").resolve())
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)

    def test_review_archive_clean_profile_blocks_candidate_json_and_pycache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            (vault / "tmp").mkdir()
            (vault / "tmp" / "release-evidence-dashboard.candidate.json").write_text("{}", encoding="utf-8")
            (vault / "tools" / "__pycache__").mkdir(parents=True)
            (vault / "tools" / "__pycache__" / "script.cpython-313.pyc").write_bytes(b"cache")
            archive_path = vault / "tmp" / "review.zip"

            with self.assertRaises(ValueError) as raised:
                build_review_archive(vault, archive_path, profile="clean")

        message = str(raised.exception)
        self.assertIn("clean profile blocked", message)
        self.assertIn("tmp/release-evidence-dashboard.candidate.json", message)
        self.assertIn("tools/__pycache__/script.cpython-313.pyc", message)

    def test_review_archive_write_report_validates_schema_backed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            report = build_review_archive(vault, vault / "tmp" / "review.zip")
            invalid_report = dict(report)
            invalid_report.pop("policy", None)

            with self.assertRaises(ValueError) as raised:
                write_review_archive_report(vault, invalid_report, "ops/reports/review-archive-report.json")

        self.assertIn("review archive report schema validation failed", str(raised.exception))

    def test_build_release_archive_uses_manifest_inventory_and_excludes_local_only_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            (vault / "ops" / "__pycache__").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "__pycache__" / "junk.pyc").write_text("cache", encoding="utf-8")
            (vault / "ops" / "cached.pyc").write_text("cache", encoding="utf-8")
            (vault / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
            (vault / ".venv" / "bin" / "python").write_text("python", encoding="utf-8")
            (vault / ".venv-py312" / "bin").mkdir(parents=True, exist_ok=True)
            (vault / ".venv-py312" / "bin" / "python").write_text("python", encoding="utf-8")
            (vault / ".tox").mkdir(exist_ok=True)
            (vault / ".tox" / "state.json").write_text("{}", encoding="utf-8")
            (vault / "llm_wiki_vnext.egg-info").mkdir(exist_ok=True)
            (vault / "llm_wiki_vnext.egg-info" / "PKG-INFO").write_text("metadata", encoding="utf-8")
            (vault / "build").mkdir(exist_ok=True)
            (vault / "build" / "artifact.txt").write_text("build", encoding="utf-8")
            (vault / "dist").mkdir(exist_ok=True)
            (vault / "dist" / "artifact.whl").write_text("wheel", encoding="utf-8")
            (vault / ".obsidian").mkdir(exist_ok=True)
            (vault / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
            (vault / "ops" / "reports").mkdir(parents=True, exist_ok=True)
            (vault / "ops" / "reports" / "tmp.json").write_text("{}", encoding="utf-8")
            (vault / "runs" / "run-1").mkdir(parents=True, exist_ok=True)
            (vault / "runs" / "run-1" / "run-ledger.json").write_text("{}", encoding="utf-8")
            (vault / "external-reports").mkdir(exist_ok=True)
            (vault / "external-reports" / "report.pdf").write_text("pdf", encoding="utf-8")
            (vault / "external-reports" / "report.docx").write_text("docx", encoding="utf-8")
            (vault / "external-reports" / "review.md").write_text("review\n", encoding="utf-8")
            (vault / "tmp").mkdir(exist_ok=True)
            (vault / "tmp" / "kept.txt").write_text("kept", encoding="utf-8")

            archive_path = vault / "tmp" / "release.zip"
            source_manifest = build_release_archive(vault, archive_path)

            with zipfile.ZipFile(archive_path) as zf:
                names = sorted(zf.namelist())
                self_description = json.loads(
                    zf.read(f"LLMwiki/{ARCHIVE_SELF_DESCRIPTION_PATH}").decode("utf-8")
                )

            self.assertIn("LLMwiki/README.md", names)
            self.assertIn(f"LLMwiki/{ARCHIVE_SELF_DESCRIPTION_PATH}", names)
            self.assertNotIn("LLMwiki/ops/__pycache__/junk.pyc", names)
            self.assertNotIn("LLMwiki/ops/cached.pyc", names)
            self.assertNotIn("LLMwiki/.venv/bin/python", names)
            self.assertNotIn("LLMwiki/.venv-py312/bin/python", names)
            self.assertNotIn("LLMwiki/.tox/state.json", names)
            self.assertNotIn("LLMwiki/llm_wiki_vnext.egg-info/PKG-INFO", names)
            self.assertNotIn("LLMwiki/build/artifact.txt", names)
            self.assertNotIn("LLMwiki/dist/artifact.whl", names)
            self.assertNotIn("LLMwiki/.obsidian/workspace.json", names)
            self.assertNotIn("LLMwiki/ops/reports/tmp.json", names)
            self.assertNotIn("LLMwiki/runs/run-1/run-ledger.json", names)
            self.assertNotIn("LLMwiki/external-reports/report.pdf", names)
            self.assertNotIn("LLMwiki/external-reports/report.docx", names)
            self.assertNotIn("LLMwiki/external-reports/review.md", names)
            self.assertNotIn("LLMwiki/tmp/kept.txt", names)
            self.assertTrue(any(entry["path"] == "README.md" for entry in source_manifest["files"]))
            self.assertFalse(any(entry["path"].startswith("external-reports/") for entry in source_manifest["files"]))
            self.assertFalse(any(entry["path"].startswith("llm_wiki_vnext.egg-info/") for entry in source_manifest["files"]))
            self.assertFalse(any(entry["path"].startswith("build/") for entry in source_manifest["files"]))
            self.assertFalse(any(entry["path"].startswith("dist/") for entry in source_manifest["files"]))
            self.assertFalse(any(entry["path"].startswith(".venv-") for entry in source_manifest["files"]))
            self.assertTrue(any(entry["path"] == ARCHIVE_SELF_DESCRIPTION_PATH for entry in source_manifest["files"]))
            self.assertEqual(source_manifest["archive_self_description"]["path"], ARCHIVE_SELF_DESCRIPTION_PATH)
            self.assertEqual(self_description["profile"], FULL_PROFILE)
            self.assertFalse(self_description["surfaces"]["tmp_included"])
            self.assertFalse(self_description["surfaces"]["external_reports_included"])
            self.assertEqual(
                self_description["evidence_linkage"]["embedded_evidence_policy"],
                "digest_link_only",
            )
            self.assertEqual(
                self_description["evidence_linkage"]["linkage_phase"],
                "pre_seal_package_build_snapshot",
            )
            self.assertEqual(
                self_description["evidence_linkage"]["post_seal_authority"],
                "build/release/release-run-manifest.json",
            )
            linked_paths = {
                item["path"]
                for item in self_description["evidence_linkage"]["linked_artifacts"]
            }
            self.assertIn("build/release/release-run-manifest.json", linked_paths)
            self.assertIn("build/release/release-closeout-batch-manifest.json", linked_paths)
            self.assertIn("build/release/release-evidence-closeout-self-check.json", linked_paths)
            self.assertIn("build/release/operator-release-summary.json", linked_paths)
            self.assertIn("ops/reports/learning-claim-evidence-bundle.json", linked_paths)
            self.assertIn("ops/reports/learning-confirmed-evidence-cohort.json", linked_paths)
            self.assertIn("ops/reports/learning-delta-scoreboard.json", linked_paths)
            self.assertEqual(
                source_manifest["archive_self_description"]["evidence_linkage_phase"],
                "pre_seal_package_build_snapshot",
            )
            self.assertIn(".venv-", source_manifest["exclusion_policy"]["excluded_prefixes"])
            self.assertIn(".pyc", source_manifest["exclusion_policy"]["excluded_suffixes"])
            self.assertIn(".tox", source_manifest["exclusion_policy"]["excluded_dev_hidden_dirs"])
            self.assertIn("__pycache__", source_manifest["exclusion_policy"]["excluded_cache_dirs"])

    def test_build_release_archive_writes_temp_then_atomic_replaces_final_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            archive_path = vault / "tmp" / "release.zip"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text("old-bytes", encoding="utf-8")

            source_manifest = build_release_archive(vault, archive_path)

            self.assertTrue(archive_path.exists())
            self.assertNotEqual(archive_path.read_bytes(), b"old-bytes")
            with zipfile.ZipFile(archive_path) as zf:
                self.assertIsNone(zf.testzip())
                self.assertIn(f"LLMwiki/{ARCHIVE_SELF_DESCRIPTION_PATH}", zf.namelist())
            self.assertTrue(any(entry["path"] == ARCHIVE_SELF_DESCRIPTION_PATH for entry in source_manifest["files"]))
            self.assertEqual(list(archive_path.parent.glob(".release.zip.*.tmp")), [])
            self.assertEqual(list(archive_path.parent.glob(".release.zip.*.quarantine")), [])

    def test_build_release_archive_quarantines_temp_zip_when_verification_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            archive_path = vault / "tmp" / "release.zip"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text("old-bytes", encoding="utf-8")

            with mock.patch(
                "ops.scripts.release_smoke._verify_release_archive",
                side_effect=ValueError("bad archive"),
            ):
                with self.assertRaises(ReleaseArchiveBuildError) as raised:
                    build_release_archive(vault, archive_path)

            archive_write = raised.exception.archive_write
            self.assertEqual(archive_path.read_text(encoding="utf-8"), "old-bytes")
            self.assertEqual(archive_write["status"], "fail")
            self.assertEqual(archive_write["phase"], "verify_temp_archive")
            self.assertFalse(archive_write["archive_replaced"])
            self.assertIn("ValueError: bad archive", archive_write["error"])
            self.assertTrue(archive_write["quarantine_path"])
            self.assertTrue((vault / archive_write["quarantine_path"]).exists())
            self.assertEqual(list(archive_path.parent.glob(".release.zip.*.tmp")), [])

    def test_build_release_archive_rejects_replayed_self_description_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            (vault / ARCHIVE_SELF_DESCRIPTION_PATH).write_text(
                json.dumps({"artifact_kind": "release_archive_self_description"}),
                encoding="utf-8",
            )
            archive_path = vault / "tmp" / "release.zip"

            with self.assertRaises(ReleaseArchiveBuildError) as raised:
                build_release_archive(vault, archive_path)

            archive_write = raised.exception.archive_write
            self.assertEqual(archive_write["phase"], "preflight_self_description_replay")
            self.assertIn(
                "release-archive-self-description.json already exists in source tree",
                archive_write["error"],
            )
            self.assertFalse(archive_path.exists())
            self.assertEqual(archive_write["quarantine_path"], "")

    def test_verify_release_archive_rejects_duplicate_self_description_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "duplicate-self-description.zip"
            payload = json.dumps({"artifact_kind": "release_archive_self_description"})
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(f"LLMwiki/{ARCHIVE_SELF_DESCRIPTION_PATH}", payload)
                with self.assertWarns(UserWarning):
                    archive.writestr(f"LLMwiki/{ARCHIVE_SELF_DESCRIPTION_PATH}", payload)

            with self.assertRaises(ValueError) as raised:
                _verify_release_archive(archive_path, "LLMwiki")

            self.assertIn(
                "release archive self-description member count must be exactly 1",
                str(raised.exception),
            )

    def test_release_output_parent_preflight_reports_unwritable_parent_before_archive_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            blocker = vault / "not-a-directory"
            blocker.write_text("file", encoding="utf-8")

            preflight = output_parent_preflight(vault, {"archive": blocker / "release.zip"})

            self.assertEqual(preflight["status"], "fail")
            self.assertEqual(preflight["checks"][0]["name"], "archive")
            with self.assertRaises(ValueError) as raised:
                ensure_output_parent_preflight(vault, {"archive": blocker / "release.zip"})
            self.assertIn("archive parent is not writable", str(raised.exception))

    def test_main_writes_partial_report_when_output_parent_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            blocker = vault / "not-a-directory"
            blocker.write_text("file", encoding="utf-8")
            report_destination = vault / "ops" / "reports" / "release-smoke-report.json"
            stdout = io.StringIO()

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.parse_args",
                        return_value=SimpleNamespace(
                            vault=str(vault),
                            python_bin="python-bin",
                            profile="full",
                            archive_out="not-a-directory/release.zip",
                            out="ops/reports/release-smoke-report.json",
                            reuse_if_current=False,
                            reuse_from=None,
                        ),
                    )
                )
                archive_builder = stack.enter_context(
                    mock.patch("ops.scripts.release_smoke.build_release_archive")
                )
                stack.enter_context(contextlib.redirect_stdout(stdout))

                with self.assertRaises(SystemExit) as raised:
                    main()

            report = json.loads(report_destination.read_text(encoding="utf-8"))
            rendered = stdout.getvalue()

        self.assertEqual(raised.exception.code, 1)
        archive_builder.assert_not_called()
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["partial_report"]["phase"], "output_parent_preflight")
        self.assertIn("release smoke output preflight failed", report["partial_report"]["message"])
        self.assertIn("archive parent is not writable", report["partial_report"]["error"])
        self.assertEqual(report["output_parent_preflight"]["status"], "fail")
        checks_by_name = {item["name"]: item for item in report["output_parent_preflight"]["checks"]}
        self.assertEqual(checks_by_name["archive"]["status"], "fail")
        self.assertEqual(checks_by_name["report"]["status"], "pass")
        self.assertIn('"output_parent_preflight"', rendered)
        self.assertIn("written_to=ops/reports/release-smoke-report.json", rendered)

    def test_compare_manifests_detects_unpack_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            (vault / "README.md").write_text("readme\n", encoding="utf-8")

            archive_path = vault / "release.zip"
            source_manifest = build_release_archive(vault, archive_path)

            extract_root = Path(temp_dir) / "unpacked"
            extracted_vault = extract_release_archive(archive_path, extract_root)
            (extracted_vault / "README.md").write_text("changed\n", encoding="utf-8")

            extracted_manifest = build_manifest(
                extracted_vault,
                extracted_vault / "ops" / "manifest.json",
            )
            comparison = compare_manifests(source_manifest, extracted_manifest)

            self.assertFalse(comparison["pass"])
            self.assertEqual(comparison["missing_paths"], [])
            self.assertEqual(comparison["unexpected_paths"], [])
            self.assertEqual(comparison["size_mismatches"][0]["path"], "README.md")
            self.assertEqual(comparison["sha_mismatches"][0]["path"], "README.md")

    def test_build_release_archive_normalizes_zip_metadata_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "README.md").write_text("readme\n", encoding="utf-8")

            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            policy_path.write_text(
                policy_path.read_text(encoding="utf-8").replace(
                    "  zip_normalization:\n    timestamp_utc: \"1980-01-01T00:00:00Z\"\n    file_mode_octal: \"0644\"\n",
                    "  zip_normalization:\n    timestamp_utc: \"2001-02-03T04:05:06Z\"\n    file_mode_octal: \"0600\"\n",
                    1,
                ),
                encoding="utf-8",
            )

            archive_path = vault / "tmp" / "release-normalized.zip"
            build_release_archive(vault, archive_path)

            with zipfile.ZipFile(archive_path) as zf:
                info = zf.getinfo("LLMwiki/README.md")

            self.assertEqual(info.date_time, (2001, 2, 3, 4, 5, 6))
            self.assertEqual(info.create_system, 3)
            self.assertEqual(info.external_attr >> 16, 0o600)

    def test_archive_budget_normalizes_windows_separator_zip_member_paths(self) -> None:
        budget = _archive_budget(
            "LLMwiki",
            {"files": [{"path": "ops\\scripts\\tool.py", "sha256": "a", "size_bytes": 1}]},
        )

        self.assertTrue(budget["pass"])
        self.assertEqual(budget["top_offenders"][0]["archive_path"], "LLMwiki/ops/scripts/tool.py")
        self.assertEqual(budget["platform_path_diagnostics"]["status"], "pass")

    def test_build_smoke_commands_match_release_gate_profiles(self) -> None:
        vault = Path("/tmp/release-vault")
        commands = build_smoke_commands(vault, "/usr/bin/python3", profile=FULL_PROFILE)
        fast_commands = build_smoke_commands(vault, "/usr/bin/python3", profile=FAST_PROFILE)

        self.assertEqual(
            [name for name, _command in commands],
            [
                "raw_registry_preflight",
                "wiki_lint",
                "wiki_eval",
                "wiki_stage2_eval",
                "planning_gate_validate",
            ],
        )
        self.assertEqual(
            commands[0][1],
            [
                "/usr/bin/python3",
                "-m",
                "ops.scripts.registry.raw_registry_preflight",
                "--vault",
                ".",
            ],
        )
        self.assertEqual(
            commands[1][1],
            [
                "/usr/bin/python3",
                "-m",
                "ops.scripts.eval.wiki_lint",
                "--vault",
                ".",
                "--release-archive-profile",
            ],
        )
        self.assertEqual(
            commands[2][1],
            [
                "/usr/bin/python3",
                "-m",
                "ops.scripts.eval.wiki_eval",
                "--vault",
                ".",
                "--release-archive-profile",
                "--require-max-score",
            ],
        )
        self.assertEqual(
            commands[-1][1],
            [
                "/usr/bin/python3",
                "-m",
                "ops.scripts.mechanism.planning_gate_validate",
                "--vault",
                ".",
            ],
        )
        self.assertEqual(fast_commands, [])

    def test_parse_args_defaults_to_full_profile_and_accepts_explicit_profiles(self) -> None:
        self.assertEqual(parse_args([]).profile, FULL_PROFILE)
        self.assertEqual(parse_args(["--profile", FULL_PROFILE]).profile, FULL_PROFILE)
        self.assertEqual(parse_args(["--profile", FAST_PROFILE]).profile, FAST_PROFILE)

    def test_default_report_out_keeps_full_canonical_and_fast_separate(self) -> None:
        self.assertEqual(default_report_out(FULL_PROFILE), "ops/reports/release-smoke-report.json")
        self.assertEqual(default_report_out(FAST_PROFILE), FAST_DEFAULT_REPORT_OUT)

    def test_release_smoke_reuse_diagnostics_accepts_only_current_passing_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            (vault / "README.md").write_text("readme\n", encoding="utf-8")
            archive_path = vault / "tmp" / "release.zip"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )
            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            report = build_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                [],
                resolved_policy_path=policy_path,
                policy_version=4,
                profile=FULL_PROFILE,
                context=context,
            )
            destination = write_report(vault, report, None)

            diagnostics = release_smoke_reuse_diagnostics(
                vault,
                destination,
                profile=FULL_PROFILE,
                resolved_policy_path=policy_path,
                context=context,
            )
            self.assertTrue(diagnostics["reusable"])
            self.assertEqual(diagnostics["reason"], "current_passing_release_smoke_report")

            (vault / "README.md").write_text("changed\n", encoding="utf-8")
            stale_diagnostics = release_smoke_reuse_diagnostics(
                vault,
                destination,
                profile=FULL_PROFILE,
                resolved_policy_path=policy_path,
                context=context,
            )

        self.assertFalse(stale_diagnostics["reusable"])
        self.assertIn("source_tree_fingerprint", stale_diagnostics["reason"])

    def test_run_smoke_commands_captures_returncodes_and_tails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            outputs = {
                "raw_registry_preflight": ("ok\n", "", 0, False, 5400, "completed"),
                "wiki_lint": ("\n".join(f"line-{i}" for i in range(60)), "warn\n", 0, False, 5400, "completed"),
                "wiki_eval": ("", "bad\n", 1, False, 5400, "completed"),
                "wiki_stage2_eval": ("stage2\n", "", 0, False, 5400, "completed"),
                "planning_gate_validate": ("plan\n", "", 1, True, 5400, "timeout"),
            }

            def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
                command_name = command[2].rsplit(".", 1)[-1]
                stdout, stderr, returncode, timed_out, timeout_seconds, termination_reason = outputs[command_name]
                return SimpleNamespace(
                    stdout=stdout,
                    stderr=stderr,
                    returncode=returncode,
                    timed_out=timed_out,
                    timeout_seconds=timeout_seconds,
                    termination_reason=termination_reason,
                )

            progress_lengths = []

            with mock.patch("ops.scripts.release_smoke.run_with_timeout", side_effect=fake_run):
                results = run_smoke_commands(
                    vault,
                    "python-bin",
                    profile=FULL_PROFILE,
                    on_result=lambda partial_results: progress_lengths.append(len(partial_results)),
                )

        self.assertEqual([item["name"] for item in results], list(outputs))
        self.assertEqual(progress_lengths, [1, 2, 3, 4, 5])
        self.assertEqual(results[0]["command"], "python -m ops.scripts.registry.raw_registry_preflight --vault .")
        self.assertEqual(
            results[1]["command"],
            "python -m ops.scripts.eval.wiki_lint --vault . --release-archive-profile",
        )
        lint_result = next(item for item in results if item["name"] == "wiki_lint")
        self.assertEqual(lint_result["returncode"], 0)
        self.assertFalse(lint_result["timed_out"])
        self.assertEqual(lint_result["timeout_seconds"], 5400)
        self.assertEqual(lint_result["termination_reason"], "completed")
        self.assertGreaterEqual(lint_result["duration_ms"], 0)
        self.assertTrue(lint_result["stdout_tail"].startswith("line-20"))
        self.assertEqual(lint_result["stderr_tail"], "warn\n")
        eval_result = next(item for item in results if item["name"] == "wiki_eval")
        self.assertFalse(eval_result["pass"])
        self.assertEqual(eval_result["returncode"], 1)
        timeout_result = next(item for item in results if item["name"] == "planning_gate_validate")
        self.assertTrue(timeout_result["timed_out"])
        self.assertEqual(timeout_result["termination_reason"], "timeout")

    def test_build_report_uses_runtime_context_and_sanitizes_ephemeral_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            ephemeral_root = Path(temp_dir) / "ephemeral"
            archive_path = ephemeral_root / "release.zip"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = ephemeral_root / "unpacked" / "vault"
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            report = build_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                [{
                    "name": "wiki_lint",
                    "command": "lint",
                    "pass": True,
                    "returncode": 0,
                    "timed_out": False,
                    "timeout_seconds": 5400,
                    "termination_reason": "completed",
                    "duration_ms": 100,
                    "stdout_tail": "",
                    "stderr_tail": "",
                }],
                resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_version=4,
                context=context,
                ephemeral_root=ephemeral_root,
            )

        self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
        self.assertEqual(report["profile"], "full")
        self.assertEqual(report["artifact_kind"], "release_smoke_report")
        self.assertEqual(report["source_command"], "python -m ops.scripts.release.release_smoke --vault . --profile full")
        self.assertEqual(report["archive_path"], f"{EPHEMERAL_REPORT_PREFIX}/release.zip")
        self.assertEqual(report["archive_file"]["path"], f"{EPHEMERAL_REPORT_PREFIX}/release.zip")
        self.assertTrue(report["archive_file"]["exists"])
        self.assertEqual(len(report["archive_file"]["sha256"]), 64)
        self.assertEqual(report["archive_class"]["name"], "release_smoke_zip")
        self.assertEqual(report["archive_class"]["root_prefix"], "LLMwiki")
        self.assertIn(".pyc", report["archive_class"]["manifest_exclusion_policy"]["excluded_suffixes"])
        self.assertTrue(report["archive_budget"]["pass"])
        self.assertEqual(report["archive_reproducibility"]["status"], "not_run")
        self.assertEqual(report["archive_budget"]["zip_path_byte_budget"]["status"], "pass")
        self.assertEqual(report["archive_budget"]["top_offenders"][0]["path"], "README.md")
        self.assertEqual(report["extracted_vault"], f"{EPHEMERAL_REPORT_PREFIX}/unpacked/vault")
        self.assertEqual(report["policy"], {"path": "ops/policies/wiki-maintainer-policy.yaml", "version": 4})
        self.assertEqual(report["currentness"], {"status": "current", "checked_at": "2026-04-15T03:45:00Z"})
        self.assertEqual(report["status"], "pass")

    def test_build_report_supports_fast_profile_without_runtime_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            archive_path = vault / "release.zip"
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            report = build_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                [],
                resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_version=4,
                profile=FAST_PROFILE,
                context=context,
            )

        self.assertEqual(report["profile"], FAST_PROFILE)
        self.assertEqual(report["source_command"], "python -m ops.scripts.release.release_smoke --vault . --profile fast")
        self.assertEqual(report["commands"], [])
        self.assertEqual(report["status"], "pass")

    def test_build_report_fails_when_archive_reproducibility_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            archive_path = vault / "release.zip"
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            report = build_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                [],
                resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_version=4,
                context=context,
                archive_reproducibility=sample_archive_reproducibility(status="fail"),
            )

        self.assertEqual(report["archive_reproducibility"]["status"], "fail")
        self.assertEqual(report["status"], "fail")

    def test_build_partial_report_is_schema_valid_failure_with_phase_and_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            (vault / "ops" / "schemas").mkdir(parents=True)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            ephemeral_root = Path(temp_dir) / "ephemeral"
            archive_path = ephemeral_root / "release.zip"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = ephemeral_root / "unpacked" / "vault"
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            report = build_partial_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]},
                None,
                [{
                    "name": "wiki_lint",
                    "command": "lint",
                    "pass": False,
                    "returncode": 1,
                    "timed_out": False,
                    "timeout_seconds": 5400,
                    "termination_reason": "completed",
                    "duration_ms": 100,
                    "stdout_tail": "tail",
                    "stderr_tail": "err",
                }],
                resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_version=4,
                phase="smoke_commands",
                message="completed 1 of 5 smoke commands",
                error="",
                context=context,
                started_at_monotonic=None,
                ephemeral_root=ephemeral_root,
                archive_write={
                    "status": "fail",
                    "phase": "verify_temp_archive",
                    "archive_path": "tmp/release.zip",
                    "temp_path": "tmp/.release.zip.1.tmp",
                    "quarantine_path": "tmp/.release.zip.2.quarantine",
                    "archive_replaced": False,
                    "error": "ValueError: bad archive",
                },
            )

            destination = write_report(vault, report, "reports/release-smoke-partial.json")
            written_report = json.loads(destination.read_text(encoding="utf-8"))

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["profile"], "full")
        self.assertEqual(report["archive_path"], f"{EPHEMERAL_REPORT_PREFIX}/release.zip")
        self.assertEqual(report["manifest_comparison"]["expected_file_count"], 1)
        self.assertEqual(report["manifest_comparison"]["extracted_file_count"], 0)
        self.assertEqual(report["partial_report"]["phase"], "smoke_commands")
        self.assertEqual(report["partial_report"]["completed_command_count"], 1)
        self.assertEqual(report["partial_report"]["elapsed_ms"], 0)
        self.assertEqual(report["partial_report"]["archive_write"]["phase"], "verify_temp_archive")
        self.assertFalse(report["partial_report"]["archive_write"]["archive_replaced"])
        self.assertEqual(written_report, report)

    def test_build_report_fails_on_archive_filename_budget_offenders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            archive_path = vault / "release.zip"
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            long_component = "a" * 260
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            report = build_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": f"{long_component}/README.md", "sha256": "a", "size_bytes": 1}]},
                {"files": [{"path": f"{long_component}/README.md", "sha256": "a", "size_bytes": 1}]},
                [],
                resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_version=4,
                context=context,
            )

        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["archive_budget"]["pass"])
        self.assertEqual(report["archive_budget"]["zip_component_byte_budget"]["status"], "fail")
        self.assertEqual(report["archive_budget"]["posix_escape_expanded_filename_budget"]["status"], "fail")
        self.assertEqual(report["archive_budget"]["blocking_budget_fail_count"], 1)
        self.assertEqual(report["archive_budget"]["platform_warning_count"], 1)
        self.assertEqual(report["archive_budget"]["platform_path_diagnostics"]["status"], "warn")
        self.assertEqual(report["archive_budget"]["top_offenders"][0]["path"], f"{long_component}/README.md")

    def test_build_report_uses_infozip_c_locale_escape_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            archive_path = vault / "release.zip"
            archive_path.write_text("zip-bytes", encoding="utf-8")
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            offender = "속보트럼프 “미 대표단, 20일 협상 위해 파키스탄 간다···합의 안하면 모든 발전소와 다리 파괴”.md"
            context = RuntimeContext(
                display_timezone=dt.timezone.utc,
                clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
            )

            report = build_report(
                vault,
                archive_path,
                extracted_vault,
                {"files": [{"path": f"raw/web-snapshots/{offender}", "sha256": "a", "size_bytes": 1}]},
                {"files": [{"path": f"raw/web-snapshots/{offender}", "sha256": "a", "size_bytes": 1}]},
                [],
                resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                policy_version=4,
                context=context,
            )

        top_offender = report["archive_budget"]["top_offenders"][0]
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["archive_budget"]["pass"])
        self.assertEqual(report["archive_budget"]["blocking_budget_fail_count"], 0)
        self.assertEqual(report["archive_budget"]["platform_warning_count"], 1)
        self.assertEqual(report["archive_budget"]["platform_path_diagnostics"]["status"], "warn")
        self.assertEqual(top_offender["path"], f"raw/web-snapshots/{offender}")
        self.assertLessEqual(top_offender["python_unicode_escape_filename_bytes"], 255)
        self.assertGreater(top_offender["infozip_c_locale_escape_filename_bytes"], 255)
        self.assertEqual(
            top_offender["posix_escape_expanded_filename_bytes"],
            top_offender["infozip_c_locale_escape_filename_bytes"],
        )

    def test_write_report_validates_and_writes_schema_backed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            (vault / "ops" / "schemas").mkdir(parents=True)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            report = {
                "$schema": "ops/schemas/release-smoke-report.schema.json",
                "vault": ".",
                "generated_at": "2026-04-15T00:00:00Z",
                "artifact_kind": "release_smoke_report",
                "producer": "ops.scripts.release_smoke",
                "source_command": "python -m ops.scripts.release.release_smoke --vault .",
                "source_revision": "unknown",
                "source_tree_fingerprint": "sample-release-smoke-fingerprint",
                "input_fingerprints": {
                    "policy": "sample-policy",
                    "schema": "sample-schema",
                    "artifact_envelope_schema": "sample-envelope-schema"
                },
                "schema_version": 1,
                "artifact_status": "current",
                "retention_policy": "canonical_report",
                "encoding": "utf-8",
                "currentness": {
                    "status": "current",
                    "checked_at": "2026-04-15T00:00:00Z"
                },
                "policy": {
                    "path": "ops/policies/wiki-maintainer-policy.yaml",
                    "version": 4
                },
                "profile": "full",
                "status": "pass",
                "archive_path": f"{EPHEMERAL_REPORT_PREFIX}/release.zip",
                "archive_file": {
                    "path": f"{EPHEMERAL_REPORT_PREFIX}/release.zip",
                    "exists": True,
                    "size_bytes": 123,
                    "sha256": "a" * 64,
                },
                "archive_class": sample_archive_class(),
                "archive_budget": sample_archive_budget(),
                "archive_reproducibility": sample_archive_reproducibility(),
                "extracted_vault": f"{EPHEMERAL_REPORT_PREFIX}/unpacked/vault",
                "packed_file_count": 1,
                "manifest_comparison": {
                    "pass": True,
                    "expected_file_count": 1,
                    "extracted_file_count": 1,
                    "missing_paths": [],
                    "unexpected_paths": [],
                    "sha_mismatches": [],
                    "size_mismatches": [],
                },
                "commands": [
                    {
                        "name": "wiki_lint",
                        "command": "lint",
                        "pass": True,
                        "returncode": 0,
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                        "duration_ms": 100,
                        "stdout_tail": "",
                        "stderr_tail": "",
                    }
                ],
            }

            destination = write_report(vault, report, "reports/release-smoke-report.json")

            self.assertEqual(destination, (vault / "reports" / "release-smoke-report.json").resolve())
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)

    def test_write_report_uses_fast_profile_default_output_when_out_path_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            (vault / "ops" / "schemas").mkdir(parents=True)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            report = {
                "$schema": "ops/schemas/release-smoke-report.schema.json",
                "vault": ".",
                "generated_at": "2026-04-15T00:00:00Z",
                "artifact_kind": "release_smoke_report",
                "producer": "ops.scripts.release_smoke",
                "source_command": "python -m ops.scripts.release.release_smoke --vault . --profile fast",
                "source_revision": "unknown",
                "source_tree_fingerprint": "sample-release-smoke-fingerprint",
                "input_fingerprints": {
                    "policy": "sample-policy",
                    "schema": "sample-schema",
                    "artifact_envelope_schema": "sample-envelope-schema"
                },
                "schema_version": 1,
                "artifact_status": "current",
                "retention_policy": "canonical_report",
                "encoding": "utf-8",
                "currentness": {
                    "status": "current",
                    "checked_at": "2026-04-15T00:00:00Z"
                },
                "policy": {
                    "path": "ops/policies/wiki-maintainer-policy.yaml",
                    "version": 4
                },
                "profile": FAST_PROFILE,
                "status": "pass",
                "archive_path": f"{EPHEMERAL_REPORT_PREFIX}/release.zip",
                "archive_file": {
                    "path": f"{EPHEMERAL_REPORT_PREFIX}/release.zip",
                    "exists": True,
                    "size_bytes": 123,
                    "sha256": "a" * 64,
                },
                "archive_class": sample_archive_class(),
                "archive_budget": sample_archive_budget(),
                "archive_reproducibility": sample_archive_reproducibility(),
                "extracted_vault": f"{EPHEMERAL_REPORT_PREFIX}/unpacked/vault",
                "packed_file_count": 1,
                "manifest_comparison": {
                    "pass": True,
                    "expected_file_count": 1,
                    "extracted_file_count": 1,
                    "missing_paths": [],
                    "unexpected_paths": [],
                    "sha_mismatches": [],
                    "size_mismatches": [],
                },
                "commands": [],
            }

            destination = write_report(vault, report, None)

            self.assertEqual(destination, (vault / FAST_DEFAULT_REPORT_OUT).resolve())
            self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)

    def test_main_exits_with_report_status_and_prints_written_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            extracted_vault.mkdir(parents=True)
            report_destination = vault / "ops" / "reports" / "release-smoke-report.json"
            report = {
                "$schema": "ops/schemas/release-smoke-report.schema.json",
                "vault": ".",
                "generated_at": "2026-04-15T00:00:00Z",
                "artifact_kind": "release_smoke_report",
                "producer": "ops.scripts.release_smoke",
                "source_command": "python -m ops.scripts.release.release_smoke --vault .",
                "source_revision": "unknown",
                "source_tree_fingerprint": "sample-release-smoke-fingerprint",
                "input_fingerprints": {
                    "policy": "sample-policy",
                    "schema": "sample-schema",
                    "artifact_envelope_schema": "sample-envelope-schema"
                },
                "schema_version": 1,
                "artifact_status": "current",
                "retention_policy": "canonical_report",
                "encoding": "utf-8",
                "currentness": {
                    "status": "current",
                    "checked_at": "2026-04-15T00:00:00Z"
                },
                "policy": {
                    "path": "ops/policies/wiki-maintainer-policy.yaml",
                    "version": 4
                },
                "profile": "full",
                "status": "fail",
                "archive_path": f"{EPHEMERAL_REPORT_PREFIX}/archive.zip",
                "archive_file": {
                    "path": f"{EPHEMERAL_REPORT_PREFIX}/archive.zip",
                    "exists": True,
                    "size_bytes": 123,
                    "sha256": "b" * 64,
                },
                "archive_class": sample_archive_class(),
                "archive_budget": sample_archive_budget(),
                "archive_reproducibility": sample_archive_reproducibility(),
                "extracted_vault": f"{EPHEMERAL_REPORT_PREFIX}/unpacked/vault",
                "packed_file_count": 1,
                "manifest_comparison": {
                    "pass": True,
                    "expected_file_count": 1,
                    "extracted_file_count": 1,
                    "missing_paths": [],
                    "unexpected_paths": [],
                    "sha_mismatches": [],
                    "size_mismatches": [],
                },
                "commands": [
                    {
                        "name": "wiki_stage2_eval",
                        "command": "stage2",
                        "pass": False,
                        "returncode": 1,
                        "timed_out": False,
                        "timeout_seconds": 5400,
                        "termination_reason": "completed",
                        "duration_ms": 100,
                        "stdout_tail": "fail",
                        "stderr_tail": "",
                    }
                ],
            }
            stdout = io.StringIO()

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.parse_args",
                        return_value=SimpleNamespace(
                            vault=str(vault),
                            python_bin="python-bin",
                            profile="full",
                            archive_out=None,
                            out="ops/reports/release-smoke-report.json",
                            reuse_if_current=False,
                            reuse_from=None,
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.load_policy",
                        return_value=(
                            {
                                "version": 4,
                                "runtime_defaults": {
                                    "display_timezone": {
                                        "label": "UTC",
                                        "utc_offset": "+00:00",
                                    }
                                },
                            },
                            vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
                        ),
                    )
                )
                stack.enter_context(mock.patch("ops.scripts.release_smoke.build_release_archive", return_value={"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]}))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.extract_release_archive", return_value=extracted_vault))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.build_manifest", return_value={"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]}))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.run_smoke_commands", return_value=report["commands"]))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.build_report", return_value=report))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.write_report", return_value=report_destination))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.sha256_file", side_effect=["a" * 64, "a" * 64]))
                stack.enter_context(contextlib.redirect_stdout(stdout))

                with self.assertRaises(SystemExit) as raised:
                    main()

        self.assertEqual(raised.exception.code, 1)
        rendered = stdout.getvalue()
        self.assertIn('"status": "fail"', rendered)
        self.assertIn("written_to=ops/reports/release-smoke-report.json", rendered)

    def test_main_builds_archive_twice_and_records_reproducibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            extracted_vault = Path(temp_dir) / "unpacked" / "vault"
            extracted_vault.mkdir(parents=True)
            report_destination = vault / "ops" / "reports" / "release-smoke-report.json"
            source_manifest = {"files": [{"path": "README.md", "sha256": "a", "size_bytes": 1}]}
            stdout = io.StringIO()

            def fake_build_release_archive(
                _vault: Path,
                archive_path: Path,
                **_kwargs: object,
            ) -> dict:
                archive_path.parent.mkdir(parents=True, exist_ok=True)
                archive_path.write_bytes(b"stable release zip bytes")
                return source_manifest

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.parse_args",
                        return_value=SimpleNamespace(
                            vault=str(vault),
                            python_bin="python-bin",
                            profile="full",
                            archive_out=None,
                            out="ops/reports/release-smoke-report.json",
                            reuse_if_current=False,
                            reuse_from=None,
                        ),
                    )
                )
                archive_builder = stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.build_release_archive",
                        side_effect=fake_build_release_archive,
                    )
                )
                stack.enter_context(mock.patch("ops.scripts.release_smoke.extract_release_archive", return_value=extracted_vault))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.build_manifest", return_value=source_manifest))
                stack.enter_context(mock.patch("ops.scripts.release_smoke.run_smoke_commands", return_value=[]))
                stack.enter_context(contextlib.redirect_stdout(stdout))

                with self.assertRaises(SystemExit) as raised:
                    main()

            report = json.loads(report_destination.read_text(encoding="utf-8"))

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(archive_builder.call_count, 2)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["archive_reproducibility"]["status"], "pass")
        self.assertEqual(report["archive_reproducibility"]["run_count"], 2)
        self.assertTrue(report["archive_reproducibility"]["same_archive_sha256"])
        self.assertTrue(report["archive_reproducibility"]["same_source_manifest_digest"])
        self.assertIn("archive_reproducibility=pass", report["archive_reproducibility"]["summary"])
        self.assertIn('"archive_reproducibility"', stdout.getvalue())

    def test_main_writes_partial_report_when_archive_phase_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            report_destination = vault / "ops" / "reports" / "release-smoke-report.json"
            stdout = io.StringIO()

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.parse_args",
                        return_value=SimpleNamespace(
                            vault=str(vault),
                            python_bin="python-bin",
                            profile="full",
                            archive_out=None,
                            out="ops/reports/release-smoke-report.json",
                            reuse_if_current=False,
                            reuse_from=None,
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.build_release_archive",
                        side_effect=RuntimeError("archive boom"),
                    )
                )
                stack.enter_context(contextlib.redirect_stdout(stdout))

                with self.assertRaises(RuntimeError):
                    main()
            report = json.loads(report_destination.read_text(encoding="utf-8"))
            rendered = stdout.getvalue()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["partial_report"]["phase"], "build_archive")
        self.assertEqual(report["partial_report"]["completed_command_count"], 0)
        self.assertIn("RuntimeError: archive boom", report["partial_report"]["error"])
        self.assertFalse(report["archive_file"]["exists"])
        self.assertIn('"partial_report"', rendered)
        self.assertIn("written_to=ops/reports/release-smoke-report.json", rendered)

    def test_main_partial_report_includes_archive_quarantine_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            report_destination = vault / "ops" / "reports" / "release-smoke-report.json"
            stdout = io.StringIO()
            archive_write = {
                "status": "fail",
                "phase": "verify_temp_archive",
                "archive_path": "tmp/vault-release-smoke.zip",
                "temp_path": "tmp/.vault-release-smoke.zip.1.tmp",
                "quarantine_path": "tmp/.vault-release-smoke.zip.2.quarantine",
                "archive_replaced": False,
                "error": "ValueError: bad archive",
            }

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.parse_args",
                        return_value=SimpleNamespace(
                            vault=str(vault),
                            python_bin="python-bin",
                            profile="full",
                            archive_out=None,
                            out="ops/reports/release-smoke-report.json",
                            reuse_if_current=False,
                            reuse_from=None,
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.build_release_archive",
                        side_effect=ReleaseArchiveBuildError(
                            "release archive build failed before atomic replace",
                            archive_write=archive_write,
                        ),
                    )
                )
                stack.enter_context(contextlib.redirect_stdout(stdout))

                with self.assertRaises(ReleaseArchiveBuildError):
                    main()
            report = json.loads(report_destination.read_text(encoding="utf-8"))
            rendered = stdout.getvalue()

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["partial_report"]["phase"], "build_archive")
        self.assertEqual(report["partial_report"]["archive_write"], archive_write)
        self.assertIn("quarantine_path", rendered)

    def test_main_writes_fast_profile_default_path_when_out_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            schema_source = Path("ops/schemas/release-smoke-report.schema.json").read_text(encoding="utf-8")
            (vault / "ops" / "schemas" / "release-smoke-report.schema.json").write_text(
                schema_source,
                encoding="utf-8",
            )
            report_destination = vault / FAST_DEFAULT_REPORT_OUT
            stdout = io.StringIO()

            with contextlib.ExitStack() as stack:
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.parse_args",
                        return_value=SimpleNamespace(
                            vault=str(vault),
                            python_bin="python-bin",
                            profile=FAST_PROFILE,
                            archive_out=None,
                            out=None,
                            reuse_if_current=False,
                            reuse_from=None,
                        ),
                    )
                )
                stack.enter_context(
                    mock.patch(
                        "ops.scripts.release_smoke.build_release_archive",
                        side_effect=RuntimeError("archive boom"),
                    )
                )
                stack.enter_context(contextlib.redirect_stdout(stdout))

                with self.assertRaises(RuntimeError):
                    main()
            report = json.loads(report_destination.read_text(encoding="utf-8"))
            rendered = stdout.getvalue()

        self.assertEqual(report["profile"], FAST_PROFILE)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["partial_report"]["phase"], "build_archive")
        self.assertIn("written_to=ops/reports/release-smoke-report-fast.json", rendered)


if __name__ == "__main__":
    unittest.main()
