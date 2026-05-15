from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.schema_constants_runtime import (
    RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH,
    RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
)
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.raw_intake_promotion_runtime import (
    render_family_pages,
    scaffold_profile_bundle,
    validate_profile_bundle,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def sample_family() -> dict:
    return {
        "family_slug": "cyber-statecraft-and-ai-security",
        "registry_ids": ["W-224", "W-270"],
        "synthesis": {
            "stem": "synthesis--cyber-statecraft-and-ai-security-2026-04-22",
            "title": "Cyber Statecraft and AI Security 2026-04-22",
            "created": "2026-04-22",
            "question": "이 축의 관련 source들을 함께 읽으면 어떤 공통 구조가 드러나는가?",
            "short_answer": "Cyber news는 실제 incident와 state signaling을 함께 본다.",
            "source_stems": [
                "source--chrome-extension-breach-hits-telegram-and-google-accounts-2026-04-21",
                "source--cyber-coercion-against-korea-by-china-russia-and-north-korea-2026-04-21",
            ],
            "bridge_source_stems": [
                "source--anthropic-mythos-security-claims-critique-2026-04-12",
            ],
            "integration_note": (
                "기존 corpus의 Mythos critique와 이번 intake incident/statecraft source를 함께 읽으면 "
                "보안 claim과 실제 coercion surface를 같은 route에서 분리해 볼 수 있다."
            ),
            "bridge_integration": {
                "kind": "bridge_context_integrated",
            },
            "analysis_blocks": [
                {
                    "heading": "일상 breach surface도 실제 피해를 만든다",
                    "body": "브라우저 확장 같은 저수준 surface가 대규모 계정 탈취의 입구가 된다.",
                    "purpose": "surface-risk-signal",
                },
                {
                    "heading": "국가는 cyber를 강압 신호로 쓴다",
                    "body": "침해는 기술문제이자 외교 압박 메시지가 된다.",
                    "purpose": "statecraft-frame",
                },
                {
                    "heading": "AI security rhetoric는 빠르게 geopolitics로 번역된다",
                    "body": "독립 검증 전에도 capability rhetoric가 지정학적 언어로 증폭된다.",
                    "purpose": "bridge-integration",
                },
            ],
            "what_this_synthesis_excludes": [
                "이 문서는 순수 benchmark debate만을 직접 다루지 않는다."
            ],
            "tensions_and_contradictions": [
                "저수준 breach reality와 과장된 cyber super-weapon 서사는 다른 속도로 움직인다."
            ],
            "implications_for_future_ingest": [
                "후속 source는 incident, coercion, AI security rhetoric를 먼저 분리 태깅한다."
            ],
            "decision_or_takeaway": "Cyber route는 incident와 statecraft를 같이 읽게 만든다.",
            "follow_up_questions": [
                "AI security rhetoric는 언제 실증 evidence를 앞질러 정책을 움직이는가?"
            ],
            "related_pages": ["query--raw-intake-absorption-decisions-2026-04-22"],
            "source_trace": [
                "wiki/query--raw-intake-absorption-decisions-2026-04-22.md",
                "raw/web-snapshots/demo.md",
            ],
        },
        "concept": {
            "stem": "concept--cyber-statecraft-and-ai-security",
            "title": "Cyber Statecraft and AI Security",
            "created": "2026-04-22",
            "summary": "Cyber incident와 국가 강압, AI security rhetoric를 함께 읽는 개념이다.",
            "why_it_matters_here": "보안 뉴스는 실제 침해와 geopolitics를 함께 본다.",
            "main_body_blocks": [
                {
                    "heading": "일상 surface가 실제 피해를 만든다",
                    "body": "브라우저·계정 surface가 침해의 입구가 될 수 있다.",
                },
                {
                    "heading": "국가는 cyber를 강압 signal로 쓴다",
                    "body": "침해는 정책 메시지와 결합된다.",
                },
                {
                    "heading": "AI security rhetoric는 지정학 언어로 증폭된다",
                    "body": (
                        "Mythos critique와 policy response가 세운 검증 축은 실제 breach와 "
                        "state pressure surface를 함께 묶으면서 capability claim이 국가경쟁 "
                        "서사로 번지는 경로를 보강한다."
                    ),
                },
            ],
            "scope_boundaries": ["이 concept는 incident와 statecraft가 함께 보일 때 적합하다."],
            "examples_and_non_examples": ["example은 browser breach와 state-backed coercion 조합이다."],
            "how_to_reuse_this_concept": ["incident, coercion, rhetoric 세 층을 분리 표시한다."],
            "focus_source_stems": [
                "source--chrome-extension-breach-hits-telegram-and-google-accounts-2026-04-21"
            ],
            "bridge_source_stems": [
                "source--anthropic-mythos-security-claims-critique-2026-04-12",
                "source--ai-security-and-mythos-policy-response-2026-04-17",
            ],
            "continuity_resolution": {
                "status": "integrated_in_main_body",
            },
            "carryover_decision": "Mythos security follow-up과 기존 policy-response source를 bridge로 유지한다.",
            "related_pages": ["query--raw-intake-absorption-decisions-2026-04-22"],
            "open_questions": ["consumer breach surface와 state coercion은 언제 같은 route로 연결되는가?"],
            "source_trace": [
                "wiki/synthesis--cyber-statecraft-and-ai-security-2026-04-22.md",
                "raw/web-snapshots/demo.md",
            ],
        },
    }


def sample_refresh() -> dict:
    return {
        "target_stem": "synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14",
        "registry_ids": ["W-301", "W-302"],
        "synthesis": {
            "stem": "synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14",
            "title": "Korea FX Liquidity and Spot-Dollar Pressure 2026-04-14",
            "created": "2026-04-14",
            "question": "question",
            "short_answer": "answer",
            "source_stems": [
                "source--wgbi-inflows-boost-korean-bond-demand-2026-04-21",
                "source--korean-corporate-dollar-hoarding-on-fx-fears-2026-04-21",
            ],
            "bridge_source_stems": [
                "source--wgbi-inclusion-and-korea-bond-inflows-fx-stability-2026-04-14",
                "source--cgfs-foreign-currency-funding-risk-and-cross-border-liquidity-2026-04-14",
            ],
            "integration_note": (
                "기존 corpus의 buffer/funding frame에 이번 intake의 corporate hoarding과 larger WGBI inflow를 "
                "겹치면, buffer와 spot pressure가 동시에 커질 수 있는 구조가 더 선명해진다."
            ),
            "bridge_integration": {
                "kind": "bridge_context_integrated",
            },
            "analysis_blocks": [
                {
                    "heading": "spot pressure와 funding buffer를 분리해야 한다",
                    "body": "기존 source는 funding 안정이 남아 있어도 환율 압력이 커질 수 있음을 보여 준다.",
                    "purpose": "legacy-frame-refresh",
                },
                {
                    "heading": "corporate demand는 spot pressure를 자율적으로 키운다",
                    "body": "새 intake는 precautionary demand가 정책 buffer와 별개로 가격을 밀 수 있음을 보강한다.",
                    "purpose": "new-signal",
                },
                {
                    "heading": "bond inflow는 완충재지만 자동 해법은 아니다",
                    "body": "WGBI inflow가 커져도 현물환시장 안정으로 곧장 번역되지 않는다는 점이 반복된다.",
                    "purpose": "integrated-takeaway",
                },
            ],
            "what_this_synthesis_excludes": ["macro 전체가 아니라 FX layer를 본다."],
            "tensions_and_contradictions": ["buffer와 pressure가 동시에 강화된다."],
            "implications_for_future_ingest": ["spot, funding, reserve, policy를 분리 태깅한다."],
            "decision_or_takeaway": "buffered-but-stressed frame이 핵심이다.",
            "follow_up_questions": ["spot pressure가 funding impairment로 번지는 선행지표는 무엇인가?"],
            "related_pages": [
                "concept--korea-fx-liquidity-and-spot-dollar-pressure",
                "query--raw-intake-absorption-decisions-2026-04-22",
            ],
            "source_trace": [
                "raw/web-snapshots/demo.md",
                "wiki/query--raw-intake-absorption-decisions-2026-04-22.md",
            ],
        },
    }


class RawIntakePromotionRuntimeTest(unittest.TestCase):
    def test_scaffold_groups_create_and_refresh_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            matrix_path = temp_path / "raw-intake-absorption-matrix-2026-04-22.json"
            (temp_path / "wiki").mkdir()
            (temp_path / "wiki" / "source--anthropic-mythos-security-claims-critique-2026-04-12.md").write_text(
                """---
title: "Anthropic Mythos Security Claims Critique"
page_type: "source"
corpus: "wiki"
aliases:
  - "source--anthropic-mythos-security-claims-critique-2026-04-12"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--anthropic-mythos-security-claims-critique-2026-04-12

## Title
Anthropic Mythos Security Claims Critique

## Summary
AI security rhetoric and cyber capability claims need independent validation.

## Why it matters
The source is useful bridge context for cyber statecraft and security analysis.

## Related pages
- [[concept--ai-capability-claims-verification]]
""",
                encoding="utf-8",
            )
            (temp_path / "wiki" / "synthesis--old.md").write_text(
                """---
title: "Old Synthesis"
page_type: "synthesis"
corpus: "wiki"
created: "2026-04-10"
aliases:
  - "synthesis--old"
tags:
  - "corpus/wiki"
  - "type/synthesis"
---

# synthesis--old

## Question
old question

## Short answer
old answer

## Evidence considered
- [[source--legacy-a-2026-04-10]]
- [[source--new-c-2026-04-21]]

## Analysis
### Legacy frame
body one

### Fresh signal
body two

### Integrated view
body three

## What this synthesis excludes
not this

## Tensions / contradictions
tension

## Implications for future ingest
future

## Decision / takeaway
takeaway

## Follow-up questions
- none

## Related pages
- [[index]]
- [[concept--old]]

## Source trace
- `raw/fake.pdf`
""",
                encoding="utf-8",
            )
            matrix_path.write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-22T11:00:00Z",
                        "matrix": [
                            {
                                "registry_id": "W-224",
                                "source_page": "wiki/source--demo-a-2026-04-21.md",
                                "proposed_action": "create_new_synthesis_family",
                                "target": "cyber-statecraft-and-ai-security",
                                "review_status": "reviewed",
                            },
                            {
                                "registry_id": "W-225",
                                "source_page": "wiki/source--demo-b-2026-04-21.md",
                                "proposed_action": "create_new_synthesis_family",
                                "target": "cyber-statecraft-and-ai-security",
                                "review_status": "approved",
                            },
                            {
                                "registry_id": "W-999",
                                "source_page": "wiki/source--demo-pending-2026-04-21.md",
                                "proposed_action": "create_new_synthesis_family",
                                "target": "cyber-statecraft-and-ai-security",
                                "review_status": "pending",
                            },
                            {
                                "registry_id": "W-226",
                                "source_page": "wiki/source--new-c-2026-04-21.md",
                                "proposed_action": "refresh_existing_synthesis",
                                "target": "synthesis--old",
                                "review_status": "reviewed",
                            },
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            manifest = scaffold_profile_bundle(matrix_path, vault=temp_path)

            self.assertEqual(manifest["family_count"], 1)
            self.assertEqual(manifest["refresh_count"], 1)
            metadata = {
                item["name"]: item["value"]
                for item in manifest["metadata"]["properties"]
            }
            self.assertEqual(metadata["skipped_unreviewed_entry_count"], "1")
            self.assertEqual(metadata["review_status_counts"], "approved:1,pending:1,reviewed:2")
            self.assertEqual(manifest["$schema"], RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH)
            schema = load_schema(REPO_ROOT / RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(manifest, schema), [])
            family = manifest["families"][0]
            refresh = manifest["refreshes"][0]
            self.assertEqual(family["family_slug"], "cyber-statecraft-and-ai-security")
            self.assertEqual(
                family["synthesis"]["source_stems"],
                ["source--demo-a-2026-04-21", "source--demo-b-2026-04-21"],
            )
            self.assertEqual(
                family["bridge_source_candidates"][0]["source_stem"],
                "source--anthropic-mythos-security-claims-critique-2026-04-12",
            )
            self.assertEqual(
                family["concept"]["bridge_source_stems"],
                ["source--anthropic-mythos-security-claims-critique-2026-04-12"],
            )
            self.assertEqual(refresh["target_stem"], "synthesis--old")
            self.assertEqual(refresh["synthesis"]["bridge_source_stems"], ["source--legacy-a-2026-04-10"])
            self.assertEqual(refresh["synthesis"]["source_stems"], ["source--new-c-2026-04-21"])

    def test_validate_manifest_rejects_split_continuity_and_followup_split_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            family = sample_family()
            family["synthesis"]["analysis_blocks"][0]["heading"] = "이 묶음이 새로 더하는 것"
            family["concept"]["continuity_blocks"] = [
                {
                    "heading": "기존 corpus와 이번 intake를 함께 읽으면 연속성이 분명해진다",
                    "body": "split continuity text",
                }
            ]
            refresh = sample_refresh()
            refresh["synthesis"]["analysis_blocks"][0]["heading"] = "2026-04-21 follow-up는 runtime issue"
            refresh["synthesis"]["integration_note"] = ""
            manifest_path.write_text(
                json.dumps({"families": [family], "refreshes": [refresh]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            report = validate_profile_bundle(manifest_path)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["$schema"], RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH)
            schema = load_schema(REPO_ROOT / RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH)
            self.assertEqual(validate_with_schema(report, schema), [])
            error_types = {item["type"] for item in report["errors"]}
            self.assertIn("concept_continuity_split_block_present", error_types)
            self.assertIn("missing_synthesis_integration_note", error_types)
            warning_types = {item["type"] for item in report["warnings"]}
            self.assertIn("analysis_template_marker_present", warning_types)
            self.assertIn("analysis_follow_up_split_marker_present", warning_types)

    def test_render_family_pages_builds_bridge_links_and_refresh_pages(self) -> None:
        rendered = render_family_pages({"families": [sample_family()], "refreshes": [sample_refresh()]})

        synthesis_text = rendered["wiki/synthesis--cyber-statecraft-and-ai-security-2026-04-22.md"]
        concept_text = rendered["wiki/concept--cyber-statecraft-and-ai-security.md"]
        refresh_text = rendered["wiki/synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14.md"]

        self.assertIn("## Analysis", synthesis_text)
        self.assertIn(
            "[[source--anthropic-mythos-security-claims-critique-2026-04-12]]",
            synthesis_text,
        )
        self.assertIn("기존 corpus의 Mythos critique", synthesis_text)

        self.assertIn("## Related pages", concept_text)
        self.assertIn("[[synthesis--cyber-statecraft-and-ai-security-2026-04-22]]", concept_text)
        self.assertIn("[[source--anthropic-mythos-security-claims-critique-2026-04-12]]", concept_text)
        self.assertIn("state pressure surface를 함께 묶으면서", concept_text)
        self.assertNotIn("기존 corpus와 이번 intake를 함께 읽으면 연속성이 분명해진다", concept_text)

        self.assertIn("[[concept--korea-fx-liquidity-and-spot-dollar-pressure]]", refresh_text)
        self.assertIn("[[source--wgbi-inclusion-and-korea-bond-inflows-fx-stability-2026-04-14]]", refresh_text)
        self.assertNotIn("### 2026-04-21 후속 근거", refresh_text)


if __name__ == "__main__":
    unittest.main()
