from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from ops.scripts.eval.wiki_page_runtime import section_body

FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|\Z)", re.DOTALL)
FENCED_BLOCK_RE = re.compile(
    r"^\s*(```|~~~).*?^\s*\1\s*$", re.MULTILINE | re.DOTALL
)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
REFERENCE_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
HTML_RE = re.compile(r"<[^>]+>")
MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)")
SENTENCE_RE = re.compile(r"[^.!?。！？\n]+[.!?。！？](?=\s|$)")
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
QUERY_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}|[가-힣]{2,}")
EMAIL_RE = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
LEADING_NOISE_RE = re.compile(
    r"^(?:by\s+|file\s+photo\s*[:=-]|caption\s*[:=-]|photo\s*[:=-]|"
    r"사진\s*[=:]|자료\s*[=:]|그래픽\s*[=:]|출처\s*[=:]|제공\s*[=:]|"
    r"입력\s|수정\s|등록\s|기자\s|관련\s*기사|기사\s*듣기|자동\s*요약)",
    re.IGNORECASE,
)
DATELINE_RE = re.compile(
    r"^(?:\([^\n)]{1,80}(?:연합뉴스|뉴시스|로이터)\)|"
    r"[A-Z][A-Z .'-]{1,50},\s+(?:[A-Z][a-z]+\s+)?\d{1,2}\s+"
    r"\((?:Reuters|AP|Bloomberg)\)\s*[-:]|"
    r"(?:SEOUL|NEW YORK|LONDON|WASHINGTON|TOKYO),\s+\((?:Reuters|AP)\)\s*[-:])",
    re.IGNORECASE,
)
MASTHEAD_RE = re.compile(
    r"^(?:Reuters|Associated Press|AP News|Bloomberg|연합뉴스|뉴시스|"
    r"조선일보|중앙일보|동아일보|한겨레|매일경제|한국경제)[.!。]?$",
    re.IGNORECASE,
)
FRAGMENT_START_RE = re.compile(
    r"^(?:[0-9][0-9.,%+/-]*|[A-Z]{2,5}(?:\.[A-Z])?)\s+"
    r"(?:[a-z]|rose\b|fell\b|gained\b|lost\b|shares?\b|points?\b)",
)
NOISE_MARKERS = (
    "all rights reserved",
    "copyright",
    "image credit",
    "photo credit",
    "getty images",
    "기사 듣기",
    "글자 크기",
    "관련 기사",
    "관련기사",
    "본문 바로가기",
    "자동요약",
    "음성으로 듣기",
    "무단전재",
    "재배포 금지",
)
QUERY_STOPWORDS = frozenset(
    {
        "source",
        "this",
        "that",
        "with",
        "from",
        "about",
        "자료",
        "원문",
        "기록",
        "근거",
        "source가",
        "source는",
    }
)
COPYRIGHT_MARKERS = (
    "copyright",
    "all rights reserved",
    "©",
    "무단 전재",
    "무단전재",
    "재배포 금지",
    "저작권자",
)


def normalize_raw_text(text: str, *, markdown: bool) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        normalized = FRONTMATTER_RE.sub("", normalized, count=1)
        normalized = FENCED_BLOCK_RE.sub("", normalized)
    normalized = IMAGE_RE.sub("", normalized)
    normalized = LINK_RE.sub(r"\1", normalized)
    normalized = REFERENCE_LINK_RE.sub(r"\1", normalized)
    normalized = URL_RE.sub("", normalized)
    normalized = HTML_RE.sub("", normalized)

    retained: list[str] = []
    for source_line in normalized.splitlines():
        line = MARKDOWN_PREFIX_RE.sub("", source_line).strip()
        if not line:
            retained.append("")
            continue
        lowered = line.casefold()
        if any(marker in lowered for marker in COPYRIGHT_MARKERS):
            continue
        if re.fullmatch(r"[:|\-\s]+", line):
            continue
        retained.append(line)
    return re.sub(r"[ \t]+", " ", "\n".join(retained)).strip()


def extract_complete_sentences(normalized_raw_text: str) -> list[str]:
    sentences: list[str] = []
    seen: set[str] = set()
    for match in SENTENCE_RE.finditer(normalized_raw_text):
        sentence = re.sub(r"\s+", " ", match.group(0)).strip()
        if sentence.endswith(("...", "…")) or sentence_is_noisy(sentence):
            continue
        if len(sentence) < 12 or len(WORD_RE.findall(sentence)) < 3:
            continue
        identity = sentence.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        sentences.append(sentence)
    return sentences


def sentence_is_noisy(sentence: str) -> bool:
    lowered = sentence.casefold()
    return bool(
        EMAIL_RE.search(sentence)
        or URL_RE.search(sentence)
        or LEADING_NOISE_RE.search(sentence)
        or DATELINE_RE.search(sentence)
        or MASTHEAD_RE.fullmatch(sentence.strip())
        or FRAGMENT_START_RE.search(sentence)
        or _has_unbalanced_delimiters(sentence)
        or any(marker in lowered for marker in NOISE_MARKERS)
        or any(marker in sentence for marker in ("**", "__", "![", "|"))
        or re.match(r"^[a-z]", sentence)
    )


def _has_unbalanced_delimiters(sentence: str) -> bool:
    stripped = sentence.strip()
    if stripped.startswith((")", "]", "}", "’", "”", "」", "』")):
        return True
    pairs = (
        ("(", ")"),
        ("[", "]"),
        ("{", "}"),
        ("“", "”"),
        ("‘", "’"),
        ("「", "」"),
        ("『", "』"),
    )
    return any(sentence.count(left) != sentence.count(right) for left, right in pairs) or sentence.count('"') % 2 == 1


def _query_tokens(page_text: str, frontmatter: dict[str, Any]) -> set[str]:
    query_parts = [
        str(frontmatter.get(field, ""))
        for field in (
            "title",
            "domain",
            "primary_concept",
            "primary_lens",
            "topic_family",
            "topic_subfamily",
        )
    ]
    query_parts.extend(
        section_body(page_text, heading) or ""
        for heading in ("Summary", "Why it matters")
    )
    return {
        token.casefold()
        for token in QUERY_TOKEN_RE.findall(" ".join(query_parts))
        if token.casefold() not in QUERY_STOPWORDS
    }


def _sentence_tokens(sentence: str) -> set[str]:
    return {
        token.casefold()
        for token in QUERY_TOKEN_RE.findall(sentence)
        if token.casefold() not in QUERY_STOPWORDS
    }


def _query_overlap_count(tokens: set[str], query_tokens: set[str]) -> int:
    matched: set[str] = set()
    for query_token in query_tokens:
        for token in tokens:
            same_cjk_term = (
                re.fullmatch(r"[가-힣]+", query_token)
                and re.fullmatch(r"[가-힣]+", token)
                and (query_token in token or token in query_token)
            )
            if query_token == token or same_cjk_term:
                matched.add(query_token)
                break
    return len(matched)


def rank_source_sentences(
    sentences: Sequence[str],
    *,
    page_text: str,
    frontmatter: dict[str, Any],
    excluded_claims: Sequence[str] = (),
) -> list[str]:
    query_tokens = _query_tokens(page_text, frontmatter)
    title = str(frontmatter.get("title", "")).strip().casefold()
    excluded_token_sets = [
        _sentence_tokens(claim) for claim in excluded_claims if claim.strip()
    ]
    ranked: list[tuple[int, int, str, set[str]]] = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.casefold()
        if title and (lowered == title or (lowered.startswith(title) and len(sentence) < 160)):
            continue
        tokens = _sentence_tokens(sentence)
        if any(_token_sets_overlap(tokens, excluded) for excluded in excluded_token_sets):
            continue
        overlap = _query_overlap_count(tokens, query_tokens)
        if query_tokens and overlap == 0:
            continue
        score = overlap * 10 + int(bool(re.search(r"\d", sentence)))
        score += int(35 <= len(sentence) <= 280)
        ranked.append((-score, index, sentence, tokens))

    selected: list[tuple[str, set[str]]] = []
    for _negative_score, _index, sentence, tokens in sorted(ranked):
        if any(
            tokens
            and existing_tokens
            and len(tokens & existing_tokens) / len(tokens | existing_tokens) >= 0.7
            for _existing, existing_tokens in selected
        ):
            continue
        selected.append((sentence, tokens))
    return [sentence for sentence, _tokens in selected]


def _token_sets_overlap(tokens: set[str], other: set[str]) -> bool:
    if not tokens or not other:
        return False
    intersection = tokens & other
    return (
        len(intersection) / len(tokens | other) >= 0.6
        or len(intersection) / min(len(tokens), len(other)) >= 0.75
    )


def candidate_section_quality_reason(candidate_text: str) -> str | None:
    summary = (section_body(candidate_text, "Summary") or "").strip()
    key_points = [
        re.sub(r"^[-*]\s+", "", line).strip()
        for line in (section_body(candidate_text, "Key points") or "").splitlines()
        if re.match(r"^[-*]\s+", line)
    ]
    summary_sentences = [
        re.sub(r"\s+", " ", match.group(0)).strip()
        for match in SENTENCE_RE.finditer(summary)
    ]
    all_claims = [*summary_sentences, *key_points]
    if any(sentence_is_noisy(claim) for claim in all_claims):
        return "candidate_section_noise"
    token_sets = [_sentence_tokens(claim) for claim in all_claims]
    number_sets = [set(re.findall(r"\d+(?:[.,]\d+)?%?", claim)) for claim in all_claims]
    for index, tokens in enumerate(token_sets):
        for other_index, other_tokens in enumerate(
            token_sets[index + 1 :], start=index + 1
        ):
            if not tokens or not other_tokens:
                continue
            intersection = tokens & other_tokens
            same_numbered_claim = bool(
                number_sets[index]
                and number_sets[index] == number_sets[other_index]
                and len(intersection) >= 2
            )
            if (
                len(intersection) / len(tokens | other_tokens) >= 0.55
                or len(intersection) / min(len(tokens), len(other_tokens)) >= 0.8
                or same_numbered_claim
            ):
                return "candidate_section_near_duplicate"
    return None
