---
title: "Prompt Robustness and Contract Design 2026-04-16"
page_type: "synthesis"
corpus: "system"
source_count: 2
created: "2026-04-16"
aliases:
  - "synthesis--prompt-robustness-and-contract-design-2026-04-16"
tags:
  - "corpus/system"
  - "type/synthesis"
---

# synthesis--prompt-robustness-and-contract-design-2026-04-16

## Question
Claude, GPT-5.4, Vertex AI의 official prompt guidance와 prompt perturbation, format sensitivity, persona/tone/underspecification 연구들을 함께 읽으면 maintainer/runtime prompt는 어떻게 설계해야 하는가?

## Short answer
두 source page, 총 18개 raw source를 함께 읽으면 prompt는 `잘 쓴 자연어`가 아니라 `취약한 runtime interface`다. Vendor guidance는 task scope, output contract, tool persistence, structured output, verification loop를 명시하라고 말하고, research papers는 typo, spelling, format, template, persona, tone, language variation, underspecification이 model behavior와 평가 결론을 흔들 수 있음을 반복해서 보여 준다. 따라서 이 repo의 maintainer prompt는 친절함보다 `명시적 완료 기준`, `schema 또는 required section`, `source-fidelity rule`, `tool/eval loop`, `불확실성 보고`, `format variance에 덜 흔들리는 contract`를 우선해야 한다.

## Evidence considered
- [[source--prompt-guidance-official-docs-2026-04-16]]
- [[source--prompt-robustness-perturbation-and-format-papers-2026-04-16]]

## Analysis
### 1. official guidance의 공통점은 prompt를 completion contract로 본다는 것이다
Claude, GPT-5.4, Vertex AI guidance는 서로 다른 product surface를 갖지만, 공통적으로 prompt가 목표와 예상 결과, structure, tool use, validation loop를 포함해야 한다고 본다. 특히 long-running assistant나 agent에서는 "무엇을 답할지"보다 "언제 완료됐다고 볼지"와 "어떤 형식으로 검증 가능한 출력을 낼지"가 더 중요해진다.

### 2. research cluster는 prompt가 작은 변형에 흔들리는 interface임을 보여 준다
PromptRobust, EACL perturbation, multilingual typo, enterprise robustness, Scientific Reports perturbation 논문은 character/word/format/language 변화가 성능을 흔들 수 있음을 보인다. Mind Your Format과 underspecification 논문은 prompt template와 output label space를 제대로 고정하지 않으면 평가 결론 자체가 달라질 수 있다고 경고한다.

### 3. persona와 tone은 UX 문제가 아니라 robustness/fairness 문제다
Politeness, tone, persona, targeted-underperformance 연구들은 사용자 writing style과 persona framing이 품질, refusal, accuracy에 영향을 줄 수 있음을 보여 준다. maintainer runtime에서는 이것을 "말투를 예쁘게 하자"가 아니라 `prompt가 user style에 과민하게 반응하지 않도록 contract를 분리하자`는 rule로 번역해야 한다.

### 4. 이 repo에서의 실용적 번역은 prompt보다 policyable contract다
운영 규칙은 prompt에 길게 설명하기보다 frontmatter, lint required sections, raw registry contract, eval fixture, output schema로 일부 내려보내야 한다. prompt는 그 contract를 invoke하고 예외를 보고하는 얇은 layer가 되는 편이 robust하다.

## What this synthesis excludes
이 문서는 개별 모델별 최적 prompt wording catalog를 만들지 않는다. 또한 polite prompt가 항상 좋다거나, 특정 XML 구조가 모든 모델에서 최선이라는 결론도 내리지 않는다.

이 문서는 prompt robustness를 deterministic test의 대체물로 보지 않는다. 반대로 prompt contract가 튼튼해질수록 lint/eval이 검사할 수 있는 surface가 늘어난다는 관점이다.

## Tensions / contradictions
가장 큰 tension은 `model-specific guidance`와 `repo-stable contract` 사이에 있다. vendor docs는 최신 모델 affordance에 맞춰 바뀌지만, maintainer runtime은 장기적으로 재현 가능한 contract가 필요하다.

또 다른 tension은 `prompt flexibility`와 `evaluation stability` 사이에 있다. 유연한 자연어 prompt는 다양한 상황에 맞추기 쉽지만, template variance와 underspecification이 커지면 eval 결과가 흔들린다.

## Implications for future ingest
후속 prompt 관련 source는 `official guidance`, `perturbation robustness`, `format/template sensitivity`, `persona/fairness`, `underspecification`, `enterprise prompt reliability` 중 어느 축을 보강하는지 먼저 태깅하는 편이 좋다.

mechanism 개선으로 옮길 때는 prompt text를 바로 늘리기보다 `required output shape`, `source trace rule`, `failure reporting`, `tool persistence`, `eval perturbation fixture` 중 하나만 선택해 실험하는 편이 안전하다.

## Decision / takeaway
maintainer/runtime prompt의 기본 원칙은 `natural-language instruction + machine-readable contract + validation loop`다. prompt 변경은 wording polish가 아니라 contract strengthening이어야 하며, contract가 강해졌는지는 lint/eval, source trace, broken-link checks, registry preflight 같은 외부 surface로 확인해야 한다.

## Follow-up questions
- 현재 `.codex/agents/` profile 중 output contract가 가장 약한 role은 무엇인가?
- wiki_lint나 wiki_eval에 prompt perturbation fixture를 넣으면 실제 mechanism score가 개선되는가?
- model-specific prompt guidance가 바뀌었을 때 repo-stable contract와 충돌하지 않게 versioning할 방법은 무엇인가?

## Related pages
- [[system-index]]
- [[concept--prompt-contract-robustness]]
- [[source--prompt-guidance-official-docs-2026-04-16]]
- [[source--prompt-robustness-perturbation-and-format-papers-2026-04-16]]
- [[concept--planning-gates]]
- [[concept--binary-evals]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Source trace
- `raw/claude-prompting-best-practices.md`
- `raw/web-snapshots/Prompt guidance for GPT-5.4.md`
- `raw/web-snapshots/프롬프트 작성 전략 개요    Generative AI on Vertex AI.md`
- `raw/2024.findings-eacl.91.pdf`
- `raw/2026.findings-eacl.38.pdf`
- `raw/2306.04528v5.pdf`
- `raw/2401.06766v3.pdf`
- `raw/2402.14531v2.pdf`
- `raw/2406.12094v2.pdf`
- `raw/2406.17737v2.pdf`
- `raw/2505.13360v2.pdf`
- `raw/2507.22168v2.pdf`
- `raw/2510.04950v1.pdf`
- `raw/2510.09536v2.pdf`
- `raw/2512.12812v2.pdf`
- `raw/2601.06341v1.pdf`
- `raw/2602.04297v1.pdf`
- `raw/s41598-025-29770-0.pdf`
- `system/system-raw-registry.md`
- `system/system-raw-registry/system.md`
