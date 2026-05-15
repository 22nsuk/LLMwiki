---
title: "Official Prompt Guidance Across Claude, GPT-5.4, and Vertex AI"
page_type: "source"
corpus: "system"
registry_id: "R-028"
raw_path: "raw/claude-prompting-best-practices.md"
source_type: "web-snapshot"
domain: "prompt-contract-design-and-official-guidance"
created: "2026-04-16"
aliases:
  - "source--prompt-guidance-official-docs-2026-04-16"
tags:
  - "corpus/system"
  - "type/source"
---

# source--prompt-guidance-official-docs-2026-04-16

## Title
Official Prompt Guidance Across Claude, GPT-5.4, and Vertex AI

## Source
- `raw/claude-prompting-best-practices.md`
- `raw/web-snapshots/Prompt guidance for GPT-5.4.md`
- `raw/web-snapshots/프롬프트 작성 전략 개요    Generative AI on Vertex AI.md`

## Type
web-snapshot

## Summary
세 공식 guidance를 함께 읽으면 prompt는 더 이상 단순한 자연어 지시문이 아니라 `output contract`, `tool-use expectation`, `evaluation loop`, `context structure`, `ambiguity handling`을 담는 runtime interface에 가깝다. Claude guidance는 clarity, examples, XML-like structure, thinking, tool use, agentic system을 폭넓게 다루고, GPT-5.4 guidance는 completeness checks, verification loops, tool persistence, structured outputs 같은 production agent contract를 전면에 둔다. Vertex AI guidance는 prompt engineering을 목표 정의, 체계적 테스트, content와 structure 조정의 반복 workflow로 설명한다.

## Why it matters
이 repo의 system corpus는 eval, lint, registry, planning gate를 이미 runtime contract로 다루고 있다. 이 source cluster는 그 원칙을 prompt 설계에도 적용하게 만든다. 좋은 prompt는 친절한 문장이 아니라 `무엇을 완료로 볼지`, `어떤 형식으로 반환할지`, `도구 사용을 언제 지속할지`, `불확실성을 어떻게 드러낼지`를 명시하는 contract surface다.

## Key points
- Claude guidance는 최신 Claude model을 대상으로 clarity, examples, XML structure, thinking, tool use, agentic systems를 하나의 prompt engineering reference로 묶는다.
- GPT-5.4 guidance는 long-running assistant와 agent에서 output contract, tool-use expectation, completion criteria를 명시할 때 성능 이득이 커진다고 설명한다.
- GPT-5.4 guidance는 completeness check, verification loop, structured output, tool persistence를 prompt pattern의 핵심 축으로 둔다.
- Vertex AI guidance는 prompt engineering을 정답 문구 찾기가 아니라 목표와 예상 결과를 정의하고 테스트하며 반복 개선하는 workflow로 본다.
- 세 guidance 모두 prompt를 모델별 syntax trick보다 task scope, response format, evidence/check loop, ambiguity 처리의 조합으로 다룬다.

## Limitations / caveats
- `raw/claude-prompting-best-practices.md`의 원 source URL은 raw snapshot 안에서 확정되지 않아 frontmatter에는 `source: "unknown"`으로 보수적으로 남겼다.
- 세 문서는 모두 vendor guidance이므로 각 vendor의 model affordance와 product positioning이 섞여 있다.
- 이 source cluster는 prompt design 원칙을 제공하지만, 개별 task에서 어떤 phrasing이 더 나은지는 별도 eval이 필요하다.

## What this source adds to the corpus
이 source는 repo의 prompt 운영 원칙을 `clear instruction` 수준에서 `auditable prompt contract` 수준으로 끌어올린다. 특히 future maintainer prompt, subagent instruction, eval prompt를 작성할 때 `completion criteria`, `verification loop`, `tool-use persistence`, `structured output`, `ambiguity handling`을 별도 축으로 점검하게 만든다.

## How strong is the evidence
증거 강도는 practical guidance anchor로는 높지만 empirical proof로는 제한적이다. vendor docs는 최신 product-facing 권장사항을 잘 보여 주지만, 특정 prompt pattern의 일반 성능 개선을 독립 실험으로 입증하는 자료는 아니다.

## Related pages
- [[system-index]]
- [[concept--prompt-contract-robustness]]
- [[synthesis--prompt-robustness-and-contract-design-2026-04-16]]
- [[concept--planning-gates]]
- [[concept--binary-evals]]
- [[source--openai-evaluation-best-practices]]

## Open questions
- repo-shared maintainer prompt에서 completion criteria와 verification loop를 어느 정도까지 구조화할 것인가?
- model-specific prompt guidance와 model-agnostic runtime contract를 어디에서 분리해야 하는가?
- prompt contract의 최소 lintable fields는 output schema, tool policy, evidence policy, stop condition 중 무엇인가?

## Source trace
- `raw/claude-prompting-best-practices.md`
- `raw/web-snapshots/Prompt guidance for GPT-5.4.md`
- `raw/web-snapshots/프롬프트 작성 전략 개요    Generative AI on Vertex AI.md`
- `system/system-raw-registry.md`
- `system/system-raw-registry/system.md`
