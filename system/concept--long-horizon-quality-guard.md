---
title: "Long Horizon Quality Guard"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--long-horizon-quality-guard"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--long-horizon-quality-guard

## Summary
long-horizon quality guard는 self-improving wiki와 maintainer runtime이 반복 개선될수록 생길 수 있는 architecture entropy, complexity drift, redundancy growth를 추적하고, 일정 임계치에서 periodic refactor loop를 요구하는 meta-research guard다.

## Why it matters here
LLM Wiki의 목표 구조는 단순히 `LLM -> research -> improvement`가 아니라, improvement의 결과를 telemetry / eval / lint / run history로 다시 읽어 meta-research가 research와 improvement 규칙을 조정하는 순환이다. SlopCodeBench는 장기 반복 coding trajectory에서 structural erosion이 80%의 trajectory에서, verbosity가 89.8%에서 증가한다고 보고한다. wiki에서도 단기 lint/eval은 통과하지만 page sprawl, 중복 synthesis, 약한 trace, 과도한 policy growth가 누적될 수 있으므로 별도 장기 guard가 필요하다.

## Main body
### Role in the architecture
```text
LLM -> research -> improvement
        ^           |
        |           v
meta-research <- telemetry / eval / lint / run history
```

이 guard의 위치는 `meta-research`다. 외부 연구 source가 말하는 failure mode와 내부 telemetry가 보여 주는 반복 패턴을 함께 읽고, improvement가 실제로 품질을 높였는지 아니면 구조 비용만 늘렸는지 판정한다.

### Metric families
- architecture entropy: route별 page count, broad synthesis watch candidate, shard line pressure, orphan/weak-link pressure, concept/synthesis/source 비율, router fan-out 증가를 본다.
- complexity drift: page line count, heading count, source_count, analysis subsection 수, policy branch count, mechanism assessment complexity score를 본다.
- redundancy growth: duplicate synthesis question, source-overlap 과다, 반복 query artifact, 같은 raw family의 단일 source seed 누적을 본다.
- refactor cadence: ingest batch 이후, 같은 review candidate가 반복될 때, mechanism run에서 line/branch growth가 test growth 없이 누적될 때 refactor budget을 예약한다.

### Existing partial implementation
- [[concept--anti-slop-wiki-governance]]는 duplicate synthesis, weak trace, orphan page 같은 문서형 slop taxonomy를 제공한다.
- [[concept--wiki-failure-mode-taxonomy]]는 lint/eval/stage2 symptom을 structural, routing/provenance, content quality, mechanism/process family로 라벨링해 repeated drift를 비교 가능하게 한다.
- [[concept--memory-management-strategies]]는 log, page, policy, raw registry, telemetry report가 각각 어떤 memory class인지 나눠, 성장 자체와 drift를 구분하게 한다.
- `ops/policies/wiki-maintainer-policy.yaml`의 `mechanism_review.families.self_mod_stability`는 verbosity growth, branch growth without test growth, high complexity low test pressure를 추적한다.
- `ops/scripts/mechanism_assess.py`와 `ops/scripts/mechanism_candidate_registry_runtime.py`는 mechanism/code surface의 structural metric과 trend candidate를 이미 일부 계산한다.
- `wiki_lint`의 broad synthesis, shard pressure, orphan/weak trace candidate는 corpus-level long-horizon guard의 raw signal로 재사용할 수 있다.

### Guard decision rule
개별 변경이 local score를 개선하더라도, architecture entropy / complexity drift / redundancy growth 중 하나를 크게 늘리면 그 변경은 refactor follow-up이나 explicit debt record와 함께만 유지한다. 반대로 단기 score delta가 작아도 반복 candidate를 줄이고 traceability를 높이는 정리는 장기 guard 관점에서 promotion 근거가 될 수 있다.

## Scope boundaries
- 이 개념은 domain claim의 진위 판정이 아니라 self-improving corpus와 runtime의 장기 구조 품질을 다룬다.
- anti-slop governance는 failure taxonomy이고, long-horizon quality guard는 그 failure가 시간에 따라 증가하는지 보는 trend/cadence layer다.
- 모든 성장을 막자는 원칙이 아니다. 새 source나 route가 들어와 page가 늘어나는 것은 정상이며, 문제는 route와 refactor 기준 없이 복잡도만 누적되는 상태다.
- fully autonomous rewrite 권한을 부여하지 않는다. guard는 refactor 필요성을 드러내고, 실제 mutation은 기존 loop와 signoff discipline을 따른다.

## Examples and non-examples
- example: broad synthesis watch candidate가 여러 작업 뒤에도 줄지 않고 같은 source overlap으로 반복되면 architecture entropy signal로 본다.
- example: policy나 script branch count는 늘었는데 test count와 eval score가 따라오지 않으면 complexity drift signal로 본다.
- example: 같은 raw family가 계속 단일 source page로만 쌓이고 concept/synthesis anchor가 생기지 않으면 redundancy growth 또는 routing debt로 본다.
- non-example: 명확한 boundary section과 source trace를 가진 큰 synthesis 하나는 단순 line count만으로 slop로 보지 않는다.
- non-example: append-only system log가 작업 이력을 남기며 늘어나는 것은 그 자체로 verbosity slop가 아니다.

## How to reuse this concept
- batch ingest 뒤에는 lint candidate 수뿐 아니라 같은 candidate family가 이전 작업에서 반복됐는지 확인한다.
- mechanism improvement를 promotion할 때는 score delta와 함께 complexity/test/branch/line trend를 본다.
- system research source를 읽을 때는 해당 source가 `research`, `improvement`, `meta-research guard` 중 어느 층을 강화하는지 먼저 라우팅한다.
- refactor 작업은 “무엇을 지웠는가”보다 “어떤 반복 drift signal을 줄였는가”로 설명한다.

## Related pages
- [[system-index]]
- [[source--slopcodebench]]
- [[concept--anti-slop-wiki-governance]]
- [[concept--wiki-failure-mode-taxonomy]]
- [[concept--memory-management-strategies]]
- [[concept--harness-optimization]]
- [[concept--self-improving-wiki-loop]]
- [[concept--binary-evals]]
- [[concept--trace-store-and-run-ledger]]
- [[synthesis--research-insights-to-practical-wiki-rules]]
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]

## Open questions
- corpus-level architecture entropy report를 `wiki_lint` 안에 둘지 별도 trend report로 둘지?
- broad synthesis watch, shard pressure, orphan pressure 중 어느 신호를 first-class long-horizon gate로 승격할지?
- periodic refactor cadence를 run count 기준으로 둘지, candidate persistence 기준으로 둘지?

## Source trace
- `raw/2603.24755v1.pdf`
- `raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md`
- `system/source--slopcodebench.md`
- `system/concept--anti-slop-wiki-governance.md`
- `system/concept--harness-optimization.md`
- `system/concept--self-improving-wiki-loop.md`
- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/scripts/mechanism_assess.py`
- `ops/scripts/mechanism_candidate_registry_runtime.py`
