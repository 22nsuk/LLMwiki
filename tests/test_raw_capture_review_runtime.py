from __future__ import annotations

import pytest

from ops.scripts.registry.raw_capture_review_runtime import capture_review_reasons

TITLE = "Library extends evening opening hours"
ARTICLE = (
    "The library will extend evening opening hours on weekdays following a six-week trial. "
    "The council allocated funding for additional staff, while weekend hours remain unchanged."
)
OTHER = (
    "The observatory launched an infrared telescope aboard a satellite to measure distant galaxies. "
    "Researchers expect the instrument to provide calibrated measurements throughout its first mission."
)
SUMMARY = "**AI-generated summary**\n\n" + ARTICLE + "\n\nRead the full article for context.\n"


@pytest.mark.parametrize(
    ("body", "title", "filename", "expected"),
    [
        ("# " + TITLE, TITLE, "capture.md", ["raw_capture_body_missing"]),
        (TITLE, TITLE, "capture.md", ["raw_capture_body_missing"]),
        ("```\n" + OTHER + "\n```", TITLE, "capture.md", ["raw_capture_body_missing"]),
        (SUMMARY + "\n## Related articles\n\n" + OTHER, TITLE, "capture.md", ["raw_capture_summary_only"]),
        ("**세 줄 요약**\n\n" + ARTICLE, TITLE, "capture.md", ["raw_capture_summary_only"]),
        (SUMMARY + "\n" + ARTICLE, TITLE, "capture.md", []),
        ("# " + TITLE + "\n\n" + ARTICLE, TITLE, "library-2024-03.md", []),
        (ARTICLE, TITLE, "Orbital telescope surveys distant galaxies.md", ["raw_capture_filename_title_mismatch"]),
        (ARTICLE, TITLE, "Library — extends evening opening hours!.md", []),
        (OTHER, TITLE, "capture.md", ["raw_capture_title_body_mismatch"]),
        ("# Orbital telescope surveys distant galaxies\n\n" + ARTICLE, TITLE, "capture.md", ["raw_capture_heading_title_mismatch"]),
        (ARTICLE + "\n\nCopyright Example Press\n\n" + OTHER, TITLE, "capture.md", ["raw_capture_multiple_articles"]),
        (ARTICLE + "\n\nCopyright Example Press\n\n## Related articles\n\n" + OTHER, TITLE, "capture.md", []),
        ("# " + TITLE + "\n\n" + ARTICLE + "\n\n# Orbital telescope surveys distant galaxies\n\n" + OTHER, TITLE, "capture.md", ["raw_capture_multiple_articles"]),
        (ARTICLE, "도서관 야간 운영 시간 연장", "capture.md", []),
        ("<!-- " + OTHER + " -->\n\n" + ARTICLE, TITLE, "capture.md", []),
        (ARTICLE, "Brief", "capture.md", []),
    ],
)
def test_capture_review_signals(body, title, filename, expected):
    assert capture_review_reasons(body=body, title=title, filename=filename) == expected


def test_korean_summary_disclaimer_and_related_photo_caption_are_not_article_body():
    body = (
        "송고 2024년03월05일\n\n**세 줄 요약**\n\n"
        "시립 도서관의 야간 운영 시간이 연장된다.\n\n"
        "인공지능이 자동으로 줄인 요약 기술을 사용합니다.\n"
        "전체 내용을 이해하기 위해서는 기사 본문과 함께 읽어야 합니다.\n\n"
        "### 관심기사 예측\n\n- ![사진](photo.jpg)\n\t" + ARTICLE
    )
    assert capture_review_reasons(body=body, title="도서관 야간 운영 시간 연장", filename="snapshot.md") == [
        "raw_capture_summary_only"
    ]


def test_korean_particles_do_not_turn_shared_title_words_into_mismatch():
    title = "도서관 야간 운영 시간 연장"
    body = "도서관은 야간에 운영하는 시간을 연장한다고 밝혔다. " * 8
    assert capture_review_reasons(body=body, title=title, filename="snapshot.md") == []
