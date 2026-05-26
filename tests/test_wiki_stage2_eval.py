from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.wiki_stage2_eval import evaluate

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
POLICY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-maintainer-policy.schema.json"
STAGE2_REPORT_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-stage2-eval-report.schema.json"


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 3, 45, tzinfo=dt.UTC),
    )


def seed_policy(root: Path) -> None:
    (root / "ops" / "policies").mkdir(parents=True)
    (root / "ops" / "schemas").mkdir(parents=True)
    (root / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        LIVE_POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "ops" / "schemas" / "wiki-maintainer-policy.schema.json").write_text(
        POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def write_page(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def simple_source(stem: str) -> str:
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
- summary

## Why it matters
- matters

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
- source-only for now

## What future cluster would absorb this
- future cluster

## Related pages
- none

## Open questions
- none

## Source trace
- `raw/fake.pdf`
"""


def content_quality_scaffold() -> str:
    return """### Core model
model

### Common misread
misread

### Key variables
- variable

### Mechanism
mechanism

### Evidence ladder
evidence

### Concrete examples
example

### Boundary
boundary
"""


class WikiStage2EvalTest(unittest.TestCase):
    def test_content_quality_scaffold_missing_sections_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            write_page(
                root,
                "wiki/concept--thin.md",
                """---
title: "Thin Concept"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "concept--thin"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--thin

## Summary
summary

## Why it matters here
matters

## Main body
body

## Related pages
- none

## Open questions
- none

## Source trace
- `raw/fake.pdf`
""",
            )

            report = evaluate(root, context=fixed_context())
            page_report = next(page for page in report["pages"] if page["page"] == "wiki/concept--thin.md")
            result = next(
                item for item in page_report["results"] if item["eval"] == "content_quality_scaffold_present"
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(result["pass"])
            self.assertEqual(
                result["detail"]["missing_sections"],
                [
                    "Core model",
                    "Common misread",
                    "Key variables",
                    "Mechanism",
                    "Evidence ladder",
                    "Concrete examples",
                    "Boundary",
                ],
            )

    def test_synthesis_source_count_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            write_page(root, "wiki/source--one.md", simple_source("source--one"))
            write_page(root, "wiki/source--two.md", simple_source("source--two"))
            write_page(
                root,
                "wiki/synthesis--mismatch.md",
                """---
title: "Mismatch Synthesis"
page_type: "synthesis"
corpus: "wiki"
source_count: 1
aliases:
  - "synthesis--mismatch"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--mismatch

## Question
question

## Short answer
answer

## Evidence considered
- [[source--one]]
- [[source--two]]

## Analysis
### A
text

## Decision / takeaway
decide

## Follow-up questions
- none
""",
            )

            report = evaluate(root, context=fixed_context())
            schema = load_schema(STAGE2_REPORT_SCHEMA_PATH)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["generated_at"], "2026-04-15T03:45:00Z")
            self.assertEqual(validate_with_schema(report, schema), [])
            self.assertEqual(report["pages"][0]["page"], "wiki/synthesis--mismatch.md")
            self.assertEqual(
                report["pages"][0]["results"][0]["eval"],
                "declared_source_count_matches_evidence",
            )
            self.assertFalse(report["pages"][0]["results"][0]["pass"])

    def test_query_pages_are_not_checked_for_source_count_consistency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            write_page(root, "wiki/source--one.md", simple_source("source--one"))
            write_page(
                root,
                "wiki/query--router.md",
                """---
title: "Router Query"
page_type: "query"
corpus: "wiki"
source_count: 99
question_scope: "news-snapshot-corpus"
aliases:
  - "query--router"
tags:
  - "corpus/wiki"
  - "type/query"
---

# query--router

## Question
question

## Short answer
answer

## Evidence considered
- [[source--one]]

## Analysis
text

## Decision / takeaway
decide

## Follow-up questions
- none
""",
            )

            report = evaluate(root)
            self.assertEqual(report["status"], "pass")
            self.assertFalse(any(page["page"] == "wiki/query--router.md" for page in report["pages"]))

    def test_central_research_source_missing_anchor_layer_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            write_page(
                root,
                "wiki/source--paper.md",
                """---
title: "Paper"
page_type: "source"
corpus: "wiki"
source_type: "domain-research-paper"
research_mode: "experiment"
aliases:
  - "source--paper"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--paper

## Title
Paper

## Source
- `raw/paper.pdf`

## Type
domain-research-paper

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

## Research frame
text

## Related pages
- [[concept--linker-1]]

## Open questions
- none

## Source trace
- `raw/paper.pdf`
""",
            )
            for index in range(1, 6):
                write_page(
                    root,
                    f"wiki/concept--linker-{index}.md",
                    f"""---
title: "Linker {index}"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "concept--linker-{index}"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--linker-{index}

## Summary
summary

## Why it matters here
matters

## Main body
{content_quality_scaffold()}
- [[source--paper]]

## Related pages
- [[source--paper]]

## Open questions
- none

## Source trace
- `raw/fake.pdf`
""",
                )

            report = evaluate(root)
            page_report = next(page for page in report["pages"] if page["page"] == "wiki/source--paper.md")
            result = next(
                item for item in page_report["results"] if item["eval"] == "central_research_source_has_anchor_layer"
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(result["pass"])
            self.assertEqual(
                result["detail"]["missing_sections"],
                [
                    "What this source adds to the corpus",
                    "How strong is the evidence",
                    "What this source does not establish",
                ],
            )

    def test_broad_synthesis_without_boundary_sections_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            for index in range(1, 6):
                write_page(root, f"wiki/source--s{index}.md", simple_source(f"source--s{index}"))

            analysis_lines = []
            for label in ["A", "B", "C", "D", "E"]:
                analysis_lines.append(f"### {label}")
                analysis_lines.extend([f"line {label}-{i}" for i in range(1, 10)])

            write_page(
                root,
                "wiki/synthesis--broad.md",
                f"""---
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

## Decision / takeaway
decide

## Follow-up questions
- none
""",
            )

            report = evaluate(root)
            page_report = next(page for page in report["pages"] if page["page"] == "wiki/synthesis--broad.md")
            result = next(
                item for item in page_report["results"] if item["eval"] == "broad_synthesis_has_boundary_sections"
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(result["pass"])
            self.assertEqual(
                result["detail"]["missing_sections"],
                [
                    "What this synthesis excludes",
                    "Tensions / contradictions",
                    "Implications for future ingest",
                ],
            )

    def test_seed_source_missing_absorption_hint_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            write_page(
                root,
                "wiki/source--seed.md",
                """---
title: "Seed Source"
page_type: "source"
corpus: "wiki"
source_type: "news-snapshot"
aliases:
  - "source--seed"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--seed

## Title
Seed Source

## Source
- `raw/seed.md`

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

## Related pages
- [[index]]

## Open questions
- none

## Source trace
- `raw/seed.md`
""",
            )
            write_page(
                root,
                "wiki/index.md",
                """---
title: "Index"
page_type: "query"
corpus: "wiki"
question_scope: "router"
aliases:
  - "index"
tags:
  - "corpus/wiki"
  - "type/query"
---

# index

## Question
question

## Short answer
answer

## Evidence considered
- [[source--seed]]

## Analysis
text

## Decision / takeaway
decide

## Follow-up questions
- none
""",
            )

            report = evaluate(root)
            page_report = next(page for page in report["pages"] if page["page"] == "wiki/source--seed.md")
            result = next(
                item for item in page_report["results"] if item["eval"] == "seed_source_has_absorption_hint"
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(result["pass"])
            self.assertEqual(
                result["detail"]["missing_sections"],
                [
                    "Why this is source-only for now",
                    "What future cluster would absorb this",
                ],
            )

    def test_source_with_stable_inbound_is_not_checked_as_seed_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            seed_policy(root)
            write_page(root, "wiki/source--one.md", simple_source("source--one"))
            write_page(
                root,
                "wiki/concept--uses-source.md",
                """---
title: "Concept"
page_type: "concept"
corpus: "wiki"
canonical: true
aliases:
  - "concept--uses-source"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--uses-source

## Summary
summary

## Why it matters here
matters

## Main body
{content_quality_scaffold()}
- [[source--one]]

## Related pages
- [[source--one]]

## Open questions
- none

## Source trace
- `raw/fake.pdf`
""",
            )

            report = evaluate(root)
            self.assertFalse(any(page["page"] == "wiki/source--one.md" for page in report["pages"]))


if __name__ == "__main__":
    unittest.main()
