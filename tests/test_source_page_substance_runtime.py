from __future__ import annotations

import re
import unittest

from ops.scripts.eval.source_page_substance_runtime import (
    evaluate_source_page_substance,
)
from ops.scripts.eval.wiki_page_runtime import section_body


def cohort_336_fingerprint_source_text(title: str = "Example Corp policy shift") -> str:
    """Fixture matching 2026-05-29 / 2026-06-17 weak-intake fingerprints."""
    return f"""---
title: "{title}"
page_type: "source"
corpus: "wiki"
---

# {title}

## Summary
{title}

## Key points
- {title}
- 에 관한 news snapshot이다
- padding bullet one
- padding bullet two

## Limitations / caveats
- news snapshot caveat

## Open questions
- 반복 mechanism인가, 일회성 event인가
"""


def legacy_count_only_substance_pass(text: str) -> bool:
    key_points_body = section_body(text, "Key points") or ""
    limitations_body = section_body(text, "Limitations / caveats") or ""
    key_points = re.findall(r"^[-*]\s+", key_points_body, flags=re.MULTILINE)
    limitations = re.findall(r"^[-*]\s+", limitations_body, flags=re.MULTILINE)
    return len(key_points) >= 4 and len(limitations) >= 1


class SourcePageSubstanceRuntimeTests(unittest.TestCase):
    def test_rejects_title_repeating_summary_and_boilerplate(self) -> None:
        text = """---
title: Example Corp raises funding
---

# Example Corp raises funding

## Summary
Example Corp raises funding is important.

## Key points
- Example Corp raises funding
- more detail one
- more detail two
- more detail three

## Limitations / caveats
- news snapshot caveat applies generally
"""
        result = evaluate_source_page_substance(text)
        self.assertFalse(result["pass"])
        self.assertIn("summary_repeats_title", result["failures"])
        self.assertIn("generic_snapshot_caveat", result["failures"])

    def test_accepts_substantive_source_page(self) -> None:
        text = """---
title: Example Corp raises funding
---

# Example Corp raises funding

## Summary
Example Corp closed a $40M Series B led by Acme Capital in March 2026. The round values the company near $300M pre-money.

## Key points
- $40M Series B led by Acme Capital
- valuation near $300M pre-money
- proceeds earmarked for inference infrastructure
- management expects margin pressure from GPU costs

## Limitations / caveats
- press release only; audited financials not provided
"""
        result = evaluate_source_page_substance(text)
        self.assertTrue(result["pass"])

    def test_cohort_336_fingerprint_fails_despite_legacy_count_threshold(self) -> None:
        text = cohort_336_fingerprint_source_text()
        self.assertTrue(legacy_count_only_substance_pass(text))
        result = evaluate_source_page_substance(text)
        self.assertFalse(result["pass"])
        self.assertIn("boilerplate_key_point_pattern", result["failures"])
        self.assertIn("generic_snapshot_caveat", result["failures"])
        self.assertIn("generic_open_question_fingerprint", result["failures"])
        self.assertIn("summary_repeats_title", result["failures"])
