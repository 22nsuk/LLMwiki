---
title: "Moisture-controlled triboelectrification during coffee grinding"
page_type: "source"
corpus: "wiki"
registry_id: "R-011"
raw_path: "raw/PIIS2590238523005684.pdf"
source_type: "domain-research-paper"
research_mode: "experiment"
domain: "coffee-grinding-static"
created: "2026-04-13"
aliases:
  - "source--coffee-grinding-moisture-and-triboelectrification-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/source"
  - "research/experiment"
---

# source--coffee-grinding-moisture-and-triboelectrification-2026-04-13

## Title
Moisture-controlled triboelectrification during coffee grinding

## Source
- `raw/PIIS2590238523005684.pdf`

## Type
domain-research-paper

## Summary
이 논문은 커피 분쇄 중 생기는 정전기가 roast color, grind coarseness, 특히 whole-bean coffee의 residual moisture에 따라 달라진다고 보고한다. 저자들은 moisture가 charge의 크기뿐 아니라 polarity까지 조절할 수 있다고 보며, 이 현상이 particle aggregation과 industrial-scale handling 문제에 연결된다고 설명한다.

## Why it matters
grinding static는 home barista workaround 정도로 다루기 쉽지만, 실제로는 retention, clumping, extraction uniformity를 함께 흔든다. 이 논문은 그 문제를 물리적 변수와 연결해 준다.

## Research frame
**Design / scope**  
이 논문은 coffee grinding 중 생기는 charge behavior를 roast color, grind coarseness, residual moisture 조건과 연결해 측정하는 physics-oriented experimental paper다. 중심 질문은 workflow tip이 아니라 정전기가 어떤 물리 변수에 의해 조절되는가다.

**What it establishes**  
이 source가 세우는 것은 static가 단순 nuisance가 아니라 measurable physical variable이며, moisture가 charge magnitude뿐 아니라 polarity까지 바꿀 수 있다는 점이다. 그래서 grinding static 문제를 anecdote가 아니라 mechanism으로 다루게 만든다.

**Transfer limits**  
이 논문은 charge behavior를 강하게 보여 주지만, 특정 개입이 extraction 품질을 얼마나 개선하는지는 직접 확정하지 않는다. 따라서 workflow prescription보다 `왜 static control이 필요한가`를 설명하는 mechanism anchor로 재사용하는 편이 적절하다.

## Key points
- coffee grinding에서는 triboelectrification과 fractoelectrification이 함께 정전기를 만든다.
- fine, darker roast가 더 큰 charge-to-mass ratio를 보일 수 있고, 내부 수분은 charge magnitude와 polarity를 조절한다.
- static는 particle aggregation과 discharge를 만들어 enthusiast scale과 industrial scale 모두에 문제를 만든다.
- 논문은 커피 입자의 charge 규모를 화산 plume이나 thundercloud와 비교 가능한 수준으로 제시해 물리적 중요성을 강조한다.

## Limitations / caveats
- 논문은 charge behavior를 강하게 보여 주지만, extraction 개선까지를 직접 일반화하지는 않는다.
- grinder 종류, burr geometry, workflow 차이가 실제 barista 환경에서 결과를 얼마나 바꾸는지는 별도 검증이 필요하다.

## What this source adds to the corpus
이 source는 static 문제를 barista workaround가 아니라 measurable physical variable로 바꿔 주는 anchor다. current coffee corpus에서 moisture, roast color, charge polarity를 한 구조 안에 묶어 설명하는 가장 핵심적인 source라고 볼 수 있다.

또한 RDT/AutoComb article과 연결할 때 이 문서는 `왜 개입이 필요한가`를, article은 `실무에서 어떻게 개입하는가`를 맡는다. 그래서 grinding static cluster에서는 이 논문이 mechanism anchor 역할을 한다.

## How strong is the evidence
증거 강도는 높지만 application bridge는 짧다. charge behavior와 moisture effect를 물리적으로 보여 주는 점은 강하지만, 그것이 곧바로 모든 espresso extraction 개선으로 이어진다고 일반화하긴 어렵다.

따라서 이 source는 `static가 실제 물리 변수인가`를 확인하는 데는 매우 강하고, `어떤 workflow가 최적인가`를 결정하는 데는 보조적이다. future session은 mechanism 확인에는 이 문서를, workflow 비교에는 후속 article이나 실험 source를 함께 보는 편이 좋다.

## What this source does not establish
이 문서는 RDT, AutoComb, humidity control 중 어떤 개입이 실무적으로 가장 우수한지를 직접 비교하지 않는다. 또한 static 저감이 모든 grinder와 espresso setup에서 동일한 extraction improvement로 이어진다는 점도 확정하지 않는다.

즉 이 source는 `왜 static control이 중요한가`를 세우는 mechanism anchor이지, 최종 workflow winner를 고르는 benchmark는 아니다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[concept--coffee-grinding-static-control]]
- [[synthesis--coffee-grinding-static-and-clumping-control-2026-04-13]]
- [[source--rdt-versus-autocomb-and-espresso-extraction-2026-04-13]]

## Open questions
- residual moisture를 정밀하게 조절하면 static control을 표준화할 수 있는가?
- charge polarity 차이가 실제 clumping 구조와 extraction outcome을 얼마나 바꾸는가?

## Source trace
- `raw/PIIS2590238523005684.pdf`
- `system/system-raw-registry.md`
- `wiki/synthesis--coffee-grinding-static-and-clumping-control-2026-04-13.md`
