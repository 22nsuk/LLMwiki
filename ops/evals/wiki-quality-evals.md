# Wiki Quality Evals

Every eval is binary. Yes or no. These are the default promotion checks for wiki changes.

## EVAL 1: Required sections present
Question: Does the page contain the minimum required sections for its prefix type?
Pass: All required headings for the page prefix or special page path are present according to `ops/policies/wiki-maintainer-policy.yaml`.
Fail: Any required heading is missing.

## EVAL 2: Source trace present
Question: Does the page include a `Source trace` section that satisfies the policy minimum?
Pass: `Source trace` exists and lists at least `readiness_gate.min_source_trace_items` source file or snapshot.
Fail: `Source trace` is missing or empty.

## EVAL 3: Source trace targets exist
Question: Do the backticked local file paths in `Source trace` resolve to real files in the vault?
Pass: Every backticked local path in `Source trace` exists.
Fail: Any backticked local path in `Source trace` is missing.

## EVAL 4: Link integration
Question: Does the page link to at least the policy minimum number of relevant wiki pages?
Pass: The `Related pages` section contains at least `readiness_gate.min_related_links` valid wikilinks to existing pages.
Fail: The `Related pages` section is missing, empty, or contains fewer than the policy minimum valid wikilinks.

## EVAL 5: Broken-link free
Question: Is the page free of broken wikilinks?
Pass: Every wikilink resolves to an existing page or a known system page.
Fail: Any wikilink target is missing.

## EVAL 6: Placeholder discipline
Question: Is the page free of unresolved placeholder language (`TODO`, `TBD`, `fill later`) outside explicitly tracked backlog sections?
Pass: No unresolved placeholder markers are found.
Fail: Placeholder markers appear in narrative sections.

## EVAL 7: Source page substance
Question: If the page is a `source--` page, does it contain enough concrete content in both `Key points` and `Limitations / caveats`?
Pass: The `Key points` section contains four or more bullets and `Limitations / caveats` contains at least one bullet.
Fail: Either section is missing substance, even if bullets elsewhere in the document make the page look dense.

## EVAL 8: Synthesis decisionability
Question: If the page is a `synthesis--` or `query--` page, does it end in an operational decision or takeaway rather than only summary?
Pass: The page contains a concrete `Decision / takeaway`.
Fail: The page only summarizes evidence and never decides.
