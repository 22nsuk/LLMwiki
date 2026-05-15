from __future__ import annotations

import re


DEFAULT_ASCII_SUMMARY_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_DATE_SUFFIX_RE = re.compile(r"^(?P<slug>.+)-(?P<date>\d{4}-\d{2}-\d{2})$")


def source_stem_slug_and_date(stem: str) -> tuple[str, str | None]:
    body = stem
    if body.startswith("source--"):
        body = body[len("source--"):]
    match = _DATE_SUFFIX_RE.match(body)
    if not match:
        return body, None
    return match.group("slug"), match.group("date")


def source_slug_validation_detail(stem: str, config: dict | None) -> dict | None:
    if not stem.startswith("source--"):
        return None

    slug, date_suffix = source_stem_slug_and_date(stem)
    review_config = config or {}
    expected_pattern = review_config.get(
        "ascii_summary_slug_pattern",
        DEFAULT_ASCII_SUMMARY_SLUG_PATTERN,
    )
    disallowed_substrings = list(review_config.get("disallowed_slug_substrings", []))

    violations: list[str] = []
    try:
        compiled_pattern = re.compile(expected_pattern)
    except re.error:
        compiled_pattern = re.compile(DEFAULT_ASCII_SUMMARY_SLUG_PATTERN)
        expected_pattern = DEFAULT_ASCII_SUMMARY_SLUG_PATTERN
        violations.append("invalid_config_pattern_fallback_used")

    if not compiled_pattern.fullmatch(slug):
        violations.append("slug_not_ascii_summary")

    matched_disallowed = [
        item
        for item in disallowed_substrings
        if isinstance(item, str) and item and item in slug
    ]
    if matched_disallowed:
        violations.append("slug_contains_disallowed_substring")

    if not violations:
        return None

    return {
        "stem": stem,
        "slug": slug,
        "date_suffix": date_suffix,
        "violations": violations,
        "expected_pattern": expected_pattern,
        "matched_disallowed_substrings": matched_disallowed,
    }

