---
title: "System Raw Registry"
page_type: "registry"
corpus: "system"
created: "2026-04-12"
special_role: "raw-registry"
aliases:
  - "system-raw-registry"
tags:
  - "corpus/system"
  - "type/registry"
---

# System Raw Registry

## Summary
이 문서는 `raw/` layer 전체 inventory의 summary router다. detailed registry entries는 corpus별 shard에 두고, 이 문서는 count와 contract, pointer만 유지한다.

현재 등록 상태:
- total registered paths: `446`
- system corpus entries: `40`
- wiki corpus entries: `406`
- ingested: `446`
- registered-not-ingested: `0`

## Registry rules
- `registry_id`는 raw entry의 machine canonical key다.
- `storage path`는 현재 workspace에서 실제 파일을 resolve하는 machine locator다.
- `display path`는 사람에게 보여 주는 human-readable label이다.
- `path aliases`는 패키징 차이, 파일명 정리, zip 인코딩 차이 때문에 생긴 alternate locator를 허용하는 optional machine locator 목록이다.
- `content sha256`는 path drift가 생겼을 때 preflight inventory 대조를 돕는 optional content identity다.
- `topic family`는 shard 이후 단계에서 broad family concentration을 보는 coarse routing label이다.
- `topic subfamily`는 broad family 안에서 corpus-map이나 synthesis 경계와 맞는 finer routing label이다.
- source page frontmatter의 `raw_path`는 registry의 `storage_path` 또는 `path_aliases` 중 하나와, slash / unicode normalization 뒤에 일치해야 한다.
- `Source trace`의 backticked local file path도 같은 normalization과 alias resolution을 거쳐 실제 vault 파일로 resolve된다.
- inventory detail은 corpus별 shard에 유지한다.
- `wiki` entry inventory는 [[system-raw-registry/wiki]]에서 시작하고, 큰 family는 그 아래 second-order shard로 내려갈 수 있다.
- 현재 second-order wiki family shard는 [[system-raw-registry/wiki/coffee]], [[system-raw-registry/wiki/middle-east]], [[system-raw-registry/wiki/middle-east-followups]], [[system-raw-registry/wiki/global-policy-and-market-seeds]], [[system-raw-registry/wiki/korea-fx]], [[system-raw-registry/wiki/ai-capability]], [[system-raw-registry/wiki/ai-compute-control]], [[system-raw-registry/wiki/ai-execution]], [[system-raw-registry/wiki/europe-tech-sovereignty]], [[system-raw-registry/wiki/ai-capability-governance-intake-2026-04-21]], [[system-raw-registry/wiki/ai-infra-compute-intake-2026-04-21]], [[system-raw-registry/wiki/defense-statecraft-intake-2026-04-21]], [[system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-1]], [[system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-2]], [[system-raw-registry/wiki/health-and-science-intake-2026-04-21]], [[system-raw-registry/wiki/korea-macro-domestic-intake-2026-04-21]], [[system-raw-registry/wiki/middle-east-energy-intake-2026-04-21]]다.
- `system` entry는 [[system-raw-registry/system]]에서 관리한다.
- `ops/raw-registry.json`은 summary page와 shard pages에서 파생되는 deterministic export이며, export 시점의 실제 `raw/` inventory를 기준으로 `path_aliases`와 `content_sha256`를 자동 보강할 수 있다.
- 배포 전 inventory 대조는 `python -m ops.scripts.registry.raw_registry_preflight --vault .`로 수행하며, preflight는 `storage_path`, `path_aliases`, `content_sha256`를 함께 사용해 drift를 진단한다.

## Registry shards
- [[system-raw-registry/wiki]]
- [[system-raw-registry/wiki/ai-capability]]
- [[system-raw-registry/wiki/ai-capability-governance-intake-2026-04-21]]
- [[system-raw-registry/wiki/ai-compute-control]]
- [[system-raw-registry/wiki/ai-infra-compute-intake-2026-04-21]]
- [[system-raw-registry/wiki/ai-execution]]
- [[system-raw-registry/wiki/coffee]]
- [[system-raw-registry/wiki/defense-statecraft-intake-2026-04-21]]
- [[system-raw-registry/wiki/europe-tech-sovereignty]]
- [[system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-1]]
- [[system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-2]]
- [[system-raw-registry/wiki/global-policy-and-market-seeds]]
- [[system-raw-registry/wiki/health-and-science-intake-2026-04-21]]
- [[system-raw-registry/wiki/korea-fx]]
- [[system-raw-registry/wiki/korea-macro-domestic-intake-2026-04-21]]
- [[system-raw-registry/wiki/middle-east]]
- [[system-raw-registry/wiki/middle-east-energy-intake-2026-04-21]]
- [[system-raw-registry/wiki/middle-east-followups]]
- [[system-raw-registry/system]]

## Pending ingest
- none currently

## Related pages
- [[system-index]]
- [[index]]
- [[system-log]]
- [[system-raw-registry/wiki]]
- [[system-raw-registry/wiki/ai-capability]]
- [[system-raw-registry/wiki/ai-capability-governance-intake-2026-04-21]]
- [[system-raw-registry/wiki/ai-compute-control]]
- [[system-raw-registry/wiki/ai-infra-compute-intake-2026-04-21]]
- [[system-raw-registry/wiki/ai-execution]]
- [[system-raw-registry/wiki/coffee]]
- [[system-raw-registry/wiki/defense-statecraft-intake-2026-04-21]]
- [[system-raw-registry/wiki/europe-tech-sovereignty]]
- [[system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-1]]
- [[system-raw-registry/wiki/global-markets-misc-intake-2026-04-21-2]]
- [[system-raw-registry/wiki/global-policy-and-market-seeds]]
- [[system-raw-registry/wiki/health-and-science-intake-2026-04-21]]
- [[system-raw-registry/wiki/korea-fx]]
- [[system-raw-registry/wiki/korea-macro-domestic-intake-2026-04-21]]
- [[system-raw-registry/wiki/middle-east]]
- [[system-raw-registry/wiki/middle-east-energy-intake-2026-04-21]]
- [[system-raw-registry/wiki/middle-east-followups]]
- [[system-raw-registry/system]]
- [[query--raw-intake-roundup-2026-04-21]]
- [[query--index-and-raw-registry-separation-design-2026-04-12]]

## Source trace
- `AGENTS.md`
- `README.md`
- `ops/README.md`
- `ops/policies/wiki-maintainer-policy.yaml`
- `ops/scripts/registry/raw_registry_runtime.py`
- `ops/scripts/registry/raw_registry_export.py`
- `ops/scripts/registry/raw_registry_preflight.py`
- `system/system-index.md`
- `system/system-log.md`
- `system/system-raw-registry/wiki.md`
- `system/system-raw-registry/wiki/ai-capability.md`
- `system/system-raw-registry/wiki/ai-compute-control.md`
- `system/system-raw-registry/wiki/ai-execution.md`
- `system/system-raw-registry/wiki/coffee.md`
- `system/system-raw-registry/wiki/europe-tech-sovereignty.md`
- `system/system-raw-registry/wiki/global-policy-and-market-seeds.md`
- `system/system-raw-registry/wiki/korea-fx.md`
- `system/system-raw-registry/wiki/middle-east.md`
- `system/system-raw-registry/wiki/middle-east-followups.md`
- `system/system-raw-registry/system.md`
