---
title: "Artifact Contracts"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--artifact-contracts"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--artifact-contracts

## Summary
artifact contract는 agent workflow의 각 산출물을 **파일명, 스키마, 필수 필드, 상태 전이**까지 포함해 명시적으로 정의하는 방식이다.

## Why it matters here
LLM Wiki가 커질수록 “무슨 파일이 어디 있어야 하는가”가 흐려지면 maintainer 품질이 빠르게 무너진다. artifact contract는 wiki를 prompt blob가 아니라 inspectable system으로 만든다.

## Main body
### 왜 contract가 필요한가
- 다음 세션 agent가 어디를 봐야 하는지 분명해진다.
- validator와 lint를 deterministic하게 만들 수 있다.
- meta-loop가 어떤 artifact를 바꾸는지 추적 가능해진다.

### 이 패키지에서의 contract 예
- `raw/`: binary는 immutable source, markdown는 contract-limited normalized source snapshot
- `wiki/source--...md`: canonical source abstraction
- `wiki/synthesis--...md`: question-driven decision artifact
- `ops/policies/*.yaml`: runtime policy
- `ops/evals/*.md`: binary eval definitions
- `ops/schemas/*.json`: machine-readable report schema
- `ops/scripts/*.py`: lint/eval/manifest helpers

### planning harness bridge
Stage 1 spec의 `seed.yaml`, `plan.md`, `task-graph.json`, `planning-validation.json`, `run-ledger.json`도 같은 철학이다. 즉, 좋은 planning runtime은 artifact contract 위에서만 자란다.

### provenance packaging 확장
RO-Crate는 이런 artifact contract를 더 넓은 metadata packaging 철학과 연결해 준다. 현재 repo는 Markdown과 JSON artifact 위주로 가볍게 운영되지만, dataset, workflow, software, provenance relation을 portable object로 묶는 사고방식 자체는 future export surface를 설계할 때 좋은 reference가 된다.

## Scope boundaries
- artifact contract는 산출물의 shape, location, schema, transition을 정하는 규칙이다.
- contract가 있다고 해서 내용의 품질이나 promotion 판단이 자동으로 보장되지는 않는다.
- ad hoc exploration note까지 모두 rigid artifact로 만들자는 뜻은 아니다.

## Examples and non-examples
- example: `runs/<run-id>/run-ledger.json`의 필수 필드와 schema를 고정하는 것은 artifact contract다.
- example: `source--`, `concept--`, `synthesis--` prefix를 page role과 연결하는 것도 artifact contract다.
- non-example: “이번 세션에서 대충 참고한 메모”를 아무 계약 없이 남기는 것은 contracted artifact가 아니다.
- non-example: source page 안의 해석이 설득력 있는지 여부는 contract보다 content quality의 문제다.

## How to reuse this concept
- 새 runtime file이나 report를 추가할 때는 먼저 “파일 경로, required field, validator가 무엇인가”를 contract로 정의한 뒤 도입한다.
- planning/mechanism run을 바꿀 때는 어떤 artifact가 single source of truth인지 명시해 중복 상태 저장을 피한다.
- future export surface를 설계할 때도 현재 local artifact contract를 그대로 portable package metadata로 사상할 수 있는지 점검한다.

## Related pages
- [[source--stage1-planning-harness-mvp]]
- [[source--ro-crate]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--planning-gates]]
- [[synthesis--karpathy-gist-to-runtime]]

## Open questions
- wiki page에 최소 frontmatter contract를 둘 것인가?
- query artifact와 log artifact도 JSON sidecar를 둘 필요가 있는가?

## Source trace
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/web-snapshots/Research Object Crate (RO-Crate).md`
- `ops/schemas/bundle-manifest.schema.json`
- `ops/schemas/run-ledger.schema.json`
