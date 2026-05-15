---
title: "Cross Reference Maintenance"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-14"
aliases:
  - "concept--cross-reference-maintenance"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--cross-reference-maintenance

## Summary
cross-reference maintenance는 page 간 연결을 dense but useful 하게 유지하는 작업이다. 좋은 wiki는 page quality만이 아니라 **routing quality**도 관리한다.

## Why it matters here
현재 초안은 flat wiki 구조를 채택했기 때문에, 폴더가 아니라 index와 wikilink가 구조 역할을 한다. 따라서 link maintenance는 선택 사항이 아니라 핵심 운영 작업이다.

## Main body
### link가 중요한 이유
- 같은 개념을 다른 이름으로 중복 생성하는 것을 줄인다.
- 다음 세션 agent가 관련 evidence를 빠르게 순회하게 한다.
- isolated page를 줄여 재사용성을 높인다.

### 기본 규칙
- 새 page를 만들면 최소 2개 이상의 관련 page에 링크한다.
- canonical page는 역링크를 받을 수 있게 index에서도 노출한다.
- source page는 concept / synthesis로 연결하고, synthesis는 다시 source로 되돌아가야 한다.
- broken link는 fail, orphan는 warn으로 다룬다.

### flat wiki와의 관계
flat 구조에서는 폴더 taxon보다 `index.md` + prefix + wikilink graph가 정보 구조다. 링크가 약하면 flat 구조의 장점이 사라진다.

## Scope boundaries
- 이 개념은 page 간 routing과 graph 품질을 다룬다.
- full ontology 설계나 자동 분류 체계 전체를 정의하는 개념은 아니다.
- 링크 수를 늘리는 것 자체보다, future session이 실제로 순회 가능한 연결을 만드는 데 초점을 둔다.

## Examples and non-examples
- example: source page가 대응 concept와 synthesis를 모두 가리키게 만드는 것은 좋은 cross-reference maintenance다.
- example: router page가 새 canonical page를 누락 없이 노출하는 것도 이 개념에 포함된다.
- non-example: 맥락 없는 상호 링크를 장식처럼 추가하는 것은 dense but useful 연결이 아니다.
- non-example: 폴더를 새로 나누는 일은 구조 개편일 수 있지만, 그 자체가 cross-reference maintenance를 대체하지는 않는다.

## How to reuse this concept
- ingest 직후에는 새 source가 어떤 concept/synthesis/router에 연결되어야 하는지 이 개념 기준으로 점검한다.
- lint 결과에서 orphan나 missing cross-reference가 나오면 file split보다 먼저 링크 그래프 보강 가능성을 본다.
- canonical page를 만들었으면 관련 source와 synthesis에 역링크를 심어 graph 중심점으로 정착시킨다.

## Related pages
- [[concept--llm-wiki]]
- [[concept--anti-slop-wiki-governance]]
- [[lint--initial-review-2026-04-12]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Open questions
- backlink 기반 index 자동 생성이 필요한 시점은 언제인가?
- link graph 시각화를 lint pass에 포함해야 하는가?

## Source trace
- `AGENTS.md`
- `system/system-index.md`
- `ops/scripts/wiki_lint.py`
