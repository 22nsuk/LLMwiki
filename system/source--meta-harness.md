---
title: "Meta-Harness: End-to-End Optimization of Model Harnesses"
page_type: "source"
corpus: "system"
registry_id: "W-005"
raw_path: "raw/web-snapshots/meta-harness-project-page-2026-04-12.md"
source_type: "web-snapshot"
domain: "harness-optimization"
created: "2026-04-12"
aliases:
  - "source--meta-harness"
tags:
  - "corpus/system"
  - "type/source"
---

# source--meta-harness

## Title
Meta-Harness: End-to-End Optimization of Model Harnesses

## Source
- `raw/2603.28052v1.pdf`
- `raw/web-snapshots/meta-harness-project-page-2026-04-12.md`

## Type
research-paper

## Summary
Meta-Harness는 LLM application의 harness code를 outer loop가 탐색하는 방식이다. proposer는 이전 후보들의 **source code, score, execution trace 전체를 filesystem으로 읽고**, 그 경험을 바탕으로 새 harness를 작성한다.

## Why it matters
현재 LLM Wiki 초안은 좋은 knowledge substrate이지만, meta-maintainer가 이전 세션의 failure trace를 선택적으로 읽고 mechanism을 개선하는 구조는 없다. Meta-Harness는 wiki 개선 루프에서 **summary보다 raw trace 접근이 더 중요할 수 있다**는 강한 근거를 제공한다.

## Key points
- target은 model weights가 아니라 prompt construction, retrieval, memory, orchestration을 포함한 harness code다.
- proposer는 raw logs를 monolithic prompt로 넣는 대신 filesystem에서 `grep`, `cat` 같은 방식으로 선택적으로 탐색한다.
- 논문은 prior methods가 summary, score, windowed history에 많이 의존한다고 비판한다.
- text classification, math retrieval, TerminalBench-2에서 hand-designed harness와 기존 optimizer를 넘는 결과를 보고한다.
- Appendix에서는 proposer가 prior failure의 confound를 추론하고 safer additive modification으로 pivot하는 질적 사례를 보여준다.
- project page는 trace-first 접근이 up to 10M tokens 규모의 diagnostic context를 다룬다고 설명한다.

## Limitations / caveats
- 강한 coding-agent proposer에 의존한다.
- full-history filesystem access는 유용하지만, history가 커질수록 navigation cost와 selection bias가 새 병목이 될 수 있다.
- harness optimization이 benchmark-specific overfitting을 유발할 위험이 있어 holdout discipline이 중요하다.

## Related pages
- [[source--bilevel-autoresearch]]
- [[concept--harness-optimization]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--self-improving-wiki-loop]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- LLM Wiki에서 full-history access를 어떤 artifact 단위로 제공할 것인가: page diff, lint report, query log, signoff log?
- wiki meta-loop는 scalar score 외에 어떤 trace를 저장해야 useful diagnosis가 가능한가?
- long-history navigation cost를 줄이기 위한 manifest / index / summary layer의 최소 형태는 무엇인가?

## Source trace
- `raw/2603.28052v1.pdf`
- `raw/web-snapshots/meta-harness-project-page-2026-04-12.md`
