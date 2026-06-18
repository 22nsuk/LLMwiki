from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.path_portability_runtime import infozip_c_locale_escape_path
from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.registry_exceptions_runtime import (
    RawRegistryInvalidContinuationLineError,
    RawRegistryLegacyCompactEntryError,
)
from ops.scripts.registry.raw_registry_runtime import (
    build_raw_registry_export,
    build_registry_source_trace_resolution_map,
    enrich_registry_entries_with_inventory,
    load_registry_source_trace_resolution_state,
    parse_raw_registry_page,
    registry_entry_locators,
)
from tests.minimal_vault_runtime import live_registry_shard_pages, seed_minimal_vault

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "raw_registry"


class RawRegistryRuntimeTest(unittest.TestCase):
    def test_multiline_field_preserves_semicolon_and_newlines(self) -> None:
        entries = parse_raw_registry_page(FIXTURES / "multiline-semicolon.md")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Alpha; Beta\nSecond line\n")
        self.assertEqual(entries[0]["domain"], "test-domain")

    def test_legacy_compact_entry_is_explicitly_rejected(self) -> None:
        with self.assertRaisesRegex(
            RawRegistryLegacyCompactEntryError,
            "legacy compact raw registry entries are unsupported",
        ):
            parse_raw_registry_page(FIXTURES / "legacy-compact-semicolon.md")

    def test_invalid_registry_continuation_line_uses_typed_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            page = Path(temp_dir) / "registry.md"
            page.write_text("# registry\n\n#### R-200\noops\n", encoding="utf-8")

            with self.assertRaises(RawRegistryInvalidContinuationLineError) as ctx:
                parse_raw_registry_page(page)

            self.assertEqual(ctx.exception.registry_id, "R-200")

    def test_path_aliases_and_content_sha256_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            page = Path(temp_dir) / "registry.md"
            page.write_text(
                """# registry

#### R-200
- storage_path: `raw\\Folder\\Cafe\u0301.pdf`
- display_path: `raw\\Folder\\Cafe\u0301.pdf`
- path aliases:
  - `raw/Caf\u00e9.pdf`
  - `raw\\Alt\\Cafe\u0301.pdf`
- content_sha256: `ABCDEF1234`
- title: *Alias test*
- type: news-snapshot
- corpus: wiki
- target_page: `source--alias`
- status: ingested
""",
                encoding="utf-8",
            )

            entries = parse_raw_registry_page(page)

            self.assertEqual(entries[0]["storage_path"], "raw/Folder/Café.pdf")
            self.assertEqual(entries[0]["display_path"], "raw/Folder/Café.pdf")
            self.assertEqual(
                entries[0]["path_aliases"],
                ["raw/Café.pdf", "raw/Alt/Café.pdf"],
            )
            self.assertEqual(entries[0]["content_sha256"], "abcdef1234")

    def test_windows_path_alias_normalization_keeps_resolution_family_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            page = Path(temp_dir) / "registry.md"
            page.write_text(
                """# registry

#### R-201
- storage_path: `raw\\Folder\\Cafe\u0301.pdf`
- display_path: `raw\\Folder\\Cafe\u0301.pdf`
- path aliases:
  - `raw/Folder/Caf\u00e9.pdf`
  - `raw\\Folder\\Cafe\u0301.pdf`
- content_sha256: `ABCDEF1234`
- title: *Windows alias test*
- type: news-snapshot
- corpus: wiki
- target_page: `source--windows-alias`
- status: ingested
""",
                encoding="utf-8",
            )

            entries = parse_raw_registry_page(page)
            locators = registry_entry_locators(entries[0])
            resolution_map = build_registry_source_trace_resolution_map(entries)

            self.assertEqual(locators, ["raw/Folder/Café.pdf"])
            self.assertEqual(
                resolution_map["raw/Folder/Café.pdf"],
                ["raw/Folder/Café.pdf"],
            )
            self.assertEqual(entries[0]["content_sha256"], "abcdef1234")

    def test_export_shape_uses_summary_and_entry_pages(self) -> None:
        expected_entry_pages = live_registry_shard_pages()
        export = build_raw_registry_export(
            [
                {
                    "registry_id": "R-001",
                    "storage_path": "raw/a.pdf",
                    "display_path": "raw/a.pdf",
                    "path_aliases": ["raw/A.pdf"],
                "content_sha256": "abc123",
                "topic_family": "coffee-science-and-brewing",
                "topic_subfamily": "coffee-extraction-models-and-brew-control",
                "registered_on": "2026-04-14",
                "type": "news-snapshot",
                "corpus": "wiki",
                "target_page": "source--a",
                "status": "ingested",
                }
            ],
            "system/system-raw-registry.md",
            expected_entry_pages,
        )
        self.assertEqual(export["summary_page"], "system/system-raw-registry.md")
        self.assertEqual(export["entry_pages"], expected_entry_pages)
        self.assertEqual(export["entry_count"], 1)
        self.assertEqual(export["entries"][0]["topic_family"], "coffee-science-and-brewing")
        self.assertEqual(
            export["entries"][0]["topic_subfamily"],
            "coffee-extraction-models-and-brew-control",
        )
        self.assertEqual(export["entries"][0]["registered_on"], "2026-04-14")
        self.assertEqual(export["entries"][0]["path_aliases"], ["raw/A.pdf"])
        self.assertEqual(export["entries"][0]["content_sha256"], "abc123")

    def test_inventory_enrichment_derives_content_hash_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            payload = b"same-bytes"
            (raw_dir / "primary.pdf").write_bytes(payload)
            (raw_dir / "alias.pdf").write_bytes(payload)

            entries = [
                {
                    "registry_id": "R-300",
                    "storage_path": "raw/primary.pdf",
                    "display_path": "raw/primary.pdf",
                    "title": "Inventory enriched",
                    "type": "news-snapshot",
                    "corpus": "wiki",
                    "target_page": "source--inventory-enriched",
                    "status": "ingested",
                }
            ]

            enriched = enrich_registry_entries_with_inventory(vault, entries)

            self.assertEqual(
                enriched[0]["content_sha256"],
                hashlib.sha256(payload).hexdigest(),
            )
            self.assertEqual(enriched[0]["path_aliases"], ["raw/alias.pdf"])

    def test_inventory_enrichment_prefers_existing_raw_digest_over_stale_registry_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            payload = b"current-bytes"
            (raw_dir / "current.pdf").write_bytes(payload)
            stale_digest = hashlib.sha256(b"old-bytes").hexdigest()

            entries = [
                {
                    "registry_id": "R-302",
                    "storage_path": "raw/current.pdf",
                    "display_path": "raw/current.pdf",
                    "content_sha256": stale_digest,
                    "title": "Inventory refreshed",
                    "type": "news-snapshot",
                    "corpus": "wiki",
                    "target_page": "source--inventory-refreshed",
                    "status": "ingested",
                }
            ]

            enriched = enrich_registry_entries_with_inventory(
                vault,
                entries,
                exported_enrichment={
                    ("R-302", "raw/current.pdf"): {"content_sha256": stale_digest},
                },
            )

            self.assertEqual(
                enriched[0]["content_sha256"],
                hashlib.sha256(payload).hexdigest(),
            )

    def test_inventory_enrichment_derives_infozip_c_locale_alias_from_storage_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            raw_dir = vault / "raw"
            raw_dir.mkdir()
            payload = b"same-bytes"
            storage_path = "raw/속보.pdf"
            escaped_path = infozip_c_locale_escape_path(storage_path)
            self.assertNotEqual(escaped_path, storage_path)
            (vault / escaped_path).write_bytes(payload)

            entries = [
                {
                    "registry_id": "R-301",
                    "storage_path": storage_path,
                    "display_path": storage_path,
                    "title": "Inventory enriched",
                    "type": "news-snapshot",
                    "corpus": "wiki",
                    "target_page": "source--inventory-enriched",
                    "status": "ingested",
                }
            ]

            enriched = enrich_registry_entries_with_inventory(vault, entries)

            self.assertEqual(
                enriched[0]["content_sha256"],
                hashlib.sha256(payload).hexdigest(),
            )
            self.assertEqual(enriched[0]["path_aliases"], [escaped_path])

    def test_source_trace_resolution_state_reports_invalid_export_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            (vault / "ops" / "raw-registry.json").write_text("{broken", encoding="utf-8")

            policy, _ = load_policy(vault)
            state = load_registry_source_trace_resolution_state(vault, policy["registry_contract"])

            self.assertIn("raw/fake.pdf", state["resolution_map"])
            self.assertEqual(len(state["warnings"]), 1)
            self.assertEqual(
                state["warnings"][0]["type"],
                "raw_registry_export_enrichment_load_failed",
            )
            self.assertEqual(
                state["warnings"][0]["diagnostic_type"],
                "raw_registry_export_invalid_json",
            )

    def test_source_trace_resolution_state_reports_registry_parse_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            shard = vault / "system" / "system-raw-registry" / "wiki.md"
            shard.write_text("# bad\n\n#### R-100\noops\n", encoding="utf-8")

            policy, _ = load_policy(vault)
            state = load_registry_source_trace_resolution_state(vault, policy["registry_contract"])

            self.assertEqual(state["resolution_map"], {})
            self.assertEqual(len(state["warnings"]), 1)
            self.assertEqual(
                state["warnings"][0]["type"],
                "raw_registry_source_trace_resolution_failed",
            )
            self.assertEqual(
                state["warnings"][0]["diagnostic_type"],
                "raw_registry_invalid_continuation_line",
            )


if __name__ == "__main__":
    unittest.main()
