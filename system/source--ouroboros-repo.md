---
title: "Q00/ouroboros repository"
page_type: "source"
corpus: "system"
registry_id: "W-004"
raw_path: "raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md"
source_type: "github-snapshot"
domain: "planning-runtime-gates"
created: "2026-04-12"
aliases:
  - "source--ouroboros-repo"
tags:
  - "corpus/system"
  - "type/source"
---

# source--ouroboros-repo

## Title
Q00/ouroboros repository

## Source
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`

## Type
github-repository

## Summary
Ouroboros는 spec-first AI development system이다. 핵심은 **Socratic interview -> immutable seed -> execute -> evaluate -> evolve**라는 명시적 상태 전이와, ambiguity / evaluation gate / persistent loop를 시스템 차원에서 강제하는 데 있다.

## Why it matters
LLM Wiki는 source page와 synthesis page를 쌓는 데 강하지만, major planning 작업에 대해서는 아직 seed freeze와 signoff가 약하다. Ouroboros는 “질문-문서화-검증-진화”를 **workflow engine**으로 다루는 방식이라, planning harness와 wiki bridge를 설계하는 데 매우 중요하다.

## Key points
- vague prompt, no spec, manual QA를 주요 실패 원인으로 본다.
- 인터뷰 단계에서 hidden assumptions를 드러내고 ambiguity threshold를 넘기 전에는 seed를 고정하지 않는다.
- seed는 immutable spec이며, 실행은 그 이후 단계다.
- 평가를 mechanical -> semantic -> multi-model consensus의 3단계 gate로 설명한다.
- `ooo` command surface와 `CLAUDE.md`는 각 기능을 skill 또는 MCP action에 연결한다.
- persistent loop `ralph`는 session boundary를 넘어 이벤트 기록을 재구성하며 계속 돈다.

## Limitations / caveats
- 전체 시스템은 넓고 복잡하다. wiki bootstrap 단계에 그대로 도입하면 과설계가 될 수 있다.
- ontology similarity, ambiguity scoring, consensus evaluation 등은 구현 비용이 높다.
- stage 1 수준에서는 full Ouroboros보다 seed freeze + signoff + event ledger만 먼저 가져오는 편이 실용적이다.

## Related pages
- [[source--stage1-planning-harness-mvp]]
- [[concept--planning-gates]]
- [[concept--trace-store-and-run-ledger]]
- [[synthesis--stage1-planning-harness-bridge]]
- [[synthesis--llm-wiki-self-improvement-architecture]]

## Open questions
- wiki에서 ambiguity gate는 page generation 전에 적용할지, only planning bundle에 적용할지?
- consensus evaluation을 wiki quality review에 언제 도입해야 하는가?
- `ralph`와 같은 persistent loop를 wiki maintainer에 붙일 최소 조건은 무엇인가?

## Source trace
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`
