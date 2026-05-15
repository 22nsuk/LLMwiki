---
title: "Coffee Water Chemistry"
page_type: "concept"
corpus: "wiki"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--coffee-water-chemistry"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--coffee-water-chemistry

## Summary
coffee water chemistry는 brew water를 단순한 중성 용매가 아니라 `cation specificity`, `alkalinity / buffering`, `hardness`, `TDS`, `brew-method ratio`, `scale risk`가 함께 작동하는 extraction lever로 읽는 개념이다.

## Why it matters here
기존 [[concept--coffee-brew-chemistry]]는 발효, roast, water, brew temperature를 한 route로 묶었다. 그러나 water source가 이미 dissolved cation mechanism과 practical alkalinity guide로 나뉘어 있어, 후속 질문에서 `TDS가 높으면 좋은가`, `Mg와 Ca는 어떻게 다른가`, `filter와 espresso 물을 같이 써도 되는가` 같은 질문을 더 좁게 받을 anchor가 필요하다.

## Main body
### Cation specificity is not the same as total dissolved solids
[[source--dissolved-cations-and-coffee-extraction-2026-04-13]]는 Na+, Mg2+, Ca2+가 coffee acids, caffeine, eugenol 같은 대표 분자와 다르게 상호작용할 수 있음을 보여 준다. 따라서 water recipe는 TDS 총량만이 아니라 어떤 ion species가 어떤 compound extraction을 밀어 주는지의 문제다.

### Alkalinity is a buffering budget
[[source--water-acidity-and-brew-method-recipes-2026-04-13]]는 pH보다 alkalinity와 beverage ratio를 더 실무적인 축으로 둔다. 같은 물이라도 filter와 espresso는 coffee acid 대비 buffering capacity가 다르게 작동하므로, 산미 체감과 scale risk가 method별로 달라질 수 있다.

### Hardness, alkalinity, and machine safety must be separated
경도는 주로 Ca/Mg 계열 mineral load와 연결되고, alkalinity는 bicarbonate buffering과 연결된다. 둘은 sensory balance와 scale risk에 서로 다른 방식으로 개입한다. 현재 corpus는 universal target ppm을 canonical rule로 고정하기보다, `경도`, `알칼리도`, `TDS`, `pH`, `brew ratio`, `scale risk`를 분리해서 읽는 기준을 세우는 데 강하다.

## Scope boundaries
- 이 concept는 water mineral composition과 buffering logic을 다룬다.
- espresso flow, grind distribution, bed geometry가 핵심이면 [[concept--coffee-extraction-and-brew-control]]가 우선이다.
- fermentation, roast, volatile profile이 핵심이면 [[concept--coffee-brew-chemistry]] 또는 [[concept--coffee-fermentation-processing]]이 우선이다.
- 현재 corpus만으로 SCA-style target range를 universal prescription처럼 고정하지 않는다.

## Examples and non-examples
- example: Mg2+, Ca2+, Na+가 coffee compounds와 다르게 결합한다는 논문은 water chemistry anchor다.
- example: filter와 espresso에서 alkalinity가 다르게 체감된다는 practical article은 water chemistry bridge다.
- non-example: 단순히 "물 온도를 바꿨다"는 brew recipe는 water chemistry가 아니라 extraction control일 수 있다.
- non-example: 특정 bottled water ranking은 source trace와 chemistry decomposition 없이는 이 concept의 대표 사례가 아니다.

## How to reuse this concept
- water 관련 질문이 들어오면 먼저 `TDS`, `hardness`, `alkalinity`, `pH`, `brew method`, `scale risk` 중 어느 변수가 핵심인지 나눈다.
- sensory claim은 cation specificity와 buffering claim으로 분리해 source trace를 붙인다.
- 후속 water source가 들어오면 target ppm보다 먼저 어떤 measurement axis를 보강하는지 태깅한다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[concept--coffee-brew-chemistry]]
- [[concept--coffee-extraction-and-brew-control]]
- [[synthesis--coffee-brew-chemistry-and-processing-2026-04-13]]
- [[source--dissolved-cations-and-coffee-extraction-2026-04-13]]
- [[source--water-acidity-and-brew-method-recipes-2026-04-13]]
- [[source--science-behind-good-cup-of-coffee-2026-04-13]]

## Open questions
- water target range를 canonical하게 다루려면 어떤 additional source를 ingest해야 하는가?
- cation specificity와 alkalinity buffering을 하나의 water concept 안에 계속 묶을지, practical recipe가 더 쌓이면 분리할지?

## Source trace
- `raw/the-role-of-dissolved-cations-in-coffee-extraction.pdf`
- `raw/web-snapshots/Water and Coffee Acidity How to Adapt Your Water for Different Extraction Methods - 25 Magazine, Issue 9.md`
- `wiki/concept--coffee-brew-chemistry.md`
- `wiki/synthesis--coffee-brew-chemistry-and-processing-2026-04-13.md`
