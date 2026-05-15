---
title: "Raw Unregistered File Review 2026-04-16"
page_type: "lint"
corpus: "system"
source_count: 33
created: "2026-04-16"
aliases:
  - "lint--raw-unregistered-file-review-2026-04-16"
tags:
  - "corpus/system"
  - "type/lint"
---

# lint--raw-unregistered-file-review-2026-04-16

## Question
현재 `raw/`에 남아 있는 unregistered raw files는 어떤 묶음으로 읽어야 하며, 어떤 기존 wiki/system route에 연결하거나 single-source ingest로 처리해야 하는가?

## Summary
`raw_registry_preflight` 기준 구조 오류는 닫혔다. `raw/claude-prompting-best-practices.md`는 frontmatter가 없어 preflight error를 만들고 있었고, markdown raw 16건은 `published`가 blank였다. Claude 파일은 source URL을 본문 중간 링크로 오인하지 않도록 `source: "unknown"`으로 안전하게 보정했고, 나머지 16건은 `raw_markdown_normalize --write`로 `published: "unknown"` 정규화만 적용했다.

이후 preflight는 `errors: 0`, `warnings: 33`이며 남은 warning은 모두 `unregistered_raw_file`이다. binary raw는 읽기만 했고 수정하지 않았다.

## Findings
남은 33건은 무작위 backlog가 아니라 세 덩어리로 나뉜다.

1. `prompt robustness / prompt contract / prompt guidance` cluster는 `system` corpus로 보내는 편이 맞다.
2. AI infra, AI capability, Middle East follow-up은 이미 존재하는 `wiki` route에 흡수할 수 있다.
3. health/science, oil-price policy, defense-industrial mobilization은 아직 단일 source seed로 두는 편이 안전하다.

## Raw inventory status
- total raw files: `195`
- markdown raw files: `140`
- PDF raw files: `55`
- normalization report: local-only validation artifact `tmp/raw-markdown-normalization-write-2026-04-16.json`
- preflight status after normalization: `warn`
- preflight errors after normalization: `0`
- preflight warnings after normalization: `33`

## Recommended fixes
다음 ingest는 아래 순서로 진행하는 편이 가장 비용 대비 효과가 크다.

## Priority 1 - system prompt robustness cluster
이 묶음은 새 system-side route가 필요하다. 권장 형태는 `concept--prompt-contract-robustness`와 `synthesis--prompt-robustness-and-contract-design-2026-04-16`이다. 기존 `wiki/ai-capability` shard에 넣기보다 maintainer/runtime prompt contract evidence로 다루는 편이 source intent와 더 잘 맞는다.

### Prompt guidance anchors
- `raw/claude-prompting-best-practices.md`
- `raw/web-snapshots/Prompt guidance for GPT-5.4.md`
- `raw/web-snapshots/프롬프트 작성 전략 개요    Generative AI on Vertex AI.md`

### Prompt perturbation / robustness papers
- `raw/2024.findings-eacl.91.pdf` — *Prompt Perturbation Consistency Learning for Robust Language Models*
- `raw/2026.findings-eacl.38.pdf` — *How Important is 'Perfect' English for Machine Translation Prompts?*
- `raw/2306.04528v5.pdf` — *PromptRobust: Towards Evaluating the Robustness of Large Language Models on Adversarial Prompts*
- `raw/2401.06766v3.pdf` — *Mind Your Format: Towards Consistent Evaluation of In-Context Learning Improvements*
- `raw/2402.14531v2.pdf` — *Should We Respect LLMs? A Cross-Lingual Study on the Influence of Prompt Politeness on LLM Performance*
- `raw/2406.12094v2.pdf` — *Who's asking? User personas and the mechanics of latent misalignment*
- `raw/2406.17737v2.pdf` — *LLM Targeted Underperformance Disproportionately Impacts Vulnerable Users*
- `raw/2505.13360v2.pdf` — *What Prompts Don't Say: Understanding and Managing Underspecification in LLM Prompts*
- `raw/2507.22168v2.pdf` — *Persona-Augmented Benchmarking: Evaluating LLMs Across Diverse Writing Styles*
- `raw/2510.04950v1.pdf` — *Mind Your Tone: Investigating How Prompt Politeness Affects LLM Accuracy*
- `raw/2510.09536v2.pdf` — *Evaluating Robustness of Large Language Models Against Multilingual Typographical Errors*
- `raw/2512.12812v2.pdf` — *Does Tone Change the Answer? Evaluating Prompt Politeness Effects on Modern LLMs: GPT, Gemini, and LLaMA*
- `raw/2601.06341v1.pdf` — *Evaluating Robustness of Large Language Models in Enterprise Applications: Benchmarks for Perturbation Consistency Across Formats and Languages*
- `raw/2602.04297v1.pdf` — *Revisiting Prompt Sensitivity in Large Language Models for Text Classification: The Role of Prompt Underspecification*
- `raw/s41598-025-29770-0.pdf` — *Large language models robustness against perturbation*

## Priority 2 - existing wiki route absorption
이 묶음은 새 top-level synthesis보다 기존 route에 흡수하는 편이 좋다.

### AI infrastructure / compute control / market rerating
- `raw/web-snapshots/AI는 지금 구글, 월가 자본 끌어다 'AI 영토' 넓힌다…빚 안 지고 AI거점 확충.md` -> [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- `raw/web-snapshots/오픈AI, 노르웨이 '스타게이트' 데이터센터도 포기…MS가 접수.md` -> [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- `raw/web-snapshots/단독 SK하이닉스, 美 ADR 6~7월 상장한다.md` -> [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]
- `raw/web-snapshots/대만증시 시총 4조달러 돌파, 영국 제치고 세계 7위…한국은.md` -> [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- `raw/web-snapshots/테슬라 주가 8% 깜짝 급등…차세대 AI 칩 진전.md` -> [[source--samsung-foundry-rebound-and-ai-nonmemory-demand-2026-04-13]]

### AI capability / execution / security follow-up
- `raw/web-snapshots/‘AI 논문·특허’ 중국이 미국 추월…2030년 세계 1위 가시권.md` -> [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]
- `raw/web-snapshots/자존심 꺾인 애플, AI 2년 지각에 '부트캠프' 초강수…시리 수장도 교체.md` -> AI execution / enterprise adoption seed
- `raw/web-snapshots/해킹 AI '판도라 상자' 되나…'미토스' 보고서 7월 예고에 각국 촉각.md` -> [[source--project-glasswing-defensive-ai-cybersecurity-2026-04-15]] 또는 [[source--anthropic-mythos-security-claims-critique-2026-04-12]]

### Middle East / Hormuz follow-up
- `raw/web-snapshots/트럼프 이스라엘·레바논에 '숨통'…휴전합의 추진 시사.md` -> [[synthesis--middle-east-war-macro-and-market-repricing-2026-04-13]]
- `raw/web-snapshots/헤즈볼라 “휴전환영” 전격 입장 선회… 美·이란 협상에 ‘청신호’.md` -> [[synthesis--middle-east-war-macro-and-market-repricing-2026-04-13]]
- `raw/web-snapshots/호르무즈 무사통과 좋아했는데…미군에 걸린 유조선의 최후.md` -> [[synthesis--middle-east-shipping-and-energy-risk-2026-04-12]]

## Priority 3 - single-source seeds
아래 네 건은 기존 synthesis에 억지로 끼우기보다 단일 source page로 시작하는 편이 낫다.

- `raw/web-snapshots/2차대전처럼 '병기창' 늘리는 트럼프…GM·포드도 무기 만들어라.md` — U.S. defense-industrial mobilization / arsenal expansion seed.
- `raw/web-snapshots/“건강 아무리 챙겨도 팔자 못 이기나요”...수명, 절반은 유전자가 결정.md` — longevity genetics seed.
- `raw/web-snapshots/소리·빛으로 알츠하이머 치료…기억력 향상 확인.md` — Alzheimer's / 40Hz stimulation digital therapeutics seed.
- `raw/web-snapshots/산업부 최고가격제로 판매량 증가 11.7% 줄어…시장 왜곡 주장 반박.md` — Korea oil-price intervention / price-cap policy seed.

## Implementation notes
- `raw/claude-prompting-best-practices.md`는 source URL을 확인할 수 없어 `source: "unknown"`으로 두었다. normalizer가 본문 중간의 `anthropic.com/glasswing` 링크를 source로 잡는 것은 false provenance risk로 판단했다.
- PDF raw는 title/first-page text만 읽고 수정하지 않았다.
- next ingest에서 prompt robustness cluster를 먼저 처리하면 남은 warning 18건을 한 번에 줄이면서 system prompt contract의 evidence base도 생긴다.
- wiki follow-up 11건은 기존 mature synthesis와 source page에 연결되므로, single-source seed보다 운영비 대비 효과가 크다.

## Validation
- `./.venv/bin/python -m ops.scripts.raw_markdown_normalize --vault . --path raw --write --report-out tmp/raw-markdown-normalization-write-2026-04-16.json`
- `./.venv/bin/python -m ops.scripts.raw_registry_preflight --vault .`

## Related pages
- [[system-index]]
- [[system-raw-registry]]
- [[system-raw-registry/wiki/ai-capability]]
- [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]
- [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]
- [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- [[synthesis--middle-east-shipping-and-energy-risk-2026-04-12]]
- [[synthesis--middle-east-war-macro-and-market-repricing-2026-04-13]]

## Source trace
- `raw/`
- `ops/scripts/raw_markdown_normalize.py`
- `ops/scripts/raw_markdown_runtime.py`
- `ops/scripts/raw_registry_preflight.py`
- `system/system-raw-registry.md`
