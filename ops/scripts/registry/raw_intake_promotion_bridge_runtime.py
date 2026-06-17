from __future__ import annotations

import re
from pathlib import Path

from ops.scripts.eval.wiki_page_runtime import section_body

from .raw_intake_promotion_shared_runtime import _section_links

BRIDGE_TOKEN_STOPWORDS = {
    "and",
    "or",
    "the",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "under",
    "after",
    "before",
    "risk",
    "policy",
    "market",
    "markets",
    "public",
    "source",
    "sources",
    "synthesis",
    "concept",
}


def _family_tokens(family_slug: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", family_slug.lower())
        if len(token) >= 3 and token not in BRIDGE_TOKEN_STOPWORDS
    }


def suggest_bridge_sources_for_family(
    vault: Path,
    family_slug: str,
    *,
    exclude_source_stems: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    tokens = _family_tokens(family_slug)
    if not tokens:
        return []

    excluded = set(exclude_source_stems or [])
    candidates: list[dict] = []
    for path in sorted((vault / "wiki").glob("source--*.md")):
        stem = path.stem
        if stem in excluded:
            continue
        text = path.read_text(encoding="utf-8")
        searchable = f"{stem}\n{section_body(text, 'Title') or ''}\n{section_body(text, 'Summary') or ''}\n"
        searchable += section_body(text, "Why it matters") or ""
        lowered = searchable.lower()
        matched_tokens = sorted(token for token in tokens if token in lowered)
        if not matched_tokens:
            continue
        score = len(matched_tokens)
        related = " ".join(_section_links(text, "Related pages")).lower()
        related_hits = sorted(token for token in tokens if token in related)
        if related_hits:
            score += len(related_hits)
        candidates.append(
            {
                "source_stem": stem,
                "score": score,
                "matched_tokens": matched_tokens,
                "signals": [
                    f"source text matched: {', '.join(matched_tokens)}",
                    *([f"related pages matched: {', '.join(related_hits)}"] if related_hits else []),
                ],
            }
        )

    candidates.sort(key=lambda item: (-int(item["score"]), item["source_stem"]))
    return candidates[: max(0, limit)]
