---
title: "Raw Registry Wiki Direct Seed Shard Review 2026-04-16"
page_type: "lint"
corpus: "system"
maintenance_scope: "raw-registry-shard-review"
created: "2026-04-16"
aliases:
  - "lint--raw-registry-wiki-direct-seed-shard-review-2026-04-16"
tags:
  - "corpus/system"
  - "type/lint"
---

# lint--raw-registry-wiki-direct-seed-shard-review-2026-04-16

## Summary
`system/system-raw-registry/wiki.md`가 다시 `raw_registry_shard_lines_over_threshold` candidate로 올라온 뒤, top contributing direct seed families인 `market-access-and-domestic-strain`, `ai-media-gatekeeping`, `european-digital-sovereignty`를 second-order shard로 승격할지 검토했다. 결론은 세 family를 그대로 모두 shard로 뽑기보다, 즉시 적용 후보는 route-aligned `Europe tech sovereignty` shard 하나로 제한하는 편이 가장 안전하다는 것이다. 후속 적용에서 `system/system-raw-registry/wiki/europe-tech-sovereignty.md`를 만들었고, parent shard는 `527` lines에서 `469` lines로 내려갔다.

## Decision
- `market-access-and-domestic-strain`: 지금은 split하지 않는다.
- `ai-media-gatekeeping`: 지금은 split하지 않고, concept 또는 synthesis 승격을 먼저 기다린다.
- `european-digital-sovereignty`: 단독 family shard보다 `europe-tech-sovereignty` route shard로 적용했다.

## Evidence
- current parent shard: `system/system-raw-registry/wiki.md`
- pre-application parent shard lines: `527`
- post-application parent shard lines: `469`
- lint threshold: `500`
- direct entries on parent shard: `41`
- `market-access-and-domestic-strain`: `6` entries / estimated `66` entry lines
- `ai-media-gatekeeping`: `3` entries / estimated `33` entry lines
- `european-digital-sovereignty`: `3` entries / estimated `33` entry lines
- moving only `market-access-and-domestic-strain` would project the parent around `461` lines before summary adjustment.
- moving only `ai-media-gatekeeping` would project the parent around `494` lines before summary adjustment.
- moving only `european-digital-sovereignty` would project the parent around `494` lines before summary adjustment.
- moving the broader Europe route entries would project the parent around `451` lines before summary adjustment.

## Findings
### F-01 — `market-access-and-domestic-strain` solves the line count but not the retrieval shape
This family is the largest of the three candidates, so moving it would clear the line threshold most decisively. The problem is semantic shape: it currently mixes franchise sales, SpaceX IPO access, Vietnam market classification, long-term care finance, airline/holding-company liquidity stress, and airport duty-free retail pricing. That is not yet one route; it is two or three possible future routes sitting under one coarse label.

The better future split is likely `cross-market allocation / capital access` versus `domestic structural pressure`, not a direct `market-access-and-domestic-strain` registry shard.

### F-02 — `ai-media-gatekeeping` is cohesive but still a seed cluster
This family has a clean three-entry shape: AI news citation concentration, Google Search AI traffic defense, and BBC / YouTube / big-tech media governance. It is a credible future route, and moving it alone would probably bring the parent shard below the line threshold.

However, it currently lacks a canonical concept or synthesis page. Creating a registry shard before creating a knowledge anchor would make the registry more granular than the corpus routing layer. That is backwards for this vault: mature knowledge route first, registry shard second.

### F-03 — `european-digital-sovereignty` has the best shard-readiness signal, but the split should be route-aligned
The direct family has only three registry entries: France Linux migration, Interoperable Europe Act, and JRC digital sovereignty framework. By raw count alone, that is small. But these entries already sit under [[concept--digital-sovereignty-in-public-it]] and [[synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12]], which makes the route mature enough for a second-order shard.

The caution is that the actual Europe route is broader than the `european-digital-sovereignty` topic family. The current synthesis also uses [[source--tesla-fsd-netherlands-approval-2026-04-12]] and [[source--hungary-post-orban-eu-realignment-2026-04-14]]. Therefore a narrow `european-digital-sovereignty` shard would make the registry less faithful to how the corpus is queried. A better shard name would be `system/system-raw-registry/wiki/europe-tech-sovereignty.md`, with topic families recorded inside it.

### F-04 — The minimal safe application is one Europe route shard, not three new shards
Adding any second-order shard requires updating `ops/policies/wiki-maintainer-policy.yaml`, `tests/minimal_vault_runtime.py`, `system/system-raw-registry.md`, `system/system-raw-registry/wiki.md`, and derived `ops/raw-registry.json`. That contract cost is worth paying for one stable route, but not for small seed clusters that do not yet have canonical wiki anchors.

## Recommended fixes
If applying now, create a single route-aligned shard:

- path: `system/system-raw-registry/wiki/europe-tech-sovereignty.md`
- parent: [[system-raw-registry/wiki]]
- registered entries: `W-013`, `W-015`, `W-055`, `R-025`, `W-085`, `W-131`
- stable routes: [[concept--digital-sovereignty-in-public-it]], [[synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12]]
- leave `market-access-and-domestic-strain` and `ai-media-gatekeeping` on the parent shard for now.

For `market-access-and-domestic-strain`, wait until either `cross-market allocation / capital access` or `domestic structural pressure` gets a concept/synthesis anchor. For `ai-media-gatekeeping`, wait until a concept or small synthesis exists, or until the family reaches roughly `5` entries.

## Related pages
- [[system-index]]
- [[system-log]]
- [[system-raw-registry]]
- [[system-raw-registry/wiki]]
- [[system-raw-registry/wiki/europe-tech-sovereignty]]
- [[concept--digital-sovereignty-in-public-it]]
- [[synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[lint--raw-registry-wiki-ai-capability-shard-review-2026-04-16]]

## Source trace
- `ops/policies/wiki-maintainer-policy.yaml`
- `tests/minimal_vault_runtime.py`
- `ops/scripts/wiki_lint_registry_runtime.py`
- `system/system-raw-registry.md`
- `system/system-raw-registry/wiki.md`
- `system/system-raw-registry/wiki/europe-tech-sovereignty.md`
- `system/lint--raw-registry-wiki-ai-capability-shard-review-2026-04-16.md`
- `wiki/index.md`
- `wiki/query--news-snapshot-roundup-2026-04-12.md`
- `wiki/concept--digital-sovereignty-in-public-it.md`
- `wiki/synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12.md`
