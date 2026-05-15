---
title: "Broad Synthesis Watch Review 2026-04-14"
page_type: "lint"
corpus: "system"
maintenance_scope: "wiki-broad-synthesis-watch"
created: "2026-04-14"
aliases:
  - "lint--broad-synthesis-watch-review-2026-04-14"
tags:
  - "corpus/system"
  - "type/lint"
---

# lint--broad-synthesis-watch-review-2026-04-14

## Summary
2026-04-18 live `wiki_lint` 기준 broad synthesis watch 후보는 다섯 건이다. 예전 review의 `ai-compute-control-and-sovereign-procurement`와 `ai-infrastructure-rerating-power-bottlenecks-and-transition-risk`는 현재 후보에서 빠졌고, `european-tech-regulation-and-digital-sovereignty`가 live 후보에 남아 있다. 다섯 후보 모두 boundary section이 비어 있지 않으므로 지금 당장 split하지 않고 `watch 유지`가 맞다. 다만 follow-up source를 붙일 때는 아래 split trigger를 먼저 확인해야 한다.

## Findings
### F-01 — `middle-east-war-macro-and-market-repricing`는 가장 넓지만 아직 macro repricing lens가 살아 있다 (KEEP/WATCH, highest split pressure)
- live lint 수치상 source 13건, analysis subsection 7개, line 123으로 다섯 후보 중 가장 넓다.
- 다만 문서의 질문은 여전히 `war shock -> cross-asset repricing -> policy reaction`으로 묶이고, physical shipping layer는 `middle-east-shipping-and-energy-risk`로 명시적으로 분리되어 있다.
- 다음 split trigger는 `Fed/inflation reaction function`, `safe-haven hierarchy`, `post-ceasefire relief rally/oil trading anomaly` 중 하나가 별도 source 묶음으로 반복될 때다. 지금은 channel tagging을 강화하며 유지한다.

### F-02 — `korea-fx-liquidity-and-spot-dollar-pressure`는 source density가 높지만 하나의 FX stress model이다 (KEEP/WATCH)
- source 10건으로 넓지만, 중심 질문은 `spot pressure vs funding impairment vs buffer/toolkit`로 일관된다.
- `official stabilization tool`과 `policy reaction function`이 두꺼워지고 있으나, 아직 policy-operation shard로 떼면 현재 문서의 위기/비위기 판별력이 약해진다.
- 다음 split trigger는 국민연금, 외평채, swap line, reserve operation 같은 official tool source가 2~3건 더 쌓여 `spot pressure diagnosis`와 독립된 운영 질문을 만들 때다.

### F-03 — `middle-east-shipping-and-energy-risk`는 physical disruption boundary가 선명하다 (KEEP/WATCH)
- source 9건, line 109로 넓지만 `외교 -> 해운 심리 -> 에너지 가격 -> 조달 완충`이라는 실물 전이 사슬이 분명하다.
- macro repricing, Gulf megaproject, domestic FX channel을 제외한다고 명시되어 있어 sibling synthesis와 충돌하지 않는다.
- 다음 split trigger는 해군 운용, 보험/운임, 기뢰 제거, 우회 항로, 수입국 조달 중 하나가 독립 evidence cluster로 자랄 때다.

### F-04 — `ai-execution-surface-and-runtime-efficiency`는 mechanism family가 많지만 split trigger가 이미 잘 적혀 있다 (KEEP/WATCH)
- source 7건, analysis subsection 7개로 broadness threshold를 넘지만, 문서의 축은 `execution surface`, `runtime efficiency`, `claim calibration`, `recurrent-memory scaling`, `architecture bypass`로 정리되어 있다.
- compute access/procurement route는 `ai-compute-control-and-sovereign-procurement`, inference economics route는 `ai-inference-economics-and-pricing`으로 빠져 있어 현재 boundary가 작동한다.
- 다음 split trigger는 특히 `runtime claim calibration` source가 vendor claim과 independent critique 쌍으로 반복될 때다.

### F-05 — `european-tech-regulation-and-digital-sovereignty`는 machine-readable boundary 보강 후 watch만 남기면 된다 (KEEP/WATCH, lowest split pressure)
- source 5건인데 analysis subsection 7개라 lint watch에 걸리지만, 현재 boundary section은 `regulated product approval`, `public-sector sovereignty`, `interoperability regime`, `strategic dependency management`, `security autonomy spillover`를 잘 분리한다.
- public IT sovereignty와 broader strategic autonomy를 같은 policy tool로 취급하지 않는다고 명시되어 있어 과잉 통합 위험도 낮아졌다.
- 다음 split trigger는 `AI product governance`와 `public-sector sovereignty`가 각각 2~3건 이상 더 쌓이거나, `security autonomy spillover`가 digital route 밖의 Europe strategic-autonomy synthesis로 커질 때다.

### F-06 — 현재 필요한 것은 split이 아니라 source-routing discipline이다 (PASS)
- 다섯 후보 모두 `What this synthesis excludes`, `Tensions / contradictions`, `Implications for future ingest`를 갖고 있고 `missing_boundary_sections`가 없다.
- broadness 신호는 구조 결함이라기보다 source density와 line count에서 오는 watch signal이다.
- 다음 ingest에서는 새 source를 바로 기존 synthesis에 붙이기 전에 위 trigger 중 어느 축을 보강하는지 먼저 태깅하고, 같은 trigger가 반복될 때만 second-order shard를 만든다.

## Recommended fixes
1. 현재 live broad synthesis watch 후보 다섯 건은 모두 `watch 유지`로 둔다. 이번 라운드에서 즉시 split할 문서는 없다.
2. split pressure는 `middle-east-war-macro`가 가장 높고, 다음은 `korea-fx`와 `middle-east-shipping`이다. `ai-execution-surface`와 `european-tech-regulation`은 boundary가 충분히 선명해 낮은 우선순위로 둔다.
3. Middle East source는 `physical disruption`과 `financial repricing`을 source 단계에서 계속 분리한다. 이 discipline이 무너지면 두 synthesis가 다시 섞일 가능성이 가장 크다.
4. Korea FX source는 `spot FX demand`, `swap/funding liquidity`, `reserve/buffer`, `official stabilization tool`, `policy reaction function` 태그를 유지한다.
5. AI execution source는 `execution surface expansion`, `compression design`, `claim calibration` 중 무엇인지 먼저 적고, economics/pricing으로 직접 이어지는 경우에는 `ai-inference-economics-and-pricing` route를 우선 검토한다.
6. Europe tech source는 `regulated product approval`, `public-sector sovereignty`, `interoperability regime`, `strategic dependency management`, `security autonomy spillover` 중 하나로 먼저 라우팅한다.

## Related pages
- [[system-index]]
- [[system-log]]
- [[lint--initial-review-2026-04-12]]
- [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]
- [[synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12]]
- [[synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14]]
- [[synthesis--middle-east-shipping-and-energy-risk-2026-04-12]]
- [[synthesis--middle-east-war-macro-and-market-repricing-2026-04-13]]

## Source trace
- `ops/scripts/wiki_lint.py`
- `ops/scripts/wiki_lint_review_runtime.py`
- `ops/scripts/wiki_stage2_runtime.py`
- `tests/test_wiki_broad_synthesis_review_candidates.py`
- `system/system-log.md`
- `wiki/synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13.md`
- `wiki/synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12.md`
- `wiki/synthesis--korea-fx-liquidity-and-spot-dollar-pressure-2026-04-14.md`
- `wiki/synthesis--middle-east-shipping-and-energy-risk-2026-04-12.md`
- `wiki/synthesis--middle-east-war-macro-and-market-repricing-2026-04-13.md`
