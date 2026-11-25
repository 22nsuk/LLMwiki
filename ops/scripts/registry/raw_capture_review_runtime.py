"""Read-only, lexical capture diagnostics; these signals do not verify claims."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

SUMMARY_START = re.compile(r"^(?:세\s*줄\s*요약|AI\s*요약|AI[- ]generated summary|Auto(?:matic)? summary)$", re.I)
SUMMARY_END = re.compile(r"인공지능이 자동으로|기사 본문과 함께|End of (?:AI|auto).*summary|Read the full article", re.I)
RELATED_START = re.compile(r"^(?:관심기사 예측|관련\s*기사|함께 (?:읽기|보면)|추천\s*기사|.*뉴스를 추천해|Related (?:articles|stories)|Recommended (?:articles|stories))", re.I)
FOOTER = re.compile(r"^(?:[<\[\\\s]*(?:저작권자|Copyright|©)|.*무단\s*전재.*재배포)", re.I)
UI_LINE = re.compile(r"^(?:송고\s|입력\s|수정\s|Published:|Updated:|Title:|URL Source:|Published Time:|Markdown Content:|본문 바로가기|메뉴 바로가기|광고$|닫기$|ESC 닫기$|공유$|구독$|로그인$)", re.I)
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


def _article_parts(body: str) -> tuple[list[str], list[str], bool, bool]:
    """Exclude recognized UI/summary regions only for analysis, never for writes."""
    prose: list[str] = []
    headings: list[str] = []
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
        if FOOTER.search(plain):
            flush()
            footer = True
            continue
        if re.match(r"^#\s+", stripped):
            flush()
            if headings and _disjoint_title(headings[0], plain) and any(len(p) >= MIN_BOUNDARY_PROSE_CHARS for p in prose):
                extra_article = True
            headings.append(plain)
            continue
        if stripped.startswith("#") or UI_LINE.search(plain):
            flush()
            continue
        if not plain or stripped.startswith(("![", "- ![")) or re.fullmatch(r"[-* ]*\[[^\]]+\]\([^)]*\)", stripped):
            flush()
            continue
        # Repeated headlines and punctuation/date-only UI are not article prose.
        if plain in headings or re.fullmatch(r"[\W\d_]+", plain):
            flush()
            continue
        current.append(plain)
    flush()
    return prose, headings, saw_summary, extra_article


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
