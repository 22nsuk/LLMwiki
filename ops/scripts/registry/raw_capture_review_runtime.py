"""Read-only, lexical capture diagnostics; these signals do not verify claims."""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from markdown_it import MarkdownIt

SUMMARY_START = re.compile(r"^(?:세\s*줄\s*요약|AI\s*요약|AI[- ]generated summary|Auto(?:matic)? summary)$", re.I)
SUMMARY_END = re.compile(r"인공지능이 자동으로|기사 본문과 함께|End of (?:AI|auto).*summary|Read the full article", re.I)
RELATED_START = re.compile(r"^(?:관심기사 예측|관련\s*기사|함께 (?:읽기|보면)|추천\s*기사|.*뉴스를 추천해|Related (?:articles|stories)|Recommended (?:articles|stories))", re.I)
FOOTER_START = re.compile(r"^[<\[\\\s]*(?:저작권자|Copyright|©)", re.I)
# Each rights clause must end in a prohibition, including clauses after a period.
RESTRICTED_USE = r"(?:무단\s*전재|수집|재?배포|AI|학습|데이터|활용|이용)"
PROHIBITION = rf"(?:\s*(?:[·,&/-]|및|{RESTRICTED_USE}))*\s*[를을]?\s*금지(?:합니다)?"
REPRINT_NOTICE = re.compile(
    rf"(?:무단\s*전재|재배포){PROHIBITION}(?:\s*[.。!,;]\s*{RESTRICTED_USE}{PROHIBITION})*"
    r"[.。!＞>\]\\)*_\s]*$",
    re.I,
)
PUBLISHER_WORD = re.compile(r"[A-Z][\w'’-]*|of|the|and|&")
PUBLISHER_LABEL = re.compile(r"(?i:press|news|media|publishing|inc|ltd|co|corp)|[\w·-]*(?:신문|일보|뉴스|통신사)")
SENTENCE_END = (".", "!", "?", "。", "！", "？")
COPYRIGHT_MARK = re.compile(r"©|ⓒ|copyright\b|저작권자|무단\s*전재|재배포(?:를)?\s*금지", re.I)
OPENING_CREDIT = re.compile(r"^(?:©|copyright\s+(?:©\s*)?\d{4}\b)", re.I)
INLINE_MARKDOWN = MarkdownIt("commonmark")
PHOTO_HINT = re.compile(r"사진|이미지|photo|image|[©ⓒ]", re.I)
PHOTO_CREDIT = re.compile(
    r"(?<!\w)(?:(?:photo(?:graph)?|image)(?:\s+credit)?|(?:사진|이미지)(?:\s*제공)?)\s*[:=]"
    r"|/\s*(?:사진|이미지)\s*[:=]|\([©ⓒ][^()\x00]*\)", re.I,
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


NoticeKind = Literal["explicit", "publisher", "possible"]


def _reprint_kind(line: str, notice: re.Match[str]) -> NoticeKind | None:
    prefix = line[:notice.start()].strip(" \t*_<>[]()\\＜")
    if not prefix or prefix.endswith((" -", " |")):
        return "explicit"
    # A company abbreviation can end in a period even in a single publisher label.
    # A complete caption sentence before the attribution still excludes that label.
    signature = re.split(r"[ⓒ©]", prefix, maxsplit=1)
    publisher = re.sub(r"\b(Inc|Ltd|Co|Corp)\.", r"\1", signature[0], flags=re.I).strip().rstrip(" ,:：")
    if re.search(r"[.!?。！？]", publisher):
        return None
    if len(signature) == 2:
        return "explicit"
    if prefix.endswith((":", "：")) and publisher in {"공지", "안내", "인용"}:
        return None
    words = publisher.split()
    if not words or not all(PUBLISHER_WORD.fullmatch(word) for word in words[:-1]):
        return None
    label = words[-1]
    if PUBLISHER_LABEL.fullmatch(label):
        return "publisher"
    # A colon after an unmarked masthead can also introduce a quotation.
    # Let the surrounding paragraphs resolve it without dropping the raw lead.
    if (
        re.search(r"[가-힣]", label) is not None
        and re.fullmatch(r"[\w·-]+", label) is not None
        and not label.endswith(("은", "는", "에서"))
        and not (label.endswith(("이", "가")) and "금지합니다" in notice[0])
    ):
        return "possible" if prefix.endswith((":", "：")) else "publisher"
    return None


def is_reprint_footer(line: str) -> bool:
    notice = REPRINT_NOTICE.search(line)
    return notice is not None and _reprint_kind(line, notice) in {"explicit", "publisher"}


def _is_credit_caption(plain: str, credit: str) -> bool:
    """Whether the text immediately before this credit is a photo description."""
    if FOOTER_START.match(plain):
        return False
    notice = REPRINT_NOTICE.search(plain)
    if notice:
        if _reprint_kind(plain, notice):
            return False
        description = plain[:notice.start()].rstrip()
        # A short caption may end in a separate, nominal rights label. A full
        # prohibition sentence can itself be the quotation an article reports.
        if (
            description.endswith(SENTENCE_END)
            and len(description) < MIN_BOUNDARY_PROSE_CHARS
            and "금지합니다" not in notice[0]
        ):
            return True
        last_clause = re.split(r"[.!?。！？]", description.rstrip(" .!?。！？"))[-1].strip()
        return bool(
            FOOTER_START.match(last_clause)
            or last_clause.startswith("ⓒ")
            or last_clause.casefold() == "all rights reserved"
        )
    # A short image label with its own reprint notice is a caption. Otherwise
    # a closed attribution has an unambiguous extent, even after unpunctuated prose.
    return (
        credit.startswith("(")
        and REPRINT_NOTICE.search(credit.rstrip(")")) is not None
        and len(plain) < MIN_BOUNDARY_PROSE_CHARS
        and not plain.endswith(SENTENCE_END)
    )


def _photo_credits(text: str) -> Iterator[re.Match[str]]:
    for credit in PHOTO_CREDIT.finditer(text):
        if not credit[0].startswith("(") or re.search(r"제공\s*[,)]", credit[0]):
            yield credit


def _inline_credit_text(line: str) -> tuple[str, str, list[tuple[int, int]], bool]:
    """Project inline tokens onto display-text offsets. Inner scopes close first."""
    text: list[str] = []
    matchable: list[str] = []
    scopes: list[tuple[int, int]] = []
    opens: list[int] = []
    offset = 0
    credited_image = False
    for token in INLINE_MARKDOWN.parseInline(line)[0].children or []:
        if token.nesting == 1:
            opens.append(offset)
        elif token.nesting == -1:
            scopes.append((opens.pop(), offset))
        elif token.type == "image":
            credited_image |= any(_photo_credits(token.content))
        else:
            text.append(token.content)
            # Code and HTML are opaque. Link destinations never enter the projection.
            matchable.append(token.content if token.type == "text" else "\x00" * len(token.content))
            offset += len(token.content)
    return "".join(text), "".join(matchable), scopes, credited_image


def without_photo_credit(line: str) -> str:
    """Remove confirmed credit spans for analysis, preserving text on either side."""
    if not PHOTO_HINT.search(line):
        return line
    text, matchable, scopes, credited_image = _inline_credit_text(line)
    credits = list(_photo_credits(matchable))
    starts = [m.start() for m in credits]
    # Use the innermost scope containing the attribution, including its source.
    # Searching by offset avoids rescanning the line for each formatted span.
    owners = [(0, len(text))] * len(credits)
    scope_starts = {0}
    for left, right in reversed(scopes):
        scope_starts.add(left)
        for i in range(bisect_left(starts, left), bisect_left(starts, right)):
            credit = credits[i]
            if credit.end() <= right and (credit[0].startswith("(") or matchable[credit.end():right].strip()):
                owners[i] = (left, right)

    kept: list[str] = []
    cursor = 0
    for credit, (left, right) in zip(credits, owners, strict=True):
        if credit.start() < cursor:
            continue
        if not credit[0].startswith(("(", "/")) and credit.start() not in scope_starts:
            continue
        if credit[0].startswith("("):
            end = credit.end()
        else:
            source = matchable[credit.end():right].strip()
            if not source:
                continue
            # A bare label has no closing delimiter. Preserve ambiguous running
            # text after it rather than consuming the rest of the line.
            if (left, right) == (0, len(text)) and not COPYRIGHT_MARK.search(source):
                words = source.split()
                if len(words) > 1 and not all(PUBLISHER_WORD.fullmatch(word) for word in words):
                    continue
            end = right
        left = max(cursor, left)
        if not matchable[left:credit.start()].strip():
            left = cursor
        description = matchable[left:credit.start()].rstrip()
        start = left if _is_credit_caption(description, credit[0]) else credit.start()
        kept.append(text[cursor:start])
        cursor = end
    if not cursor and not credited_image:
        return line
    kept.append(text[cursor:])
    return "".join(kept).strip()


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


def _review_notice_blocks(
    prose: list[str], headings: list[tuple[str, int]], notices: dict[int, NoticeKind], start: int,
) -> tuple[list[str], bool]:
    """A publisher notice between article blocks is evidence of a boundary."""
    if not notices:
        return prose[start:], False
    new_headings = {
        position for i, (title, position) in enumerate(headings)
        if i == 0 or title.casefold() != headings[i - 1][0].casefold()
    }
    retained: list[str] = []
    preceding_article = ""
    pending_end: int | None = None
    quoted_predicate = False
    for i in range(start, len(prose)):
        paragraph = prose[i]
        kind = notices.get(i)
        if kind is not None:
            if preceding_article and pending_end is None:
                pending_end = len(retained)
                quoted_predicate = "금지합니다" in paragraph
            if kind == "possible":
                retained.append(paragraph)
            continue

        substantial = len(paragraph) >= MIN_BOUNDARY_PROSE_CHARS
        if pending_end is not None:
            # A new heading with prose or a substantial next paragraph can
            # confirm the cut. A finite prohibition can be an in-article quote;
            # require a topic change or new heading in that case.
            if i in new_headings:
                return retained[:pending_end], True
            if substantial:
                if not quoted_predicate or _tokens(preceding_article).isdisjoint(_tokens(paragraph)):
                    return retained[:pending_end], True
                pending_end = None
        if pending_end is None and (substantial or paragraph.endswith(SENTENCE_END)):
            preceding_article = paragraph
        retained.append(paragraph)
    return retained, False


def _article_parts(body: str) -> tuple[list[str], list[str], bool, bool]:
    """Exclude recognized UI/summary regions only for analysis, never for writes."""
    prose: list[str] = []
    headings: list[tuple[str, int]] = []
    notices: dict[int, NoticeKind] = {}
    cover_end: int | None = None
    current: list[str] = []
    summary = False
    saw_summary = False
    footer = False
    extra_article = False
    fence = ""

    def flush() -> None:
        nonlocal extra_article, cover_end, footer
        paragraph = " ".join(current).strip()
        current.clear()
        if not paragraph:
            return
        if footer:
            extra_article |= len(paragraph) >= MIN_BOUNDARY_PROSE_CHARS
            return
        notice = REPRINT_NOTICE.search(paragraph)
        kind = _reprint_kind(paragraph, notice) if notice else None
        if kind is not None:
            if kind != "possible" and not saw_summary and cover_end is None and _on_report_cover(headings, prose):
                cover_end = len(prose)
                return
            if kind == "explicit":
                footer = True
                return
            notices[len(prose)] = kind
        prose.append(paragraph)

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
        if FOOTER_START.match(plain):
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
    article, mixed = _review_notice_blocks(prose, headings, notices, cover_end or 0)
    return article, [title for title, _ in headings], saw_summary, extra_article or mixed


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
