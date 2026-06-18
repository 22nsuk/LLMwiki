from __future__ import annotations

import datetime as dt
import hashlib
import zipfile
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_ZIP_TIMESTAMP_TIMEZONE = "UTC"


def _timezone_for_zip_timestamps(name: str) -> dt.tzinfo:
    value = str(name).strip() or DEFAULT_ZIP_TIMESTAMP_TIMEZONE
    if value.upper() == "UTC":
        return dt.UTC
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return dt.UTC


def _zip_info_mtime_iso_z(info: zipfile.ZipInfo, *, timezone_assumption: str) -> str:
    local_tz = _timezone_for_zip_timestamps(timezone_assumption)
    timestamp = dt.datetime(*info.date_time, tzinfo=local_tz)
    return (
        timestamp.astimezone(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def normalize_zip_member_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def zip_member_mtimes(
    zip_metadata_path: Path, *, timezone_assumption: str
) -> dict[str, str]:
    mtimes: dict[str, str] = {}
    with zipfile.ZipFile(zip_metadata_path) as archive:
        for info in archive.infolist():
            rel_path = normalize_zip_member_path(info.filename)
            if not rel_path or rel_path.endswith("/"):
                continue
            mtime = _zip_info_mtime_iso_z(
                info,
                timezone_assumption=timezone_assumption,
            )
            candidates = [rel_path]
            if "/" in rel_path:
                candidates.append(rel_path.split("/", 1)[1])
            for candidate in candidates:
                current = mtimes.get(candidate)
                if current is None or mtime > current:
                    mtimes[candidate] = mtime
    return mtimes


def zip_member_timestamp_semantics(zip_metadata_path: Path) -> str:
    with zipfile.ZipFile(zip_metadata_path) as archive:
        timestamps = {
            info.date_time for info in archive.infolist() if not info.is_dir()
        }
    return _zip_timestamp_semantics(timestamps)


def _root_prefix_for_members(names: list[str]) -> str:
    first_parts = {name.split("/", 1)[0] for name in names if name and "/" in name}
    if len(first_parts) != 1:
        return ""
    prefix = next(iter(first_parts))
    return prefix if all(name.startswith(f"{prefix}/") for name in names) else ""


def _strip_zip_root_prefix(name: str, root_prefix: str) -> str:
    if root_prefix and name.startswith(f"{root_prefix}/"):
        return name.split("/", 1)[1]
    return name


def _zip_timestamp_text(value: tuple[int, int, int, int, int, int] | None) -> str:
    if value is None:
        return ""
    year, month, day, hour, minute, second = value
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"


def _zip_timestamp_semantics(
    timestamps: set[tuple[int, int, int, int, int, int]],
) -> str:
    if not timestamps:
        return "not_applicable"
    if timestamps == {(1980, 1, 1, 0, 0, 0)}:
        return "normalized_archive_timestamp"
    return "archive_member_timestamp"


def zip_manifest(zip_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        file_infos = [info for info in infos if not info.is_dir()]
        normalized_names = [
            normalize_zip_member_path(info.filename) for info in file_infos
        ]
        root_prefix = _root_prefix_for_members(normalized_names)
        files = []
        timestamps = {info.date_time for info in file_infos}
        for info, normalized_name in zip(file_infos, normalized_names, strict=True):
            rel_path = _strip_zip_root_prefix(normalized_name, root_prefix)
            content = archive.read(info.filename)
            files.append(
                {
                    "path": rel_path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
            )
        files.sort(key=lambda item: str(item["path"]))
        timestamp_min = min(timestamps) if timestamps else None
        timestamp_max = max(timestamps) if timestamps else None
        return {
            "files": files,
            "root_prefix": root_prefix,
            "entry_count": len(infos),
            "file_count": len(file_infos),
            "directory_entry_count": len(infos) - len(file_infos),
            "uncompressed_size_bytes": sum(info.file_size for info in file_infos),
            "timestamp_unique_count": len(timestamps),
            "timestamp_min": _zip_timestamp_text(timestamp_min),
            "timestamp_max": _zip_timestamp_text(timestamp_max),
            "timestamp_semantics": _zip_timestamp_semantics(timestamps),
        }
