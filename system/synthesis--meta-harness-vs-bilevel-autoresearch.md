---
title: "Meta Harness vs Bilevel Autoresearch"
page_type: "synthesis"
corpus: "system"
source_count: 4
created: "2026-04-12"
aliases:
  - "synthesis--meta-harness-vs-bilevel-autoresearch"
tags:
  - "corpus/system"
  - "type/synthesis"
---

# synthesis--meta-harness-vs-bilevel-autoresearch

## Question
Bilevel Autoresearch와 Meta-Harness는 무엇이 같고, LLM Wiki에는 무엇을 각각 가져와야 하는가?

## Short answer
둘 다 “inner task loop를 둘러싼 outer improvement loop”를 제안하지만, 초점이 다르다. Bilevel Autoresearch는 **search mechanism code injection**에, Meta-Harness는 **full-history filesystem diagnosis**에 더 강하다. 여기에 새 multi-agent topology 연구는 **broad parallel search와 deep expert handoff를 task complexity에 따라 route해야 한다**는 empirical signal을 더한다. LLM Wiki에는 이 셋을 합쳐, trace-first outer loop가 template / policy / script를 one-at-a-time으로 바꾸되 협업 topology까지 고정하지 않는 구조가 적합하다.

## Evidence considered
- [[source--bilevel-autoresearch]]
- [[source--meta-harness]]
- [[source--karpathy-autoresearch-repo]]
- [[source--multi-agent-collaboration-for-automated-research]]
- [[concept--harness-optimization]]
- [[concept--trace-store-and-run-ledger]]

## Analysis
### 공통점
- inner loop와 outer loop를 분리한다.
- 모델 weights 대신 code / search logic / harness를 개선 대상으로 둔다.
- keep/discard 또는 frontier selection 같은 explicit selection rule을 둔다.
- prior experience를 재사용한다.

### 차이점
- Bilevel Autoresearch는 runner code에 새 search mechanism을 **삽입**하는 관점이 강하다.
- Meta-Harness는 source code, score, execution trace 전체를 파일시스템에서 **탐색**하게 하는 관점이 강하다.
- Bilevel은 mechanism novelty와 구조적 탐색 확대에 초점을 두고, Meta-Harness는 diagnosis quality와 confound isolation에 초점을 둔다.
- Bilevel의 논리에서는 validate-and-revert가 중요하고, Meta-Harness의 논리에서는 trace accessibility와 navigation ergonomics가 중요하다.

### multi-agent topology 연구가 더해 주는 것
- subagent architecture는 isolated worktree와 post-hoc consolidation을 통해 짧은 budget 아래에서 더 resilient한 empirical search를 제공한다.
- expert team architecture는 shared worktree handoff 탓에 더 fragile하지만, deep refactor와 structurally diverse proposal을 만들 가능성이 더 높다.
- 즉 outer loop는 항상 single topology를 고정하기보다, task complexity와 available compute budget에 따라 collaboration mode를 route하는 쪽이 낫다.

### LLM Wiki에의 번역
- Bilevel에서 가져올 것: mechanism-level mutation, validate-and-revert, one-target-at-a-time
- Meta-Harness에서 가져올 것: full-history artifacts, lint/eval/log/file diff의 raw access, summary에 과도하게 의존하지 않는 diagnosis
- multi-agent topology 연구에서 가져올 것: broad shallow search에는 subagent-style 병렬 탐색, deep refactor에는 slower expert handoff를 검토하는 [[concept--multi-agent-routing]] 사고방식
- Karpathy minimalism에서 가져올 것: baseline first, keep/discard, simplicity criterion
- Long-horizon quality guard에서 가져올 것: outer-loop mutation이 실제 개선인지, 아니면 architecture entropy와 complexity drift를 누적하는지 trend로 판정하는 feedback lens
- failure mode taxonomy에서 가져올 것: lint/eval symptom을 structural, routing/provenance, content quality, mechanism/process family로 나눠 outer-loop mutation 대상을 좁히는 기준

## What this synthesis excludes
- 이 synthesis는 어떤 특정 multi-agent topology를 지금 즉시 채택하자는 구현 결정문이 아니다.
- code-level patch protocol이나 sandbox/security boundary 설계는 현재 범위를 넘는다.
- Bilevel과 Meta-Harness의 benchmark 우열을 일반적으로 확정하려는 문서도 아니다.

## Tensions / contradictions
- Bilevel은 mechanism injection에 강하고 Meta-Harness는 diagnosis/navigation에 강해, mutation novelty와 trace richness 사이에 우선순위 긴장이 있다.
- subagent architecture는 resilient하지만 shallow해질 수 있고, expert-team handoff는 deeper insight를 줄 수 있지만 coordination fragility가 크다.
- one-mechanism discipline을 지키려면 collaboration topology까지 함께 바꾸지 않는 편이 낫지만, 실제 복잡한 task는 topology 차이의 영향을 크게 받을 수 있다.

## Implications for future ingest
- 후속 system source는 `mechanism mutation`, `trace accessibility`, `collaboration routing`, `validate-and-revert discipline` 중 어느 축을 보강하는지 먼저 태깅하는 편이 좋다.
- new agent/runtime paper를 읽을 때는 single-topology proposal인지 routed topology proposal인지 분리해 저장해야 outer loop 설계가 덜 섞인다.
- future automation 단계에서도 먼저 trace-first diagnosis를 유지한 채, collaboration routing만 작은 policy surface로 실험하는 편이 안전하다.

## Decision / takeaway
LLM Wiki의 outer loop는 다음 원칙을 따른다.
1. inner loop는 page maintenance다.
2. outer loop는 template / policy / script / command 중 **하나의 mechanism**만 바꾼다.
3. decision은 binary eval + lint + trace review로 내린다.
4. raw history는 `log + snapshots + manifest + report`로 보존한다.
5. mechanism patch는 쉽게 revert 가능해야 한다.

## Follow-up questions
- future stage에서 outer loop가 실제 Python script patch까지 허용될 때 safety boundary는 어디에 둘 것인가?
- long-history navigation을 위해 별도 trace index나 diff viewer가 필요한가?

## Related pages
- [[concept--harness-optimization]]
- [[concept--multi-agent-routing]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--wiki-failure-mode-taxonomy]]
- [[concept--long-horizon-quality-guard]]
- [[synthesis--karpathy-gist-to-runtime]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Source trace
- `raw/2603.23420v1.pdf`
- `raw/2603.28052v1.pdf`
- `raw/2603.24755v1.pdf`
- `raw/2603.29632v1.pdf`
- `raw/web-snapshots/meta-harness-project-page-2026-04-12.md`
- `raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md`
- `raw/V2 stage1_mvp_specification.pdf`
- `ops/schemas/run-ledger.schema.json`
