from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.registry.source_substance_cohort_classify import (
    DEFAULT_OUT,
    SCHEMA_PATH,
    build_report,
    main,
    write_report,
)
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.default_test_boundary,
]


def _source_page(
    *,
    title: str,
    created: str,
    raw_path: str,
    route_decision: str | None = None,
    synthesis_link: str | None = None,
    passing: bool = False,
) -> str:
    frontmatter = [
        "---",
        f'created: "{created}"',
        f'raw_path: "{raw_path}"',
    ]
    if route_decision is not None:
        frontmatter.append(f'route_decision: "{route_decision}"')
    frontmatter.extend(["---", "", f"# {title}", "", "## Summary"])
    if passing:
        frontmatter.append(
            "Independent evidence establishes alpha. Separate measurements establish beta."
        )
        key_points = ["alpha", "beta", "gamma", "delta"]
    else:
        frontmatter.append(f"{title} repeats the title.")
        key_points = [title]
    frontmatter.extend(["", "## Key points", *(f"- {point}" for point in key_points)])
    frontmatter.extend(
        [
            "",
            "## Limitations / caveats",
            "- synthetic coverage is intentionally bounded",
            "",
            "## Open questions",
            "- none",
        ]
    )
    if synthesis_link is not None:
        frontmatter.extend(["", "## Related pages", f"- [[{synthesis_link}]]"])
    return "\n".join(frontmatter) + "\n"


class SourceSubstanceCohortClassifyTests(unittest.TestCase):
    def _seed_vault(self, root: Path) -> Path:
        vault = root / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)
        for corpus in ("wiki", "system"):
            for pattern in ("source--*.md", "synthesis--*.md"):
                for path in (vault / corpus).glob(pattern):
                    path.unlink()
        schema_source = REPO_ROOT / SCHEMA_PATH
        schema_destination = vault / SCHEMA_PATH
        schema_destination.write_text(
            schema_source.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return vault

    def test_all_dates_system_pages_inverse_links_and_conservative_raw_routes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._seed_vault(Path(temp_dir))
            raw = vault / "raw"
            (raw / "direct.md").write_text("text", encoding="utf-8")
            (raw / "inverse.pdf").write_bytes(b"%PDF synthetic")
            (raw / "unlinked.txt").write_text("text", encoding="utf-8")
            (raw / "system.md").write_text("text", encoding="utf-8")
            (raw / "other.bin").write_bytes(b"synthetic")

            pages = {
                "wiki/source--direct-2024-01-02.md": _source_page(
                    title="Direct weak",
                    created="2025-03-04",
                    raw_path="raw/direct.md",
                    route_decision="absorb_existing_concept",
                    synthesis_link="synthesis--direct",
                ),
                "wiki/source--inverse.md": _source_page(
                    title="Inverse weak",
                    created="2023-02-01",
                    raw_path="raw/inverse.pdf",
                ),
                "wiki/source--unlinked-2022-12-31.md": _source_page(
                    title="Unlinked weak",
                    created="2026-01-01",
                    raw_path="raw/unlinked.txt",
                    route_decision="keep_source_only_seed",
                ),
                "system/source--runtime-without-date.md": _source_page(
                    title="System weak",
                    created="2021-01-01",
                    raw_path="raw/system.md",
                ),
                "wiki/source--missing-2020-05-06.md": _source_page(
                    title="Missing weak",
                    created="2020-05-07",
                    raw_path="raw/missing.md",
                    synthesis_link="synthesis--direct",
                ),
                "wiki/source--other-2019-01-01.md": _source_page(
                    title="Other weak",
                    created="2019-01-02",
                    raw_path="raw/other.bin",
                    synthesis_link="synthesis--direct",
                ),
                "wiki/source--passing-2018-01-01.md": _source_page(
                    title="Passing source",
                    created="2018-01-02",
                    raw_path="raw/missing-passing.md",
                    passing=True,
                ),
                "wiki/synthesis--direct.md": "# Direct synthesis\n",
                "system/synthesis--inverse.md": "# Inverse synthesis\n\n- [[source--inverse]]\n",
            }
            for relative_path, text in pages.items():
                path = vault / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")

            report = build_report(vault)
            entries = {entry["page"]: entry for entry in report["entries"]}

            self.assertEqual(report["schema_version"], 2)
            self.assertEqual(report["$schema"], SCHEMA_PATH)
            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["summary"]["total_source_count"], 7)
            self.assertEqual(report["summary"]["passing_count"], 1)
            self.assertEqual(report["summary"]["failing_count"], 6)
            self.assertEqual(
                report["summary"]["remediation_route_counts"],
                {
                    "no_action": 1,
                    "recover_from_text_raw": 1,
                    "recover_from_pdf_raw": 1,
                    "retained_operator_review": 2,
                    "operator_review": 2,
                },
            )
            self.assertEqual(
                report["summary"]["failing_by_corpus"], {"wiki": 5, "system": 1}
            )
            self.assertEqual(
                report["summary"]["failure_reason_counts"],
                {
                    "first_key_point_repeats_title": 6,
                    "key_points_below_minimum": 6,
                    "summary_lacks_source_specific_facts": 6,
                    "summary_repeats_title": 6,
                },
            )
            self.assertEqual(
                entries["wiki/source--direct-2024-01-02.md"]["remediation_route"],
                "recover_from_text_raw",
            )
            direct = entries["wiki/source--direct-2024-01-02.md"]
            self.assertEqual(direct["created"], "2025-03-04")
            self.assertRegex(direct["page_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(direct["raw_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(direct["filename_date"], "2024-01-02")
            self.assertIsNone(direct["ingest_cohort"])
            self.assertTrue(direct["synthesis_linkage"]["linked"])
            self.assertEqual(direct["synthesis_linkage"]["linkage_count"], 1)

            inverse = entries["wiki/source--inverse.md"]
            self.assertEqual(inverse["remediation_route"], "recover_from_pdf_raw")
            self.assertEqual(
                inverse["synthesis_linkage"]["inverse_links"],
                ["system/synthesis--inverse.md"],
            )
            self.assertIsNone(inverse["filename_date"])
            self.assertEqual(
                entries["wiki/source--unlinked-2022-12-31.md"]["remediation_route"],
                "retained_operator_review",
            )
            self.assertEqual(
                entries["system/source--runtime-without-date.md"]["remediation_route"],
                "retained_operator_review",
            )
            self.assertEqual(
                entries["system/source--runtime-without-date.md"]["corpus"], "system"
            )
            self.assertIsNone(
                entries["system/source--runtime-without-date.md"]["route_decision"]
            )
            self.assertEqual(
                entries["wiki/source--missing-2020-05-06.md"]["remediation_route"],
                "operator_review",
            )
            self.assertEqual(
                entries["wiki/source--other-2019-01-01.md"]["remediation_route"],
                "operator_review",
            )
            self.assertEqual(
                entries["wiki/source--passing-2018-01-01.md"]["remediation_route"],
                "no_action",
            )

    def test_raw_paths_outside_vault_are_not_read_or_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            vault = self._seed_vault(root)
            outside = root / "outside.txt"
            outside.write_text("host-only evidence", encoding="utf-8")
            pages = {
                "wiki/source--absolute.md": str(outside),
                "wiki/source--traversal.md": "../outside.txt",
            }
            try:
                (vault / "raw/outside-link.txt").symlink_to(outside)
            except OSError:
                pass
            else:
                pages["wiki/source--symlink.md"] = "raw/outside-link.txt"
            for relative_path, raw_path in pages.items():
                path = vault / relative_path
                path.write_text(
                    _source_page(
                        title=path.stem,
                        created="2026-07-12",
                        raw_path=raw_path,
                    ),
                    encoding="utf-8",
                )

            report = build_report(vault)
            entries = {entry["page"]: entry for entry in report["entries"]}

            for page in pages:
                entry = entries[page]
                self.assertIsNone(entry["raw_path"])
                self.assertFalse(entry["raw_exists"])
                self.assertEqual(entry["raw_media_class"], "missing")
                self.assertIsNone(entry["raw_sha256"])
                self.assertEqual(entry["remediation_route"], "operator_review")

    def test_raw_input_fingerprint_tracks_safe_missing_create_replace_and_delete(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._seed_vault(Path(temp_dir))
            page = vault / "wiki/source--tracked-raw.md"
            page.write_text(
                _source_page(
                    title="Tracked raw",
                    created="2026-07-12",
                    raw_path="raw/tracked.txt",
                    synthesis_link="synthesis--tracked",
                ),
                encoding="utf-8",
            )
            (vault / "wiki/synthesis--tracked.md").write_text(
                "# Tracked synthesis\n", encoding="utf-8"
            )
            raw = vault / "raw/tracked.txt"

            missing = build_report(vault)
            missing_entry = missing["entries"][0]
            self.assertEqual(missing_entry["raw_path"], "raw/tracked.txt")
            self.assertFalse(missing_entry["raw_exists"])

            raw.write_text("first raw payload", encoding="utf-8")
            created = build_report(vault)
            raw.write_text("second raw payload", encoding="utf-8")
            replaced = build_report(vault)
            raw.unlink()
            deleted = build_report(vault)

            fingerprints = [
                report["input_fingerprints"]["raw_paths"]
                for report in (missing, created, replaced, deleted)
            ]
            self.assertNotEqual(fingerprints[0], fingerprints[1])
            self.assertNotEqual(fingerprints[1], fingerprints[2])
            self.assertNotEqual(fingerprints[2], fingerprints[3])
            self.assertEqual(fingerprints[0], fingerprints[3])

    def test_write_report_rejects_invalid_payload_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._seed_vault(Path(temp_dir))
            report = build_report(vault)
            report["summary"]["passing_count"] = "invalid"
            destination = vault / DEFAULT_OUT

            with self.assertRaisesRegex(ValueError, "schema validation failed"):
                write_report(vault, report)

            self.assertFalse(destination.exists())

    def test_build_and_cli_do_not_mutate_system_log_or_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = self._seed_vault(Path(temp_dir))
            log_path = vault / "system" / "system-log.md"
            original_log = log_path.read_bytes()
            before_build = {
                path.relative_to(vault).as_posix(): path.read_bytes()
                for path in vault.rglob("*")
                if path.is_file()
            }

            build_report(vault)

            after_build = {
                path.relative_to(vault).as_posix(): path.read_bytes()
                for path in vault.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after_build, before_build)

            self.assertEqual(main(["--vault", str(vault)]), 0)
            self.assertTrue((vault / DEFAULT_OUT).is_file())
            self.assertEqual(log_path.read_bytes(), original_log)
            self.assertFalse((vault / "system" / "events.jsonl").exists())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
