---
title: "Coffee Science Corpus Map 2026-04-13"
page_type: "query"
corpus: "wiki"
question_scope: "coffee-science-corpus"
created: "2026-04-13"
aliases:
  - "query--coffee-science-corpus-map-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/query"
---

# query--coffee-science-corpus-map-2026-04-13

## Question
현재 등록된 coffee science raw 24건을 어떤 구조로 읽어야 하고, 어떤 질문에 어떤 page를 먼저 재사용하면 좋은가?

## Short answer
이번 batch는 크게 네 축과 하나의 agronomy/reference seed로 읽는 것이 가장 효율적이다. `sensory lexicon / flavor mapping`은 커피를 묘사하는 언어 체계를, `extraction / brew control`은 TDS·추출수율·유량·분쇄·온도 같은 공정 변수를, `grinding / static control`은 분쇄 중 정전기와 클럼핑, 분배 도구의 역할을, `brew chemistry / processing`은 발효·로스팅·온도·물·추출 시간이 화학 조성과 향미에 미치는 영향을 맡는다. WCR varieties catalog는 품종·재배·고도·병해충 저항성 reference라서 brew chemistry에 바로 흡수하지 않고 `coffee varieties / agronomy` seed로 둔다. 커피 질문이 들어오면 먼저 이 문서에서 어느 축인지 고른 뒤 해당 concept와 synthesis로 내려가는 편이 가장 빠르다.

## Evidence considered
- [[concept--coffee-sensory-lexicon]]
- [[concept--coffee-extraction-and-brew-control]]
- [[concept--coffee-grinding-static-control]]
- [[concept--coffee-brew-chemistry]]
- [[concept--coffee-water-chemistry]]
- [[concept--coffee-fermentation-processing]]
- [[synthesis--coffee-sensory-language-and-flavor-mapping-2026-04-13]]
- [[synthesis--coffee-extraction-models-and-brew-control-2026-04-13]]
- [[synthesis--coffee-grinding-static-and-clumping-control-2026-04-13]]
- [[synthesis--coffee-brew-chemistry-and-processing-2026-04-13]]

## Analysis
### 1. sensory lexicon 축은 "무슨 단어로 묘사할 것인가"를 맡는다
WCR sensory lexicon, flavor wheel redesign 논문, coffee character wheel 논문, flavor wheel poster는 커피 향미를 말할 때 어떤 용어를 쓰고 어떤 관계로 묶어야 하는지를 다룬다. 향미 vocabulary, wheel 구조, acidity·mouthfeel·aftertaste까지 넓힌 character language가 모두 이 축에 들어간다.

### 2. extraction / brew control 축은 "어떤 변수로 추출을 설명할 것인가"를 맡는다
brewing control chart, espresso modeling, uneven extraction, CFD 기반 추출 균일성, espresso kinetics, drip temperature, immersion desorption model, immersion sensory-over-time 논문은 추출을 감이 아니라 변수와 모델로 읽는 방법을 제공한다. 이 축은 strength, extraction yield, brew ratio, flow rate, particle size, geometry, brew temperature, nonuniform pathway가 각각 어디까지 중요한지 정리한다.

### 3. grinding / static 축은 "분쇄와 분배가 추출 전단에서 무엇을 바꾸는가"를 맡는다
triboelectrification 논문과 RDT vs AutoComb article은 정전기, 수분, retention, clumping, declumping tool을 한 묶음으로 읽게 만든다. 이 축은 분쇄 직후의 입자 거동이 결국 extraction uniformity에 어떻게 번역되는지 보여준다.

### 4. chemistry / processing 축은 "어떤 화학 조성과 공정이 컵에 남는가"를 맡는다
fermentation, dissolved cations, hot/cold brew chemistry, volatile compounds, cold brew extraction time, general coffee science article은 bean, roast, water ions, brew temperature, extraction time이 어떤 화합물과 감각 차이로 이어지는지를 보여준다. 이 중 water minerals/buffering은 [[concept--coffee-water-chemistry]], post-harvest fermentation은 [[concept--coffee-fermentation-processing]]가 더 좁은 entry point다.

### 5. varieties / agronomy seed는 "어떤 원재료와 재배 조건에서 시작하는가"를 맡는다
[[source--world-coffee-research-varieties-catalog-2026-04-18]]는 Arabica/Robusta 품종의 수량, 재배 고도, 영양 요구, 병해충 저항성, cup quality, climate adaptation을 catalog 형태로 제공한다. 현재 corpus의 네 stable route는 주로 컵 안의 감각·추출·화학을 다루므로, 이 catalog는 아직 새 synthesis로 승격하지 않고 cultivar/agronomy reference seed로 둔다.

## Decision / takeaway
coffee science corpus는 단일 "커피 논문 모음"이 아니라 네 개의 stable route와 하나의 agronomy seed로 읽는 것이 좋다. vocabulary가 필요하면 `coffee-sensory-lexicon`, 변수와 모델이 필요하면 `coffee-extraction-and-brew-control`, 분쇄와 정전기 질문이면 `coffee-grinding-static-control`, 화학/공정 차이면 `coffee-brew-chemistry`를 먼저 읽는다. 품종·재배 조건이 질문이면 WCR varieties catalog를 source-only reference로 본 뒤, 후속 agronomy source가 더 쌓일 때 concept 분리를 검토한다.

## Follow-up questions
- water chemistry와 mineral composition 축은 별도 concept로 분리할 만큼 source가 충분한가?
- sensory vocabulary와 extraction variable을 한 문서에서 직접 연결하는 bridge synthesis가 필요한가?
- espresso와 immersion, cold brew를 method-specific concept로 더 쪼갤 시점은 언제인가?

## Related pages
- [[index]]
- [[concept--coffee-sensory-lexicon]]
- [[concept--coffee-extraction-and-brew-control]]
- [[concept--coffee-grinding-static-control]]
- [[concept--coffee-brew-chemistry]]
- [[concept--coffee-water-chemistry]]
- [[concept--coffee-fermentation-processing]]
- [[synthesis--coffee-sensory-language-and-flavor-mapping-2026-04-13]]
- [[synthesis--coffee-extraction-models-and-brew-control-2026-04-13]]
- [[synthesis--coffee-grinding-static-and-clumping-control-2026-04-13]]
- [[synthesis--coffee-brew-chemistry-and-processing-2026-04-13]]
- [[source--world-coffee-research-varieties-catalog-2026-04-18]]

## Source trace
- `system/system-raw-registry.md`
- `wiki/index.md`
- `wiki/synthesis--coffee-sensory-language-and-flavor-mapping-2026-04-13.md`
- `wiki/synthesis--coffee-extraction-models-and-brew-control-2026-04-13.md`
- `wiki/synthesis--coffee-grinding-static-and-clumping-control-2026-04-13.md`
- `wiki/synthesis--coffee-brew-chemistry-and-processing-2026-04-13.md`
- `wiki/source--world-coffee-research-varieties-catalog-2026-04-18.md`
