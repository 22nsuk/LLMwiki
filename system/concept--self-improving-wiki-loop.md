---
title: "Self Improving Wiki Loop"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--self-improving-wiki-loop"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--self-improving-wiki-loop

## Summary
self-improving wiki loop는 wiki content를 유지하는 inner loop, 작업을 통제하는 planning gate, policy/template/script를 개선하는 outer loop, 그리고 telemetry / eval / lint / run history를 다시 읽는 meta-research feedback layer를 분리해 운영하는 구조다.

## Why it matters here
사용자가 요청한 통합의 핵심은 단순 source ingest가 아니라 **자기개선 방향의 접목**이다. 이 개념 페이지는 Bilevel Autoresearch, Meta-Harness, autoresearch-skill, Ouroboros를 wiki 운영 모델로 번역하는 중심 개념이다.

## Main body
### Inner loop: content maintenance
- ingest source
- update source / concept / synthesis pages
- run lint / eval
- keep/discard page changes
- update index / log

### Middle loop: gate and planning
- deep-dive or interview
- seed draft / freeze
- plan draft
- validation / signoff
- bundle ready or blocked

### Outer loop: mechanism improvement
- inspect prior pages, lint reports, eval reports, changelog, run ledger
- change one mechanism: template, policy, script, command surface
- re-run eval
- promote only if score improves

### Meta-research feedback layer
```text
LLM -> research -> improvement
        ^           |
        |           v
meta-research <- telemetry / eval / lint / run history
```

meta-research는 외부 연구 source와 내부 run evidence를 함께 읽어 improvement 규칙을 조정한다. 예를 들어 SlopCodeBench의 long-horizon degradation signal은 단순 prompt hygiene보다 trajectory-level metric과 periodic refactor loop가 필요하다는 근거가 된다. 이 layer는 content page를 직접 늘리는 route가 아니라, 기존 loop가 반복될수록 품질이 무너지는지 감시하는 guard surface다.

### Design principle
summary만 보는 것이 아니라 raw trace와 prior artifact를 다시 볼 수 있어야 한다.

## Scope boundaries
- self-improving wiki loop는 content maintenance loop와 mechanism improvement loop의 분리 원칙을 다룬다.
- raw source를 수정해서 점수를 올리는 행위나, 여러 mechanism을 한 번에 바꾸는 실험은 이 개념의 허용 범위 밖이다.
- 모든 변경을 자동화하자는 주장도 아니고, human signoff를 없애자는 구조도 아니다.
- meta-research feedback은 새 content route가 아니라 improvement loop를 감시하고 조정하는 layer다.

## Examples and non-examples
- example: source ingest 후 page를 갱신하고 lint/eval을 돌리는 것은 inner loop다.
- example: policy 한 항목만 바꾸고 baseline/candidate를 비교하는 것은 outer loop다.
- example: 여러 run에서 broad synthesis candidate가 반복되는지 보고 refactor budget을 예약하는 것은 meta-research feedback이다.
- non-example: source page와 lint script와 eval definition을 한 번에 바꾸는 것은 one-mechanism discipline에 어긋난다.
- non-example: raw registry를 promotion ledger처럼 쓰는 것은 loop boundary를 흐리는 설계다.

## How to reuse this concept
- 새 작업이 content mutation인지 mechanism mutation인지 먼저 분류해 적절한 artifact와 gate를 선택한다.
- outer loop 실험을 설계할 때는 baseline, mutation unit, fixed eval, revert path를 한 세트로 묶는다.
- system corpus를 읽을 때도 각 문서가 inner loop 지원, planning gate, outer loop 설계, meta-research guard 중 어디에 속하는지 구분하는 기준점으로 사용한다.

## Related pages
- [[source--bilevel-autoresearch]]
- [[source--meta-harness]]
- [[source--slopcodebench]]
- [[source--autoresearch-skill-repo]]
- [[source--kevinrgu-autoagent-repo]]
- [[source--ouroboros-repo]]
- [[concept--long-horizon-quality-guard]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- page mutation loop와 mechanism mutation loop를 같은 run ledger로 묶을지?
- outer loop가 직접 script를 수정하게 할 시점은 언제인가?

## Source trace
- `raw/2603.23420v1.pdf`
- `raw/2603.28052v1.pdf`
- `raw/2603.24755v1.pdf`
- `raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md`
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`
- `ops/policies/wiki-maintainer-policy.yaml`
