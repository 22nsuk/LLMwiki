---
title: "Coffee extraction kinetics in a well mixed system"
page_type: "source"
corpus: "wiki"
registry_id: "R-017"
raw_path: "raw/s13362-016-0024-6.pdf"
source_type: "domain-research-paper"
research_mode: "model"
domain: "coffee-extraction-kinetics"
created: "2026-04-13"
aliases:
  - "source--coffee-extraction-kinetics-in-well-mixed-system-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/source"
  - "research/model"
---

# source--coffee-extraction-kinetics-in-well-mixed-system-2026-04-13

## Title
Coffee extraction kinetics in a well mixed system

## Source
- `raw/s13362-016-0024-6.pdf`

## Type
domain-research-paper

## Summary
이 논문은 roasted and ground coffee extraction을 설명하는 기존 double porosity model을 well-mixed dilute suspension 조건에서 asymptotic solution으로 단순화한다. 저자들은 packed bed와 다른 잘 섞인 시스템에서 dominant mechanism이 무엇인지 분리해 설명한다.

## Why it matters
coffee extraction model은 method-specific이어야 한다는 점을 잘 보여 주는 source다. 동일한 extraction problem도 packed bed가 아니라 well-mixed system으로 가면 지배 메커니즘과 해석 방식이 달라진다.

## Research frame
**Design / scope**  
이 논문은 기존 double porosity model을 well-mixed dilute suspension 조건에 맞춰 asymptotic solution으로 단순화하는 model paper다. 중심 질문은 extraction 일반론이 아니라 `잘 섞인 시스템에서 무엇이 지배 메커니즘인가`다.

**What it establishes**  
이 source가 세우는 것은 packed bed와 well-mixed extraction을 같은 intuition으로 읽으면 안 된다는 점이다. 동일한 coffee extraction problem도 system geometry와 mixing condition이 달라지면 해석해야 할 변수층이 달라진다.

**Transfer limits**  
이 논문은 mechanism localization에는 강하지만 drip bed나 espresso puck을 직접 설명하지 않는다. 따라서 universal extraction law보다 immersion-type model family를 이해하는 anchor로 재사용하는 편이 더 정확하다.

## Key points
- 논문은 기존 extraction model을 dilute suspension, well-mixed system 조건으로 단순화해 해석한다.
- packed bed와 well-mixed extraction은 같은 공정이 아니며, transport와 dissolution의 중요도도 달라진다.
- asymptotic solution은 복잡한 full model을 method-specific intuition으로 바꾸는 데 유용하다.
- full model이 주로 수치해에 의존하는 상황에서, 이 논문은 dominant mechanism을 더 읽기 쉬운 형태로 꺼내려는 시도다.

## Limitations / caveats
- well-mixed system 결과를 그대로 espresso나 drip packed bed에 적용하면 오해가 생길 수 있다.
- 이 논문은 direct sensory result보다 model simplification과 mechanism localization에 초점이 있다.

## What this source adds to the corpus
이 source는 extraction cluster에서 `well-mixed system`을 packed bed와 분리해 읽게 만드는 기준점이다. coffee extraction을 하나의 보편 법칙으로 뭉개지 않고, geometry와 mixing condition에 따라 지배 메커니즘이 달라진다는 점을 corpus 안에서 선명하게 만든다.

또한 immersion 계열 source와 함께 읽을 때 이 문서는 `모델을 얼마나 단순화해도 핵심 메커니즘을 잃지 않는가`를 보여 주는 출발점이 된다. extraction model을 brew method별 family로 나누어 읽는 습관을 만드는 데 유용하다.

## How strong is the evidence
증거 강도는 strong for model framing, moderate for direct recipe transfer로 보는 편이 맞다. mechanism을 localize하는 데는 강하지만, actual brewing preference나 practical parameter choice를 직접 세우는 문서는 아니다.

따라서 future session은 이 문서를 `well-mixed extraction을 어떤 구조로 읽을 것인가`를 정하는 anchor로 재사용하는 편이 좋다. recipe recommendation이나 sensory prediction은 다른 실험 source와 함께 읽는 것이 안전하다.

## What this source does not establish
이 문서는 espresso puck이나 drip bed의 extraction logic를 직접 설명하지 않는다. 또한 어떤 immersion recipe가 실제로 가장 맛있는가를 정하는 sensory evidence도 제공하지 않는다.

즉 이 source는 `system geometry가 중요하다`를 세우는 모델 anchor이지, cross-method universal recipe guide는 아니다.

## Related pages
- [[index]]
- [[query--coffee-science-corpus-map-2026-04-13]]
- [[concept--coffee-extraction-and-brew-control]]
- [[synthesis--coffee-extraction-models-and-brew-control-2026-04-13]]
- [[source--coffee-bed-extraction-uniformity-modeling-2026-04-13]]
- [[source--full-immersion-coffee-desorption-model-2026-04-13]]

## Open questions
- well-mixed extraction model은 cupping bowl이나 immersion brew의 일부 조건을 얼마나 잘 설명하는가?
- packed bed와 well-mixed system을 잇는 intermediate model이 필요한가?

## Source trace
- `raw/s13362-016-0024-6.pdf`
- `system/system-raw-registry.md`
- `wiki/synthesis--coffee-extraction-models-and-brew-control-2026-04-13.md`
