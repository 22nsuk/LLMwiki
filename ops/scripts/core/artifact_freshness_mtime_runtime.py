#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import zipfile
from collections.abc import Mapping
from pathlib import Path


def parse_generated_at(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)
    except ValueError:
        return None


def mtime_utc(path: Path) -> dt.datetime | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.UTC)
    except OSError:
        return None


def zip_info_mtime(info: zipfile.ZipInfo) -> dt.datetime:
    return dt.datetime(*info.date_time, tzinfo=dt.UTC)


def normalize_zip_member_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def zip_info_mtimes(zip_metadata_path: Path) -> dict[str, dt.datetime]:
    mtimes: dict[str, dt.datetime] = {}
    with zipfile.ZipFile(zip_metadata_path) as archive:
        for info in archive.infolist():
            rel_path = normalize_zip_member_path(info.filename)
            if not rel_path or rel_path.endswith("/"):
                continue
            current = mtimes.get(rel_path)
            candidate = zip_info_mtime(info)
            if current is None or candidate > current:
                mtimes[rel_path] = candidate
    return mtimes


def load_zip_info_mtimes(zip_metadata_path: Path | None) -> dict[str, dt.datetime]:
    if zip_metadata_path is None:
        return {}
    return zip_info_mtimes(zip_metadata_path)


def mtime_for_source(
    path: Path,
    rel_path: str,
    *,
    mtime_source: str,
    zip_mtimes: Mapping[str, dt.datetime],
) -> dt.datetime | None:
    if mtime_source == "filesystem":
        return mtime_utc(path)
    if mtime_source == "zip_info":
        return zip_mtimes.get(rel_path)
    if mtime_source == "embedded_currentness":
        return None
    raise ValueError(f"unsupported mtime_source: {mtime_source}")


def format_mtime(value: dt.datetime | None) -> str:
    if value is None:
        return ""
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
