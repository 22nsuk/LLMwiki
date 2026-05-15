---
title: "Prompt Robustness, Perturbation, Format, Persona, and Tone Sensitivity Papers"
page_type: "source"
corpus: "system"
registry_id: "R-031"
raw_path: "raw/2024.findings-eacl.91.pdf"
source_type: "research-paper"
domain: "prompt-robustness-and-sensitivity-evidence"
created: "2026-04-16"
aliases:
  - "source--prompt-robustness-perturbation-and-format-papers-2026-04-16"
tags:
  - "corpus/system"
  - "type/source"
---

# source--prompt-robustness-perturbation-and-format-papers-2026-04-16

## Title
Prompt Robustness, Perturbation, Format, Persona, and Tone Sensitivity Papers

## Source
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

## Type
research-paper

## Summary
이 research cluster는 LLM prompt가 작은 wording, typo, format, persona, tone, language variation, underspecification에 민감하다는 공통 신호를 제공한다. PromptRobust, EACL prompt perturbation, multilingual typo robustness, enterprise perturbation benchmark, Scientific Reports perturbation 논문은 typos, substitutions, formatting, language variation이 output quality를 흔들 수 있음을 보인다. Mind Your Format, underspecification 논문은 평가 결과가 prompt template와 task specification에 크게 의존한다고 경고한다. Politeness, tone, persona, targeted-underperformance 논문들은 사용자 정체성, writing style, politeness, non-native English variation이 fairness와 robustness 문제로 이어질 수 있음을 보여 준다.

## Why it matters
maintainer/runtime prompt는 한 번 잘 써 놓으면 고정되는 문서가 아니다. 이 cluster는 prompt가 `semantic instruction`인 동시에 `fragile interface`라는 사실을 보여 준다. 따라서 repo prompt, subagent profile, eval prompt, lint prompt는 wording만으로 통제하지 말고, explicit contract, format constraints, perturbation-aware tests, fairness-aware route를 함께 가져야 한다.

## Key points
- Prompt Perturbation Consistency Learning은 intent classification과 slot filling에서 oronym, synonym, paraphrase perturbation이 성능을 떨어뜨리고 consistency regularization이 일부 회복할 수 있음을 보인다.
- Perfect English for MT prompts는 자연스러운 spelling error가 LLM translation quality를 흔들 수 있지만, initial prompt choice variance도 크다고 정리한다.
- PromptRobust는 character, word, sentence, semantic level adversarial prompt benchmark를 제시하며 LLM이 adversarial prompt에 robust하지 않다고 보고한다.
- Mind Your Format은 in-context learning 평가에서 template format 선택이 모델과 setup별로 크게 달라져, template를 무시한 성능 비교가 misleading할 수 있다고 경고한다.
- Politeness/tone papers는 polite, neutral, rude prompt가 model, language, domain에 따라 다른 영향을 줄 수 있고, 그 효과가 항상 단순하지 않음을 보여 준다.
- Persona and targeted-underperformance papers는 user persona, dialect, education, disability, race 같은 user-trait framing이 response quality와 refusal behavior에 영향을 줄 수 있음을 다룬다.
- Underspecification papers는 prompt sensitivity의 상당 부분이 task constraints와 output label space를 충분히 명시하지 않은 데서 생길 수 있다고 본다.
- Enterprise robustness paper는 punctuation, whitespace, JSON/YAML formatting, multilingual/cross-lingual inputs, instruction position 같은 현실적 perturbation을 enterprise task quality 관점에서 본다.

## Limitations / caveats
- 논문별 task, model, benchmark, perturbation type이 달라서 단일 effect size로 합치기 어렵다.
- 일부 tone/politeness 결과는 dataset scale과 domain coverage에 따라 통계적 유의성이 약해질 수 있다.
- 이 cluster는 prompt fragility를 입증하는 데 강하지만, 이 repo의 특정 maintainer prompt가 얼마나 취약한지는 별도 eval로 확인해야 한다.

## What this source adds to the corpus
이 source는 prompt contract를 `clarity best practice`에서 `robustness engineering`으로 확장한다. 특히 system prompt나 eval prompt를 고칠 때, 좋은 문장인지보다 `format perturbation에 견디는가`, `underspecified output space가 없는가`, `persona/tone/language variation에 과민하지 않은가`, `template 선택이 평가 결론을 바꾸지 않는가`를 물어야 한다는 근거가 된다.

## How strong is the evidence
증거 강도는 cluster-level로 강하다. 개별 논문마다 task 범위는 제한적이지만, 서로 다른 perturbation, format, persona, tone, language 축에서 같은 방향의 경고가 반복된다. 다만 operational rule로 옮길 때는 repo-local eval로 재검증해야 한다.

## Related pages
- [[system-index]]
- [[concept--prompt-contract-robustness]]
- [[synthesis--prompt-robustness-and-contract-design-2026-04-16]]
- [[concept--binary-evals]]
- [[concept--anti-slop-wiki-governance]]
- [[source--prompt-guidance-official-docs-2026-04-16]]

## Open questions
- maintainer prompt eval에 typo/format/persona perturbation subset을 넣을 가치가 있는가?
- prompt template variance를 줄이기 위해 canonical prompt shape와 output schema를 어디까지 고정할 것인가?
- fairness-sensitive persona variation은 system corpus의 prompt lint에서 어떤 수준으로 다룰 수 있는가?

## Source trace
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

