---
title: "LLM Wiki 초안 검토 및 자기개선 통합 설계 보고서"
page_type: "source"
corpus: "system"
registry_id: "R-000"
raw_path: "raw/llm_wiki_review_report.pdf"
source_type: "review-report"
domain: "wiki-runtime-review"
created: "2026-04-12"
aliases:
  - "source--llm-wiki-review-report"
tags:
  - "corpus/system"
  - "type/source"
---

# source--llm-wiki-review-report

## Title
LLM Wiki 초안 검토 및 자기개선 통합 설계 보고서

## Source
- `raw/llm_wiki_review_report.pdf`

## Type
review-report

## Summary
이 보고서는 LLM Wiki 초안을 검토한 뒤, 업로드된 논문 3편과 GitHub 저장소 4개, Stage 1 planning harness 명세를 함께 대조해 **실행 가능한 self-improving wiki runtime**으로 재구성하는 방향을 제안한다. 핵심 주장은 위키를 버리거나 대체하는 것이 아니라, 기존 raw/wiki 뼈대를 유지한 채 `ops/` control layer와 planning/meta loops를 덧붙여야 한다는 것이다.

## Why it matters
이 문서는 현재 저장소 패키지 자체를 설명하는 가장 직접적인 통합 소스다. 개별 논문과 저장소가 왜 이 구조에 반영됐는지, bootstrap 결함을 어떤 우선순위로 보완해야 하는지, 그리고 package baseline을 어떤 순서로 운영에 올릴지 한 문서에서 묶어 준다.

## Key points
- 초안의 강점은 raw/wiki 분리, flat wiki, append-only log, source fidelity라는 네 가지 bootstrap 결정에 있으며, 이것들은 유지 대상으로 분류된다.
- 가장 큰 결핍은 canonical page의 실제 부재, deterministic lint/eval 부재, mechanism-level self-improvement 정의 부재였다고 진단한다.
- 권장 목표 구조는 **4계층 저장소(raw/wiki/ops/rules)** 와 **3중 루프(content maintenance / planning gate / mechanism improvement)** 의 결합이다.
- 외부 소스별 교훈을 policy/template/script 수준의 runtime rule로 번역해야 한다고 정리한다. 예를 들어 Bilevel은 mechanism mutation, SlopCodeBench는 anti-slop governance, Meta-Harness는 trace-first diagnosis로 연결된다.
- 실행 로드맵은 baseline 정리 -> 실제 ingest 루프 검증 -> planning gate 파일럿 -> meta-loop 시작 -> trace-first outer loop 확장의 순서를 권장한다.
- 패키지 결과물로 source/concept/synthesis/query/lint 페이지, raw snapshot, ops script/schema/policy를 묶어 baseline runtime으로 제시한다.

## Limitations / caveats
- 이 문서는 package 통합 보고서라서, 세부 주장 중 일부는 개별 raw 논문과 snapshot을 다시 내려가며 검증해야 한다.
- 2026-04-12 시점의 저장소 상태를 기준으로 작성된 진단이라, 이후 구조가 바뀌면 일부 평가와 우선순위는 stale해질 수 있다.
- 보고서 자체는 synthesis 성격이 강하므로, 메커니즘 수정이나 policy promotion의 최종 근거로 쓸 때는 원천 source trace를 함께 확인하는 편이 안전하다.

## Related pages
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[synthesis--research-insights-to-practical-wiki-rules]]
- [[query--runtime-quickstart-2026-04-15]]
- [Historical bootstrap note: Recommended Next Actions 2026-04-12](../external-reports/query--recommended-next-actions-2026-04-12.md)
- [[source--stage1-planning-harness-mvp]]
- [[source--bilevel-autoresearch]]
- [[source--meta-harness]]

## Open questions
- 이 보고서를 historical snapshot source로 둘지, 후속 검토가 나올 때 같은 canonical page를 계속 갱신할지?
- package-level review report와 individual synthesis page 사이의 책임 경계를 어디까지 분리할지?
- 다음 메타 리뷰 때는 어떤 baseline artifact를 추가로 남겨야 비교가 더 쉬워질지?

## Source trace
- `raw/llm_wiki_review_report.pdf`
