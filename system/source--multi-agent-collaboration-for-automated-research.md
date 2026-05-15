---
title: "An Empirical Study of Multi-Agent Collaboration for Automated Research"
page_type: "source"
corpus: "system"
registry_id: "R-027"
raw_path: "raw/2603.29632v1.pdf"
source_type: "research-paper"
domain: "multi-agent-autoresearch-topologies"
created: "2026-04-13"
aliases:
  - "source--multi-agent-collaboration-for-automated-research"
tags:
  - "corpus/system"
  - "type/source"
---

# source--multi-agent-collaboration-for-automated-research

## Title
An Empirical Study of Multi-Agent Collaboration for Automated Research

## Source
- `raw/2603.29632v1.pdf`

## Type
research-paper

## Summary
이 논문은 automated ML optimization에서 **single agent**, **subagent architecture**, **agent team architecture**를 같은 execution testbed 위에서 비교한다. 핵심 결론은, subagent 구조는 fixed time budget 아래에서 **높은 throughput과 operational stability**를 주고, expert team 구조는 더 fragile하지만 **깊은 구조적 refactor**를 할 때 더 이론적으로 정렬된 탐색을 가능하게 한다는 것이다.

## Why it matters
현재 system corpus에는 bilevel autoresearch, Meta-Harness, Karpathy-style minimal loop는 있지만, **multi-agent collaboration topology 자체를 empirical하게 비교한 source**는 없었다. 이 논문은 meta-maintainer runtime에서 언제 broad parallel exploration이 맞고, 언제 slower expert handoff가 맞는지 생각하게 만드는 직접적인 evidence다.

## Key points
- 저자들은 Git worktree isolation, deterministic patch contract, global explicit memory를 갖춘 execution-based testbed를 구축한다.
- subagent mode는 독립 worker가 병렬로 짧은 실험을 돌리고, improvement가 여러 개 나오면 orchestrator가 post-hoc merge한다.
- agent team mode는 architecture / optimizer / engineering expert가 pre-execution handoff를 하며 하나의 shared worktree에 집중한다.
- 짧은 time budget에서는 subagent mode가 crash/failure rate가 낮고 valid proposal volume이 높았다.
- agent team mode는 더 적은 성공 횟수를 보였지만, parameter squeezing보다 구조적·다축적 modification을 더 자주 만들었다.
- 결론은 rigid topology 하나를 고집하기보다, task complexity와 available compute budget에 따라 routed collaboration이 필요하다는 것이다.

## Limitations / caveats
- benchmark가 neural network optimization에 집중되어 있어 문서형 wiki runtime으로 직접 일반화하긴 어렵다.
- agent team fragility는 저자들의 handoff design과 model choice에 영향을 받는다.
- multi-agent quality를 semantic discussion depth 대신 val_bpb / stability 같은 execution metric 중심으로 본다.

## Related pages
- [[source--bilevel-autoresearch]]
- [[source--meta-harness]]
- [[source--karpathy-autoresearch-repo]]
- [[source--kevinrgu-autoagent-repo]]
- [[concept--multi-agent-routing]]
- [[concept--harness-optimization]]
- [[concept--self-improving-wiki-loop]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]

## Open questions
- wiki meta-maintainer에서는 subagent-style broad search와 expert-team-style deep review를 어떤 task boundary에서 갈라야 하는가?
- fixed time budget 아래의 operational stability와 longer deliberation 아래의 structural depth를 어떻게 promotion rule에 반영할 것인가?
- global explicit memory와 worktree isolation을 wiki maintenance loop에 옮길 때 최소 artifact surface는 무엇인가?

## Source trace
- `raw/2603.29632v1.pdf`
