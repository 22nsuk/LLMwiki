---
title: "Raw Registry Wiki AI Capability Shard Review 2026-04-16"
page_type: "lint"
corpus: "system"
maintenance_scope: "raw-registry-shard-review"
created: "2026-04-16"
aliases:
  - "lint--raw-registry-wiki-ai-capability-shard-review-2026-04-16"
tags:
  - "corpus/system"
  - "type/lint"
---

# lint--raw-registry-wiki-ai-capability-shard-review-2026-04-16

## Summary
`system/system-raw-registry/wiki.md`의 live `raw_registry_shard_lines_over_threshold` candidate를 다시 검토한 결과, 이번 초과는 direct entry count 자체보다 `ai-capability-and-agent-strategy` family가 이미 reusable concept/synthesis anchor를 가진 mature route인데도 상위 shard에 직접 남아 있던 구조 신호로 보는 편이 맞았다. 따라서 `ai-capability` second-order shard를 추가해 상위 router line pressure를 낮추고, capability-validation cluster를 retrieval-friendly하게 분리했다.

## Findings
### F-01 — 현재 candidate는 growth 자체보다 `mature family 미분리`에 가깝다
- live lint는 `system/system-raw-registry/wiki.md`가 `575` lines로 threshold `500`을 넘는다고 보고했다.
- 하지만 direct entry count는 `46`으로 entry threshold `60` 아래였고, line pressure의 핵심은 top-contributing family concentration이었다.
- 따라서 이번 신호는 generic trimming보다 second-order shard 적합성을 다시 보라는 구조 후보로 읽는 편이 맞다.

### F-02 — `ai-capability-and-agent-strategy`는 이제 독립 shard 이득이 충분하다
- 이 family는 `9` entries로 top contributor였고, Mythos critique, Glasswing original post, automated researcher, advisor strategy, research-roadmap reconstruction, long-horizon evaluation, policy endorsement까지 하나의 capability-validation cluster 안에서 읽히고 있다.
- 또한 [[concept--ai-capability-claims-verification]]와 [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]가 이미 canonical anchor 역할을 하고 있어, second-order shard가 page sprawl이 아니라 retrieval cost 절감으로 이어진다.

### F-03 — `market-access-and-domestic-strain`는 이번에도 상위 shard에 남기는 편이 낫다
- 같은 top contributor라도 이 family는 franchise, IPO access, market classification, domestic finance strain, airport retail pricing처럼 아직 heterogeneous seed가 섞여 있다.
- 지금 sub-shard를 만들면 family clarity보다 page proliferation이 더 커질 가능성이 높다.

### F-04 — shard 추가는 policy contract와 test fixture를 같이 갱신해야 한다
- raw-registry runtime은 `registry_contract.raw_registry_shard_pages`와 `raw_registry_entry_page_corpus`를 공식 shard surface로 읽는다.
- minimal vault test fixture도 family shard 파일 집합을 알고 있으므로, 새 shard를 추가할 때는 policy contract와 test fixture를 같은 턴에 같이 맞춰야 contract drift가 생기지 않는다.

## Recommended fixes
1. `system/system-raw-registry/wiki.md`에서 `ai-capability-and-agent-strategy` direct entries를 `system/system-raw-registry/wiki/ai-capability.md`로 승격한다.
2. 상위 `wiki` shard는 mixed seed와 smaller family를 담는 corpus router 역할을 유지한다.
3. `ops/policies/wiki-maintainer-policy.yaml`의 special page contract와 registry shard 목록을 같은 턴에 갱신한다.
4. `tests/minimal_vault_runtime.py`의 family shard fixture도 새 shard 집합에 맞게 갱신한다.

## Related pages
- [[system-index]]
- [[system-log]]
- [[system-raw-registry]]
- [[system-raw-registry/wiki]]
- [[system-raw-registry/wiki/ai-capability]]
- [[concept--ai-capability-claims-verification]]
- [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]

## Source trace
- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/scripts/wiki_lint_registry_runtime.py`
- `tests/minimal_vault_runtime.py`
- `system/system-raw-registry.md`
- `system/system-raw-registry/wiki.md`
- `system/system-raw-registry/wiki/ai-capability.md`
- `wiki/concept--ai-capability-claims-verification.md`
- `wiki/synthesis--ai-capability-claims-and-validation-gap-2026-04-12.md`
