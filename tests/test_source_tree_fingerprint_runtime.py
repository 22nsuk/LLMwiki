from __future__ import annotations

import datetime as dt
import os
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.source_tree_fingerprint_runtime import (
    producer_input_fingerprint,
    release_source_tree_change_sample,
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
        self._write("runs/run-local/report.json", "{}\n")
        self._write("tmp/scratch.txt", "scratch\n")
        self._write("downloaded-report.md:Zone.Identifier", "[ZoneTransfer]\nZoneId=3\n")

        self.assertEqual(release_source_tree_fingerprint(self.vault), baseline)

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
        self._write("tmp/scratch.txt", "scratch\n")
        self._set_mtime("tmp/scratch.txt", "2026-04-29T08:00:05Z")

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
