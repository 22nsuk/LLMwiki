from __future__ import annotations

import re
from typing import Any

from ops.scripts.eval.wiki_page_runtime import section_body

GENERIC_OPEN_QUESTION_FINGERPRINTS = (
    "반복 mechanism인가, 일회성 event인가",
    "repeated mechanism or one-off event",
)
GENERIC_SNAPSHOT_CAVEAT_FINGERPRINTS = (
    "snapshot caveat",
    "news snapshot caveat",
    "일반화된 snapshot caveat",
    "단일 기사 기반",
)
TITLE_REPEAT_PATTERNS = (
    re.compile(r"^에 관한 news snapshot이다\.?$"),
    re.compile(r"^에 관한 원문 기록이다\.?$"),
)


def _bullet_lines(section_text: str) -> list[str]:
    return [
        line.strip()
        for line in re.findall(r"^[-*]\s+(.+)$", section_text or "", flags=re.MULTILINE)
    ]


def _page_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return ""


def _summary_body(text: str) -> str:
    return (section_body(text, "Summary") or "").strip()


def _count_title_independent_facts(summary: str, title: str) -> int:
    if not summary or not title:
        return 0
    title_tokens = {token for token in re.split(r"\W+", title.lower()) if len(token) > 2}
    sentences = [part.strip() for part in re.split(r"[.!?]\s+", summary) if part.strip()]
    independent = 0
    for sentence in sentences:
        lowered = sentence.lower()
        if sentence == title or lowered.startswith(title.lower()):
            continue
        tokens = {token for token in re.split(r"\W+", lowered) if len(token) > 2}
        if tokens - title_tokens:
            independent += 1
    return independent


def _has_generic_fingerprint(text: str, fingerprints: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(fingerprint.lower() in lowered for fingerprint in fingerprints)


def evaluate_source_page_substance(text: str) -> dict[str, Any]:
    title = _page_title(text)
    summary = _summary_body(text)
    key_points_body = section_body(text, "Key points") or ""
    limitations_body = section_body(text, "Limitations / caveats") or ""
    key_points = _bullet_lines(key_points_body)
    limitations = _bullet_lines(limitations_body)
    failures: list[str] = []

    if len(key_points) < 4:
        failures.append("key_points_below_minimum")
    if len(limitations) < 1:
        failures.append("limitations_below_minimum")
    if title and summary and summary.strip().startswith(title):
        failures.append("summary_repeats_title")
    if title and key_points and key_points[0].strip() == title:
        failures.append("first_key_point_repeats_title")
    if _count_title_independent_facts(summary, title) < 2:
        failures.append("summary_lacks_source_specific_facts")
    for point in key_points:
        if point.endswith(("...", "…")):
            failures.append("truncated_key_point")
            break
        for pattern in TITLE_REPEAT_PATTERNS:
            if pattern.search(point):
                failures.append("boilerplate_key_point_pattern")
                break
    if _has_generic_fingerprint(limitations_body or "", GENERIC_SNAPSHOT_CAVEAT_FINGERPRINTS):
        failures.append("generic_snapshot_caveat")
    open_questions = section_body(text, "Open questions") or ""
    if _has_generic_fingerprint(open_questions, GENERIC_OPEN_QUESTION_FINGERPRINTS):
        failures.append("generic_open_question_fingerprint")

    return {
        "eval": "source_page_substance",
        "pass": not failures,
        "failures": failures,
        "metrics": {
            "key_point_count": len(key_points),
            "limitation_count": len(limitations),
            "title_independent_fact_count": _count_title_independent_facts(summary, title),
        },
    }
