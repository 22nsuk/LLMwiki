---
title: "Runtime Quickstart 2026-04-15"
page_type: "query"
corpus: "system"
source_count: 5
created: "2026-04-15"
aliases:
  - "query--runtime-quickstart-2026-04-15"
tags:
  - "corpus/system"
  - "type/query"
---

# query--runtime-quickstart-2026-04-15

## Question
현재 이 저장소를 받은 뒤, 어떤 순서와 분기 규칙으로 시작하는 것이 가장 좋은가?

## Short answer
지금 이 저장소는 더 이상 bootstrap package가 아니라 **active full-vault runtime**으로 보는 편이 맞다. 시작 순서는 `환경 확인 -> 필요하면 baseline health 확인 -> 작업 surface 분류 -> 해당 루프 진입 -> log 포함 최종 gate`가 가장 안전하다. 작업 전 `.venv/bin/python -m ops.scripts.wiki_lint --vault .`, `.venv/bin/python -m ops.scripts.wiki_eval --vault .`, `.venv/bin/python -m ops.scripts.wiki_stage2_eval --vault .`는 현재 상태를 보는 선택적 baseline이고, closeout 통과 판정은 `system/system-log.md`까지 갱신한 최종 tree에서 한 번 실행한 lint/eval/stage2를 기준으로 삼는다.

## Evidence considered
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[synthesis--stage1-planning-harness-bridge]]
- [[concept--planning-gates]]
- [[concept--artifact-contracts]]
- [[concept--self-improving-wiki-loop]]

## Analysis
### 1. 먼저 현재 health를 확인한다
- `.venv`가 없거나 의존성이 어긋나면 `make dev-install`부터 맞춘다.
- current corpus 상태가 불확실하면 `.venv/bin/python -m ops.scripts.wiki_lint --vault .`, `.venv/bin/python -m ops.scripts.wiki_eval --vault .`, `.venv/bin/python -m ops.scripts.wiki_stage2_eval --vault .`로 baseline을 확인한다.
- 이 단계는 bootstrap cleanup이 아니라, 지금부터 만질 surface가 이미 green baseline인지 확인하는 절차다. 다만 이 baseline은 closeout gate가 아니며, 최종 gate는 log append 이후 한 번만 돌리는 것을 기본값으로 한다.

### 2. 작업을 세 가지 surface 중 하나로 분류한다
- `content ingest/query`: `wiki/`, `system/`, `raw/`, `system/system-raw-registry.md`, `system/system-log.md`를 직접 다루는 full-vault maintenance
- `planning/handoff`: bundle, seed, validation, run ledger처럼 knowledge layer와 operational layer 사이를 다루는 path
- `system_mechanism`: `ops/**`, `tests/**`, run artifact, append-only `system/system-log.md`를 바꾸는 runtime improvement path

### 3. content ingest는 raw-first 순서를 따른다
- 대상 raw를 먼저 확인하고, markdown raw면 필요할 때만 `raw_markdown_normalize` contract 안에서 정리한다.
- 그 다음 source page, 관련 concept/synthesis, router, raw registry, system log 순서로 mutation을 이어 간다.
- generated artifact가 필요하면 `raw_registry_export`나 manifest 갱신까지 마친 뒤, `system-log`가 포함된 최종 tree에서 lint/eval/stage2를 1회 실행한다.
- query나 synthesis를 먼저 늘리기보다, mature route에 흡수되는지 source-only seed로 남는지부터 판단하는 편이 현재 corpus 운영 원칙과 맞다.

### 4. system_mechanism은 bounded write surface만 건드린다
- mechanism work의 기본 surface는 `ops/**`, `tests/**`, run artifact, append-only `system/system-log.md`다.
- `raw/`, `wiki/`, 일반 `system/` page는 자동 개선 루프의 write boundary 밖으로 두는 편이 현재 contract에 맞다.
- 이 경로에서는 `run_mechanism_experiment`나 `auto_improve_loop`를 써도 되지만, focused test와 repo-health green을 먼저 확보하는 쪽이 안전하다. 수동 closeout에서는 log append가 필요한 경우 먼저 log를 남기고, 그 뒤 최종 repo-health gate를 실행한다.

### 5. planning/handoff는 wiki와 bundle의 경계를 유지한다
- wiki는 knowledge memory이고, planning bundle은 frozen operational commitment다.
- ambiguous request를 다룰 때만 planning gate를 세게 쓰고, 단순 corpus maintenance까지 bundle로 끌고 가지 않는 편이 운영 마찰을 줄인다.
- 현재 quickstart는 planning harness를 무조건 먼저 돌리라는 뜻이 아니라, `질문이 모호하고 handoff가 중요한 경우`에만 그 경로를 명시적으로 고르라는 뜻이다.

### 6. historical bootstrap note는 archive로만 본다
- 2026-04-12 onboarding note는 초기 package 상태를 이해하는 데는 여전히 유용하다.
- 다만 현재 quickstart를 대신하지는 않으므로, 필요할 때만 historical rationale로 참고하는 편이 맞다.

## Decision / takeaway
현재 가장 안전한 시작 순서는 아래다.
1. `system-index`와 `ops/README.md`로 현재 control surface를 확인한다.
2. 필요하면 lint/eval/stage2를 baseline으로 돌려 green starting point인지 본다.
3. 작업이 `content ingest/query`, `planning/handoff`, `system_mechanism` 중 어디인지 먼저 분류한다.
4. content면 raw-first corpus mutation, mechanism이면 bounded write surface와 focused test, planning이면 bundle/freeze 경로를 따른다.
5. router/registry/generated artifact와 `system-log`까지 먼저 갱신한 뒤, 최종 lint/eval/stage2를 1회 실행한다.
6. historical bootstrap note는 현재 quickstart가 아니라 archive context로만 참고한다.

## Follow-up questions
- 지금 하려는 작업은 content ingest인지, system mechanism인지, planning/handoff인지?
- current green baseline 위에서 작은 단일 mutation으로 끝낼 수 있는가, 아니면 별도 run artifact가 필요한가?

## Related pages
- [[system-index]]
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[synthesis--stage1-planning-harness-bridge]]
- [[concept--planning-gates]]
- [[concept--artifact-contracts]]
- [Historical bootstrap note: Recommended Next Actions 2026-04-12](../external-reports/query--recommended-next-actions-2026-04-12.md)

## Source trace
- `AGENTS.md`
- `AGENTS.local.md`
- `ops/README.md`
- `system/system-index.md`
- `system/system-log.md`
- `system/synthesis--llm-wiki-self-improvement-architecture.md`
- `system/synthesis--stage1-planning-harness-bridge.md`
