---
title: "Planning Gates"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-14"
aliases:
  - "concept--planning-gates"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--planning-gates

## Summary
planning gate는 “이제 다음 단계로 넘어가도 되는가?”를 prompt convention이 아니라 **runtime rule**로 판정하는 구조다. PASS / WARN / FAIL과 명시적 next action이 핵심이다.

## Why it matters here
지금까지 많은 agent workflow는 “대충 충분해 보이면 계속”에 기대 왔다. 하지만 planning harness나 wiki self-improvement에서는 seed freeze, source trace, task graph, signoff 같은 조건을 통과하지 못하면 다음 단계로 넘어가면 안 된다.

## Main body
### gate가 필요한 이유
- ambiguity를 남긴 채로 plan을 만들면 이후 수정 비용이 폭증한다.
- source trace가 약한 page를 canonical page로 승격하면 이후 query 품질이 흔들린다.
- long-horizon editing에서는 초반 구조 결함이 누적되기 쉽다.

### Stage 1 spec에서의 핵심 요소
- success criteria testability
- scope separation
- task graph validity
- task size 제한
- acceptance traceability
- open-question budget
- signoff requirement

### wiki에 맞춘 해석
- page readiness gate: required headings, source trace, broken link free 여부
- synthesis readiness gate: evidence 충분성, contradiction surfaced 여부, decision/takeaway 존재 여부
- bundle readiness gate: seed frozen, validation report 존재, signoff logged 여부

## Scope boundaries
- planning gate는 단계 전이 허용 여부를 판정하는 운영 규칙이다.
- 일반적인 task reminder나 개인 작업 메모를 의미하지 않는다.
- 실행 자체를 대신하는 개념도 아니고, evidence synthesis를 모두 gate field로 환원하는 개념도 아니다.

## Examples and non-examples
- example: seed가 frozen되지 않았으면 `PLAN_DRAFT`로 못 넘어가게 하는 것은 planning gate다.
- example: page가 required sections와 source trace를 만족해야 readiness를 얻는 것도 gate 해석이다.
- non-example: “왠지 충분해 보인다”는 암묵적 진행은 gate가 아니다.
- non-example: signoff 없이 planning 상태를 말로만 업데이트하는 것은 auditable transition이 아니다.

## How to reuse this concept
- ambiguity가 큰 request를 다룰 때는 바로 page를 쓰기보다 어느 gate를 먼저 통과해야 하는지 정리한다.
- promotion이나 handoff가 걸린 artifact에는 PASS/WARN/FAIL 기준과 next action을 먼저 적는다.
- query/synthesis가 넓어질 때도 “지금 answer를 얼려도 되는가”를 gate 관점에서 다시 본다.

## Related pages
- [[source--stage1-planning-harness-mvp]]
- [[source--ouroboros-repo]]
- [[concept--binary-evals]]
- [[synthesis--stage1-planning-harness-bridge]]

## Open questions
- wiki page에는 PASS/WARN/FAIL 상태를 frontmatter로 둘지 별도 report artifact로 둘지?
- medium severity open question budget을 page type별로 다르게 둘 필요가 있는가?

## Source trace
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`
