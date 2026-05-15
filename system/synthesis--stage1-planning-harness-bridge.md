---
title: "Stage1 Planning Harness Bridge"
page_type: "synthesis"
corpus: "system"
source_count: 2
created: "2026-04-12"
aliases:
  - "synthesis--stage1-planning-harness-bridge"
tags:
  - "corpus/system"
  - "type/synthesis"
---

# synthesis--stage1-planning-harness-bridge

## Question
현재 LLM Wiki와 Stage 1 Planning Harness MVP를 어떻게 연결해야 하는가?

## Short answer
LLM Wiki는 **planning harness의 upstream evidence layer**가 되고, Stage 1 bundle은 **execution handoff layer**가 된다. 즉, wiki는 source / concept / synthesis를 통해 근거를 정리하고, Stage 1은 그 근거를 seed / plan / task graph / validation artifact로 고정한다.

## Evidence considered
- [[source--stage1-planning-harness-mvp]]
- [[source--ouroboros-repo]]
- [[concept--llm-wiki]]
- [[concept--planning-gates]]
- [[concept--artifact-contracts]]

## Analysis
### wiki가 맡을 일
- source별 핵심 주장과 caveat 정리
- 반복 개념 canonicalization
- 과거 결정과 질의 artifact 보관
- source trace 유지

### planning harness가 맡을 일
- 현재 요청을 seed spec로 freezing
- success criteria와 scope 명시
- task graph 생성
- planning gate 판정
- signoff / ledger 관리

### 연결 지점
- Stage 1 인터뷰는 wiki의 existing concept/synthesis page를 먼저 읽고 시작한다.
- seed 작성 시 wiki canonical page의 source trace를 evidence로 재사용한다.
- planning validation이 FAIL이면 wiki에 `query--` 또는 `lint--` artifact를 남겨 unresolved gap을 기록한다.
- bundle READY 이후에는 해당 bundle을 참조하는 synthesis page를 wiki에 만든다.

## What this synthesis excludes
- 이 문서는 Stage 2 execution runtime이나 downstream task runner 설계까지 포함하지 않는다.
- planning bundle을 wiki 내부에 그대로 흡수하는 저장 방식의 세부 구현도 아직 결정하지 않는다.
- post-run ingest automation 전체를 여기서 고정하지는 않는다.

## Tensions / contradictions
- wiki는 가변적 해석 layer이고 planning bundle은 frozen commitment layer라, 같은 evidence를 다루더라도 업데이트 속도와 안정성 요구가 다르다.
- planning gate를 세게 걸수록 handoff 품질은 좋아지지만, 가벼운 exploratory 작업에는 과한 friction이 될 수 있다.
- wiki canonical page를 충분히 읽지 않고 bundle을 만들면 evidence drift가 생기고, 반대로 bundle logic을 wiki 안으로 과도하게 끌어오면 operational boundary가 흐려진다.

## Implications for future ingest
- 후속 planning source는 `seed freeze`, `validation gate`, `run artifact`, `post-run back-ingest` 중 어느 연결 지점을 강화하는지 먼저 분류하는 편이 좋다.
- execution results를 다시 corpus에 흡수하는 규칙이 생기면 query/synthesis보다 별도 handoff or run-summary artifact를 먼저 검토해야 한다.
- wiki page와 run artifact의 역할이 다시 섞이기 시작하면 이 synthesis를 기준으로 boundary refactor를 걸 수 있다.

## Decision / takeaway
둘을 합칠 때 가장 좋은 분리는 아래와 같다.
- wiki = knowledge memory
- stage1 bundle = operational commitment
- ops = rule/eval/tooling
- log/ledger = chronology and provenance

즉, wiki가 planning harness를 대체하지 않고, planning harness가 wiki를 대체하지도 않는다. 둘은 서로 다른 계층이다.

## Follow-up questions
- bundle manifest를 wiki index에서 직접 노출할지?
- stage2 실행 결과를 wiki로 다시 흡수하는 post-run ingest 규칙은 어떻게 둘지?

## Related pages
- [[concept--planning-gates]]
- [[concept--artifact-contracts]]
- [[concept--llm-wiki]]
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[query--runtime-quickstart-2026-04-15]]
- [Historical bootstrap note: Recommended Next Actions 2026-04-12](../external-reports/query--recommended-next-actions-2026-04-12.md)

## Source trace
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`
- `AGENTS.md`
- `ops/schemas/run-ledger.schema.json`
- `ops/schemas/bundle-manifest.schema.json`
