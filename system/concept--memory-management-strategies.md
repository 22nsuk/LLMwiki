---
title: "Memory Management Strategies"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--memory-management-strategies"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--memory-management-strategies

## Summary
memory management strategies는 persistent wiki runtime에서 working, episodic, semantic, procedural, provenance, telemetry memory를 구분하고, 각 memory class를 어떤 artifact에 남기고 언제 승격할지 정하는 운영 개념이다.

## Why it matters here
LLM Wiki는 단순 RAG store가 아니라 source snapshot, canonical page, policy, lint/eval result, system log가 함께 움직이는 memory system이다. 모든 것을 session context에 맡기면 다음 작업에서 재구성할 수 없고, 모든 것을 append-only log로만 남기면 검색과 refactor가 무거워진다. A-Mem은 dynamic note linking의 장점을 보여 주지만, 이 repo에서는 append-only provenance와 mutable semantic page의 경계를 먼저 지켜야 한다.

## Main body
### Memory classes
- working memory: 현재 세션의 임시 reasoning context다. canonical하지 않으며, 재사용 가치가 있을 때만 query/log/page로 승격한다.
- episodic memory: `system/system-log.md`, run ledger, promotion report처럼 시간순 사건을 남기는 append-only memory다.
- semantic memory: concept, synthesis, source page처럼 의미 구조를 축적하는 mutable curated memory다.
- procedural memory: `AGENTS.md`, `AGENTS.local.md`, ops policy, scripts, schemas, templates, agent profiles처럼 다음 행동 방식을 바꾸는 memory다.
- provenance memory: raw snapshots, raw registry, source trace처럼 사실 주장과 source lineage를 재검증하게 해 주는 memory다.
- telemetry memory: lint/eval/stage2 reports, mechanism assessment, review candidates처럼 runtime 품질 신호를 남기는 memory다.

### Promotion rule
working memory는 바로 semantic page가 되지 않는다. 먼저 reusable query artifact, system log, lint report, or source note로 남길 가치가 있는지 판단한다. 반복적으로 재사용되는 판단만 concept/synthesis/policy로 승격하고, 단일 사건은 episodic memory에 둔다.

### Drift controls
- episodic memory는 append-only로 유지해 later diagnosis를 가능하게 한다.
- semantic memory는 source trace와 related pages를 통해 재검증 가능해야 한다.
- procedural memory는 one-mechanism discipline과 deterministic tests를 요구한다.
- provenance memory는 raw source를 복제하거나 의역하지 않고 path와 registry를 통해 연결한다.
- telemetry memory는 [[concept--long-horizon-quality-guard]]와 [[concept--wiki-failure-mode-taxonomy]]의 trend input으로 재사용한다.

## Scope boundaries
- 이 개념은 vector database 설계 문서가 아니다.
- raw source 내용을 semantic page에 복사해 provenance를 대체하지 않는다.
- 모든 session note를 영구 저장하자는 원칙이 아니다.
- dynamic memory update는 append-only ledger와 source trace discipline을 대체할 수 없다.

## Examples and non-examples
- example: system 작업 후 `system/system-log.md`에 append하는 것은 episodic memory다.
- example: 반복되는 routing 판단을 concept page로 빼는 것은 semantic memory 승격이다.
- example: `ops/policies/wiki-maintainer-policy.yaml` 변경은 procedural memory mutation이므로 test와 gate가 필요하다.
- non-example: 한 번 나온 아이디어를 검증 없이 canonical synthesis로 만드는 것은 memory promotion이 아니라 context leakage다.
- non-example: raw PDF 내용을 wiki page에 길게 붙여 넣는 것은 provenance memory를 semantic memory로 오염시키는 것이다.

## How to reuse this concept
- 새 artifact를 만들 때 먼저 memory class를 정한다.
- query answer가 재사용 가치가 크면 query artifact로, 반복 운영 판단이면 concept/policy 후보로, 단일 작업 이력은 log로 남긴다.
- run history를 읽을 때는 단순 chronology와 reusable semantic lesson을 분리한다.
- memory-related research source는 trace storage, note organization, procedural policy, telemetry trend 중 어느 층을 보강하는지 태깅한다.

## Related pages
- [[source--a-mem-agentic-memory]]
- [[source--ro-crate]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--persistent-wiki-vs-rag]]
- [[concept--self-improving-wiki-loop]]
- [[concept--long-horizon-quality-guard]]
- [[concept--artifact-contracts]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- dynamic note linking을 별도 graph artifact로 둘 만큼 memory pressure가 충분히 커졌는가?
- query artifact와 system log 사이의 승격 기준을 더 machine-readable하게 만들 필요가 있는가?
- telemetry memory의 retention과 compaction rule은 어디에 둘 것인가?

## Source trace
- `raw/2502.12110v11.pdf`
- `raw/web-snapshots/Research Object Crate (RO-Crate).md`
- `system/source--a-mem-agentic-memory.md`
- `system/source--ro-crate.md`
- `system/concept--trace-store-and-run-ledger.md`
- `AGENTS.local.md`
