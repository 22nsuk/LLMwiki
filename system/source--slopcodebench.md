---
title: "SlopCodeBench: Benchmarking How Coding Agents Degrade Over Long-Horizon Iterative Tasks"
page_type: "source"
corpus: "system"
registry_id: "W-006"
raw_path: "raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md"
source_type: "web-snapshot"
domain: "long-horizon-degradation"
created: "2026-04-12"
aliases:
  - "source--slopcodebench"
tags:
  - "corpus/system"
  - "type/source"
---

# source--slopcodebench

## Title
SlopCodeBench: Benchmarking How Coding Agents Degrade Over Long-Horizon Iterative Tasks

## Source
- `raw/2603.24755v1.pdf`
- `raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md`

## Type
research-paper

## Summary
이 논문은 agent가 자기 코드를 반복적으로 확장할 때 생기는 품질 저하를 측정하기 위해 SCBench를 제안한다. 핵심 메시지는 단순 pass rate만으로는 충분하지 않고, **verbosity**와 **structural erosion** 같은 trajectory-level 품질 지표가 필요하다는 점이다.

## Why it matters
LLM Wiki도 반복 편집 대상이다. 현재 초안처럼 규칙은 좋아도, 장기적으로는 source page 중복, synthesis 비대화, orphan link, weak trace 같은 **문서형 slop**이 누적될 수 있다. 이 논문은 prompt hygiene만으로는 저하 속도를 멈추지 못하고, 구조적 제약과 평가 기준이 필요함을 시사한다.

## Key points
- benchmark는 20개 문제와 93 checkpoints로 구성되며, agent는 이전에 자신이 쓴 코드를 계속 확장한다.
- 품질 지표는 redundant/duplicated code를 보는 verbosity와, 복잡도가 소수의 고복잡 함수에 몰리는지를 보는 structural erosion이다.
- 원문은 structural erosion이 trajectory의 80%에서, verbosity가 89.8%에서 증가한다고 보고해 장기 반복의 steady degradation을 강조한다.
- 논문은 agent code가 human repo보다 더 verbose하고 더 eroded하다고 보고한다.
- quality-aware prompt는 초기 품질을 조금 높일 수 있지만, degradation slope 자체는 멈추지 못했다고 주장한다.
- design philosophy는 no prescribed interfaces, hidden tests, black-box contracts를 강조한다.
- 즉, 구조 품질은 **입력 prompt**보다 **장기 확장에 견디는 artifact shape**에 달려 있다.

## Limitations / caveats
- benchmark는 coding agent 중심이고, wiki/document artifact에 직접 적용된 것은 아니다.
- erosion/verbosity 정의를 문서에 그대로 옮기기보다 wiki에 맞는 proxy metric으로 재설계해야 한다.
- prompt intervention 결과가 모든 문서형 작업에 동일하게 적용된다고 볼 수는 없다.

## Related pages
- [[concept--anti-slop-wiki-governance]]
- [[concept--long-horizon-quality-guard]]
- [[concept--planning-gates]]
- [[concept--cross-reference-maintenance]]
- [[synthesis--research-insights-to-practical-wiki-rules]]
- [[lint--initial-review-2026-04-12]]

## Open questions
- wiki에서 verbosity와 erosion에 해당하는 최소 지표 조합은 무엇인가?
- long page, duplicate synthesis, broken links, stale claims를 어떤 gate로 결합할 것인가?
- 어떤 proxy metric을 long-horizon quality guard의 첫 trend report로 승격할 것인가?
- prompt-only guidance와 template/schema enforcement의 기여를 어떻게 분리할 것인가?

## Source trace
- `raw/2603.24755v1.pdf`
- `raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md`
