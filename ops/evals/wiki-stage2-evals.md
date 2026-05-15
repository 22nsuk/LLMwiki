# Wiki Stage 2 Evals

Stage 2 evals are still binary, but they ask whether a page keeps performing its semantic or operational role inside the corpus after Stage 1 contract checks already pass.

## EVAL 1: Declared source count matches evidence
Question: If a `synthesis--` page declares `source_count`, does that number match the unique `source--` pages linked from `Evidence considered`?
Pass: `source_count` exists as an integer and equals the unique resolved source-link count in `Evidence considered`.
Fail: `source_count` is missing, not an integer, or does not match the unique source-link count.

## EVAL 2: Central research source has anchor layer
Question: If a `wiki/source--` page is a central `domain-research-paper`, does it carry the anchor-layer sections that explain why the corpus keeps reusing it?
Pass: The page is reused by at least `content_promotion_review.research_anchor_min_inbound_links` pages and contains every heading listed in `content_promotion_review.research_anchor_required_sections`.
Fail: A central research source is missing one or more required anchor-layer headings.

## EVAL 3: Broad synthesis has boundary sections
Question: If a `wiki/synthesis--` page is broad enough to hit the multi-question synthesis thresholds, does it explicitly state its boundary and future ingest direction?
Pass: The page exceeds the broad-synthesis thresholds and includes `What this synthesis excludes`, `Tensions / contradictions`, and `Implications for future ingest`.
Fail: A broad synthesis is missing any required boundary section.

## EVAL 4: Seed source has absorption hint
Question: If a `wiki/source--` page is still operating as a source-only seed rather than a reused concept/synthesis input, does it explain why it remains source-only and what future cluster should absorb it?
Pass: The page is a non-research `wiki/source--` page with no inbound `concept--` or `synthesis--` linkers and includes both `Why this is source-only for now` and `What future cluster would absorb this`.
Fail: A source-only seed is missing either required absorption-hint section.
