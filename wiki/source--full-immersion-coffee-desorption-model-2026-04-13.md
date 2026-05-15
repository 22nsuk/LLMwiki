---
title: "An equilibrium desorption model for the strength and extraction yield of full immersion brewed coffee"
page_type: "source"
corpus: "wiki"
registry_id: "R-020"
raw_path: "raw/s41598-021-85787-1.pdf"
source_type: "domain-research-paper"
research_mode: "model"
domain: "immersion-brew-extraction"
created: "2026-04-13"
aliases:
  - "source--full-immersion-coffee-desorption-model-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/source"
  - "research/model"
---

# source--full-immersion-coffee-desorption-model-2026-04-13

## Title
An equilibrium desorption model for the strength and extraction yield of full immersion brewed coffee

## Source
- `raw/s41598-021-85787-1.pdf`

## Type
domain-research-paper

## Summary
이 논문은 full immersion coffee에서 TDS와 extraction yield를 설명하는 pseudo-equilibrium desorption model을 제안한다. 저자들은 이 모델이 brew ratio에 따른 TDS 변화를 설명하면서도, extraction yield는 상당히 넓은 조건에서 약 21% 근처로 유지될 수 있다고 보고한다.

## Why it matters
immersion brew를 packed bed intuition으로만 읽지 않게 해 주는 대표 source다. equilibrium/desorption model이 method-specific control logic를 제공한다.

## Research frame
**Design / scope**  
이 논문은 full immersion brewed coffee의 strength와 extraction yield를 설명하기 위해 pseudo-equilibrium desorption model을 제안하는 model paper다. 중심 질문은 packed bed intuition이 아니라 immersion-specific equilibrium logic가 얼마나 설명력이 있는가다.

**What it establishes**  
이 source가 세우는 것은 immersion brew에서 TDS와 extraction yield가 brew ratio 및 retained brew 문제와 함께 해석돼야 하며, extraction yield가 비교적 넓은 조건에서 비슷한 수준에 머물 수 있다는 점이다. 즉 immersion control logic는 packed bed와 다르다는 신호를 준다.

**Transfer limits**  
이 model은 full immersion에 잘 맞지만 packed bed나 high-pressure extraction을 직접 설명하지 않는다. 따라서 universal extraction law보다 immersion-specific anchor로 읽는 편이 정확하고, actual recipe choice는 sensory source와 함께 봐야 한다.

## Key points
- 모델은 TDS가 water/coffee mass brew ratio에 대체로 inverse하게 반응한다고 예측한다.
- extraction yield는 equilibrium에서 brew ratio와 비교적 독립적일 수 있다는 결과가 제시된다.
- 저자들은 grind size, roast level, brew temperature에 대해 K 값이 크게 변하지 않는다고 본다.
- 논문은 moist grounds 안에 남은 brew 때문에 oven-drying 기반 extraction 측정이 true value를 과소평가할 수 있다고 지적한다.

## Limitations / caveats
- pseudo-equilibrium approach는 full immersion에 잘 맞지만, packed bed나 high-pressure extraction을 직접 설명하지는 않는다.
- extraction yield 측정 방법과 moist grounds retained brew 문제를 함께 고려해야 한다.

## What this source adds to the corpus
이 source는 immersion extraction cluster에서 가장 명확한 method-specific model anchor 중 하나다. packed bed intuition과 분리된 equilibrium/desorption logic를 세워 주기 때문에, immersion brew를 독립적인 control family로 읽게 만든다.

또한 well-mixed kinetics source와 함께 읽으면 immersion 계열 모델 안에서도 `mechanism 단순화`와 `equilibrium framing`이 어떻게 다른지 비교할 수 있게 해 준다.

## How strong is the evidence
증거 강도는 strong for model framing, moderate for recipe transfer다. immersion-specific logic를 비교적 선명하게 세우지만, 실제 practical brewing choice는 sensory source와 결합해 읽어야 한다.

따라서 이 문서는 `immersion brew를 어떤 모델로 읽을 것인가`를 정하는 데는 강하고, 세부 recipe prescription을 직접 주는 문서로는 제한적이다.

## What this source does not establish
이 문서는 drip이나 espresso의 extraction logic를 설명하지 않는다. 또한 immersion recipe 간 taste preference 우위를 직접 확정하는 sensory evidence도 아니다.

즉 이 source는 model anchor이지, final brewing preference guide는 아니다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[concept--coffee-extraction-and-brew-control]]
- [[synthesis--coffee-extraction-models-and-brew-control-2026-04-13]]
- [[source--coffee-extraction-kinetics-in-well-mixed-system-2026-04-13]]
- [[source--full-immersion-brew-temperature-and-flavor-over-time-2026-04-13]]

## Open questions
- equilibrium desorption model은 immersion methods 간 recipe transfer에 얼마나 유용한가?
- practical brewing에서 true extraction yield 측정은 어떤 방식으로 보정해야 하는가?

## Source trace
- `raw/s41598-021-85787-1.pdf`
- `system/system-raw-registry.md`
- `wiki/synthesis--coffee-extraction-models-and-brew-control-2026-04-13.md`
