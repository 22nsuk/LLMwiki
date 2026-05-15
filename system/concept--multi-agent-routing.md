---
title: "Multi Agent Routing"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--multi-agent-routing"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--multi-agent-routing

## Summary
multi-agent routing은 single-agent, parallel subagent, expert-team handoff, reviewer/validator pass 같은 collaboration topology를 **task complexity, write-set coupling, evidence breadth, time budget, validation cost**에 따라 고르는 harness-level 판단 기준이다.

## Why it matters here
이 repo에는 system research, lint/eval telemetry, `.codex/agents/` role surface가 함께 있다. 모든 작업을 한 topology로 밀어 넣으면 쉬운 편집에는 coordination cost가 커지고, 넓은 evidence review나 deep refactor에는 탐색 폭이 부족해진다. 다만 현재 Codex 세션에서는 도구 계약상 **사용자가 명시적으로 요청할 때만 subagent를 spawn**한다. 이 concept은 세션 권한을 넓히는 문서가 아니라, runtime/policy/agent profile을 정리할 때 쓸 routing vocabulary다.

## Main body
### Routing axes
- task decomposability: 하위 문제가 서로 독립적으로 풀리는가?
- evidence breadth: 여러 source family를 병렬로 읽어야 하는가?
- write-set coupling: 같은 파일이나 같은 policy surface를 동시에 만질 위험이 있는가?
- ownership boundary: public/private, raw/wiki/system, ops/test 경계가 섞이는가?
- time budget: 짧은 budget에서 proposal volume이 중요한가, 깊은 구조 판단이 중요한가?
- validation cost: patch integration 뒤 deterministic gate를 얼마나 쉽게 재실행할 수 있는가?

### Collaboration topologies
- local single-agent: tightly coupled edit, next critical-path blocker, one-file correction, source-fidelity risk가 큰 작업의 기본값이다.
- parallel subagent search: read-only evidence gathering, independent shard review, disjoint write set이 명확한 bounded patch에 적합하다.
- expert-team handoff: architecture, optimization, engineering 판단이 모두 필요한 deep refactor 후보에 적합하지만 coordination fragility가 크다.
- reviewer/validator pass: patch 후 correctness, source fidelity, contract drift, missing test를 독립적으로 점검할 때 쓴다.

### Repo-local operating rule
delegation은 integration owner를 없애지 않는다. subagent가 병렬로 탐색하거나 patch를 만들더라도, 최종 page/router/log/eval 일관성은 main maintainer가 통합해야 한다. coding task를 위임할 때는 write set을 분리하고, read-only review라면 어떤 decision에 필요한 evidence인지 먼저 좁힌다.

## Scope boundaries
- 이 개념은 subagent를 자동 spawn하라는 허가가 아니다.
- model selection, staffing chart, organization design을 다루지 않는다.
- raw source, private corpus, public export boundary 같은 기존 권한 경계를 우회하지 않는다.
- collaboration topology 자체를 mechanism experiment로 바꿀 때도 one-mechanism discipline과 validation gate가 우선이다.

## Examples and non-examples
- example: broad raw report 비교처럼 source family가 넓고 read-only 판단이 많은 작업은 사용자가 허용하면 parallel evidence review 후보가 된다.
- example: `system/system-index.md` 한 줄 보정처럼 tightly coupled한 작은 편집은 local single-agent가 맞다.
- example: disjoint shard ingest는 write set을 분리할 수 있을 때만 subagent patch 후보가 된다.
- non-example: 같은 synthesis를 여러 agent가 동시에 고치게 하고 post-hoc으로 충돌을 맞추는 것은 routing이 아니라 coordination debt다.
- non-example: subagent를 많이 쓰는 것 자체를 품질 향상으로 간주하지 않는다.

## How to reuse this concept
- 작업을 시작할 때 먼저 local, parallel search, expert handoff, validator pass 중 어느 topology가 맞는지 분류한다.
- subagent가 유리해 보여도 write-set coupling과 integration owner가 불명확하면 local 작업으로 축소한다.
- mechanism improvement에서는 topology 변경을 policy/template/script 변경과 한 번에 묶지 말고 별도 experiment로 다룬다.
- review 보고서나 system source를 ingest할 때 `collaboration routing` 주장을 이 concept에 연결한다.

## Related pages
- [[source--multi-agent-collaboration-for-automated-research]]
- [[source--bilevel-autoresearch]]
- [[source--meta-harness]]
- [[source--voyager-open-ended-embodied-agent]]
- [[source--dspy-framework]]
- [[concept--harness-optimization]]
- [[concept--self-improving-wiki-loop]]
- [[concept--trace-store-and-run-ledger]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]

## Open questions
- routing decision을 AGENTS text, policy YAML, or agent profile 중 어디에 가장 작게 표현할 수 있는가?
- read-only parallel review와 disjoint patch delegation을 서로 다른 permission class로 나눌 필요가 있는가?
- route choice 자체를 eval할 최소 deterministic fixture는 무엇인가?

## Source trace
- `raw/2603.29632v1.pdf`
- `raw/2603.23420v1.pdf`
- `raw/2603.28052v1.pdf`
- `raw/web-snapshots/An Open-Ended Embodied Agent with Large Language Models.md`
- `raw/web-snapshots/DSPy.md`
- `system/source--multi-agent-collaboration-for-automated-research.md`
- `system/concept--harness-optimization.md`
