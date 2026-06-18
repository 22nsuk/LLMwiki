from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

import pytest

from ops.scripts.release.release_closeout_batch_manifest_zip_runtime import (
    normalize_zip_member_path,
    zip_manifest,
    zip_member_mtimes,
    zip_member_timestamp_semantics,
)

pytestmark = [pytest.mark.public, pytest.mark.release_sealing]


class ReleaseCloseoutBatchManifestZipRuntimeTests(unittest.TestCase):
    def test_zip_manifest_strips_single_archive_root_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo(
                        "LLMwiki-source/ops/reports/release-smoke-report.json",
                        (2026, 5, 2, 9, 0, 0),
                    ),
                    "{}",
                )

            manifest = zip_manifest(archive_path)

        self.assertEqual(manifest["root_prefix"], "LLMwiki-source")
        self.assertEqual(
            [item["path"] for item in manifest["files"]],
            ["ops/reports/release-smoke-report.json"],
        )
        self.assertEqual(manifest["timestamp_semantics"], "archive_member_timestamp")

    def test_zip_member_mtimes_indexes_full_and_root_stripped_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo(
                        "LLMwiki-source/ops/reports/test-execution-summary.json",
                        (2026, 5, 2, 9, 30, 0),
                    ),
                    "{}",
                )

            mtimes = zip_member_mtimes(archive_path, timezone_assumption="UTC")

        self.assertEqual(
            mtimes["LLMwiki-source/ops/reports/test-execution-summary.json"],
            "2026-05-02T09:30:00Z",
        )
        self.assertEqual(
            mtimes["ops/reports/test-execution-summary.json"],
            "2026-05-02T09:30:00Z",
        )

    def test_normalized_zip_timestamps_are_not_temporal_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "release.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(
                    zipfile.ZipInfo("LLMwiki-source/README.md", (1980, 1, 1, 0, 0, 0)),
                    "readme",
                )

            semantics = zip_member_timestamp_semantics(archive_path)

        self.assertEqual(semantics, "normalized_archive_timestamp")

    def test_normalize_zip_member_path_removes_portable_prefix_noise(self) -> None:
        self.assertEqual(
            normalize_zip_member_path(r"/././LLMwiki-source\README.md"),
            "LLMwiki-source/README.md",
        )


if __name__ == "__main__":
    unittest.main()
