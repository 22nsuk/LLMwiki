from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops.scripts.core.filesystem_runtime import (
    atomic_multi_write as real_atomic_multi_write,
)
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.eval.source_page_substance_runtime import (
    evaluate_source_page_substance,
)
from ops.scripts.eval.wiki_page_runtime import section_body
from ops.scripts.registry import source_substance_cohort_remediate as remediation
from tests.minimal_vault_runtime import seed_minimal_vault

FIXED_CONTEXT = RuntimeContext(
    clock=lambda: dt.datetime(2026, 7, 12, 3, 4, 5, tzinfo=dt.UTC),
    display_timezone=dt.UTC,
)

ENGLISH_SENTENCES = (
    "The field team measured twelve stable samples.",
    "The second trial reduced processing time by six minutes.",
    "Independent reviewers confirmed the recorded temperature range.",
    "The final dataset retained every accepted observation.",
    "A separate audit reproduced the reported sample count.",
    "The published method documents the bounded collection window.",
)

KOREAN_SENTENCES = (
    "연구팀은 첫 번째 실험에서 안정적인 결과를 확인했다.",
    "두 번째 측정은 처리 시간을 여섯 분 줄였다.",
    "독립 검토자는 기록된 온도 범위를 다시 확인했다.",
    "최종 자료는 승인된 관측값을 모두 보존했다.",
    "별도 감사는 보고된 표본 수를 재현했다.",
    "공개된 방법은 제한된 수집 기간을 문서화했다.",
)


def weak_page(raw_path: str, *, summary: str = "Synthetic Source") -> str:
    return f"""---
title: Synthetic Source
page_type: source
corpus: content
registry_id: W-TEST
aliases: [source--synthetic]
tags: [source]
raw_path: {raw_path}
primary_lens: field team trial reviewers dataset audit method 연구팀 측정 검토자 자료 감사 방법 최종 승인 관측값 공개 수집 기간
---

# Synthetic Source

## Source

- Synthetic publication

## Type

- Test source

## Summary

{summary}

## Why it matters

This section must remain byte-for-byte stable.

## Key points

- Incomplete point...

## Limitations / caveats

- The synthetic sample covers one controlled setting only.

## Related pages

- [[synthesis--synthetic]]

## Open questions

- Which controlled setting should be tested next?

## Source trace

- `{raw_path}`
"""


def raw_markdown(sentences: tuple[str, ...] = ENGLISH_SENTENCES) -> str:
    return """---
title: Raw fixture
source: synthetic
---

![decorative image](image.png)

""" + "\n\n".join(
        [
            sentences[0],
            f"[{sentences[1]}](https://example.invalid/reference)",
            sentences[2],
            sentences[3],
            sentences[4],
            sentences[5],
            "Copyright 2026 Synthetic Publisher. All rights reserved.",
        ]
    )


class SuccessfulPdfExtractor:
    def __init__(self, text: str) -> None:
        self.text = text
        self.paths: list[Path] = []

    def extract(self, path: Path) -> str:
        self.paths.append(path)
        return self.text.replace(".", f" for {path.stem}.")


class FailingPdfExtractor:
    def extract(self, path: Path) -> str:
        raise RuntimeError(f"synthetic failure for {path.name}")


class SourceSubstanceCohortRemediateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.vault = Path(self.temporary_directory.name)
        seed_minimal_vault(self.vault)
        for root_name in ("wiki", "system"):
            for path in (self.vault / root_name).glob("source--*.md"):
                path.unlink()
        (self.vault / "raw").mkdir(exist_ok=True)
        (self.vault / "wiki/synthesis--synthetic.md").write_text(
            "# Synthetic synthesis\n\n- [[source--synthetic]]\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _write_page(
        self,
        *,
        root: str = "wiki",
        name: str = "source--synthetic.md",
        raw_path: str = "raw/synthetic.md",
        text: str | None = None,
    ) -> Path:
        path = self.vault / root / name
        path.write_text(text or weak_page(raw_path), encoding="utf-8")
        return path

    def _write_raw(self, text: str, name: str = "synthetic.md") -> Path:
        path = self.vault / "raw" / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_english_markdown_dry_run_is_source_faithful_and_schema_valid(self) -> None:
        page = self._write_page()
        raw = self._write_raw(raw_markdown())
        page_before = page.read_bytes()
        raw_before = raw.read_bytes()

        report = remediation.build_report(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(page.read_bytes(), page_before)
        self.assertEqual(raw.read_bytes(), raw_before)
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(report["summary"]["candidate_ready"], 1)
        entry = report["entries"][0]
        self.assertEqual(entry["status"], "candidate_ready")
        self.assertTrue(entry["candidate_eval"]["pass"])
        self.assertEqual(len(entry["summary_sentence_digests"]), 2)
        self.assertEqual(len(entry["key_point_sentence_digests"]), 4)
        serialized = json.dumps(report, ensure_ascii=False)
        for sentence in ENGLISH_SENTENCES:
            self.assertNotIn(sentence, serialized)
        schema = load_schema(
            Path(remediation.__file__).parents[2]
            / "schemas/source-substance-cohort-remediation.schema.json"
        )
        self.assertEqual(validate_with_schema(report, schema), [])

    def test_korean_markdown_apply_is_atomic_and_preserves_unrepaired_content(
        self,
    ) -> None:
        page = self._write_page(root="system")
        raw = self._write_raw(raw_markdown(KOREAN_SENTENCES))
        before = page.read_text(encoding="utf-8")
        frontmatter_before = before.split("---", 2)[1]
        why_before = section_body(before, "Why it matters")

        with patch.object(
            remediation,
            "atomic_multi_write",
            wraps=real_atomic_multi_write,
        ) as atomic_write:
            report = remediation.apply_remediation(
                self.vault, context=FIXED_CONTEXT, enforce_registry=False
            )

        atomic_write.assert_called_once()
        after = page.read_text(encoding="utf-8")
        entry = report["entries"][0]
        self.assertEqual(report["mode"], "apply")
        self.assertEqual(entry["status"], "applied")
        self.assertNotEqual(entry["page_sha256_before"], entry["page_sha256_after"])
        self.assertEqual(entry["page_sha256_after"], entry["page_sha256_candidate"])
        self.assertEqual(after.split("---", 2)[1], frontmatter_before)
        self.assertEqual(section_body(after, "Why it matters"), why_before)
        self.assertTrue(evaluate_source_page_substance(after)["pass"])
        self.assertEqual(
            raw.read_text(encoding="utf-8"), raw_markdown(KOREAN_SENTENCES)
        )
        self.assertEqual(list(page.parent.glob(f".{page.name}.*.tmp")), [])

    def test_existing_passing_summary_is_preserved_when_only_key_points_fail(
        self,
    ) -> None:
        passing_summary = (
            "Operators measured twelve stable samples. "
            "Reviewers confirmed the recorded temperature range."
        )
        page = self._write_page(
            text=weak_page("raw/synthetic.md", summary=passing_summary)
        )
        self._write_raw(raw_markdown())

        remediation.apply_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        after = page.read_text(encoding="utf-8")
        self.assertEqual(section_body(after, "Summary").strip(), passing_summary)
        self.assertTrue(evaluate_source_page_substance(after)["pass"])

    def test_summary_repair_fails_closed_when_only_raw_facts_duplicate_key_points(
        self,
    ) -> None:
        page_text = weak_page("raw/synthetic.md")
        passing_key_points = "\n".join(
            f"- {sentence}" for sentence in ENGLISH_SENTENCES
        )
        page_text = page_text.replace("- Incomplete point...", passing_key_points)
        page = self._write_page(text=page_text)
        self._write_raw(raw_markdown())
        before_key_points = section_body(page_text, "Key points")

        before = page.read_bytes()
        report = remediation.apply_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(page.read_bytes(), before)
        self.assertEqual(
            section_body(page.read_text(encoding="utf-8"), "Key points"),
            before_key_points,
        )
        self.assertEqual(report["entries"][0]["status"], "operator_review")

    def test_summary_only_repair_preserves_passing_key_points(self) -> None:
        passing_key_points = "\n".join(
            [
                "- Operators archived the calibration protocol for later audits.",
                "- The control group retained its original sampling schedule.",
                "- Reviewers documented the equipment boundary before collection.",
                "- The published appendix identifies the independent review window.",
            ]
        )
        page_text = weak_page("raw/synthetic.md").replace(
            "- Incomplete point...", passing_key_points
        )
        self._write_page(text=page_text)
        self._write_raw(raw_markdown())

        build = remediation.build_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(build.report["summary"]["candidate_ready"], 1)
        entry = build.report["entries"][0]
        candidate = build.candidates[0].after_text
        self.assertEqual(len(entry["summary_sentence_digests"]), 2)
        self.assertEqual(entry["key_point_sentence_digests"], [])
        self.assertEqual(
            section_body(candidate, "Key points"),
            section_body(page_text, "Key points"),
        )
        self.assertNotEqual(
            section_body(candidate, "Summary"),
            section_body(page_text, "Summary"),
        )

    def test_truncated_and_insufficient_raw_never_writes(self) -> None:
        page = self._write_page()
        raw_text = " ".join(
            [
                ENGLISH_SENTENCES[0],
                ENGLISH_SENTENCES[1],
                ENGLISH_SENTENCES[2],
                "The fourth observation is truncated without terminal punctuation",
            ]
        )
        self._write_raw(raw_text, name="synthetic.md")
        before = page.read_bytes()

        report = remediation.apply_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(page.read_bytes(), before)
        entry = report["entries"][0]
        self.assertEqual(entry["status"], "operator_review")
        self.assertIn("insufficient_key_point_sentences", entry["reason_codes"])
        self.assertIsNone(entry["page_sha256_after"])

    def test_missing_raw_path_is_operator_review(self) -> None:
        page = self._write_page(raw_path="raw/does-not-exist.md")
        before = page.read_bytes()

        report = remediation.apply_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(page.read_bytes(), before)
        self.assertEqual(report["entries"][0]["status"], "operator_review")
        self.assertEqual(report["entries"][0]["reason_codes"], ["raw_path_not_file"])

    def test_pdf_extractor_success_and_failure_are_reported_without_binary_coupling(
        self,
    ) -> None:
        success_page = self._write_page(
            name="source--pdf-success.md",
            raw_path="raw/success.pdf",
            text=weak_page("raw/success.pdf"),
        )
        failure_page = self._write_page(
            name="source--pdf-failure.md",
            raw_path="raw/failure.pdf",
            text=weak_page("raw/failure.pdf"),
        )
        (self.vault / "raw/success.pdf").write_bytes(b"synthetic-pdf-success")
        (self.vault / "raw/failure.pdf").write_bytes(b"synthetic-pdf-failure")
        extractor = SuccessfulPdfExtractor(" ".join(ENGLISH_SENTENCES))

        default_report = remediation.build_report(
            self.vault,
            context=FIXED_CONTEXT,
            pdf_extractor=extractor,
            enforce_registry=False,
        )
        for entry in default_report["entries"]:
            self.assertEqual(entry["status"], "operator_review")
            self.assertEqual(entry["reason_codes"], ["pdf_requires_operator_review"])

        success_report = remediation.build_report(
            self.vault,
            context=FIXED_CONTEXT,
            pdf_extractor=extractor,
            enforce_registry=False,
            allow_pdf_candidates=True,
        )
        success_entries = {entry["page"]: entry for entry in success_report["entries"]}
        self.assertEqual(
            success_entries["wiki/source--pdf-success.md"]["status"],
            "candidate_ready",
        )
        self.assertEqual(len(extractor.paths), 2)

        failure_report = remediation.build_report(
            self.vault,
            context=FIXED_CONTEXT,
            pdf_extractor=FailingPdfExtractor(),
            enforce_registry=False,
            allow_pdf_candidates=True,
        )
        for entry in failure_report["entries"]:
            self.assertEqual(entry["status"], "operator_review")
            self.assertEqual(entry["reason_codes"], ["pdf_extraction_failed"])
        self.assertTrue(success_page.is_file())
        self.assertTrue(failure_page.is_file())

    def test_leading_noise_is_rejected_before_relevant_source_facts(self) -> None:
        self._write_page()
        noisy_raw = "\n\n".join(
            [
                "By Synthetic Reporter reporter@example.invalid.",
                "사진=Example Publisher copyright image credit.",
                "기사 듣기 글자 크기 관련 기사.",
                *ENGLISH_SENTENCES,
            ]
        )
        self._write_raw(noisy_raw)

        build = remediation.build_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(build.report["summary"]["candidate_ready"], 1)
        candidate = build.candidates[0].after_text
        self.assertNotIn("Synthetic Reporter", candidate)
        self.assertNotIn("사진=", candidate)
        self.assertNotIn("기사 듣기", candidate)
        self.assertIn(ENGLISH_SENTENCES[2], candidate)

    def test_structural_news_noise_and_fragments_are_rejected(self) -> None:
        noisy = (
            "NEW YORK, June 17 (Reuters) - Synthetic markets opened higher.",
            "(서울=연합뉴스) 합성 시장이 상승했다.",
            "FILE PHOTO: An analyst walks past a synthetic display.",
            "Reuters.",
            '"An unfinished quotation ended without its pair.',
            "123.4 shares rose after the announcement.",
        )

        extracted = remediation.extract_complete_sentences(
            "\n".join((*noisy, *ENGLISH_SENTENCES))
        )

        self.assertEqual(extracted, list(ENGLISH_SENTENCES))

    def test_candidate_quality_rejects_contained_and_same_number_claims(self) -> None:
        contained = weak_page("raw/synthetic.md").replace(
            "\nSynthetic Source\n\n## Why it matters",
            "\nOperators measured twelve stable samples. "
            "Independent reviewers confirmed the temperature range."
            "\n\n## Why it matters",
        ).replace(
            "- Incomplete point...",
            "- The field team measured twelve stable samples during the trial.\n"
            "- The team measured twelve stable samples.\n"
            "- Reviewers confirmed the recorded temperature range.\n"
            "- The final dataset retained every accepted observation.",
        )

        self.assertEqual(
            remediation._candidate_section_quality_reason(contained),
            "candidate_section_near_duplicate",
        )

    def test_cross_page_sentence_reuse_requires_operator_review(self) -> None:
        self._write_page(name="source--first.md", raw_path="raw/first.md")
        self._write_page(name="source--second.md", raw_path="raw/second.md")
        self._write_raw(raw_markdown(), name="first.md")
        self._write_raw(raw_markdown(), name="second.md")

        report = remediation.build_report(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(report["summary"]["candidate_ready"], 0)
        self.assertEqual(report["summary"]["operator_review"], 2)
        self.assertEqual(
            {tuple(entry["reason_codes"]) for entry in report["entries"]},
            {("sentence_reused_across_source_pages",)},
        )

    def test_registry_path_target_hash_and_trace_are_fail_closed(self) -> None:
        self._write_page()
        raw = self._write_raw(raw_markdown())
        raw_sha256 = hashlib.sha256(raw.read_bytes()).hexdigest()
        registry_path = self.vault / "ops/raw-registry.json"
        registry_path.write_text(
            json.dumps(
                {
                    "entries": [
                        {
                            "registry_id": "W-TEST",
                            "target_page": "source--synthetic",
                            "storage_path": "raw/synthetic.md",
                            "content_sha256": raw_sha256,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        current = remediation.build_report(self.vault, context=FIXED_CONTEXT)
        self.assertEqual(current["summary"]["candidate_ready"], 1)

        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["entries"][0]["content_sha256"] = "0" * 64
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        drifted = remediation.build_report(self.vault, context=FIXED_CONTEXT)

        self.assertEqual(drifted["summary"]["candidate_ready"], 0)
        self.assertEqual(
            drifted["entries"][0]["reason_codes"],
            ["registry_raw_sha256_mismatch"],
        )

    def test_raw_fidelity_failure_is_operator_review_and_never_writes(self) -> None:
        page = self._write_page()
        self._write_raw(raw_markdown())
        before = page.read_bytes()
        alien_sentences = [
            "This sentence was never present in the normalized raw source.",
            *ENGLISH_SENTENCES,
        ]

        with patch.object(
            remediation,
            "_rank_source_sentences",
            return_value=alien_sentences,
        ):
            report = remediation.apply_remediation(
                self.vault, context=FIXED_CONTEXT, enforce_registry=False
            )

        self.assertEqual(page.read_bytes(), before)
        entry = report["entries"][0]
        self.assertEqual(entry["reason_codes"], ["raw_fidelity_failed"])
        self.assertEqual(entry["used_sentence_count"], 6)
        self.assertEqual(len(entry["summary_sentence_digests"]), 2)
        self.assertEqual(len(entry["key_point_sentence_digests"]), 4)
        self.assertIsNone(entry["candidate_eval"])
        self.assertIsNone(entry["page_sha256_candidate"])

    def test_default_cli_prints_report_without_writing(self) -> None:
        page = self._write_page()
        self._write_raw(raw_markdown())
        before = page.read_bytes()
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            return_code = remediation.main(["--vault", str(self.vault)])

        self.assertEqual(return_code, 0)
        self.assertEqual(page.read_bytes(), before)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["mode"], "dry_run")

    def test_apply_is_idempotent(self) -> None:
        page = self._write_page()
        self._write_raw(raw_markdown())

        first = remediation.apply_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )
        after_first = page.read_bytes()
        second = remediation.apply_remediation(
            self.vault, context=FIXED_CONTEXT, enforce_registry=False
        )

        self.assertEqual(first["summary"]["applied"], 1)
        self.assertEqual(page.read_bytes(), after_first)
        self.assertEqual(second["summary"]["failed_pages"], 0)
        self.assertEqual(second["summary"]["applied"], 0)


if __name__ == "__main__":
    unittest.main()
