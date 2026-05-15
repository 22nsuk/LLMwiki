---
title: "Uneven Extraction in Coffee Brewing"
page_type: "source"
corpus: "wiki"
registry_id: "R-022"
raw_path: "raw/2206.12373v2.pdf"
source_type: "domain-research-paper"
research_mode: "model"
domain: "coffee-extraction-nonuniformity"
created: "2026-04-13"
aliases:
  - "source--uneven-extraction-in-coffee-brewing-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/source"
  - "research/model"
---

# source--uneven-extraction-in-coffee-brewing-2026-04-13

## Title
Uneven Extraction in Coffee Brewing

## Source
- `raw/2206.12373v2.pdf`

## Type
domain-research-paper

## Summary
이 논문은 grind를 더 곱게 하면 extraction이 계속 올라갈 것이라는 단순 직관이 실제로는 깨질 수 있다고 보고, 두 개의 유로가 경쟁하는 low-dimensional pathway model로 그 이유를 설명한다. 핵심 주장은 아주 미세한 grind 구간에서는 porosity와 permeability의 작은 차이가 flow와 extraction의 positive feedback으로 증폭되어, bed 일부만 과도하게 추출되고 다른 부분은 덜 참여하는 `uneven extraction` 상태가 생길 수 있다는 것이다.

## Why it matters
현재 coffee extraction corpus에는 espresso modeling과 porous-bed CFD source가 이미 있지만, `왜 finer grind가 오히려 extraction drop을 만들 수 있는가`를 직접 다루는 bridge source는 없었다. 이 논문은 control chart 언어와 packed-bed nonuniformity 사이를 잇는 설명층을 추가한다.

## Research frame
**Design / scope**  
이 연구는 espresso 및 다른 brewing method에서 관찰된 non-monotonic extraction 현상을 설명하기 위해 두 개의 가능한 flow path를 가진 단순화 모델을 제안한다. 실험 결과를 직접 크게 확장하기보다, nonuniform extraction hypothesis가 어떤 메커니즘으로 가능한지를 수학적으로 보여 주는 데 초점을 둔다.

**What it establishes**  
이 source가 확실하게 세우는 것은 fine grind 영역에서 extraction 감소를 단순 clogging 가정 없이도 `flow-extraction feedback`으로 설명할 수 있다는 점이다. 작은 porosity/permeability imbalance가 시간이 지나며 증폭될 수 있고, 이 과정이 uneven extraction과 extraction yield peak를 만들 수 있다는 메커니즘을 제시한다.

**Transfer limits**  
모델은 intentionally low-dimensional이며 실제 coffee bed의 모든 geometry, fines migration, particle-size distribution을 그대로 복제하지 않는다. 따라서 이 결과는 full physical description보다 `왜 nonuniformity가 핵심 변수인가`를 보여 주는 mechanism source로 쓰는 편이 맞다.

## Key points
- finer grind below a critical threshold can reduce extraction because flow becomes uneven rather than uniformly slower.
- the model treats the coffee bed as two competing pathways whose permeability evolves with extraction.
- extraction increases porosity and permeability, which can reinforce early flow imbalances instead of smoothing them out.
- the paper explains why a simple `smaller particle -> more extraction` rule can fail in espresso-like systems.
- this mechanism is relevant beyond espresso because similar peaked extraction trends are observed in other brewing methods too.

## Limitations / caveats
- the model is simplified and does not fully represent real coffee-bed geometry or multimodal particle distributions.
- it is strongest as a mechanism explanation, not as a direct recipe optimizer for baristas.
- practical variables like puck prep, declumping, and grinder workflow still require companion sources to interpret fully.

## What this source adds to the corpus
이 source는 extraction cluster 안에서 `nonuniformity mechanism anchor` 역할을 한다. `Systematically Improving Espresso`가 현상을 보여 주고 CFD uniformity paper가 packed bed structure를 정리한다면, 이 논문은 둘 사이에서 왜 fine grind가 역효과를 낼 수 있는지를 더 직접적으로 설명한다.

즉 future session이 extraction paper를 볼 때 `flow rate`, `geometry`, `equilibrium model`과 별개로 `feedback-driven uneven extraction`이라는 독립된 해석 층을 붙일 수 있게 만든다.

## How strong is the evidence
증거 강도는 medium-to-strong mechanism evidence로 보는 편이 좋다. 실제 brewing experiment 하나를 통째로 대체하지는 않지만, observed anomaly를 설명하는 명확한 수학적 가설을 제공하고 기존 espresso literature와도 잘 맞물린다.

특히 corpus 관점에서는 recipe tip보다 `왜 같은 extraction 언어가 실제 bed 안에서는 쉽게 깨지는가`를 설명하는 reusable source라는 점이 강점이다.

## What this source does not establish
이 논문은 특정 grinder setting, temperature, recipe가 항상 더 낫다는 실무 규칙을 직접 주지 않는다. 또한 fines migration, declumping tool, RDT 같은 workflow intervention이 이 메커니즘을 얼마나 줄일 수 있는지도 단독으로는 확정하지 않는다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[concept--coffee-extraction-and-brew-control]]
- [[synthesis--coffee-extraction-models-and-brew-control-2026-04-13]]
- [[source--espresso-modeling-and-extraction-variation-2026-04-13]]
- [[source--coffee-bed-extraction-uniformity-modeling-2026-04-13]]

## Open questions
- 실제 espresso workflow에서 uneven extraction signal을 가장 먼저 보여 주는 측정치는 shot time, EY, TDS, puck imaging 중 무엇인가?
- fines migration과 declumping intervention을 넣으면 이 논문의 feedback mechanism이 얼마나 약해지는가?

## Source trace
- `raw/2206.12373v2.pdf`
- `system/system-raw-registry.md`
- `wiki/concept--coffee-extraction-and-brew-control.md`
- `wiki/synthesis--coffee-extraction-models-and-brew-control-2026-04-13.md`
