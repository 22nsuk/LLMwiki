---
title: "Stage 1 MVP Specification"
page_type: "source"
corpus: "system"
registry_id: "R-004"
raw_path: "raw/V2 stage1_mvp_specification.pdf"
source_type: "implementation-spec"
domain: "planning-bundle-contracts"
created: "2026-04-12"
aliases:
  - "source--stage1-planning-harness-mvp"
tags:
  - "corpus/system"
  - "type/source"
---

# source--stage1-planning-harness-mvp

## Title
Stage 1 MVP Specification

## Source
- `raw/V2 stage1_mvp_specification.pdf`

## Type
implementation-spec

## Summary
이 문서는 Stage 1 Planning Harness MVP를 위한 구현 명세다. 목표는 자연어 요청을 **reviewable planning bundle**로 바꾸고, 준비가 충분하지 않으면 planning gate가 실행을 막도록 하는 CLI-first / artifact-first / gate-driven runtime을 정의하는 데 있다.

## Why it matters
이 문서는 현재 LLM Wiki 초안과 가장 직접적으로 연결된다. Wiki가 단순 지식 저장소를 넘어서 planning harness의 evidence layer가 되려면, seed freeze, task graph, validation report, run ledger 같은 artifact contract가 필요하다.

## Key points
- 제품 정의는 인터뷰 도구가 아니라 planning bundle runtime이다.
- scope는 request -> interview -> seed freeze -> plan -> task graph -> planning validation -> bundle export까지이며, 코드 실행과 self-improvement loop는 비범위다.
- 상태 전이는 REQUEST_IN부터 BUNDLE_READY/BUNDLE_BLOCKED까지 명시적으로 정의된다.
- `seed.yaml`, `plan.md`, `task-graph.json`, `planning-validation.json`, `open-questions.md`, `run-ledger.json` 등 artifact contract를 세분화한다.
- planning gate는 PASS / WARN / FAIL로 동작하며, success criteria testability, DAG validity, task size, acceptance traceability 등을 체크한다.
- 인터뷰는 clarity rubric을 쓰고, seed는 draft에서 frozen으로 승격되며 silent rewrite를 금지한다.

## Limitations / caveats
- stage 1은 deliberate하게 좁다. execution, verifier, dashboard, self-improvement loop는 아직 포함하지 않는다.
- ontology-heavy ambiguity scoring이나 multi-agent fanout은 future stage에 남겨 둔다.
- planning gate는 강하지만, source ingest와 wiki page maintenance를 직접 다루지는 않는다.

## Related pages
- [[source--ouroboros-repo]]
- [[concept--planning-gates]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--artifact-contracts]]
- [[synthesis--stage1-planning-harness-bridge]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- Stage 1 artifact contract를 wiki canonical page와 어떻게 매핑할 것인가?
- planning bundle과 wiki synthesis를 하나의 vault 안에서 어떻게 분리/연결할 것인가?
- stage 2 실행기 이전에도 wiki-based preflight gate를 걸 수 있는가?

## Source trace
- `raw/V2 stage1_mvp_specification.pdf`
