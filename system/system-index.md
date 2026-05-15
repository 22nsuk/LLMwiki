---
title: "System Index"
page_type: "system-index"
corpus: "system"
created: "2026-04-12"
special_role: "router"
aliases:
  - "system-index"
tags:
  - "corpus/system"
  - "type/system-index"
---

# System Index

이 문서는 **private maintainer/runtime/self-improvement corpus router**다.
공유 가능한 구조 설명은 루트의 [ARCHITECTURE.md](../ARCHITECTURE.md)에 두고, 이 문서는 private corpus의 현재 router surface와 handoff에 집중한다.

## Summary
- system corpus pages: `71`
- system raw entries: `40`
- wiki raw entries: `406`
- full raw inventory: [[system-raw-registry]]
- content corpus router: [[index]]

## How to use this system corpus
- maintainer/runtime/self-improvement 질문은 먼저 이 router에서 출발한 뒤, 필요한 canonical page로 내려간다.
- raw inventory, provenance, ingest 상태가 필요하면 [[system-raw-registry]]를 먼저 본다.
- 과거 운영 판단, correction, schema change chronology가 필요하면 [[system-log]]를 본다.
- 실제 command, policy, schema, script entrypoint는 [ops/README.md](../ops/README.md)와 `ops/` tree를 canonical control surface로 본다.
- research가 improvement로 번역되는 과정에서 장기 품질 저하를 감시할 때는 [[concept--long-horizon-quality-guard]]를 meta-research feedback lens로 둔다.
- delegation, memory, failure diagnosis가 섞인 system 작업은 [[concept--multi-agent-routing]], [[concept--memory-management-strategies]], [[concept--wiki-failure-mode-taxonomy]]로 먼저 분리한다.

## System pages
- [[system-index]] — 현재 파일. system corpus router.
- [[system-raw-registry]] — raw source inventory summary router와 shard pointer.
- [[system-log]] — append-only 운영 이력.
- [[AGENTS]] — 운영 규칙.

## System knowledge pages
### Sources
- [[source--llm-wiki-review-report]]
- [[source--bilevel-autoresearch]]
- [[source--slopcodebench]]
- [[source--meta-harness]]
- [[source--a-mem-agentic-memory]]
- [[source--karpathy-autoresearch-repo]]
- [[source--kevinrgu-autoagent-repo]]
- [[source--multi-agent-collaboration-for-automated-research]]
- [[source--openai-evaluation-best-practices]]
- [[source--semantic-checks-and-execution-feedback-for-llm-assistants]]
- [[source--prompt-guidance-official-docs-2026-04-16]]
- [[source--prompt-robustness-perturbation-and-format-papers-2026-04-16]]
- [[source--natural-language-agent-harnesses-2026-04-17]]
- [[source--voyager-open-ended-embodied-agent]]
- [[source--dspy-framework]]
- [[source--ro-crate]]
- [[source--autoresearch-skill-repo]]
- [[source--jangpm-meta-skills-repo]]
- [[source--ouroboros-repo]]
- [[source--stage1-planning-harness-mvp]]

### Concepts
- [[concept--llm-wiki]]
- [[concept--persistent-wiki-vs-rag]]
- [[concept--harness-optimization]]
- [[concept--multi-agent-routing]]
- [[concept--planning-gates]]
- [[concept--artifact-contracts]]
- [[concept--binary-evals]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--memory-management-strategies]]
- [[concept--anti-slop-wiki-governance]]
- [[concept--wiki-failure-mode-taxonomy]]
- [[concept--long-horizon-quality-guard]]
- [[concept--cross-reference-maintenance]]
- [[concept--self-improving-wiki-loop]]
- [[concept--prompt-contract-robustness]]

### Syntheses
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]
- [[synthesis--karpathy-gist-to-runtime]]
- [[synthesis--research-insights-to-practical-wiki-rules]]
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[synthesis--stage1-planning-harness-bridge]]
- [[synthesis--prompt-robustness-and-contract-design-2026-04-16]]

### Query artifacts
- [[query--runtime-quickstart-2026-04-15]]
- [[query--index-and-raw-registry-separation-design-2026-04-12]]

### Historical external notes
- [Historical bootstrap note: Recommended Next Actions 2026-04-12](../external-reports/query--recommended-next-actions-2026-04-12.md)

### Lint artifacts
- [[lint--initial-review-2026-04-12]]
- [[lint--broad-synthesis-watch-review-2026-04-14]]
- [[lint--raw-registry-wiki-shard-line-threshold-review-2026-04-14]]
- [[lint--raw-registry-wiki-ai-capability-shard-review-2026-04-16]]
- [[lint--raw-registry-wiki-direct-seed-shard-review-2026-04-16]]
- [[lint--raw-unregistered-file-review-2026-04-16]]

## Content corpus handoff
- 일반 뉴스/content corpus는 [[index]]가 담당한다.
- 현재 content corpus는 두 개의 stable corpus map과 하나의 recent raw intake router를 가진다.
  - 뉴스/시장/지정학 묶음: [[query--news-snapshot-roundup-2026-04-12]]
  - coffee science 묶음: [[query--coffee-science-corpus-map-2026-04-13]]
  - 2026-04-21 raw intake batch: [[query--raw-intake-roundup-2026-04-21]]
- 현재 canonical wiki concepts:
  - [[concept--ai-ran]]
  - [[concept--ai-compute-infrastructure-buildout-stack]]
  - [[concept--ai-compute-control]]
  - [[concept--ai-capability-claims-verification]]
  - [[concept--digital-sovereignty-in-public-it]]
  - [[concept--korea-fx-liquidity-and-spot-dollar-pressure]]
  - [[concept--middle-east-energy-shock-transmission]]
  - [[concept--coffee-sensory-lexicon]]
  - [[concept--coffee-extraction-and-brew-control]]
  - [[concept--coffee-grinding-static-control]]
  - [[concept--coffee-brew-chemistry]]
- 현재 canonical wiki syntheses:
  - [[synthesis--middle-east-shipping-and-energy-risk-2026-04-12]]
  - [[synthesis--middle-east-war-macro-and-market-repricing-2026-04-13]]
  - [[synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14]]
  - [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]
  - [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]
  - [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]
  - [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]
  - [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
  - [[synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12]]
  - [[synthesis--coffee-sensory-language-and-flavor-mapping-2026-04-13]]
  - [[synthesis--coffee-extraction-models-and-brew-control-2026-04-13]]
  - [[synthesis--coffee-grinding-static-and-clumping-control-2026-04-13]]
  - [[synthesis--coffee-brew-chemistry-and-processing-2026-04-13]]

## Ops surface
- runtime contract의 canonical source of truth는 `ops/policies/wiki-maintainer-policy.yaml`이다.
- lint/eval/stage2/planning gate와 public export helper는 `ops/scripts/` 아래에 있고, 실제 진입점 요약은 [ops/README.md](../ops/README.md)에 정리돼 있다.
- public-safe 구조 설명과 export boundary는 [ARCHITECTURE.md](../ARCHITECTURE.md)와 [README.md](../README.md)가 담당한다.

## Related pages
- [[index]]
- [[system-raw-registry]]
- [[system-log]]
- [ARCHITECTURE.md](../ARCHITECTURE.md)
- [[query--runtime-quickstart-2026-04-15]]
- [Historical bootstrap note: Recommended Next Actions 2026-04-12](../external-reports/query--recommended-next-actions-2026-04-12.md)
- [[query--coffee-science-corpus-map-2026-04-13]]

## Source trace
- `AGENTS.md`
- `README.md`
- `system/system-log.md`
- `system/system-raw-registry.md`
- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/README.md`
- `ops/scripts/wiki_lint.py`
- `ops/scripts/wiki_eval.py`
