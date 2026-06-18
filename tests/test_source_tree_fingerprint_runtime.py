from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.source_tree_fingerprint_runtime import (
    producer_input_fingerprint,
    release_source_tree_change_sample,
    release_source_tree_divergence_diagnostics,
    release_source_tree_fingerprint,
)

pytestmark = pytest.mark.public


class SourceTreeFingerprintRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp_dir.name) / "vault"
        self.vault.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, rel_path: str, text: str) -> None:
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _set_mtime(self, rel_path: str, when: str) -> None:
        path = self.vault / rel_path
        timestamp = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        os.utime(path, (timestamp, timestamp))

    def test_release_source_tree_fingerprint_tracks_release_manifest_surface(self) -> None:
        self._write("ops/scripts/example.py", "print('one')\n")
        baseline = release_source_tree_fingerprint(self.vault)

        self._write("ops/scripts/example.py", "print('two changed')\n")
        changed = release_source_tree_fingerprint(self.vault)

        self.assertNotEqual(baseline, changed)

    def test_release_source_tree_fingerprint_ignores_generated_and_external_surfaces(self) -> None:
        self._write("ops/scripts/example.py", "print('one')\n")
        baseline = release_source_tree_fingerprint(self.vault)

        self._write("ops/script-output-surfaces.json", '{"generated_at":"one"}\n')
        self._write("ops/reports/generated.json", "{}\n")
        self._write("ops/operator/operator-release-summary.json", "{}\n")
        self._write("external-reports/private-review.md", "operator note\n")
        self._write("raw/private-source.md", "private raw\n")
        self._write("wiki/private-page.md", "private wiki\n")
        self._write("system/private-runtime.md", "private system\n")
        self._write("runs/run-local/report.json", "{}\n")
        self._write("tmp/scratch.txt", "scratch\n")
        self._write("downloaded-report.md:Zone.Identifier", "[ZoneTransfer]\nZoneId=3\n")

        self.assertEqual(release_source_tree_fingerprint(self.vault), baseline)

    def test_release_source_tree_fingerprint_ignores_redundant_extra_exclusions(self) -> None:
        self._write("ops/scripts/example.py", "print('one')\n")
        baseline = release_source_tree_fingerprint(self.vault)

        self.assertEqual(
            release_source_tree_fingerprint(
                self.vault,
                extra_excluded_files=(
                    "ops/reports/canonical-report.json",
                    "ops/operator/operator-release-summary.json",
                    "external-reports/report-reference-manifest.json",
                    "raw/private-source.md",
                    "wiki/private-page.md",
                    "system/private-runtime.md",
                    "runs/local-run/report.json",
                    "tmp/scratch.json",
                    "ops/manifest.json",
                    "ops/script-output-surfaces.json",
                    "downloaded-report.md:Zone.Identifier",
                ),
            ),
            baseline,
        )

    def test_release_source_tree_fingerprint_accepts_report_specific_exclusions(self) -> None:
        self._write("ops/scripts/example.py", "print('one')\n")
        baseline = release_source_tree_fingerprint(
            self.vault,
            extra_excluded_files=("ops/custom-generated.json",),
        )

        self._write("ops/custom-generated.json", '{"generated_at":"one"}\n')

        self.assertNotEqual(release_source_tree_fingerprint(self.vault), baseline)
        self.assertEqual(
            release_source_tree_fingerprint(
                self.vault,
                extra_excluded_files=("ops/custom-generated.json",),
            ),
            baseline,
        )

    def test_release_source_tree_fingerprint_can_scope_to_included_prefixes(self) -> None:
        self._write("ops/scripts/example.py", "print('one')\n")
        self._write("README.md", "# one\n")
        baseline = release_source_tree_fingerprint(
            self.vault,
            included_prefixes=("ops/scripts",),
        )

        self._write("README.md", "# changed outside scope\n")
        self.assertEqual(
            release_source_tree_fingerprint(
                self.vault,
                included_prefixes=("ops/scripts",),
            ),
            baseline,
        )

        self._write("ops/scripts/example.py", "print('two')\n")
        self.assertNotEqual(
            release_source_tree_fingerprint(
                self.vault,
                included_prefixes=("ops/scripts",),
            ),
            baseline,
        )

    def test_producer_input_fingerprint_is_stable_and_order_independent(self) -> None:
        left = producer_input_fingerprint({"input_fingerprints": {"b": "two", "a": "one"}})
        right = producer_input_fingerprint({"input_fingerprints": {"a": "one", "b": "two"}})

        self.assertEqual(left, right)
        self.assertNotEqual(left, producer_input_fingerprint({"input_fingerprints": {"a": "changed"}}))
        self.assertEqual(producer_input_fingerprint({}), "")

    def test_release_source_tree_change_sample_tracks_release_manifest_surface(self) -> None:
        self._write("ops/scripts/example.py", "print('tracked')\n")
        self._set_mtime("ops/scripts/example.py", "2026-04-29T08:00:01Z")

        sample = release_source_tree_change_sample(
            self.vault,
            generated_at="2026-04-29T08:00:00Z",
        )

        self.assertEqual(sample["changed_after_generated_at_count"], 1)
        self.assertEqual(sample["changed_after_generated_at_path_limit"], 10)
        self.assertEqual(
            sample["changed_after_generated_at"],
            [{"path": "ops/scripts/example.py", "mtime": "2026-04-29T08:00:01Z"}],
        )

    def test_release_source_tree_change_sample_ignores_generated_and_external_surfaces(self) -> None:
        self._write("ops/scripts/example.py", "print('tracked')\n")
        self._set_mtime("ops/scripts/example.py", "2026-04-29T07:59:59Z")
        self._write("ops/reports/generated.json", "{}\n")
        self._set_mtime("ops/reports/generated.json", "2026-04-29T08:00:02Z")
        self._write("ops/operator/operator-release-summary.json", "{}\n")
        self._set_mtime("ops/operator/operator-release-summary.json", "2026-04-29T08:00:03Z")
        self._write("external-reports/private-review.md", "note\n")
        self._set_mtime("external-reports/private-review.md", "2026-04-29T08:00:04Z")
        self._write("raw/private-source.md", "private raw\n")
        self._set_mtime("raw/private-source.md", "2026-04-29T08:00:05Z")
        self._write("wiki/private-page.md", "private wiki\n")
        self._set_mtime("wiki/private-page.md", "2026-04-29T08:00:06Z")
        self._write("system/private-runtime.md", "private system\n")
        self._set_mtime("system/private-runtime.md", "2026-04-29T08:00:07Z")
        self._write("tmp/scratch.txt", "scratch\n")
        self._set_mtime("tmp/scratch.txt", "2026-04-29T08:00:08Z")

        sample = release_source_tree_change_sample(
            self.vault,
            generated_at="2026-04-29T08:00:00Z",
        )

        self.assertEqual(sample["changed_after_generated_at_count"], 0)
        self.assertEqual(sample["changed_after_generated_at"], [])

    def test_release_source_tree_change_sample_accepts_report_specific_exclusions(self) -> None:
        self._write("ops/scripts/example.py", "print('tracked')\n")
        self._set_mtime("ops/scripts/example.py", "2026-04-29T08:00:01Z")

        baseline = release_source_tree_change_sample(
            self.vault,
            generated_at="2026-04-29T08:00:00Z",
        )
        excluded = release_source_tree_change_sample(
            self.vault,
            generated_at="2026-04-29T08:00:00Z",
            extra_excluded_files=("ops/scripts/example.py",),
        )

        self.assertEqual(baseline["changed_after_generated_at_count"], 1)
        self.assertEqual(excluded["changed_after_generated_at_count"], 0)
        self.assertEqual(excluded["changed_after_generated_at"], [])

    def test_release_source_tree_change_sample_can_scope_to_included_prefixes(self) -> None:
        self._write("ops/scripts/example.py", "print('tracked')\n")
        self._set_mtime("ops/scripts/example.py", "2026-04-29T08:00:01Z")
        self._write("README.md", "# changed outside scope\n")
        self._set_mtime("README.md", "2026-04-29T08:00:02Z")

        sample = release_source_tree_change_sample(
            self.vault,
            generated_at="2026-04-29T08:00:00Z",
            included_prefixes=("ops/scripts",),
        )

        self.assertEqual(sample["changed_after_generated_at_count"], 1)
        self.assertEqual(
            sample["changed_after_generated_at"],
            [{"path": "ops/scripts/example.py", "mtime": "2026-04-29T08:00:01Z"}],
        )

    def test_release_source_tree_divergence_diagnostics_reports_noncurrent_components(self) -> None:
        self._write("ops/scripts/example.py", "print('tracked')\n")
        self._set_mtime("ops/scripts/example.py", "2026-04-29T08:00:01Z")
        components = [
            {
                "load_status": "ok",
                "name": "current",
                "path": "ops/reports/current.json",
                "generated_at": "2026-04-29T08:00:00Z",
                "source_tree_fingerprint": "current-fingerprint",
                "modified_after_generated_at": False,
            },
            {
                "load_status": "ok",
                "name": "fingerprint_drift",
                "path": "ops/reports/fingerprint-drift.json",
                "generated_at": "2026-04-29T08:00:00Z",
                "source_tree_fingerprint": "old-fingerprint",
                "modified_after_generated_at": False,
            },
            {
                "load_status": "ok",
                "name": "mtime_drift",
                "path": "ops/reports/mtime-drift.json",
                "generated_at": "2026-04-29T08:00:00Z",
                "source_tree_fingerprint": "current-fingerprint",
                "modified_after_generated_at": True,
            },
            {
                "load_status": "missing",
                "name": "missing",
                "path": "ops/reports/missing.json",
            },
        ]

        diagnostics = release_source_tree_divergence_diagnostics(
            self.vault,
            components,
            current_source_tree_fingerprint="current-fingerprint",
        )

        self.assertEqual(diagnostics["path_limit"], 10)
        by_name = {item["name"]: item for item in diagnostics["components"]}
        self.assertEqual(set(by_name), {"fingerprint_drift", "mtime_drift"})
        self.assertFalse(by_name["fingerprint_drift"]["matches_current_source_tree_fingerprint"])
        self.assertTrue(by_name["mtime_drift"]["matches_current_source_tree_fingerprint"])
        self.assertEqual(
            by_name["mtime_drift"]["changed_after_generated_at"],
            [{"path": "ops/scripts/example.py", "mtime": "2026-04-29T08:00:01Z"}],
        )
