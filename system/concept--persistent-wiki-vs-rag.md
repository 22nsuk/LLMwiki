---
title: "Persistent Wiki vs RAG"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-14"
aliases:
  - "concept--persistent-wiki-vs-rag"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--persistent-wiki-vs-rag

## Summary
persistent wiki는 retrieval-only memory와 달리 **사람과 agent가 함께 유지하는 canonical document layer**를 갖는다. RAG가 “찾아오기”에 강하다면, wiki는 “정리하고 연결하고 정정하기”에 강하다.

## Why it matters here
사용자가 원하는 것은 단순 검색이 아니라, 첨부 논문과 GitHub 방향을 장기적으로 축적하며 다음 단계 설계에 재사용하는 것이다. 이 요구는 pure RAG보다 persistent wiki가 더 잘 맞는다.

## Main body
### RAG가 잘하는 것
- 많은 raw source를 빠르게 검색한다.
- 질의 시점에만 필요한 근거를 당겨온다.
- 새로운 source가 들어와도 인덱싱만 되면 바로 쓸 수 있다.

### Persistent wiki가 잘하는 것
- 반복적으로 등장하는 개념을 canonical page로 정착시킨다.
- source 간 tension, caveat, decision을 사람이 읽을 수 있는 형태로 유지한다.
- 다음 세션의 maintainer가 “이미 정리된 판단”을 재사용하게 한다.
- query artifact와 lint artifact를 남겨 knowledge quality를 계속 다듬을 수 있다.

### 결론
실무적으로는 둘 중 하나가 아니라:
- raw / search는 RAG적,
- canonical page / synthesis / policy는 wiki적
이어야 한다.

## Scope boundaries
- 이 개념은 memory architecture 선택과 역할 분담을 비교한다.
- persistent wiki를 위해 RAG를 완전히 버리자는 주장도 아니고, 반대로 wiki를 검색 index로 환원하자는 주장도 아니다.
- 특정 vendor/product 비교보다는 `retrieval` 대 `maintained knowledge`의 구조 차이를 다룬다.

## Examples and non-examples
- example: raw 재조회는 RAG적 surface로, recurring interpretation은 concept/synthesis page로 남기는 hybrid flow가 이 개념의 대표 사례다.
- example: query 전에 canonical page를 먼저 읽고 부족할 때만 raw로 내려가는 운영은 persistent wiki 쪽에 가깝다.
- non-example: 모든 raw source를 manual page로 강제로 옮기는 것은 hybrid balance를 잃은 운영이다.
- non-example: vector search 결과를 그대로 summary로 내보내는 것만으로는 persistent wiki layer가 생기지 않는다.

## How to reuse this concept
- 새 source를 다룰 때 “즉시 retrieval로 충분한가, 반복 재사용 가치가 있어 canonical page가 필요한가”를 판단할 때 쓴다.
- query 설계에서 router -> page -> raw 순서를 유지해야 하는 이유를 설명할 때 재사용한다.
- future export나 agent memory design 논의에서도 search surface와 maintained corpus를 분리하는 기준점으로 삼는다.

## Related pages
- [[concept--llm-wiki]]
- [[concept--trace-store-and-run-ledger]]
- [[source--meta-harness]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Open questions
- 언제 raw 재조회가 필요한지에 대한 규칙을 더 엄격히 둘 필요가 있는가?
- wiki page를 생성하기 전의 retrieval trace도 저장해야 하는가?

## Source trace
- `AGENTS.md`
- `system/system-index.md`
- `raw/2603.28052v1.pdf`
