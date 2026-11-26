from __future__ import annotations

import pytest

from ops.scripts.registry.raw_capture_review_runtime import capture_review_reasons
from ops.scripts.registry.raw_intake_source_quality import extract_clean_lead

TITLE = "Library extends evening opening hours"
SECOND_TITLE = "Orbital telescope surveys distant galaxies"
ARTICLE = (
    "The library will extend evening opening hours on weekdays following a six-week trial. "
    "The council allocated funding for additional staff, while weekend hours remain unchanged."
)
OTHER = (
    "The observatory launched an infrared telescope aboard a satellite to measure distant galaxies. "
    "Researchers expect the instrument to provide calibrated measurements throughout its first mission."
)
SUMMARY = "**AI-generated summary**\n\n" + ARTICLE + "\n\nRead the full article for context.\n"

PHOTO_ALT = "Archive photograph of the old council building and surrounding streets before reconstruction"
REFERENCE_IMAGE = f"![{PHOTO_ALT}][Photo]"
PHOTO_DEFINITION = '[photo]: https://example.com/image.jpg\n  "An archive photograph"'
PHOTO_CREDIT = "Photo credit: Example Archive. Copyright 2024."
PHOTO_AND_LEAD = "*도서관 외관. 무단 전재 및 재배포 금지. /사진=자료실* " + ARTICLE
TRAILING_CREDIT = " /사진=자료실 © Example Archive"
CREDITED_FOOTER = "Copyright 2024 Example Press /사진=자료실"
REPRINT_FOOTER = "무단 전재 및 재배포 금지"
PAREN_CREDIT = "(ⓒ Example Archive 제공)"
COLON_FOOTER = "매일경제: " + REPRINT_FOOTER
QUOTED_NOTICE_ARTICLE = (
    "법원은 지역 신문의 사진 이용을 제한한 조항을 심리했고, 원문 사용을 허가받지 않은 포털 운영자의 책임을 인정했다. "
    "재판부가 인용한 공지의 마지막 문장은 다음과 같다: 재배포를 금지합니다."
)
EXTENDED_REPRINT_FOOTER = REPRINT_FOOTER + ". AI 학습 및 활용 금지."
REPRINT_ARTICLE = (
    "법원은 지역 신문 기사를 무단 전재한 포털 운영자에게 손해배상 책임이 있다고 판결했다. "
    "재판부는 원문을 허가 없이 복제한 행위가 시장 경쟁을 해쳤다고 설명했으며, "
    "운영자는 판결에 불복해 항소할 계획이라고 밝혔다."
)
REPORT_COVER = f"# {TITLE}\n\nPrepared for the council\n\n# Research Report 27\n\n© 2024 Example Council"
REPORT = REPORT_COVER + "\n\n" + ARTICLE + "\n\n# Staffing and Budget Forecasts\n\n" + ARTICLE


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
        ("입력: 2024-03-05\n\n© Example Archive\n\n" + ARTICLE, TITLE, "capture.md", []),
        (PHOTO_CREDIT + "\n\n" + ARTICLE, TITLE, "capture.md", []),
        (ARTICLE + "\n\n" + PHOTO_AND_LEAD, TITLE, "capture.md", []),
        (PHOTO_CREDIT, TITLE, "capture.md", []),
        (PAREN_CREDIT, TITLE, "capture.md", ["raw_capture_body_missing"]),
        ("The library facade. Copyright 2024. 무단 전재 및 재배포 금지. /사진=자료실\n\n" + ARTICLE,
         TITLE, "capture.md", []),
        ("# " + TITLE + "\n\n저작권자 Example Press 무단전재 및 재배포 금지\n\n" + OTHER,
         TITLE, "capture.md", []),
        (SUMMARY + "\n" + PAREN_CREDIT, TITLE, "capture.md", ["raw_capture_summary_only"]),
        (PHOTO_AND_LEAD, TITLE, "capture.md", []),
        ("*The library facade. Copyright © Example Press. 무단 전재 및 재배포 금지. /사진=자료실* " + ARTICLE,
         TITLE, "capture.md", []),
        ("*Photo credit: © Example Archive* " + OTHER, TITLE, "capture.md", ["raw_capture_title_body_mismatch"]),
        ("Warehouses by the harbor (ⓒ Example 제공, 무단 전재 및 재배포 금지)", TITLE, "capture.md", []),
        (f"{ARTICLE}\n\n{PHOTO_CREDIT}\n\nCopyright Example Press\n\n{OTHER}",
         TITLE, "capture.md", []),
        ("**Photo: © Example Archive**" + OTHER, TITLE, "capture.md", ["raw_capture_title_body_mismatch"]),
        ("Research Report 27\n\n© 2024 Example Council\n\n" + ARTICLE, TITLE, "capture.md", []),
        (REPORT_COVER, TITLE, "capture.md", ["raw_capture_body_missing"]),
        (REPORT_COVER + "\n\n" + SUMMARY, TITLE, "capture.md", ["raw_capture_summary_only"]),
        (REPORT, TITLE, "capture.md", []),
        (REPORT + "\n\n# Orbital telescope surveys distant galaxies\n\n" + OTHER,
         TITLE, "capture.md", ["raw_capture_multiple_articles"]),
        (REPORT + "\n\nCopyright Example Press\n\n" + OTHER, TITLE, "capture.md", []),
        ("# Annual Report\n\nBrief update.\n\nCopyright 2024 Example Press\n\n" + OTHER,
         TITLE, "capture.md", ["raw_capture_title_body_mismatch"]),
        (ARTICLE + "\n\nCopyright Example Press\n\n" + OTHER, TITLE, "capture.md", []),
        (ARTICLE + "\n\nCopyright Example Press\n\n## Related articles\n\n" + OTHER, TITLE, "capture.md", []),
        ("# " + TITLE + "\n\n" + ARTICLE + "\n\n# Orbital telescope surveys distant galaxies\n\n" + OTHER, TITLE, "capture.md", ["raw_capture_multiple_articles"]),
        (ARTICLE, "도서관 야간 운영 시간 연장", "capture.md", []),
        ("<!-- " + OTHER + " -->\n\n" + ARTICLE, TITLE, "capture.md", []),
        (f"<div>\n{ARTICLE}\n</div>", TITLE, "capture.md", []),
        (ARTICLE, "Brief", "capture.md", []),
    ],
)
def test_capture_review_signals(body, title, filename, expected):
    assert capture_review_reasons(body=body, title=title, filename=filename) == expected


@pytest.mark.parametrize("layout", [
    "{credit} {body}", "{body} {credit}", "*{body}* {credit}", "{body} *{credit}*", "*{body} {credit}*",
    "**[{body}](https://example.com/article)** *{credit}*",
])
@pytest.mark.parametrize("body", [ARTICLE, ARTICLE.rstrip(".")])
def test_credit_span_is_independent_of_emphasis(layout, body):
    line = layout.format(body=body, credit=PAREN_CREDIT)
    assert extract_clean_lead(line) == body
    assert capture_review_reasons(body=line, title=TITLE, filename="capture.md") == []


@pytest.mark.parametrize(("line", "lead"), [
    (f"{ARTICLE} {PAREN_CREDIT} {OTHER}", ARTICLE + " " + OTHER),
    (f"{ARTICLE} {PAREN_CREDIT} {OTHER} {PAREN_CREDIT}", ARTICLE + " " + OTHER),
    (f"{ARTICLE} *사진: 자료실* {OTHER}", f"{ARTICLE} *사진: 자료실* {OTHER}"),
    (f"{ARTICLE} /사진=자료실", f"{ARTICLE} /사진=자료실"),
    (f"Photo credit: © Example Archive. {ARTICLE}", f"Photo credit: © Example Archive. {ARTICLE}"),
    (f"![cover](image.jpg){ARTICLE}", ARTICLE),
    ("before![cover](image.jpg)after", "before after"),
    (f"(© 2024 Example Archive) {ARTICLE}", f"(© 2024 Example Archive) {ARTICLE}"),
    (f"{ARTICLE} (ⓒ Example Archive 제공, 무단 전재 금지)", ARTICLE),
    (PHOTO_CREDIT, PHOTO_CREDIT),
    (PAREN_CREDIT, ""),
    ("자료 화면 /사진=자료실에서 받은 뒤 편집부가 내용을 확인했다.", "자료 화면 /사진=자료실에서 받은 뒤 편집부가 내용을 확인했다."),
    (f"![사진: 자료실](image.jpg) {ARTICLE}", ARTICLE),
    (f"`{PAREN_CREDIT}` {ARTICLE}", PAREN_CREDIT + " " + ARTICLE),
])
def test_credit_spans_keep_surrounding_text(line, lead):
    assert extract_clean_lead(line) == lead


@pytest.mark.parametrize(("body", "lead"), [
    (f"{REFERENCE_IMAGE}\n\n{PHOTO_DEFINITION}", ""),
    (f"{REFERENCE_IMAGE}\n\n{ARTICLE}\n\n{PHOTO_DEFINITION}", ARTICLE),
    (f"{PHOTO_DEFINITION}\n\nBefore ![Archive\nphotograph][PHOTO] after", "Before after"),
    (f"{PHOTO_DEFINITION}\n\n![photo][] ![photo] {ARTICLE}", ARTICLE),
    (f"{REFERENCE_IMAGE}\n\n```\n{PHOTO_DEFINITION}\n```", REFERENCE_IMAGE),
])
def test_reference_images_use_document_definitions(body, lead):
    assert extract_clean_lead(body) == lead
    assert capture_review_reasons(body=body, title="", filename="capture.md") == (
        [] if lead else ["raw_capture_body_missing"]
    )


@pytest.mark.parametrize("notice", [CREDITED_FOOTER, COLON_FOOTER, EXTENDED_REPRINT_FOOTER, "> " + REPRINT_FOOTER])
@pytest.mark.parametrize(("following", "mixed"), [
    ("", False), (OTHER, False), (f"- {OTHER}", False),
    (f"## Related articles\n\n# {SECOND_TITLE}\n\n{OTHER}", False),
    (f"# {SECOND_TITLE}", False), (f"# {SECOND_TITLE}\n\n- {OTHER}", False),
    (f"# {SECOND_TITLE}\n\n> {OTHER}", False), (f"# {SECOND_TITLE}\n\n```\n{OTHER}\n```", False),
    (f"# {SECOND_TITLE}\n\n{OTHER}", True),
])
def test_second_story_needs_a_heading_and_article_prose(notice, following, mixed):
    body = f"# {TITLE}\n\n{ARTICLE}\n\n{notice}\n\n{following}"
    assert capture_review_reasons(body=body, title=TITLE, filename="capture.md") == (
        ["raw_capture_multiple_articles"] if mixed else []
    )


@pytest.mark.parametrize("lead", [
    REPRINT_ARTICLE,
    REPRINT_FOOTER + ". AI 학습에 대한 법원의 판단은 달랐다.",
    "기사에 실린 조항의 제목은 " + EXTENDED_REPRINT_FOOTER,
    "The article quotes Example Press " + REPRINT_FOOTER,
    "법원은 무단 전재 및 재배포를 금지합니다.",
    "법원이 재배포를 금지합니다.",
    "공지: 재배포를 금지합니다.",
    "무단 전재한 기사가 여러 매체에 재배포됐다고 법원은 밝혔다.",
    "법원은 재배포 금지 조항이 해당 기사에 적용되는지 판단했다.",
])
def test_reprint_reporting_preserves_the_lead(lead):
    assert extract_clean_lead(lead) == lead
    assert capture_review_reasons(body=lead, title="", filename="capture.md") == []


def test_bracketed_usage_terms_preserve_the_paragraph():
    line = f"자료 사진 [열람 전용. 재배포 금지.] {ARTICLE}"
    assert extract_clean_lead(line) == line


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


@pytest.mark.parametrize(
    ("transport", "cookie", "article", "expected"),
    [
        (False, True, SUMMARY, ["raw_capture_summary_only"]),
        (True, True, SUMMARY, ["raw_capture_summary_only"]),
        (False, True, SUMMARY + f"\n# {TITLE}\n\n" + SUMMARY, ["raw_capture_summary_only"]),
        (True, False, "# Orbital telescope surveys distant galaxies\n\n" + OTHER,
         ["raw_capture_heading_title_mismatch", "raw_capture_title_body_mismatch"]),
        (True, False, ARTICLE, []),
        (False, True, ARTICLE, []),
        (True, False, PHOTO_AND_LEAD, []),
        (False, False, ARTICLE + TRAILING_CREDIT, []),
        (False, False, f"**{ARTICLE}{TRAILING_CREDIT}**", []),
        (False, False, f"Photo credit: © Example Archive. {ARTICLE}", []),
        (False, False, f"{REFERENCE_IMAGE}\n\n{PHOTO_DEFINITION}", ["raw_capture_body_missing"]),
        (False, False, f"{REFERENCE_IMAGE}\n\n[photo]:\nblob:http://localhost/123", ["raw_capture_body_missing"]),
        (False, False, f"{REFERENCE_IMAGE}\n\n{PHOTO_DEFINITION}\n\n{ARTICLE}", []),
        (False, False, f"![Photo](blob:http://localhost/123) {ARTICLE}", []),
        (False, True, ARTICLE + f" Unique introduction.\n\n# {TITLE}\n\n" + ARTICLE, []),
        (False, False, f"{ARTICLE}\n\n{COLON_FOOTER}\n\n{OTHER}", []),
        (False, False, f"{ARTICLE}\n\n{CREDITED_FOOTER}\n\n- {OTHER}", []),
        (False, False, f"{ARTICLE}\n\n{COLON_FOOTER}\n\n# {SECOND_TITLE}\n\n{OTHER}",
         ["raw_capture_multiple_articles"]),
        (False, False, QUOTED_NOTICE_ARTICLE + " /사진=자료실", []),
        (False, False, f"*{ARTICLE}* {PAREN_CREDIT}", []),
        (False, False, f"{ARTICLE} *{PAREN_CREDIT}*", []),
        (False, False, f"{ARTICLE} /사진=자료실\n\n# {TITLE}\n\n{ARTICLE}", []),
        (False, False, REPRINT_ARTICLE, []),
        (False, False, REPORT, []),
        (False, False, REPORT + "\n\nCopyright Example Press\n\n" + OTHER, []),
    ],
)
def test_capture_reports_agree_before_and_after_normalization(tmp_path, transport, cookie, article, expected):
    from ops.scripts.eval.wiki_lint import lint
    from ops.scripts.registry.raw_intake_source_quality import build_report
    from ops.scripts.registry.raw_markdown_runtime import (
        apply_raw_markdown_normalization,
        raw_markdown_quality_report,
    )
    from tests.minimal_vault_runtime import seed_minimal_vault
    from tests.test_raw_intake_source_quality import (
        matrix_entry,
        write_matrix,
        write_source,
    )

    seed_minimal_vault(tmp_path)
    path = tmp_path / "raw" / "source.md"
    header = (
        f"Title: {TITLE}\nURL Source: https://example.com/story\nMarkdown Content:\n"
        if transport else
        f'---\ntitle: "{TITLE}"\nsource: "https://example.com/story"\n'
        'published: "unknown"\ncreated: "unknown"\n---\n'
    )
    banner = "This website uses cookies\n\nAllow all Customize Allow selection Deny\n\n" if cookie else ""
    text = header + f"# {TITLE}\n\n" + banner + article
    # A swapped capture has only the wrong article heading, not the declared one.
    if article.startswith("#"):
        text = header + article
    path.write_text(text, encoding="utf-8")
    write_source(tmp_path / "wiki" / "source--quality.md", summary=ARTICLE, key_points=[
        "The library trial measured weekday attendance over six weeks.",
        "The council approved additional staffing for longer opening hours.",
        "Weekend schedules remained outside the scope of the trial.",
        "The announcement did not report long-term operating costs.",
    ])
    write_matrix(tmp_path / "matrix.json", [matrix_entry()])

    for phase in ("original", "normalized"):
        before = path.read_text(encoding="utf-8")
        assert raw_markdown_quality_report(tmp_path, path).capture_review_reasons == expected, phase
        candidates = [item for item in lint(tmp_path)["review_candidates"]
                      if item["type"] == "raw_snapshot_capture_review"]
        assert [item["detail"]["reasons"] for item in candidates] == ([expected] if expected else []), phase
        report = build_report(tmp_path, matrix_path="matrix.json")
        if "raw_capture_body_missing" in expected:
            assert report["findings"][0]["cleaned_raw_lead"]["status"] == "empty", phase
            assert set(report["findings"][0]["issues"]) == {
                "raw_body_empty", "cleaned_raw_lead_below_min_chars", *expected,
            }, phase
            assert report["status"] == "fail", phase
        else:
            assert report["findings"][0]["issues"] == expected, phase
            assert report["status"] == ("attention" if expected else "pass"), phase
        assert path.read_text(encoding="utf-8") == before
        result = apply_raw_markdown_normalization(tmp_path, path)
        assert result.manual_review_reasons == expected, phase
        assert article in result.text
        if phase == "original":
            assert ("cookie_banner" in result.removed_noise_classes) == cookie
            assert result.quality.capture_review_reasons == expected
        else:
            assert not result.changed
            assert path.read_text(encoding="utf-8") == before
