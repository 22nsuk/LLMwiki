---
title: "Raw Registry Wiki Shard Line Threshold Review 2026-04-14"
page_type: "lint"
corpus: "system"
maintenance_scope: "raw-registry-shard-review"
created: "2026-04-14"
aliases:
  - "lint--raw-registry-wiki-shard-line-threshold-review-2026-04-14"
tags:
  - "corpus/system"
  - "type/lint"
---

# lint--raw-registry-wiki-shard-line-threshold-review-2026-04-14

## Summary
`system/system-raw-registry/wiki.md`의 `raw_registry_shard_lines_over_threshold` 후보를 다시 검토한 결과, 이번 후보는 단순 2줄 초과 잡음이라기보다 `ai-execution-surface-and-runtime-efficiency` family가 이미 독립 route를 갖고 있는데도 상위 shard에 직접 남아 있던 구조 신호로 보는 편이 맞았다. 따라서 상위 shard를 억지로 압축하지 않고, `ai-execution` second-order shard를 추가해 line pressure와 route clarity를 함께 개선했다.

## Findings
### F-01 — 현재 wiki shard 초과는 direct-entry 과밀보다 `mature family 미분리` 문제에 가깝다
- live lint candidate는 `system/system-raw-registry/wiki.md`가 `502` lines로 threshold `500`을 넘는다고 보고했다.
- 하지만 이 page는 직접 listed entries가 `40`건이고, family shard가 이미 `coffee`, `middle-east`, `korea-fx`, `ai-compute-control`로 나뉘어 있다.
- 즉 초과 자체는 크지 않지만, 어떤 family를 상위 shard에 계속 둘지 다시 판단할 시점이라는 신호로 읽는 편이 맞다.

### F-02 — `ai-execution-surface-and-runtime-efficiency`는 second-order shard로 빼기에 가장 자연스럽다
- lint candidate의 top contributing family 중 가장 큰 것은 `ai-execution-surface-and-runtime-efficiency`였다.
- 이 family는 `nvidia-marvell`, `triattention`, `turboquant`, `claim calibration`, `MIT attention matching`, `memory caching`, `HBM challenger`처럼 해석 surface가 이미 하나의 stable route로 묶여 있다.
- 또한 [[concept--ai-ran]]과 [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]라는 reusable route anchor가 이미 있으므로, second-order shard가 page sprawl이 아니라 retrieval 비용 절감으로 이어진다.

### F-03 — `ai-capability-and-agent-strategy`와 `market-access-and-domestic-strain`은 아직 상위 shard에 남기는 편이 낫다
- 이 둘도 top contributing family지만, 현재는 여러 seed와 cross-cutting source가 섞여 있어 second-order shard를 추가해도 아직 retrieval gain이 작다.
- `ai-capability-and-agent-strategy`는 capability claim, roadmap, orchestration, long-horizon evaluation이 같이 있고, `market-access-and-domestic-strain`도 mobility, IPO access, domestic strain이 섞여 있다.
- 따라서 이번 review에서는 `ai-execution`만 분리하고, 나머지는 후속 raw가 더 쌓일 때 다시 보는 편이 합리적이다.

### F-04 — second-order shard 추가는 registry markdown만이 아니라 policy contract도 함께 갱신해야 한다
- raw-registry runtime은 summary markdown의 링크를 동적으로 수집하지 않고, `registry_contract.raw_registry_shard_pages`와 `raw_registry_entry_page_corpus`를 official entry-page 목록으로 읽는다.
- 따라서 새 shard를 만들 때 policy contract를 같이 갱신하지 않으면 export/preflight가 새 page를 누락해 summary mismatch와 unregistered raw warning이 재발할 수 있다.

## Recommended fixes
1. `system/system-raw-registry/wiki.md`에서는 `ai-execution-surface-and-runtime-efficiency` family를 second-order shard로 승격한다.
2. 상위 shard는 여러 small family와 seed family를 담는 corpus router 역할을 유지한다.
3. 다음 review까지는 `ai-capability-and-agent-strategy`, `market-access-and-domestic-strain`의 direct-entry 증가만 watch한다.
4. 새 raw-registry shard를 추가할 때는 `ops/policies/wiki-maintainer-policy.yaml`의 special page contract와 `registry_contract` 목록도 같은 턴에 함께 갱신한다.

## Related pages
- [[system-index]]
- [[system-log]]
- [[system-raw-registry]]
- [[system-raw-registry/wiki]]
- [[system-raw-registry/wiki/ai-execution]]
- [[concept--ai-ran]]
- [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]

## Source trace
- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/scripts/wiki_lint_registry_runtime.py`
- `ops/scripts/raw_registry_runtime.py`
- `tests/test_registry_review_candidates.py`
- `system/system-raw-registry.md`
- `system/system-raw-registry/wiki.md`
- `system/system-raw-registry/wiki/ai-execution.md`
