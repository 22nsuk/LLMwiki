---
title: "Harness Optimization"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--harness-optimization"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--harness-optimization

## Summary
harness optimization은 모델 weights가 아니라 **모델을 둘러싼 code, prompt, retrieval, memory, orchestration, gate**를 개선하는 일이다.

## Why it matters here
LLM Wiki는 본질적으로 하나의 harness다. 어떤 source를 먼저 읽는지, 어떤 page shape를 강제하는지, 언제 raw로 내려가는지, 어떤 lint/eval을 통과해야 promotion되는지 모두 harness design의 일부다.

## Main body
### 포함되는 것
- prompt template
- page template
- retrieval order
- link policy
- lint / eval rule
- signoff / freeze gate
- run ledger와 trace storage

### 포함되지 않는 것
- foundation model training 자체
- raw source 내용의 변조
- benchmark leakage를 위한 test-tuning

### 왜 중요한가
- 동일한 모델이라도 harness가 다르면 성능과 안정성이 크게 달라진다.
- wiki에서는 page 내용뿐 아니라 운영 방법 자체가 장기 품질을 좌우한다.
- mechanism-level 개선은 source fidelity와 maintainability를 동시에 건드릴 수 있다.

### 최근 system source가 더해 주는 관점
Voyager는 reusable skill library와 automatic curriculum 관점에서 harness를 보게 만들고, DSPy는 prompt string보다 signature와 module, optimizer 구조로 harness를 설계하게 만든다. 여기에 multi-agent autoresearch topology 연구는 **broad parallel search와 deep expert handoff를 같은 harness 안에서 어떻게 route할지**라는 새 질문을 더한다. 셋 다 이 repo에 그대로 이식할 대상은 아니지만, `행동 단위 재사용`, `programming not prompting`, `task-complexity-aware collaboration routing`이라는 세 방향의 reference surface로는 유용하다. [[concept--multi-agent-routing]]은 이 routing 질문을 별도 decision vocabulary로 분리한다.

### meta-research feedback
harness optimization은 새 논문에서 아이디어를 가져오는 일만이 아니다. telemetry / eval / lint / run history를 다시 읽어, 어떤 harness change가 장기적으로 architecture entropy나 complexity drift를 키웠는지도 봐야 한다. [[concept--memory-management-strategies]]는 어떤 artifact가 working, episodic, semantic, procedural memory인지 나누고, [[concept--wiki-failure-mode-taxonomy]]는 반복 증상을 cause family로 묶는다. [[concept--long-horizon-quality-guard]]는 harness가 좋아지는 중인지, 아니면 점수는 유지하지만 운영 표면만 무거워지는 중인지 판정하는 feedback lens다.

## Scope boundaries
- harness optimization은 모델 바깥의 editable runtime surface를 다룬다.
- foundation model training, raw source 수정, benchmark leakage를 위한 test tuning은 범위 밖이다.
- 모든 개선을 한 번에 묶는 대형 refactor보다, 평가 가능한 mechanism unit으로 자르는 것이 전제다.

## Examples and non-examples
- example: retrieval order, page template, policy rule, eval script를 조정하는 것은 harness optimization이다.
- example: single-agent와 subagent routing 조건을 바꾸는 것도 harness design 변경이다.
- non-example: raw PDF를 손봐서 eval을 높이는 것은 harness optimization이 아니라 금지된 source mutation이다.
- non-example: 모델 자체의 weights나 serving stack을 바꾸는 일은 현재 repo 스코프 밖이다.

## How to reuse this concept
- 개선 아이디어가 나오면 먼저 그것이 prompt tweak인지, policy/template/script 같은 harness surface인지 분류한다.
- mechanism experiment를 설계할 때는 editable boundary를 한 군데로 좁혀 complexity와 revert cost를 낮춘다.
- 새 research source를 읽을 때도 곧바로 채택 여부를 정하기보다, 어떤 harness layer에 시사점을 주는지부터 매핑한다.

## Related pages
- [[source--meta-harness]]
- [[source--bilevel-autoresearch]]
- [[source--karpathy-autoresearch-repo]]
- [[source--kevinrgu-autoagent-repo]]
- [[source--multi-agent-collaboration-for-automated-research]]
- [[source--voyager-open-ended-embodied-agent]]
- [[source--dspy-framework]]
- [[concept--multi-agent-routing]]
- [[concept--memory-management-strategies]]
- [[concept--wiki-failure-mode-taxonomy]]
- [[concept--long-horizon-quality-guard]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- wiki harness의 optimization unit을 policy / script / page template / command 중 어디서 자를 것인가?
- harness-level score와 page-level score를 어떻게 결합할 것인가?
- task complexity와 time budget에 따라 single-agent / subagent / expert-team 협업을 어떻게 route할 것인가?

## Source trace
- `raw/2603.28052v1.pdf`
- `raw/2603.23420v1.pdf`
- `raw/2603.24755v1.pdf`
- `raw/2603.29632v1.pdf`
- `raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md`
- `raw/web-snapshots/An Open-Ended Embodied Agent with Large Language Models.md`
- `raw/web-snapshots/DSPy.md`
