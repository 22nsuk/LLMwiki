---
title: "Bilevel Autoresearch: Meta-Autoresearching Itself"
page_type: "source"
corpus: "system"
registry_id: "R-001"
raw_path: "raw/2603.23420v1.pdf"
source_type: "research-paper"
domain: "bilevel-mechanism-search"
created: "2026-04-12"
aliases:
  - "source--bilevel-autoresearch"
tags:
  - "corpus/system"
  - "type/source"
---

# source--bilevel-autoresearch

## Title
Bilevel Autoresearch: Meta-Autoresearching Itself

## Source
- `raw/2603.23420v1.pdf`

## Type
research-paper

## Summary
이 논문은 inner autoresearch loop가 task output을 개선하는 동안, outer loop가 **search mechanism 자체를 코드 생성으로 바꾸는** bilevel 구조를 제안한다. 핵심 주장은 ‘autoresearch가 연구를 할 수 있다면, autoresearch 자신도 연구할 수 있다’는 것이다.

## Why it matters
현재 LLM Wiki 초안은 source ingest와 page maintenance 규칙은 있지만, **maintainer mechanism을 평가하고 교체하는 상위 루프**는 없다. 이 논문은 wiki에도 content-level 개선과 mechanism-level 개선을 분리해야 함을 보여준다.

## Key points
- inner loop는 proposal -> train -> evaluate -> keep/discard 구조로 task를 최적화한다.
- outer loop는 trace와 runner code를 읽고, 새 search mechanism을 Python code로 생성해 런타임에 주입한다.
- 같은 모델을 inner/outer loop에 모두 사용해도 의미 있는 개선이 가능하다는 점을 강조한다.
- Karpathy benchmark에서 Level 2 mechanism research가 inner loop 단독 대비 더 큰 개선을 냈다고 보고한다.
- 저자들은 성공 원인을 **LLM 기본 탐색 경로가 피하는 방향을 강제로 탐색하게 만든 점**으로 해석한다.
- mechanism inventory 예시는 tabu search, bandit proposer, orthogonal exploration처럼 서로 다른 외부 도메인에서 온 전략이다.

## Limitations / caveats
- 실험 반복 수가 작고 단일 benchmark에 집중되어 있어 일반화는 아직 약하다.
- 동적 코드 주입과 외부 dependency는 실패 가능성이 높고, validate-and-revert 없이는 위험하다.
- mechanism prompt가 후보 도메인을 암시하므로 발견 공간이 완전히 열린 것은 아니다.

## Related pages
- [[source--karpathy-autoresearch-repo]]
- [[source--meta-harness]]
- [[concept--harness-optimization]]
- [[concept--trace-store-and-run-ledger]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- wiki maintainer runtime에서 ‘mechanism injection’의 최소 단위는 prompt, template, policy, script 중 무엇인가?
- outer loop가 page content 대신 `ops/` policy와 script를 바꾸도록 제한하면 안정성이 충분한가?
- runtime code patch와 document policy patch를 같은 평가식으로 다룰 수 있는가?

## Source trace
- `raw/2603.23420v1.pdf`
