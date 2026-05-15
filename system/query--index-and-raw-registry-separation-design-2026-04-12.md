---
title: "Index and Raw Registry Separation Design 2026-04-12"
page_type: "query"
corpus: "system"
created: "2026-04-12"
aliases:
  - "query--index-and-raw-registry-separation-design-2026-04-12"
tags:
  - "corpus/system"
  - "type/query"
---

# query--index-and-raw-registry-separation-design-2026-04-12

## Question
`system/system-index.md`와 raw registry의 역할을 어떻게 분리하는 것이 가장 좋은가?

## Short answer
권장 설계는 **router / summary-registry / corpus router / family shard / machine-readable export**의 5층 분리다. `system/system-index.md`는 탐색 시작점으로, `system/system-raw-registry.md`는 canonical summary router로, `system/system-raw-registry/wiki.md`는 wiki inventory corpus router로, 큰 family는 `system/system-raw-registry/wiki/coffee.md`, `system/system-raw-registry/wiki/middle-east.md`, `system/system-raw-registry/wiki/middle-east-followups.md`, `system/system-raw-registry/wiki/global-policy-and-market-seeds.md`, `system/system-raw-registry/wiki/ai-capability.md`, `system/system-raw-registry/wiki/ai-compute-control.md`, `system/system-raw-registry/wiki/ai-execution.md`, `system/system-raw-registry/wiki/europe-tech-sovereignty.md` 같은 second-order shard로, `system/system-raw-registry/system.md`는 system corpus detail shard로, `ops/raw-registry.json`은 lint와 자동화를 위한 derived export로 두는 구성이 가장 안정적이다.

## Evidence considered
- [[concept--artifact-contracts]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--cross-reference-maintenance]]
- [[concept--anti-slop-wiki-governance]]
- [[lint--initial-review-2026-04-12]]

## Analysis
### 1. 왜 분리가 필요한가
기존 `system/system-index.md`가 query router와 raw registration ledger를 함께 맡으면, 라우팅 비용과 inventory 유지 비용이 같이 커진다. 이 문제는 formatting noise가 아니라 역할 과적재 문제로 보는 편이 맞다.

### 2. 각 artifact의 책임
#### `system/system-index.md`
- 사람이 먼저 읽는 system router
- canonical page, latest query, lint artifact 안내
- raw registry 전체를 다시 적는 장소는 아님

#### `system/system-raw-registry.md`
- `raw/` 등록 상태의 canonical human-readable summary router
- count, contract, shard pointer 보관
- raw-path lint와 ingest 추적의 entry source를 어디서 봐야 하는지 알려 주는 진입점

#### `system/system-raw-registry/wiki.md`
- wiki corpus inventory의 corpus router
- direct entry를 유지하되, line pressure가 큰 family는 second-order shard로 내리는 진입점
- 현재 second-order shard는 `system/system-raw-registry/wiki/coffee.md`, `system/system-raw-registry/wiki/middle-east.md`, `system/system-raw-registry/wiki/middle-east-followups.md`, `system/system-raw-registry/wiki/global-policy-and-market-seeds.md`, `system/system-raw-registry/wiki/ai-capability.md`, `system/system-raw-registry/wiki/ai-compute-control.md`, `system/system-raw-registry/wiki/ai-execution.md`, `system/system-raw-registry/wiki/europe-tech-sovereignty.md`

#### `system/system-raw-registry/wiki/coffee.md`, `system/system-raw-registry/wiki/middle-east.md`, `system/system-raw-registry/wiki/middle-east-followups.md`, `system/system-raw-registry/wiki/global-policy-and-market-seeds.md`, `system/system-raw-registry/wiki/ai-capability.md`, `system/system-raw-registry/wiki/ai-compute-control.md`, `system/system-raw-registry/wiki/ai-execution.md`, `system/system-raw-registry/wiki/europe-tech-sovereignty.md`
- wiki corpus 안의 large family를 위한 second-order detail shard
- corpus-map이나 synthesis 경계가 이미 분명한 cluster를 page pressure에서 분리하는 용도

#### `system/system-raw-registry/system.md`
- system corpus detailed registry shard
- `registry_id`, `storage path`, `display path`, `title`, `type`, `corpus`, `topic family`, `topic subfamily`, `target page`, `status` 보관
- packaging 차이와 사람용 label을 분리하기 위한 상세 inventory 층

#### `ops/raw-registry.json`
- registry의 deterministic derived export
- lint, diff, report generation 같은 자동화 입력

### 3. 운영 변화
#### ingest
1. raw 추가
2. source / concept / synthesis 갱신
3. 적절한 shard page에 raw entry를 추가
4. `system/system-raw-registry.md` summary/router를 갱신
5. `wiki` family가 이미 크면 `system/system-raw-registry/wiki.md` 아래 second-order shard로 바로 넣는다
6. `system/system-index.md`는 summary와 pointer만 갱신
7. `ops/raw-registry.json` regenerate
8. `system/system-log.md` append

#### query
1. 먼저 `system/system-index.md`를 읽는다.
2. 관련 canonical page를 읽는다.
3. raw registration 맥락이 필요할 때만 `system/system-raw-registry.md`를 본다.
4. 실제 entry detail이 필요하면 corpus router에서 family shard까지 내려간다.

#### lint
- raw path mismatch와 unregistered raw file은 shard detail과 실제 `raw/` inventory를 preflight/lint로 함께 판단한다.
- shard 이후 review candidate는 단일 entry count보다 shard line count, backlog, topic-family concentration, 그리고 필요 시 family-level second-order shard pressure를 우선 본다.
- index는 registry detail 때문에 길어지지 않게 유지한다.

### 4. 구현 요지
- index에는 `Registered raw summary`와 pointer만 남긴다.
- summary registry는 count와 contract만 유지한다.
- raw registry detail은 corpus router와 필요한 family shard로 내린다.
- machine-readable export와 preflight는 summary+shard에서만 파생한다.
- `ops/manifest.json` 같은 다른 artifact에 registry 역할을 섞지 않는다.

## Decision / takeaway
다음 설계 결정을 권장한다.
1. `system/system-index.md`는 router로 고정
2. `system/system-raw-registry.md`는 summary router로 유지
3. `system/system-raw-registry/wiki.md`는 corpus router/direct shard로 유지하고, 큰 family는 `system/system-raw-registry/wiki/coffee.md`, `system/system-raw-registry/wiki/middle-east.md`, `system/system-raw-registry/wiki/middle-east-followups.md`, `system/system-raw-registry/wiki/global-policy-and-market-seeds.md`, `system/system-raw-registry/wiki/ai-capability.md`, `system/system-raw-registry/wiki/ai-compute-control.md`, `system/system-raw-registry/wiki/ai-execution.md`, `system/system-raw-registry/wiki/europe-tech-sovereignty.md` 같은 second-order page로 내린다
4. `system/system-raw-registry/system.md`는 system human-readable detail shard로 유지
5. `ops/raw-registry.json`과 preflight를 summary+shard에서 파생
6. lint의 raw-path registration checks는 shard detail 기준으로 전환
7. index의 raw summary는 counts + latest additions만 유지

이 방향이면 index의 탐색성, raw registry의 완전성, automation의 견고함을 동시에 확보할 수 있다.

## Follow-up questions
- `ops/raw-registry.json`을 lint가 직접 읽게 할지, raw-registry markdown을 parse한 뒤 export만 별도 저장할지?

## Related pages
- [[system-index]]
- [[system-raw-registry]]
- [[concept--artifact-contracts]]
- [[concept--cross-reference-maintenance]]
- [[lint--initial-review-2026-04-12]]

## Source trace
- `AGENTS.md`
- `system/system-index.md`
- `system/concept--artifact-contracts.md`
- `system/concept--trace-store-and-run-ledger.md`
- `system/concept--anti-slop-wiki-governance.md`
- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/scripts/wiki_lint.py`
- `system/system-raw-registry/wiki.md`
- `system/system-raw-registry/wiki/ai-capability.md`
- `system/system-raw-registry/wiki/ai-compute-control.md`
- `system/system-raw-registry/wiki/ai-execution.md`
- `system/system-raw-registry/wiki/coffee.md`
- `system/system-raw-registry/wiki/europe-tech-sovereignty.md`
- `system/system-raw-registry/wiki/global-policy-and-market-seeds.md`
- `system/system-raw-registry/wiki/middle-east-followups.md`
- `system/system-raw-registry/wiki/middle-east.md`
