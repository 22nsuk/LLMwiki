"""Read-only, lexical capture diagnostics; these signals do not verify claims."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

SUMMARY_START = re.compile(r"^(?:세\s*줄\s*요약|AI\s*요약|AI[- ]generated summary|Auto(?:matic)? summary)$", re.I)
SUMMARY_END = re.compile(r"인공지능이 자동으로|기사 본문과 함께|End of (?:AI|auto).*summary|Read the full article", re.I)
RELATED_START = re.compile(r"^(?:관심기사 예측|관련\s*기사|함께 (?:읽기|보면)|추천\s*기사|.*뉴스를 추천해|Related (?:articles|stories)|Recommended (?:articles|stories))", re.I)
FOOTER_START = re.compile(r"^[<\[\\\s]*(?:저작권자|Copyright|©)", re.I)
REPRINT_NOTICE = re.compile(r"무단\s*전재.*재배포", re.I)
COPYRIGHT_MARK = re.compile(r"©|ⓒ|copyright\b|저작권자|무단\s*전재", re.I)
OPENING_CREDIT = re.compile(r"^(?:©|copyright\s+(?:©\s*)?\d{4}\b)", re.I)
PHOTO_CREDIT = re.compile(
    r"^(?:(?:photo(?:graph)?|image)(?:\s+credit)?|(?:사진|이미지)(?:\s*제공)?)\s*[:=]"
    r"|/\s*(?:사진|이미지)\s*[:=]|\([©ⓒ][^()]*제공\s*[,)]", re.I,
)
REPORT_LABEL = re.compile(r"\breport\s+(?:no\.?\s*)?\d+\b|\b(?:annual|research|technical) report\b|보고서", re.I)
UI_LINE = re.compile(r"^(?:(?:송고|입력|수정)(?:\s|:)|Published:|Updated:|Title:|URL Source:|Published Time:|Markdown Content:|본문 바로가기|메뉴 바로가기|광고$|닫기$|ESC 닫기$|공유$|구독$|로그인$)", re.I)
STOP_WORDS = {"the", "and", "for", "with", "from", "this", "that", "after", "before", "news", "report", "기사", "관련", "대한"}
MIN_TITLE_TOKENS = 3
MIN_BODY_COMPARISON_CHARS = 160
MIN_BOUNDARY_PROSE_CHARS = 80


def _plain(line: str) -> str:
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"<[^>]*>", "", line)
    return line.strip(" #*`_>\t\\")


def _tokens(text: str) -> set[str]:
    text = unicodedata.normalize("NFKC", text).casefold()
    return {word for word in re.findall(r"[^\W\d_]+", text) if len(word) >= 2 and word not in STOP_WORDS}


def _disjoint_title(title: str, other: str) -> bool:
    left, right = _tokens(title), _tokens(other)
    if len(left) < MIN_TITLE_TOKENS or len(right) < MIN_TITLE_TOKENS:
        return False
    # A translated headline is not evidence of a bad capture. Limit comparison
    # to the same Latin/Hangul script, without guessing translations/entities.
    def script(words: set[str]) -> str:
        if any(re.search(r"[가-힣]", word) for word in words):
            return "hangul"
        return "latin" if all(re.fullmatch(r"[a-z]+", word) for word in words) else "other"

    if script(left) != script(right) or script(left) == "other":
        return False
    return not any(a.startswith(b) or b.startswith(a) for a in left for b in right)


def _photo_credit_prefix(line: str, credit: re.Match[str]) -> str:
    prefix = line[:credit.start()].rstrip()
    plain = _plain(prefix)
    if FOOTER_START.match(plain):
        return prefix
    if REPRINT_NOTICE.search(plain):
        return ""
    if credit[0].startswith("/") or prefix.endswith((".", "!", "?", "。", "！", "？")):
        return prefix
    return ""


def without_photo_credit(line: str) -> str:
    """Keep article text and footer boundaries sharing a line with a photo credit."""
    if not COPYRIGHT_MARK.search(line):
        return line
    emphasis = re.match(r"^(\*{1,2}|_{1,2})(.+?)\1(.*)$", line)
    if emphasis and COPYRIGHT_MARK.search(emphasis[2]):
        credit = PHOTO_CREDIT.search(emphasis[2])
        if credit:
            prefix = _photo_credit_prefix(emphasis[2], credit)
            return " ".join(filter(None, (prefix, emphasis[3].lstrip())))
    credit = PHOTO_CREDIT.search(line)
    return _photo_credit_prefix(line, credit) if credit else line


def _on_report_cover(headings: list[tuple[str, int]], prose: list[str]) -> bool:
    # A report identifier can be a heading or a short line on a printed cover.
    if any(len(p) >= MIN_BOUNDARY_PROSE_CHARS or p.endswith((".", "!", "?")) for p in prose):
        return False
    return any(REPORT_LABEL.search(title) for title, _ in headings) or any(REPORT_LABEL.search(p) for p in prose)


def _has_second_article_heading(
    headings: list[tuple[str, int]], prose: list[str], *, report_cover: bool,
) -> bool:
    first_lead = next((i for i, p in enumerate(prose) if len(p) >= MIN_BOUNDARY_PROSE_CHARS), len(prose))
    for i, (title, start) in enumerate(headings[1:], 1):
        if start <= first_lead or not _disjoint_title(headings[0][0], title):
            continue
        if not report_cover:
            return True
        # An exported report can use H1 for its chapters. Check the prose under
        # this particular heading, so a separate story can still be detected.
        end = headings[i + 1][1] if i + 1 < len(headings) else len(prose)
        section = " ".join(prose[start:end])
        if len(section) >= MIN_BOUNDARY_PROSE_CHARS and _disjoint_title(headings[0][0], section):
            return True
    return False


def _article_parts(body: str) -> tuple[list[str], list[str], bool, bool]:
    """Exclude recognized UI/summary regions only for analysis, never for writes."""
    prose: list[str] = []
    headings: list[tuple[str, int]] = []
    cover_end: int | None = None
    current: list[str] = []
    summary = False
    saw_summary = False
    footer = False
    extra_article = False
    fence = ""

    def flush() -> None:
        nonlocal extra_article
        paragraph = " ".join(current).strip()
        if paragraph:
            if footer:
                extra_article |= len(paragraph) >= MIN_BOUNDARY_PROSE_CHARS
            else:
                prose.append(paragraph)
        current.clear()

    for line in re.sub(r"<!--.*?-->", "", body, flags=re.S).splitlines():
        stripped = line.strip()
        fence_match = re.match(r"^(`{3,}|~{3,})", stripped)
        if fence_match:
            marker = fence_match.group(1)
            if not fence:
                flush()
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        stripped = without_photo_credit(stripped)
        plain = _plain(stripped)
        if RELATED_START.search(plain):
            flush()
            break
        if SUMMARY_START.fullmatch(plain):
            flush()
            summary = saw_summary = True
            continue
        if SUMMARY_END.search(plain):
            summary = False
            continue
        if summary:
            continue
        if FOOTER_START.match(plain) or REPRINT_NOTICE.search(plain):
            flush()
            if not (footer or saw_summary):
                if cover_end is None and _on_report_cover(headings, prose):
                    cover_end = len(prose)
                    continue
                if not prose and OPENING_CREDIT.match(plain):
                    continue
            footer = True
            continue
        if re.match(r"^#\s+", stripped):
            flush()
            headings.append((plain, len(prose)))
            continue
        if stripped.startswith("#") or UI_LINE.search(plain):
            flush()
            continue
        if not plain or stripped.startswith(("![", "- ![")) or re.fullmatch(r"[-* ]*\[[^\]]+\]\([^)]*\)", stripped):
            flush()
            continue
        # Repeated headlines and punctuation/date-only UI are not article prose.
        if any(plain == title for title, _ in headings) or re.fullmatch(r"[\W\d_]+", plain):
            flush()
            continue
        current.append(plain)
    flush()
    extra_article = extra_article or _has_second_article_heading(headings, prose, report_cover=cover_end is not None)
    return prose[cover_end:], [title for title, _ in headings], saw_summary, extra_article


def capture_review_reasons(*, body: str, title: str, filename: str) -> list[str]:
    """Return stable review codes, not an admission verdict or edited content.

    Missing/unsupported markers, short titles, translations, generic filenames,
    paraphrases and lexical overlap can evade these deliberately bounded rules.
    """
    prose, headings, saw_summary, extra_article = _article_parts(body)
    title = title or (headings[0] if headings else "")
    prose = [paragraph for paragraph in prose if _plain(paragraph) != _plain(title)]
    reasons: list[str] = []
    if not prose:
        reasons.append("raw_capture_summary_only" if saw_summary else "raw_capture_body_missing")
    if extra_article:
        reasons.append("raw_capture_multiple_articles")
    if title and headings and _disjoint_title(title, headings[0]):
        reasons.append("raw_capture_heading_title_mismatch")
    # Human-readable filenames can reveal a swapped capture even when the
    # copied frontmatter and body agree. Slugs, IDs and hashes are not titles.
    stem = Path(filename).stem
    if " " in stem and title and _disjoint_title(title, stem):
        reasons.append("raw_capture_filename_title_mismatch")
    article = " ".join(prose)
    if len(article) >= MIN_BODY_COMPARISON_CHARS and title and _disjoint_title(title, article):
        reasons.append("raw_capture_title_body_mismatch")
    return reasons
