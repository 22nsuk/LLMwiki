"""Read-only, lexical capture diagnostics; these signals do not verify claims."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from markdown_it.utils import EnvType

SUMMARY_START = re.compile(r"^(?:세\s*줄\s*요약|AI\s*요약|AI[- ]generated summary|Auto(?:matic)? summary)$", re.I)
SUMMARY_END = re.compile(r"인공지능이 자동으로|기사 본문과 함께|End of (?:AI|auto).*summary|Read the full article", re.I)
RELATED_START = re.compile(r"^(?:관심기사 예측|관련\s*기사|함께 (?:읽기|보면)|추천\s*기사|.*뉴스를 추천해|Related (?:articles|stories)|Recommended (?:articles|stories))", re.I)
MARKDOWN = MarkdownIt("commonmark", {"inline_definitions": True})
PHOTO_MARKERS = ("![", "(©", "(ⓒ")
PAREN_ATTRIBUTION = re.compile(r"\([©ⓒ][^()]*\)")
COVER_COPYRIGHT = re.compile(r"^(?:©|Copyright\b|저작권자)", re.I)
REPORT_LABEL = re.compile(r"\breport\s+(?:no\.?\s*)?\d+\b|\b(?:annual|research|technical) report\b|보고서", re.I)
UI_LINE = re.compile(r"^(?:(?:송고|입력|수정)(?:\s|:)|Published:|Updated:|Title:|URL Source:|Published Time:|Markdown Content:|본문 바로가기|메뉴 바로가기|광고$|닫기$|ESC 닫기$|공유$|구독$|로그인$)", re.I)
STOP_WORDS = {"the", "and", "for", "with", "from", "this", "that", "after", "before", "news", "report", "기사", "관련", "대한"}
MIN_TITLE_TOKENS = 3
MIN_BODY_COMPARISON_CHARS = 160
MIN_BOUNDARY_PROSE_CHARS = 80


def _plain(line: str, *, strip_tags: bool = True) -> str:
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
    if strip_tags:
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


def _strip_attribution(match: re.Match[str]) -> str:
    source = match[0][1:-1].partition(",")[0].rstrip()
    return " " if source.endswith("제공") else match[0]


def markdown_blocks(body: str) -> tuple[list[Token], EnvType]:
    """Collect definition spans and their document-scoped inline reference table."""
    blocks: list[Token] = []
    env: EnvType = {}
    MARKDOWN.block.parse(body, MARKDOWN, env, blocks)
    return blocks, env


def _without_photo_credit(content: str, env: EnvType) -> str:
    """Project images and closed attributions out of analysis. Bare labels are prose."""
    if not any(marker in content for marker in PHOTO_MARKERS):
        return content
    tokens = MARKDOWN.parseInline(content, env)[0].children or []
    parts: list[str] = []
    removed = False
    for token in tokens:
        if token.type == "image":
            removed = True
            parts.append(" ")
        elif token.type in {"softbreak", "hardbreak"}:
            parts.append("\n")
        elif token.type == "text":
            text = PAREN_ATTRIBUTION.sub(_strip_attribution, token.content)
            parts.append(text)
            removed |= text != token.content
        else:
            parts.append(token.content)
    return "".join(parts) if removed else content


def lead_analysis_lines(body: str) -> Iterator[str]:
    """Keep source lines for lead selection, replacing only images, credits and definitions."""
    if not any(marker in body for marker in (*PHOTO_MARKERS, "]:")):
        yield from body.splitlines()
        return
    # Block maps use CommonMark line endings; keep their offsets into the source.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = body.split("\n")
    blocks, env = markdown_blocks(body)
    cursor = 0
    for i, block in enumerate(blocks):
        if block.map is None:
            continue
        if block.type == "definition":
            replacement = ""
        elif block.type in {"inline", "html_block"}:
            replacement = _without_photo_credit(block.content, env)
            if replacement == block.content:
                continue
            if block.type == "inline" and blocks[i - 1].type == "heading_open":
                replacement = ""
        else:
            continue
        start, end = block.map
        yield from lines[cursor:start]
        yield from replacement.split("\n")
        cursor = end
    yield from lines[cursor:]


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


_CaptureBlock = tuple[str, Iterator[tuple[str, str]]]


def _markdown_lines(content: str, env: EnvType, *, strip_tags: bool = True) -> Iterator[tuple[str, str]]:
    for line in _without_photo_credit(content, env).splitlines():
        yield line, _plain(line, strip_tags=strip_tags)


def _visible_lines(content: str) -> Iterator[tuple[str, str]]:
    # Inline markup and entities have been decoded. There is no Markdown
    # source line here for the standalone-link filter.
    for line in content.splitlines():
        yield "", line.strip()


def _inline_paragraph(content: str, env: EnvType, excluded: list[str]) -> Iterator[_CaptureBlock]:
    kind = "other" if excluded else "body"
    if "<" not in content and "[" not in content:
        yield kind, _markdown_lines(content, env)
        return

    inline = MARKDOWN.parseInline(content, env)
    children = inline[0].children or []
    has_html = any(token.type == "html_inline" for token in children)
    if not has_html and not any(token.type == "link_open" for token in children):
        yield kind, _markdown_lines(content, env)
        return

    # Let CommonMark resolve links and escape literal markup before the HTML
    # parser determines where the paragraph has prose outside a link.
    for token in children:
        if token.type == "text":
            token.content = PAREN_ATTRIBUTION.sub(_strip_attribution, token.content)
    markup = MARKDOWN.renderer.render(inline, MARKDOWN.options, env)
    paragraphs = _html_paragraphs(markup, excluded)
    if has_html:
        for role, text in paragraphs:
            yield role, _visible_lines(text)
    else:
        # Preserve the source spelling for Markdown-only navigation and credit filters.
        kind = "body" if any(role == "body" for role, _ in paragraphs) else "other"
        yield kind, _markdown_lines(content, env)


def _capture_blocks(blocks: list[Token], env: EnvType) -> Iterator[_CaptureBlock]:
    excluded: list[str] = []
    for i, block in enumerate(blocks):
        if block.type == "html_block" and block.level == 0:
            for kind, content in _html_paragraphs(block.content, excluded):
                yield kind, _markdown_lines(content, env, strip_tags=False)
        elif block.type == "inline":
            parent = blocks[i - 1]
            if parent.type == "paragraph_open" and parent.level == 0:
                yield from _inline_paragraph(block.content, env, excluded)
            elif parent.type == "heading_open":
                is_h1 = parent.level == 0 and not excluded and parent.tag == "h1"
                yield "h1" if is_h1 else "heading", _markdown_lines(block.content, env)
            else:
                yield "other", _markdown_lines(block.content, env)
        elif block.type == "html_block":
            yield "other", _markdown_lines(block.content, env)


def _article_parts(body: str, title: str) -> tuple[list[str], list[str], bool, bool]:
    """Only a distinct top-level heading with article prose can start a second story."""
    blocks, env = markdown_blocks(re.sub(r"<!--.*?-->", "", body, flags=re.S))
    headings: list[tuple[str, int]] = []
    prose: list[str] = []
    # Quoted text and list items can belong to an article. Neither establishes
    # that a heading introduces a new article.
    body_paragraphs: set[int] = set()
    cover_end: int | None = None
    summary = saw_summary = False
    for kind, paragraph_lines in _capture_blocks(blocks, env):
        lines: list[str] = []
        related = False
        for line, plain in paragraph_lines:
            if RELATED_START.search(plain):
                related = True
                break
            if SUMMARY_START.fullmatch(plain):
                summary = saw_summary = True
                continue
            if SUMMARY_END.search(plain):
                summary = False
                continue
            if summary or not plain:
                continue
            if kind in {"h1", "heading"}:
                if kind == "h1":
                    headings.append((plain, len(prose)))
                continue
            if UI_LINE.search(plain) or re.fullmatch(r"[\W\d_]+", plain):
                continue
            if re.fullmatch(r"\[[^\]]*\]\([^)]*\)", line.strip()):
                continue
            if any(plain == heading for heading, _ in headings):
                continue
            lines.append(plain)
        paragraph = " ".join(lines)
        if paragraph:
            if (cover_end is None and not saw_summary and COVER_COPYRIGHT.match(paragraph)
                    and len(paragraph) < MIN_BOUNDARY_PROSE_CHARS and _on_report_cover(headings, prose)):
                cover_end = len(prose)
            else:
                if kind == "body":
                    body_paragraphs.add(len(prose))
                prose.append(paragraph)
        if related:
            break

    end = _second_article_start(title, headings, prose, body_paragraphs, cover_end)
    return prose[cover_end or 0:end], [h for h, _ in headings], saw_summary, end < len(prose)


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
    prose = [paragraph for paragraph in prose if paragraph != _plain(title)]
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
