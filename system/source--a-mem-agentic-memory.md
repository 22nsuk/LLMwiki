---
title: "A-Mem: Agentic Memory for LLM Agents"
page_type: "source"
corpus: "system"
registry_id: "R-024"
raw_path: "raw/2502.12110v11.pdf"
source_type: "research-paper"
domain: "agentic-memory-organization"
created: "2026-04-13"
aliases:
  - "source--a-mem-agentic-memory"
tags:
  - "corpus/system"
  - "type/source"
---

# source--a-mem-agentic-memory

## Title
A-Mem: Agentic Memory for LLM Agents

## Source
- `raw/2502.12110v11.pdf`

## Type
research-paper

## Summary
이 논문은 기존 LLM agent memory가 저장·검색은 하더라도 구조 조직과 적응성이 약하다고 보고, Zettelkasten 원리를 따라 note attributes, dynamic indexing, meaningful linking, historical memory update를 수행하는 `agentic memory`를 제안한다. 핵심은 memory access pattern과 schema를 고정하지 않고, 새 경험이 들어올 때 기존 note network 자체를 재구성하게 만드는 것이다.

## Why it matters
현재 system corpus의 `trace store` 개념은 raw artifact를 남기는 쪽에 가깝고, `run ledger`는 chronological event log에 가깝다. 이 논문은 그 위에 `memory organization layer`를 한 단계 더 올려, trace가 쌓인 뒤 어떤 note network와 link maintenance를 해야 하는지 생각하게 만든다.

## Key points
- traditional memory systems require predefined storage and retrieval points, which limits adaptability.
- A-Mem creates structured notes with context, keywords, and tags when new memory arrives.
- it then links new memories to historical memories where similarities are meaningful.
- memory evolution means old memories can be updated as new context arrives, not just appended forever.
- the paper reports gains over prior memory baselines across multiple foundation models.

## Limitations / caveats
- benchmark improvement alone does not prove the design is operationally safe for persistent wiki maintenance.
- dynamic memory updates can introduce drift if there is no append-only ledger or promotion gate around them.
- the paper focuses on agent memory performance, not on human-readable governance or auditability by default.

## Related pages
- [[concept--memory-management-strategies]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--self-improving-wiki-loop]]
- [[concept--persistent-wiki-vs-rag]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- should wiki maintenance treat note linking and note rewriting as separate permission classes?
- when does a dynamic memory graph become worth maintaining in addition to append-only logs and canonical pages?

## Source trace
- `raw/2502.12110v11.pdf`
