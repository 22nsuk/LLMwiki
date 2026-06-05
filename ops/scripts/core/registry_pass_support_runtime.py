from __future__ import annotations

import datetime as dt


def registry_review_exempt_paths(registry_contract: dict) -> set[str]:
    exempt_paths = {registry_contract["raw_registry_page"]}
    exempt_paths.update(registry_contract.get("raw_registry_shard_pages", []))
    return exempt_paths


def registry_entry_target_report_path(entry: dict, corpus_roots: dict[str, str]) -> str | None:
    corpus = entry.get("corpus")
    target_page = entry.get("target_page")
    if not corpus or not target_page:
        return None
    corpus_root = corpus_roots.get(corpus)
    if corpus_root is None:
        return None
    return f"{corpus_root}/{target_page}.md"


def registry_topic_family(entry: dict) -> str | None:
    value = entry.get("topic_family")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def registry_topic_subfamily(entry: dict) -> str | None:
    value = entry.get("topic_subfamily")
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def registry_entry_line_span(entry: dict) -> int | None:
    start_line = entry.get("_entry_start_line")
    end_line = entry.get("_entry_end_line")
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return None
    if end_line < start_line:
        return None
    return end_line - start_line + 1


def _parse_registry_iso_date(value: object) -> dt.date | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if "T" in text:
            return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _backlog_entry_age_days(entry: dict, *, today: dt.date) -> int | None:
    if entry.get("status") != "registered-not-ingested":
        return None
    registered_on = _parse_registry_iso_date(entry.get("registered_on"))
    if registered_on is None:
        return None
    return max(0, (today - registered_on).days)


__all__ = [
    "_backlog_entry_age_days",
    "_parse_registry_iso_date",
    "registry_entry_line_span",
    "registry_entry_target_report_path",
    "registry_review_exempt_paths",
    "registry_topic_family",
    "registry_topic_subfamily",
]
