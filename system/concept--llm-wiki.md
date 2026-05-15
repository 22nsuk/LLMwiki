---
title: "LLM Wiki"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-14"
aliases:
  - "concept--llm-wiki"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--llm-wiki

## Summary
LLM Wiki는 raw source snapshot layer를 보존하면서, agent가 유지하는 canonical page를 누적해 다음 세션이 이어받을 수 있게 만드는 **persistent knowledge layer**다.

## Why it matters here
현재 초안의 핵심 가치는 “대화가 사라지지 않고, source 근거가 남는 것”이다. 앞으로 planning harness나 self-improving runtime을 붙이더라도, 이 persistent layer를 유지하지 않으면 모든 개선 루프가 매 세션 다시 시작된다.

## Main body
### 역할
- raw source를 바로 답변에 재사용하기 어렵게 만드는 마찰을 줄인다.
- source / concept / synthesis / query / lint를 분리해 장기 유지에 필요한 memory shape를 제공한다.
- future agent가 “무엇을 안다 / 무엇이 아직 불확실한가 / 어디서 근거가 나왔는가”를 빠르게 파악하게 한다.

### 무엇이 아닌가
- 단순 vector store가 아니다.
- 일회성 chat transcript dump도 아니다.
- raw source를 압축해 근거를 지워 버리는 summary cache도 아니다.

### 운영상 핵심
- binary raw는 immutable이고, markdown raw는 source fidelity를 해치지 않는 minimal normalization만 허용된다. wiki는 mutable이다.
- canonical page를 우선 업데이트하고 page sprawl을 억제한다.
- index와 log가 navigation + chronology를 담당한다.
- 링크 밀도와 source trace 품질이 wiki usefulness를 좌우한다.

## Scope boundaries
- LLM Wiki는 persistent canonical knowledge layer를 뜻한다.
- vector index, transcript archive, planning bundle, execution harness 전체를 한 단어로 뭉개지 않기 위해 이 경계를 유지한다.
- 모든 질문에 대해 곧바로 새 page를 만드는 것을 정당화하는 개념도 아니다.

## Examples and non-examples
- example: `source--`, `concept--`, `synthesis--`, `query--` page를 누적해 future session이 이어받게 만드는 구조는 LLM Wiki다.
- example: `system-log`와 router page를 통해 chronology와 navigation을 남기는 것도 이 구조의 일부다.
- non-example: raw chunk를 임베딩해 질의 시점에만 꺼내 쓰는 retrieval cache는 그 자체로 wiki가 아니다.
- non-example: 세션 transcript를 폴더에 쌓아 두는 것만으로는 canonical knowledge layer가 되지 않는다.

## How to reuse this concept
- 새 artifact를 만들 때 “이것이 future session이 재사용할 canonical memory인가, 아니면 일회성 run artifact인가”를 구분하는 기준으로 쓴다.
- query에 답할 때는 raw를 바로 읽기 전에 관련 concept/synthesis page를 먼저 보는 흐름을 정당화한다.
- self-improvement를 설계할 때도 content corpus와 ops/runtime corpus를 분리해야 하는 이유를 설명하는 anchor 개념으로 재사용한다.

## Related pages
- [[concept--persistent-wiki-vs-rag]]
- [[concept--cross-reference-maintenance]]
- [[source--stage1-planning-harness-mvp]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- wiki canonical page에 frontmatter나 structured metadata를 도입할 시점은 언제인가?
- source / concept / synthesis 사이의 경계를 언제 더 엄격하게 schema화할 것인가?

## Source trace
- `AGENTS.md`
- `system/system-index.md`
- `raw/V2 stage1_mvp_specification.pdf`
