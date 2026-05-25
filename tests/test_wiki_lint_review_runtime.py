from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.policy_runtime import load_policy
from ops.scripts.wiki_lint import lint
from ops.scripts.wiki_lint_review_runtime import (
    active_source_missing_concept_candidates,
    concept_carryover_continuity_candidates,
    content_promotion_candidates,
    synthesis_analysis_template_candidates,
    synthesis_follow_up_split_candidates,
    wiki_synthesis_multi_question_candidates,
)
from ops.scripts.wiki_snapshot_runtime import build_wiki_runtime_snapshot

from tests.minimal_vault_runtime import seed_open_question_smoke_vault


def write_page(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def valid_source(stem: str) -> str:
    return f"""---
title: "{stem}"
page_type: "source"
corpus: "wiki"
aliases:
  - "{stem}"
tags:
  - "corpus/wiki"
  - "type/source"
---

# {stem}

## Title
{stem}

## Source
- `raw/fake.pdf`

## Type
news-snapshot

## Summary
summary

## Why it matters
matters

## Key points
- one
- two
- three
- four

## Limitations / caveats
- one

## Provisional thesis
- thesis

## Why this is source-only for now
- source-only

## What future cluster would absorb this
- future cluster

## Related pages
- [[index]]
- [[source--fake]]

## Open questions
- none

## Source trace
- `raw/fake.pdf`
"""


def valid_concept(stem: str) -> str:
    return f"""---
title: "{stem}"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "{stem}"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# {stem}

## Summary
summary

## Why it matters here
matters

## Main body
text

## Scope boundaries
- applies to the canonical topic only

## Examples and non-examples
- example: source cluster interpretation anchor
- non-example: ad hoc scratch answer

## How to reuse this concept
- link it from synthesis pages that reuse the same interpretation layer

## Related pages
- [[index]]
- [[source--fake]]

## Open questions
- none

## Source trace
- `raw/fake.pdf`
"""


def broad_synthesis(include_boundary_sections: bool) -> str:
    analysis_lines: list[str] = []
    for label in ["A", "B", "C", "D", "E"]:
        analysis_lines.append(f"### {label}")
        analysis_lines.extend([f"line {label}-{index}" for index in range(1, 6)])
        analysis_lines.append("")
    boundary_sections = ""
    if include_boundary_sections:
        boundary_sections = """
## What this synthesis excludes
- not `macro policy`

## Tensions / contradictions
- tension between `shipping shock` and `macro spillover` interpretations

## Implications for future ingest
- tag future source as `shipping`, `procurement`, or `macro spillover`
"""
    return f"""---
title: "Broad Synthesis"
page_type: "synthesis"
corpus: "wiki"
source_count: 5
aliases:
  - "synthesis--broad"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--broad

## Question
question

## Short answer
answer

## Evidence considered
- [[source--s1]]
- [[source--s2]]
- [[source--s3]]
- [[source--s4]]
- [[source--s5]]

## Analysis
{chr(10).join(analysis_lines)}
{boundary_sections}
## Decision / takeaway
decide

## Follow-up questions
- none

## Related pages
- [[index]]
- [[concept--theme]]
- [[source--s1]]

## Source trace
- `raw/fake.pdf`
"""


def seed_broad_synthesis_vault(vault: Path, *, include_boundary_sections: bool) -> None:
    seed_open_question_smoke_vault(vault)
    write_page(vault / "wiki" / "concept--theme.md", valid_concept("concept--theme"))
    for index in range(1, 6):
        write_page(vault / "wiki" / f"source--s{index}.md", valid_source(f"source--s{index}"))
    write_page(
        vault / "wiki" / "synthesis--broad.md",
        broad_synthesis(include_boundary_sections=include_boundary_sections),
    )


def template_drift_synthesis() -> str:
    return """---
title: "Template Drift Synthesis"
page_type: "synthesis"
corpus: "wiki"
source_count: 2
aliases:
  - "synthesis--template-drift"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--template-drift

## Question
question

## Short answer
answer

## Evidence considered
- [[source--s1]]
- [[source--s2]]

## Analysis
### 이 묶음이 새로 더하는 것
line one

### source 신호
line two

### 라우팅 기준
line three

## What this synthesis excludes
- unrelated route

## Tensions / contradictions
- tension

## Implications for future ingest
- future route

## Decision / takeaway
decide

## Follow-up questions
- none

## Related pages
- [[index]]
- [[source--s1]]
- [[source--s2]]

## Source trace
- `raw/fake.pdf`
"""


def follow_up_split_synthesis() -> str:
    return """---
title: "Follow Up Split Synthesis"
page_type: "synthesis"
corpus: "wiki"
source_count: 3
aliases:
  - "synthesis--follow-up-split"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--follow-up-split

## Question
question

## Short answer
answer

## Evidence considered
- [[source--s1]]

### 2026-04-21 후속 근거
- [[source--s2]]
- [[source--s3]]

## Analysis
### baseline
line one

### 2026-04-21 follow-up는 새 정보가 분리돼 있다
line two

### integrated view
line three

## What this synthesis excludes
- unrelated route

## Tensions / contradictions
- tension

## Implications for future ingest
- future route

## Decision / takeaway
decide

## Follow-up questions
- none

## Related pages
- [[index]]
- [[concept--theme]]
- [[source--s1]]

## Source trace
- `raw/fake.pdf`
"""


def concept_without_continuity() -> str:
    return """---
title: "Carryover Gap Concept"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "concept--carryover-gap"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--carryover-gap

## Summary
summary

## Why it matters here
matters

## Main body
### route
text

### more route
text

### scope
text

## Scope boundaries
- applies to the canonical topic only

## Examples and non-examples
- example: source cluster interpretation anchor
- non-example: ad hoc scratch answer

## How to reuse this concept
- link it from synthesis pages that reuse the same interpretation layer

## Related pages
- [[index]]
- [[source--legacy-a-2026-04-12]]
- [[source--fresh-b-2026-04-21]]

## Open questions
- none

## Source trace
- `raw/fake.pdf`
"""


def concept_with_split_continuity() -> str:
    return """---
title: "Carryover Split Concept"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "concept--carryover-split"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--carryover-split

## Summary
summary

## Why it matters here
matters

## Main body
### route
text

### more route
text

### 기존 corpus와 이번 intake를 함께 읽으면 연속성이 분명해진다
split continuity block

## Scope boundaries
- applies to the canonical topic only

## Examples and non-examples
- example: source cluster interpretation anchor
- non-example: ad hoc scratch answer

## How to reuse this concept
- link it from synthesis pages that reuse the same interpretation layer

## Related pages
- [[index]]
- [[source--legacy-a-2026-04-12]]
- [[source--fresh-b-2026-04-21]]

## Open questions
- none

## Source trace
- `raw/fake.pdf`
"""


def source_without_concept(*, active: bool) -> str:
    synthesis_link = "- [[synthesis--theme]]\n" if active else ""
    return f"""---
title: "source--active-source"
page_type: "source"
corpus: "wiki"
created: "2026-04-16"
aliases:
  - "source--active-source"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--active-source

## Title
source--active-source

## Source
- `raw/fake.pdf`

## Type
news-snapshot

## Summary
summary

## Why it matters
matters

## Key points
- one
- two
- three
- four

## Limitations / caveats
- one

## Provisional thesis
- thesis

## Why this is source-only for now
- source-only

## What future cluster would absorb this
- future cluster

## Related pages
- [[index]]
{synthesis_link}
## Open questions
- none

## Source trace
- `raw/fake.pdf`
"""


def theme_synthesis() -> str:
    return """---
title: "Theme Synthesis"
page_type: "synthesis"
corpus: "wiki"
source_count: 1
created: "2026-04-15"
aliases:
  - "synthesis--theme"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--theme

## Question
q

## Short answer
a

## Evidence considered
- [[source--active-source]]

## Analysis
- x

## What this synthesis excludes
- unrelated

## Tensions / contradictions
- tension

## Implications for future ingest
- future route

## Decision / takeaway
- x

## Follow-up questions
- none

## Related pages
- [[index]]
- [[source--active-source]]

## Source trace
- `raw/fake.pdf`
"""


def seed_template_drift_vault(vault: Path) -> None:
    seed_open_question_smoke_vault(vault)
    write_page(vault / "wiki" / "source--s1.md", valid_source("source--s1"))
    write_page(vault / "wiki" / "source--s2.md", valid_source("source--s2"))
    write_page(vault / "wiki" / "synthesis--template-drift.md", template_drift_synthesis())


def seed_follow_up_split_vault(vault: Path) -> None:
    seed_open_question_smoke_vault(vault)
    write_page(vault / "wiki" / "concept--theme.md", valid_concept("concept--theme"))
    for stem in ["source--s1", "source--s2", "source--s3"]:
        write_page(vault / "wiki" / f"{stem}.md", valid_source(stem))
    write_page(vault / "wiki" / "synthesis--follow-up-split.md", follow_up_split_synthesis())


def seed_concept_carryover_gap_vault(vault: Path) -> None:
    seed_open_question_smoke_vault(vault)
    write_page(vault / "wiki" / "source--legacy-a-2026-04-12.md", valid_source("source--legacy-a-2026-04-12"))
    write_page(vault / "wiki" / "source--fresh-b-2026-04-21.md", valid_source("source--fresh-b-2026-04-21"))
    write_page(vault / "wiki" / "concept--carryover-gap.md", concept_without_continuity())


def seed_concept_carryover_split_vault(vault: Path) -> None:
    seed_open_question_smoke_vault(vault)
    write_page(vault / "wiki" / "source--legacy-a-2026-04-12.md", valid_source("source--legacy-a-2026-04-12"))
    write_page(vault / "wiki" / "source--fresh-b-2026-04-21.md", valid_source("source--fresh-b-2026-04-21"))
    write_page(vault / "wiki" / "concept--carryover-split.md", concept_with_split_continuity())


def seed_active_source_without_concept_vault(vault: Path, *, active: bool) -> None:
    seed_open_question_smoke_vault(vault)
    write_page(vault / "wiki" / "source--active-source.md", source_without_concept(active=active))
    write_page(vault / "wiki" / "synthesis--theme.md", theme_synthesis())


def synthesis_review_candidates(vault: Path) -> list[dict]:
    policy, _ = load_policy(vault)
    snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
    return wiki_synthesis_multi_question_candidates(
        vault,
        snapshot.pages,
        snapshot.evidence_links,
        policy["content_promotion_review"],
        policy["refactor_triggers"],
    )


class WikiLintReviewRuntimeTest(unittest.TestCase):
    def test_content_promotion_candidates_emit_family_ordered_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            pages = {
                "source--w1": vault / "wiki" / "source--w1.md",
                "source--w2": vault / "wiki" / "source--w2.md",
                "synthesis--wiki-topic": vault / "wiki" / "synthesis--wiki-topic.md",
                "source--sys1": vault / "system" / "source--sys1.md",
                "source--sys2": vault / "system" / "source--sys2.md",
                "synthesis--system-topic": vault / "system" / "synthesis--system-topic.md",
            }

            candidates = content_promotion_candidates(
                vault,
                pages,
                related_links={
                    "synthesis--wiki-topic": set(),
                    "synthesis--system-topic": set(),
                },
                evidence_links={
                    "synthesis--wiki-topic": {"source--w1", "source--w2"},
                    "synthesis--system-topic": {"source--sys1", "source--sys2"},
                },
                registry_entries=[
                    {
                        "corpus": "wiki",
                        "status": "ingested",
                        "domain": "defense",
                        "target_page": "source--w1",
                    },
                    {
                        "corpus": "wiki",
                        "status": "ingested",
                        "domain": "defense",
                        "target_page": "source--w2",
                    },
                ],
                refactor_triggers={"max_candidates_per_family": 1},
                content_promotion_review={
                    "wiki_missing_concept_min_source_links": 2,
                    "wiki_missing_synthesis_min_sources": 2,
                    "synthesis_source_overlap_for_coverage": 3,
                    "system_missing_concept_min_source_links": 2,
                },
            )

            self.assertEqual(
                [candidate["type"] for candidate in candidates],
                [
                    "wiki_missing_concept_candidate",
                    "wiki_missing_synthesis_candidate",
                    "system_missing_concept_candidate",
                ],
            )
            by_type = {candidate["type"]: candidate for candidate in candidates}
            self.assertEqual(by_type["wiki_missing_concept_candidate"]["domains"], ["defense"])
            self.assertEqual(
                by_type["wiki_missing_synthesis_candidate"]["supporting_pages"],
                ["wiki/source--w1.md", "wiki/source--w2.md"],
            )
            self.assertEqual(
                by_type["system_missing_concept_candidate"]["supporting_pages"],
                ["system/source--sys1.md", "system/source--sys2.md"],
            )

    def test_broad_synthesis_without_boundary_sections_requests_split_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_broad_synthesis_vault(vault, include_boundary_sections=False)

            candidate = next(
                item
                for item in synthesis_review_candidates(vault)
                if item["page"] == str((vault / "wiki" / "synthesis--broad.md").as_posix())
            )

            self.assertEqual(candidate["type"], "wiki_synthesis_multi_question_candidate")
            self.assertEqual(
                candidate["missing_boundary_sections"],
                [
                    "What this synthesis excludes",
                    "Tensions / contradictions",
                    "Implications for future ingest",
                ],
            )
            self.assertEqual(
                candidate["suggested_action"],
                "review_for_scope_split_or_subsynthesis_extraction",
            )

    def test_broad_synthesis_with_boundary_sections_becomes_watch_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_broad_synthesis_vault(vault, include_boundary_sections=True)

            candidate = next(
                item
                for item in synthesis_review_candidates(vault)
                if item["page"] == str((vault / "wiki" / "synthesis--broad.md").as_posix())
            )

            self.assertEqual(candidate["type"], "wiki_synthesis_multi_question_watch_candidate")
            self.assertEqual(candidate["missing_boundary_sections"], [])
            self.assertEqual(
                candidate["suggested_action"],
                "watch_scope_boundary_and_future_ingest_routes",
            )
            self.assertEqual(
                candidate["advisory"]["boundary_sections_present"],
                [
                    "What this synthesis excludes",
                    "Tensions / contradictions",
                    "Implications for future ingest",
                ],
            )
            self.assertEqual(candidate["advisory"]["exclusion_axes"], ["macro policy"])
            self.assertEqual(
                candidate["advisory"]["tension_axes"],
                ["shipping shock", "macro spillover"],
            )
            self.assertEqual(
                candidate["advisory"]["future_ingest_axes"],
                ["shipping", "procurement", "macro spillover"],
            )

    def test_synthesis_analysis_template_candidates_flag_promotion_memo_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_template_drift_vault(vault)

            policy, _ = load_policy(vault)
            snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
            candidate = synthesis_analysis_template_candidates(
                vault,
                snapshot.pages,
                policy["refactor_triggers"],
            )[0]

            self.assertEqual(candidate["type"], "synthesis_analysis_template_drift_candidate")
            self.assertEqual(
                candidate["template_markers"],
                ["이 묶음이 새로 더하는 것", "source 신호", "라우팅 기준"],
            )
            self.assertEqual(
                candidate["suggested_action"],
                "rewrite_analysis_as_cross_source_synthesis",
            )

    def test_active_source_missing_concept_candidates_flag_only_active_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_active_source_without_concept_vault(vault, active=True)

            policy, _ = load_policy(vault)
            snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
            candidate = active_source_missing_concept_candidates(
                vault,
                snapshot.pages,
                snapshot.related_links,
                snapshot.frontmatters,
            )[0]

            self.assertEqual(candidate["type"], "active_source_missing_concept_link_candidate")
            self.assertEqual(candidate["value"], 1)
            self.assertEqual(
                candidate["supporting_pages"],
                ["wiki/synthesis--theme.md"],
            )
            self.assertEqual(
                candidate["suggested_action"],
                "review_for_active_source_concept_linkage",
            )

    def test_synthesis_follow_up_split_candidates_flag_dated_refresh_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_follow_up_split_vault(vault)

            policy, _ = load_policy(vault)
            snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
            candidate = synthesis_follow_up_split_candidates(
                vault,
                snapshot.pages,
                policy["refactor_triggers"],
            )[0]

            self.assertEqual(candidate["type"], "synthesis_follow_up_split_candidate")
            self.assertIn("### 2026-04-21 후속 근거", candidate["markers"])
            self.assertEqual(
                candidate["suggested_action"],
                "rewrite_refresh_as_integrated_synthesis_update",
            )

    def test_concept_carryover_continuity_candidates_flag_missing_prose_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_concept_carryover_gap_vault(vault)

            policy, _ = load_policy(vault)
            snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
            candidate = concept_carryover_continuity_candidates(
                vault,
                snapshot.pages,
                snapshot.related_links,
                policy["refactor_triggers"],
            )[0]

            self.assertEqual(candidate["type"], "concept_carryover_continuity_missing_candidate")
            self.assertIn("wiki/source--fresh-b-2026-04-21.md", candidate["supporting_pages"])
            self.assertEqual(candidate["suggested_action"], "merge_bridge_context_into_concept_main_body")

    def test_concept_carryover_continuity_candidates_flag_split_prose_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_concept_carryover_split_vault(vault)

            policy, _ = load_policy(vault)
            snapshot = build_wiki_runtime_snapshot(vault, registry_contract=policy["registry_contract"])
            candidate = concept_carryover_continuity_candidates(
                vault,
                snapshot.pages,
                snapshot.related_links,
                policy["refactor_triggers"],
            )[0]

            self.assertEqual(candidate["type"], "concept_carryover_split_candidate")
            self.assertIn("기존 corpus와 이번 intake", candidate["markers"])
            self.assertEqual(candidate["suggested_action"], "merge_bridge_context_into_concept_main_body")

    def test_lint_wires_analysis_template_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_template_drift_vault(vault)

            candidate = next(
                item
                for item in lint(vault)["review_candidates"]
                if item["type"] == "synthesis_analysis_template_drift_candidate"
            )

            self.assertEqual(
                candidate["page"],
                str((vault / "wiki" / "synthesis--template-drift.md").as_posix()),
            )

    def test_lint_wires_active_source_missing_concept_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_active_source_without_concept_vault(vault, active=True)

            candidate = next(
                item
                for item in lint(vault)["review_candidates"]
                if item["type"] == "active_source_missing_concept_link_candidate"
            )

            self.assertEqual(
                candidate["page"],
                str((vault / "wiki" / "source--active-source.md").as_posix()),
            )

    def test_lint_wires_follow_up_split_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_follow_up_split_vault(vault)

            candidate = next(
                item
                for item in lint(vault)["review_candidates"]
                if item["type"] == "synthesis_follow_up_split_candidate"
            )

            self.assertEqual(
                candidate["page"],
                str((vault / "wiki" / "synthesis--follow-up-split.md").as_posix()),
            )

    def test_lint_wires_concept_carryover_gap_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_concept_carryover_gap_vault(vault)

            candidate = next(
                item
                for item in lint(vault)["review_candidates"]
                if item["type"] == "concept_carryover_continuity_missing_candidate"
            )

            self.assertEqual(
                candidate["page"],
                str((vault / "wiki" / "concept--carryover-gap.md").as_posix()),
            )

    def test_lint_wires_concept_carryover_split_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_concept_carryover_split_vault(vault)

            candidate = next(
                item
                for item in lint(vault)["review_candidates"]
                if item["type"] == "concept_carryover_split_candidate"
            )

            self.assertEqual(
                candidate["page"],
                str((vault / "wiki" / "concept--carryover-split.md").as_posix()),
            )

    def test_lint_skips_inactive_source_without_concept_review_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_active_source_without_concept_vault(vault, active=False)

            candidate_types = {
                item["type"]
                for item in lint(vault)["review_candidates"]
            }
            self.assertNotIn("active_source_missing_concept_link_candidate", candidate_types)


if __name__ == "__main__":
    unittest.main()
