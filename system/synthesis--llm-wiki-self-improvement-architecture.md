---
title: "LLM Wiki Self Improvement Architecture"
page_type: "synthesis"
corpus: "system"
source_count: 5
created: "2026-04-12"
aliases:
  - "synthesis--llm-wiki-self-improvement-architecture"
tags:
  - "corpus/system"
  - "type/synthesis"
---

# synthesis--llm-wiki-self-improvement-architecture

## Question
현재 LLM Wiki 초안을 자기개선 가능한 runtime으로 발전시키는 목표 아키텍처는 무엇인가?

## Short answer
권장 아키텍처는 **3중 루프 + 4계층 저장소 + meta-research feedback layer**다. 저장소는 raw / wiki / ops / rules로 나누고, 루프는 (1) content maintenance, (2) planning gate, (3) mechanism improvement로 나눈다. 여기에 telemetry / eval / lint / run history를 다시 읽는 meta-research layer를 붙여, research가 improvement로 번역되는 과정에서 장기 품질 저하가 누적되지 않게 한다.

## Evidence considered
- [[source--llm-wiki-review-report]]
- [[concept--llm-wiki]]
- [[concept--self-improving-wiki-loop]]
- [[concept--long-horizon-quality-guard]]
- [[concept--planning-gates]]
- [[concept--artifact-contracts]]
- [[source--bilevel-autoresearch]]
- [[source--meta-harness]]
- [[source--stage1-planning-harness-mvp]]
- [[source--ouroboros-repo]]

## Analysis
### Layer model
- Raw: immutable binary source + contract-limited normalized markdown source snapshots
- Wiki: canonical source / concept / synthesis / query / lint pages
- Ops: policies, evals, schemas, scripts
- Rules: AGENTS.md

### Loop 1 — content maintenance
입력:
- raw source
- user query
- prior canonical pages

출력:
- updated wiki pages
- index/log update
- optional query artifact

selection:
- `wiki_eval.py` + `wiki_lint.py` score

### Loop 2 — planning gate
입력:
- ambiguous request
- existing bundle / existing wiki context

출력:
- seed draft / freeze
- plan draft
- task graph
- validation report
- signoff log

selection:
- PASS / WARN / FAIL gate

### Loop 3 — mechanism improvement
입력:
- prior pages
- lint/eval reports
- log / manifest / snapshot
- failing patterns

출력:
- changed template / policy / script / command surface

selection:
- keep/discard/revert with binary eval delta

### Meta-research feedback edge
입력:
- external system research sources
- telemetry / eval / lint / run history
- repeated review candidate families
- mechanism assessment complexity and structural metrics

출력:
- guard concepts
- metric families
- refactor cadence
- tighter routing and promotion rules

selection:
- long-horizon quality guard: architecture entropy, complexity drift, redundancy growth가 줄었거나 명시적으로 containment됐는지 확인

### 왜 이 구조가 필요한가
- wiki content만 바꾸면 반복 편집에서 운영 슬롭이 누적된다.
- mechanism만 바꾸면 실제 knowledge quality가 비어 있을 수 있다.
- planning gate가 없으면 ambiguous synthesis가 너무 빨리 canonical page가 된다.
- short-term lint/eval pass만 보면 장기 반복에서 verbosity와 structural erosion이 누적되는지 놓칠 수 있다.
- raw source snapshot layer가 약하면 future correction이 어려워진다. 다만 markdown capture에 한해 non-semantic normalization path를 두면 provenance를 크게 해치지 않으면서 운영 잡음을 줄일 수 있다.

### 권장 state transition
`REQUEST -> DISCOVERY -> INTERVIEW(optional) -> DRAFT -> VALIDATE -> SIGNOFF(optional) -> PROMOTE -> LOG`

### package-level baseline artifact
- `source--llm-wiki-review-report`는 개별 논문과 저장소에서 끌어온 방향을 현재 vault 설계와 실행 순서로 묶어 주는 **integration source**다.
- future session에서는 개별 source로 내려가기 전에 이 보고서를 먼저 읽고, 필요한 주장만 다시 raw 논문과 snapshot으로 역추적하는 방식이 효율적이다.

## What this synthesis excludes
- 이 문서는 production deployment topology, scheduler cadence, operator staffing plan까지 결정하지 않는다.
- fully autonomous outer loop를 곧바로 활성화하자는 설계 문서도 아니다.
- corpus별 개별 page shape 세부를 모두 나열하는 운영 매뉴얼 역할 역시 범위를 넘는다.

## Tensions / contradictions
- content loop와 mechanism loop를 분리할수록 구조는 선명해지지만 운영 마찰은 늘어날 수 있다.
- planning gate는 quality를 올리지만, 모든 작업에 적용하면 ingest 속도와 가벼운 maintenance를 방해할 수 있다.
- raw binary immutable layer를 강하게 유지할수록 correction trace는 좋아진다. 반면 markdown capture는 quick-fix 유혹을 막으면서도 capture noise를 줄일 수 있게 별도 minimal normalization contract가 필요하다.

## Implications for future ingest
- 후속 system source는 `content maintenance`, `planning gate`, `mechanism improvement`, `trace/provenance` 중 어느 루프를 직접 강화하는지 먼저 라우팅하면 좋다.
- long-horizon degradation이나 self-modification stability를 다루는 source는 `meta-research feedback` 또는 [[concept--long-horizon-quality-guard]]로 우선 라우팅한다.
- 새로운 script나 artifact를 추가할 때는 이 3중 루프 중 어느 층의 책임인지 명시해야 architecture drift를 줄일 수 있다.
- full auto persistent loop 관련 source가 더 쌓이더라도 우선은 layer separation을 깨지 않는 범위에서 단계적으로 흡수하는 편이 안전하다.

## Decision / takeaway
다음 단계의 구현 우선순위는 아래 순서다.
1. 현재 package의 source/concept/synthesis page를 canonical seed로 채택
2. lint/eval/manifest 스크립트를 반복 실행 가능한 기본 루틴으로 사용
3. planning bundle이 필요한 작업에만 seed freeze + signoff 도입
4. mechanism improvement는 우선 policy/template부터, 나중에 script까지 확장
5. meta-research feedback은 lint/eval/run-history trend를 읽어 refactor budget을 예약하는 guard로 먼저 붙임
6. full auto persistent loop는 trace store와 long-horizon guard가 충분히 쌓인 뒤에만 붙임

## Follow-up questions
- planning bundle을 wiki 내부에 둘지 별도 artifact store로 둘지?
- meta-loop를 수동 실행 명령으로 둘지, 야간 자동 배치로 둘지?

## Related pages
- [[system-index]]
- [[concept--llm-wiki]]
- [[concept--self-improving-wiki-loop]]
- [[concept--long-horizon-quality-guard]]
- [[concept--multi-agent-routing]] / [[concept--memory-management-strategies]] / [[concept--wiki-failure-mode-taxonomy]]
- [[concept--planning-gates]]
- [[synthesis--stage1-planning-harness-bridge]]

## Source trace
- `raw/llm_wiki_review_report.pdf`
- `raw/2603.23420v1.pdf`
- `raw/2603.28052v1.pdf`
- `raw/2603.24755v1.pdf`
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/web-snapshots/meta-harness-project-page-2026-04-12.md`
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`
- `AGENTS.md`
- `ops/evals/wiki-quality-evals.md`
- `ops/policies/wiki-maintainer-policy.yaml`
