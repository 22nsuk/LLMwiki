from __future__ import annotations

import datetime as dt


def parse_iso_z(value: str) -> dt.datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def age_seconds(now_iso: str, observed_iso: str) -> int | None:
    now = parse_iso_z(now_iso)
    observed = parse_iso_z(observed_iso)
    if now is None or observed is None:
        return None
    return max(0, int((now - observed).total_seconds()))


def freshness_status(
    *,
    now_iso: str,
    observed_iso: str,
    interval_seconds: int,
    allow_not_recorded: bool = False,
) -> str:
    if not observed_iso:
        return "not_recorded" if allow_not_recorded else "unknown"
    age = age_seconds(now_iso, observed_iso)
    if age is None:
        return "unknown"
    return "current" if age <= interval_seconds * 2 else "stale"


def backoff_status(now_iso: str, last_backoff_until: str) -> str:
    if not last_backoff_until:
        return "inactive"
    now = parse_iso_z(now_iso)
    backoff_until = parse_iso_z(last_backoff_until)
    if now is None or backoff_until is None:
        return "unknown"
    return "active" if backoff_until > now else "expired"
