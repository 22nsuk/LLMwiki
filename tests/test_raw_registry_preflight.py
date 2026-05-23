from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from ops.scripts.path_portability_runtime import infozip_c_locale_escape_path
from ops.scripts.policy_runtime import load_policy, report_path
from ops.scripts.raw_registry_runtime import (
    parse_raw_registry_pages,
    registry_entry_page_paths,
    registry_summary_page_path,
    write_raw_registry_export,
)
from ops.scripts.raw_registry_preflight import (
    ALIAS_POLICY_VERSION,
    PATH_ALIAS_RESOLUTION_MODE,
    build_reproducibility_report,
    load_stored_preflight_report,
    preflight,
    write_report,
    write_reproducibility_report,
)
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import (
    RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH,
    RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from tests.minimal_vault_runtime import (
    add_registry_entry_scalar_field,
    live_registry_shard_pages,
    seed_minimal_vault,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.timezone.utc,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.timezone.utc),
    )


class RawRegistryPreflightTest(unittest.TestCase):
    def test_preflight_passes_for_sharded_minimal_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            report = preflight(vault, context=fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(report["artifact_kind"], "raw_registry_preflight_report")
            self.assertEqual(report["$schema"], RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH)
            self.assertEqual(report["path_alias_resolution_mode"], PATH_ALIAS_RESOLUTION_MODE)
            self.assertEqual(report["alias_policy_version"], ALIAS_POLICY_VERSION)
            self.assertEqual(report["environment_fingerprint"]["algorithm"], "sha256-json-v1")
            self.assertRegex(report["environment_fingerprint"]["value"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                report["metric_semantics"]["path_alias_match_count"]["scope"],
                "entries_with_missing_canonical_storage_path",
            )
            self.assertIn("environment_fingerprint", report["input_fingerprints"])
            self.assertEqual(report["stats"]["entry_count"], 1)
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["warnings"], [])
            self.assertEqual(
                validate_with_schema(
                    report,
                    load_schema(vault / RAW_REGISTRY_PREFLIGHT_REPORT_SCHEMA_PATH),
                ),
                [],
            )

    def test_preflight_warns_for_unregistered_raw_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw" / "extra.pdf").write_text("x", encoding="utf-8")

            report = preflight(vault)

            self.assertEqual(report["status"], "warn")
            self.assertEqual(report["errors"], [])
            self.assertEqual(len(report["warnings"]), 1)
            self.assertEqual(report["warnings"][0]["type"], "unregistered_raw_file")

    def test_preflight_fails_for_raw_markdown_without_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw" / "snapshot.md").write_text(
                "# Snapshot: Demo\n- URL: https://example.com/demo\n",
                encoding="utf-8",
            )

            report = preflight(vault)
            error_types = {issue["type"] for issue in report["errors"]}

            self.assertEqual(report["status"], "fail")
            self.assertIn("raw_markdown_missing_frontmatter", error_types)

    def test_preflight_fails_for_posix_escape_expanded_raw_path_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            snapshot_dir = vault / "raw" / "web-snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            # 43 Hangul chars stay below common filesystem byte limits while
            # still exceeding the Info-ZIP C-locale escape-expanded budget.
            long_name = f"{'가' * 43}.md"
            (snapshot_dir / long_name).write_text(
                """---
title: "Long filename"
source: "https://example.com/long"
author:
published: "unknown"
created: 2026-04-21
description:
tags:
  - "clippings"
---
Body
""",
                encoding="utf-8",
            )

            report = preflight(vault)
            portability_error = next(
                item for item in report["errors"] if item["type"] == "raw_path_posix_portability_budget"
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(portability_error["detail"]["limit_bytes"], 255)
            self.assertGreater(portability_error["detail"]["posix_escape_expanded_component_bytes"], 255)
            self.assertEqual(
                portability_error["detail"]["recommended_action"],
                "rename_raw_web_snapshot_to_slug_hash_and_preserve_alias",
            )
            self.assertEqual(portability_error["detail"]["escape_mode"], "infozip_c_locale")

    def test_preflight_uses_infozip_c_locale_escape_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            snapshot_dir = vault / "raw" / "web-snapshots"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            offender = "속보트럼프 “미 대표단, 20일 협상 위해 파키스탄 간다···합의 안하면 모든 발전소와 다리 파괴”.md"
            (snapshot_dir / offender).write_text(
                """---
title: "Long filename"
source: "https://example.com/long"
author:
published: "unknown"
created: 2026-04-21
description:
tags:
  - "clippings"
---
Body
""",
                encoding="utf-8",
            )

            report = preflight(vault)
            portability_error = next(
                item for item in report["errors"] if item["type"] == "raw_path_posix_portability_budget"
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(portability_error["detail"]["escape_mode"], "infozip_c_locale")
            self.assertLessEqual(portability_error["detail"]["python_unicode_escape_component_bytes"], 255)
            self.assertGreater(portability_error["detail"]["infozip_c_locale_escape_component_bytes"], 255)

    def test_preflight_warns_for_blank_required_raw_markdown_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw" / "snapshot.md").write_text(
                """---
title: "Demo"
source: "https://example.com/demo"
published:
created:
---

Title: Demo

Body
""",
                encoding="utf-8",
            )

            report = preflight(vault)
            warning_types = {issue["type"] for issue in report["warnings"]}

            self.assertIn("raw_markdown_blank_published", warning_types)
            self.assertIn("raw_markdown_blank_created", warning_types)
            self.assertIn("raw_markdown_transport_noise", warning_types)

    def test_preflight_fails_when_shard_page_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "system" / "system-raw-registry" / "system.md").unlink()

            report = preflight(vault)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["errors"][0]["type"], "missing_raw_registry_shard_page")

    def test_release_archive_profile_skips_absent_corpus_registry_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            for surface in ("raw", "wiki", "system"):
                shutil.rmtree(vault / surface)

            strict_report = preflight(vault, context=fixed_context())
            release_report = preflight(
                vault,
                context=fixed_context(),
                release_archive_profile=True,
            )

            self.assertEqual(strict_report["status"], "fail")
            self.assertEqual(release_report["status"], "pass")
            self.assertEqual(release_report["entry_pages"], [])
            self.assertEqual(release_report["stats"]["entry_count"], 0)
            self.assertIn("--release-archive-profile", release_report["source_command"])

    def test_preflight_accepts_existing_alias_when_canonical_storage_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "raw" / "fake.pdf").rename(vault / "raw" / "fake-alias.pdf")
            shard = vault / "system" / "system-raw-registry" / "wiki.md"
            text = shard.read_text(encoding="utf-8")
            text = text.replace(
                "- display_path: `raw/fake.pdf`\n",
                "- display_path: `raw/fake.pdf`\n- path aliases:\n  - `raw/fake-alias.pdf`\n",
            )
            shard.write_text(text, encoding="utf-8")

            report = preflight(vault)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["stats"]["path_alias_match_count"], 1)

    def test_preflight_accepts_infozip_c_locale_escaped_storage_path_variant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            storage_path = "raw/속보.pdf"
            seed_minimal_vault(vault, source_trace_ref=storage_path)
            escaped_path = infozip_c_locale_escape_path(storage_path)
            (vault / "raw" / "fake.pdf").rename(vault / escaped_path)
            shard = vault / "system" / "system-raw-registry" / "wiki.md"
            text = shard.read_text(encoding="utf-8")
            text = text.replace(
                "- storage_path: `raw/fake.pdf`\n- display_path: `raw/fake.pdf`\n",
                f"- storage_path: `{storage_path}`\n- display_path: `{storage_path}`\n",
            )
            shard.write_text(text, encoding="utf-8")

            report = preflight(vault)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["stats"]["path_alias_match_count"], 1)

    def test_preflight_accepts_unique_content_hash_match_when_path_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            raw_file = vault / "raw" / "fake.pdf"
            content_sha = __import__("hashlib").sha256(raw_file.read_bytes()).hexdigest()
            raw_file.rename(vault / "raw" / "fake-renamed.pdf")
            shard = vault / "system" / "system-raw-registry" / "wiki.md"
            text = shard.read_text(encoding="utf-8")
            text = text.replace(
                "- display_path: `raw/fake.pdf`\n",
                f"- display_path: `raw/fake.pdf`\n- content sha256: `{content_sha}`\n",
            )
            shard.write_text(text, encoding="utf-8")

            report = preflight(vault)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["stats"]["content_hash_fallback_count"], 1)

    def test_preflight_reports_vault_relative_paths_in_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "system" / "system-raw-registry" / "system.md").unlink()

            report = preflight(vault)

            self.assertEqual(report["vault"], ".")
            self.assertEqual(report["errors"][0]["page"], "system/system-raw-registry/system.md")

    def test_preflight_uses_exported_content_hash_as_fallback_for_path_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            raw_file = vault / "raw" / "fake.pdf"
            content_sha = hashlib.sha256(raw_file.read_bytes()).hexdigest()
            (vault / "ops").mkdir(exist_ok=True)
            (vault / "ops" / "raw-registry.json").write_text(
                json.dumps(
                    {
                        "summary_page": "system/system-raw-registry.md",
                        "entry_pages": live_registry_shard_pages(),
                        "entry_count": 1,
                        "entries": [
                            {
                                "registry_id": "R-100",
                                "storage_path": "raw/fake.pdf",
                                "display_path": "raw/fake.pdf",
                                "content_sha256": content_sha,
                                "type": "news-snapshot",
                                "corpus": "wiki",
                                "target_page": "source--fake",
                                "status": "ingested",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            raw_file.rename(vault / "raw" / "fake-renamed.pdf")

            report = preflight(vault)

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["errors"], [])
            self.assertEqual(report["warnings"], [])
            self.assertEqual(report["stats"]["content_hash_fallback_count"], 1)

    def test_preflight_keeps_pass_result_after_full_zip_roundtrip_with_exported_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            policy, _ = load_policy(vault)
            registry_contract = policy["registry_contract"]
            entry_pages = registry_entry_page_paths(vault, registry_contract)
            write_raw_registry_export(
                vault / registry_contract["raw_registry_export"],
                parse_raw_registry_pages(entry_pages),
                report_path(vault, registry_summary_page_path(vault, registry_contract)),
                [report_path(vault, page) for page in entry_pages],
            )

            original_report = preflight(vault, context=fixed_context())

            archive_path = Path(temp_dir) / "vault-roundtrip.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in sorted(vault.rglob("*")):
                    if path.is_file():
                        archive.write(path, arcname=path.relative_to(vault).as_posix())

            extracted_vault = Path(temp_dir) / "extracted-vault"
            extracted_vault.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(extracted_vault)

            extracted_report = preflight(extracted_vault, context=fixed_context())

            self.assertTrue((extracted_vault / "ops" / "raw-registry.json").exists())
            self.assertEqual(original_report["status"], "pass")
            self.assertEqual(original_report["errors"], [])
            self.assertEqual(original_report["warnings"], [])
            self.assertEqual(extracted_report, original_report)

    def test_reproducibility_report_compares_stored_and_live_preflight_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            live_report = preflight(vault, context=fixed_context())
            stored_report = json.loads(json.dumps(live_report))
            stored_report["stats"]["path_alias_match_count"] = 99
            stored_path = vault / "ops" / "reports" / "raw-registry-preflight-report.json"
            stored_path.parent.mkdir(parents=True, exist_ok=True)
            stored_path.write_text(
                json.dumps(stored_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            loaded_stored_report, stored_diagnostics = load_stored_preflight_report(
                vault,
                stored_path,
            )

            report = build_reproducibility_report(
                vault,
                live_report=live_report,
                stored_report=loaded_stored_report,
                stored_diagnostics=stored_diagnostics,
                stored_report_path=stored_path,
                context=fixed_context(),
            )

            comparison = next(
                item
                for item in report["comparisons"]
                if item["field"] == "stats.path_alias_match_count"
            )
            self.assertEqual(report["artifact_kind"], "raw_registry_preflight_reproducibility")
            self.assertEqual(report["diff_status"], "mismatch")
            self.assertEqual(report["status"], "warn")
            self.assertEqual(comparison["status"], "mismatch")
            self.assertEqual(comparison["stored_value"], 99)
            self.assertEqual(comparison["live_value"], 0)
            self.assertEqual(report["stored_report"]["path"], "ops/reports/raw-registry-preflight-report.json")
            self.assertEqual(report["path_alias_resolution_mode"], PATH_ALIAS_RESOLUTION_MODE)
            self.assertEqual(report["alias_policy_version"], ALIAS_POLICY_VERSION)
            self.assertEqual(
                validate_with_schema(
                    report,
                    load_schema(vault / RAW_REGISTRY_PREFLIGHT_REPRODUCIBILITY_SCHEMA_PATH),
                ),
                [],
            )

    def test_reproducibility_report_matches_after_writing_preflight_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            live_report = preflight(vault, context=fixed_context())
            stored_path = write_report(vault, live_report, None)
            stored_report, stored_diagnostics = load_stored_preflight_report(vault, stored_path)
            reproducibility_report = build_reproducibility_report(
                vault,
                live_report=live_report,
                stored_report=stored_report,
                stored_diagnostics=stored_diagnostics,
                stored_report_path=stored_path,
                context=fixed_context(),
            )
            destination = write_reproducibility_report(vault, reproducibility_report, None)

            self.assertEqual(reproducibility_report["diff_status"], "match")
            self.assertEqual(reproducibility_report["status"], "pass")
            self.assertTrue(destination.exists())
            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                reproducibility_report,
            )

    def test_preflight_surfaces_typed_registry_parse_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            shard = vault / "system" / "system-raw-registry" / "wiki.md"
            shard.write_text("# bad\n\n#### R-100\noops\n", encoding="utf-8")

            report = preflight(vault)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["errors"][0]["type"], "raw_registry_parse_error")
            self.assertEqual(
                report["errors"][0]["detail"]["diagnostic_type"],
                "raw_registry_invalid_continuation_line",
            )

    def test_preflight_fails_for_noncanonical_source_target_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            add_registry_entry_scalar_field(
                vault / "system" / "system-raw-registry" / "wiki.md",
                "R-100",
                "target_page",
                "`source--global-markets-misc-intake-w-100-2026-04-21`",
                after_field="corpus",
            )

            report = preflight(vault)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["errors"][0]["type"], "noncanonical_source_target_page")


if __name__ == "__main__":
    unittest.main()
