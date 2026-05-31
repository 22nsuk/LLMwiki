from __future__ import annotations

import datetime as dt
import os
import zipfile
from pathlib import Path

from ops.scripts.core.artifact_freshness_mtime_runtime import (
    format_mtime,
    load_zip_info_mtimes,
    mtime_for_source,
    normalize_zip_member_path,
    parse_generated_at,
)


def test_parse_and_format_generated_at_round_trip_without_microseconds() -> None:
    parsed = parse_generated_at("2026-04-24T12:00:00.123456Z")

    assert parsed == dt.datetime(2026, 4, 24, 12, 0, 0, 123456, tzinfo=dt.UTC)
    assert format_mtime(parsed) == "2026-04-24T12:00:00Z"


def test_zip_info_mtimes_normalize_members_and_keep_latest(tmp_path: Path) -> None:
    archive_path = tmp_path / "release.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(zipfile.ZipInfo("./ops/reports/example.json", (2026, 4, 24, 12, 0, 0)), "{}")
        archive.writestr(zipfile.ZipInfo("/ops/reports/example.json", (2026, 4, 24, 12, 1, 0)), "{}")

    mtimes = load_zip_info_mtimes(archive_path)

    assert normalize_zip_member_path(r".\ops\reports\example.json") == "ops/reports/example.json"
    assert mtimes["ops/reports/example.json"] == dt.datetime(2026, 4, 24, 12, 1, tzinfo=dt.UTC)


def test_mtime_for_source_uses_selected_authority(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    timestamp = dt.datetime(2026, 4, 24, 12, 0, 0, tzinfo=dt.UTC).timestamp()
    os.utime(artifact, (timestamp, timestamp))

    assert mtime_for_source(
        artifact,
        "artifact.json",
        mtime_source="filesystem",
        zip_mtimes={},
    ) == dt.datetime(2026, 4, 24, 12, 0, tzinfo=dt.UTC)
    assert mtime_for_source(
        artifact,
        "artifact.json",
        mtime_source="zip_info",
        zip_mtimes={"artifact.json": dt.datetime(2026, 4, 24, 12, 1, tzinfo=dt.UTC)},
    ) == dt.datetime(2026, 4, 24, 12, 1, tzinfo=dt.UTC)
    assert mtime_for_source(
        artifact,
        "artifact.json",
        mtime_source="embedded_currentness",
        zip_mtimes={},
    ) is None
