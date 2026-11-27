"""Read-only, lexical capture diagnostics; these signals do not verify claims."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator
from html.parser import HTMLParser
from pathlib import Path
from typing import NamedTuple

from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it.utils import EnvType

SUMMARY_START = re.compile(r"^(?:세\s*줄\s*요약|AI\s*요약|AI[- ]generated summary|Auto(?:matic)? summary)$", re.I)
SUMMARY_END = re.compile(r"인공지능이 자동으로|기사 본문과 함께|End of (?:AI|auto).*summary|Read the full article", re.I)
RELATED_START = re.compile(r"^(?:관심기사 예측|관련\s*기사|함께 (?:읽기|보면)|추천\s*기사|.*뉴스를 추천해|Related (?:articles|stories)|Recommended (?:articles|stories))", re.I)
MARKDOWN = MarkdownIt("commonmark", {"inline_definitions": True})
PAREN_ATTRIBUTION = re.compile(r"\([©ⓒ][^()]*\)")
COVER_COPYRIGHT = re.compile(r"^(?:©|Copyright\b|저작권자)", re.I)
# A symbol can label a free-form publisher, including a domain. A bare
# label needs a name because an article about copyright can start the same way.
_RIGHTS_HOLDER = (
    r"(?:(?:(?:copyright|저작권자)\s*)?[©ⓒ](?:[^.!?\n]|\.(?=\S)){1,64}?"
    r"|(?:copyright(?:\s+\d{4})?|저작권자)\s+(?-i:[A-Z][\w-]*(?:\s+[A-Z][\w-]*){0,4}|[가-힣]+))"
)
_RESERVATION = r"(?:all rights reserved|무단\s*전재[^.!?\n]{0,64}금지)"
_RIGHTS_CLAUSE = (
    rf"(?:{_RESERVATION}|"
    r"no (?:part|material|content)\b[^.!?\n]{0,120}\breproduced without\b[^.!?\n]{0,64}\bpermission)"
)
RIGHTS_NOTICE = re.compile(rf"{_RIGHTS_HOLDER}\.?\s*{_RESERVATION}(?:\.\s+{_RIGHTS_CLAUSE})*\.?", re.I)
REPORT_LABEL = re.compile(r"\breport\s+(?:no\.?\s*)?\d+\b|\b(?:annual|research|technical) report\b|보고서", re.I)
UI_LINE = re.compile(r"^(?:(?:송고|입력|수정)(?:\s|:)|Published:|Updated:|Title:|URL Source:|Published Time:|Markdown Content:|본문 바로가기|메뉴 바로가기|광고$|닫기$|ESC 닫기$|공유$|구독$|로그인$)", re.I)
STOP_WORDS = {"the", "and", "for", "with", "from", "this", "that", "after", "before", "news", "report", "기사", "관련", "대한"}
MIN_SUMMARY_SHARED_TERMS = 2
MIN_SUMMARY_OVERLAP = 0.25
MIN_TITLE_TOKENS = 3
MIN_BODY_COMPARISON_CHARS = 160
MIN_BOUNDARY_PROSE_CHARS = 80


def _plain(line: str, *, strip_tags: bool = True) -> str:
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
    if strip_tags:
        line = re.sub(r"<[^>]*>", "", line)
    return line.strip(" #*`_>\t\\")


def is_rights_notice(paragraph: str) -> bool:
    """A whole notice is ineligible as article evidence, wherever it occurs."""
    text = " ".join(paragraph.split())
    return text.casefold().removesuffix(".") == "all rights reserved" or RIGHTS_NOTICE.fullmatch(text) is not None


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


def _strip_attribution(match: re.Match[str]) -> str:
    source = match[0][1:-1].partition(",")[0].rstrip()
    return " " if source.endswith("제공") else match[0]


def markdown_blocks(body: str) -> tuple[list[Token], EnvType]:
    """Collect definition spans and their document-scoped inline reference table."""
    blocks: list[Token] = []
    env: EnvType = {}
    MARKDOWN.block.parse(body, MARKDOWN, env, blocks)
    return blocks, env


class _Line(NamedTuple):
    text: str
    link_only: bool = False
    source_lines: int = 1


class _InlineText(NamedTuple):
    lines: list[_Line]
    boundary_prose: bool
    keep_source_lead: bool


def _project_inline(children: list[Token], *, markdown_text: bool = True) -> _InlineText | None:
    """Project visible inline text and retain link scope for each line."""
    if not children:
        return None
    lines: list[_Line] = []
    parts: list[str] = []
    project = False
    in_link = saw_link = False
    source_lines = 1
    unlinked_text = boundary_prose = False
    for token in children:
        if token.type == "image":
            project = True
            parts.append(" ")
        elif token.type in {"softbreak", "hardbreak"}:
            lines.append(_Line("".join(parts), not unlinked_text, source_lines))
            source_lines = 1
            parts.clear()
            unlinked_text = False
        elif token.type == "html_inline":
            source_lines += token.content.count("\n")
            if token.content.startswith("<!--"):
                project = True
                parts.append(" ")
            elif not markdown_text:
                parts.append(token.content)
            else:
                # Formatting can split a word. Layout and void elements separate text.
                tag = re.match(r"</?([a-zA-Z][a-zA-Z0-9-]*)", token.content)
                if tag and tag[1].lower() not in _HTMLProse.formatting and tag[1].lower() != "a":
                    parts.append(" ")
        elif token.type in {"link_open", "link_close"}:
            saw_link = True
            in_link = token.type == "link_open"
        elif token.type in {"text", "code_inline"}:
            text = token.content
            if token.type == "text":
                text = PAREN_ATTRIBUTION.sub(_strip_attribution, text)
                boundary_prose |= not in_link and bool(text.strip())
            project |= token.type == "code_inline" or text != token.content
            # An attributed linked sentence can supply lead text, although its
            # label alone cannot corroborate a second article.
            unlinked_text |= (not in_link and bool(token.content.strip())) or text != token.content
            parts.append(text)
    keep_source_lead = not (project or saw_link)
    # HTMLParser has already decoded literal HTML text, including escaped tags.
    if keep_source_lead and not markdown_text:
        return None
    lines.append(_Line("".join(parts), not unlinked_text, source_lines))
    return _InlineText(lines, boundary_prose or not saw_link, keep_source_lead)


def _inline_tokens(content: str, env: EnvType) -> list[Token]:
    return MARKDOWN.parseInline(content, env)[0].children or []


class LeadLine(NamedTuple):
    excerpt: str
    visible: str


def lead_analysis_lines(body: str) -> Iterator[LeadLine]:
    """Keep excerpt spelling alongside the parsed text used to recognize notices."""
    # Block maps use CommonMark line endings; keep their offsets into the source.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = body.split("\n")
    blocks, env = markdown_blocks(body)
    cursor = 0
    for block in blocks:
        if block.map is None or block.map[0] < cursor:
            continue
        start, end = block.map
        if block.type in {"heading_open", "definition"} or (
            block.type == "html_block" and block.content.lstrip().startswith("<!--") and "-->" not in block.content
        ):
            replacement = [LeadLine("", "")]
        elif block.type in {"inline", "html_block"}:
            projected = _project_inline(_inline_tokens(block.content, env), markdown_text=block.type == "inline")
            if projected is None:
                continue
            if projected.keep_source_lead:
                replacement = []
                offset = start
                for line in projected.lines:
                    stop = offset + line.source_lines
                    replacement.append(LeadLine("\n".join(lines[offset:stop]), line.text))
                    offset = stop
                if offset != end:
                    continue
            else:
                visible = ("" if line.link_only else line.text for line in projected.lines)
                replacement = [LeadLine(text, text) for text in visible]
        else:
            continue
        yield from (LeadLine(line, line) for line in lines[cursor:start])
        yield from replacement
        cursor = end
    yield from (LeadLine(line, line) for line in lines[cursor:])


def _on_report_cover(headings: list[tuple[str, int]], prose: list[str]) -> bool:
    # A report identifier can be a heading or a short line on a printed cover.
    if any(len(p) >= MIN_BOUNDARY_PROSE_CHARS or p.endswith((".", "!", "?")) for p in prose):
        return False
    return any(REPORT_LABEL.search(title) for title, _ in headings) or any(REPORT_LABEL.search(p) for p in prose)


class _HTMLProse(HTMLParser):
    """Separate prose paragraphs from other HTML text, including nested containers."""

    containers = {"article", "body", "div", "html", "main", "p", "section"}
    formatting = {"b", "em", "i", "mark", "s", "small", "span", "strong", "sub", "sup", "u"}
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
            "param", "source", "track", "wbr"}

    def __init__(self, excluded: list[str]) -> None:
        super().__init__()
        self.excluded = excluded
        self.has_prose = False
        self.text: list[str] = []
        self.paragraphs: list[tuple[str, str]] = []

    def flush(self) -> None:
        content = "".join(self.text).strip()
        if content:
            kind = "body" if self.has_prose else "other"
            self.paragraphs.append((kind, content))
        self.text.clear()
        self.has_prose = False

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if not self.excluded and PAREN_ATTRIBUTION.sub(_strip_attribution, data).strip():
            self.has_prose = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.excluded.append(tag)
        elif tag in self.void:
            self.text.append(" ")
        elif tag not in self.formatting:
            self.flush()
            if tag not in self.containers:
                self.excluded.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.formatting or tag in self.void:
            return
        if tag != "a":
            self.flush()
        if self.excluded and tag == self.excluded[-1]:
            self.excluded.pop()
        elif tag in self.excluded:
            # HTML permits omitted closing tags, for example </li> before </ul>.
            while self.excluded.pop() != tag:
                pass


def _html_paragraphs(markup: str, excluded: list[str]) -> list[tuple[str, str]]:
    # Each CommonMark fragment is complete input. Only open element scopes
    # carry across fragments, never undecoded input or an unfinished paragraph.
    html = _HTMLProse(excluded)
    try:
        html.feed(markup)
        html.close()
    except (AssertionError, ValueError):
        # HTMLParser can reject malformed declarations and character references.
        excluded.clear()
        return [("other", markup)]
    html.flush()
    return html.paragraphs


_CaptureBlock = tuple[str, Iterable[_Line]]


def _markdown_block(kind: str, content: str, children: list[Token], *, markdown_text: bool = True) -> _CaptureBlock:
    projected = _project_inline(children, markdown_text=markdown_text)
    if projected is not None:
        if kind == "body" and not projected.boundary_prose:
            kind = "other"
        return kind, projected.lines
    return kind, (_Line(_plain(line, strip_tags=markdown_text)) for line in content.splitlines())


def _inline_paragraph(content: str, env: EnvType, excluded: list[str]) -> Iterator[_CaptureBlock]:
    children = _inline_tokens(content, env)
    if not any(token.type == "html_inline" for token in children):
        yield _markdown_block("other" if excluded else "body", content, children)
        return

    # Let CommonMark resolve links and escape literal markup before reading
    # the HTML element scopes shared with surrounding raw HTML blocks.
    for token in children:
        if token.type == "text":
            token.content = PAREN_ATTRIBUTION.sub(_strip_attribution, token.content)
    markup = MARKDOWN.renderer.render(children, MARKDOWN.options, env)
    for role, text in _html_paragraphs(markup, excluded):
        yield role, (_Line(line) for line in text.splitlines())


def _capture_blocks(blocks: list[Token], env: EnvType) -> Iterator[_CaptureBlock]:
    excluded: list[str] = []
    for i, block in enumerate(blocks):
        if block.type == "html_block" and block.level == 0:
            for kind, content in _html_paragraphs(block.content, excluded):
                yield _markdown_block(kind, content, _inline_tokens(content, env), markdown_text=False)
        elif block.type == "inline":
            parent = blocks[i - 1]
            if parent.type == "paragraph_open" and parent.level == 0:
                yield from _inline_paragraph(block.content, env, excluded)
                continue
            kind = "other"
            if parent.type == "heading_open":
                is_h1 = parent.level == 0 and not excluded and parent.tag == "h1"
                kind = "h1" if is_h1 else "heading"
            yield _markdown_block(kind, block.content, _inline_tokens(block.content, env))
        elif block.type == "html_block":
            yield _markdown_block("other", block.content, _inline_tokens(block.content, env))


def _has_summary_body(terms: set[str], title: str, paragraphs: Iterable[str]) -> bool:
    """Seek independent prose about the story outside the marked summary."""
    title_terms = _tokens(title)
    if len(terms) < MIN_SUMMARY_SHARED_TERMS:
        terms = terms | title_terms
    if len(terms) < MIN_SUMMARY_SHARED_TERMS:
        return any(len(p) >= MIN_BOUNDARY_PROSE_CHARS for p in paragraphs)
    for paragraph in paragraphs:
        words = _tokens(paragraph)
        shared = words & terms
        if len(shared) < MIN_SUMMARY_SHARED_TERMS:
            continue
        # Two incidental words in a long notice are weak evidence. Look for
        # the headline topic or substantial overlap with the shorter text.
        if (len(shared & title_terms) >= MIN_SUMMARY_SHARED_TERMS
                or len(shared) >= MIN_SUMMARY_OVERLAP * min(len(words), len(terms))):
            return True
    return False


def _article_parts(body: str, title: str) -> tuple[list[str], list[str], bool, bool]:
    """Find the primary article and check its prose against any marked summary."""
    blocks, env = markdown_blocks(re.sub(r"<!--.*?-->", "", body, flags=re.S))
    headings: list[tuple[str, int]] = []
    prose: list[str] = []
    # Quoted text and list items can belong to an article. Neither establishes
    # that a heading introduces a new article.
    body_paragraphs: set[int] = set()
    cover_end: int | None = None
    # Index by position so a summary in a second story cannot qualify the first.
    summaries: dict[int, set[str]] = {}
    active_summary: set[str] | None = None
    for kind, paragraph_lines in _capture_blocks(blocks, env):
        lines: list[str] = []
        related = False
        for line in paragraph_lines:
            plain = line.text.strip()
            if RELATED_START.search(plain):
                related = True
                break
            if SUMMARY_START.fullmatch(plain):
                active_summary = summaries.setdefault(len(prose), set())
                continue
            if SUMMARY_END.search(plain):
                active_summary = None
                continue
            if active_summary is not None:
                if not line.link_only:
                    active_summary.update(_tokens(plain))
                continue
            if not plain:
                continue
            if kind in {"h1", "heading"}:
                if kind == "h1":
                    headings.append((plain, len(prose)))
                continue
            if UI_LINE.search(plain) or re.fullmatch(r"[\W\d_]+", plain):
                continue
            if line.link_only:
                continue
            if any(plain == heading for heading, _ in headings):
                continue
            lines.append(plain)
        paragraph = " ".join(lines)
        if paragraph:
            if (cover_end is None and not summaries and COVER_COPYRIGHT.match(paragraph)
                    and len(paragraph) < MIN_BOUNDARY_PROSE_CHARS and _on_report_cover(headings, prose)):
                cover_end = len(prose)
            elif not is_rights_notice(paragraph):
                if kind == "body":
                    body_paragraphs.add(len(prose))
                prose.append(paragraph)
        if related:
            break

    end = _second_article_start(title, headings, prose, body_paragraphs, cover_end)
    start = cover_end or 0
    extra_article = end < len(prose)
    if extra_article:
        summaries = {i: words for i, words in summaries.items() if i < end}
    titles = [h for h, _ in headings]
    resolved_title = title or (titles[0] if titles else "")
    plain_title = _plain(resolved_title)
    article = [p for p in prose[start:end] if p != plain_title]
    if summaries:
        candidates = (prose[i] for i in body_paragraphs if start <= i < end and prose[i] != plain_title)
        if not _has_summary_body(set().union(*summaries.values()), resolved_title, candidates):
            article = []
    return article, titles, bool(summaries), extra_article


def _second_article_start(
    title: str, headings: list[tuple[str, int]], prose: list[str],
    body_paragraphs: set[int], cover_end: int | None,
) -> int:
    if not headings:
        return len(prose)
    first_title = headings[0][0] if headings[0][1] == 0 else title
    first_lead = next((i for i in range(cover_end or 0, len(prose))
                       if i in body_paragraphs and len(prose[i]) >= MIN_BOUNDARY_PROSE_CHARS), len(prose))
    for i, (heading, start) in enumerate(headings):
        if start <= first_lead or not _disjoint_title(first_title, heading):
            continue
        end = headings[i + 1][1] if i + 1 < len(headings) else len(prose)
        section = " ".join(prose[k] for k in range(start, end) if k in body_paragraphs)
        if not section:
            continue
        # Reports can also label chapters with H1. Compare the chapter text.
        if cover_end is None or (len(section) >= MIN_BOUNDARY_PROSE_CHARS and _disjoint_title(first_title, section)):
            return start
    return len(prose)


def capture_review_reasons(*, body: str, title: str, filename: str) -> list[str]:
    """Return stable review codes, not an admission verdict or edited content.

    Missing/unsupported markers, short titles, translations, generic filenames,
    paraphrases and lexical overlap can evade these deliberately bounded rules.
    """
    prose, headings, saw_summary, extra_article = _article_parts(body, title)
    title = title or (headings[0] if headings else "")
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
