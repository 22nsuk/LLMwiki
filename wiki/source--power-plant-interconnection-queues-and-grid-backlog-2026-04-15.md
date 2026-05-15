---
title: "Queued Up: 2025 Edition"
page_type: "source"
corpus: "wiki"
registry_id: "W-122"
raw_path: "raw/Queued Up 2025 Edition.pdf"
source_type: "domain-research-paper"
research_mode: "reference"
domain: "power-plant-interconnection-queues-and-grid-backlog"
created: "2026-04-15"
aliases:
  - "source--power-plant-interconnection-queues-and-grid-backlog-2026-04-15"
tags:
  - "corpus/wiki"
  - "research/reference"
  - "type/source"
---

# source--power-plant-interconnection-queues-and-grid-backlog-2026-04-15

## Title
Queued Up: 2025 Edition

## Source
- `raw/Queued Up 2025 Edition.pdf`

## Type
domain-research-paper

## Research frame
- design / scope: Berkeley Lab와 Interconnection.fyi가 2024년 말 기준 미국 bulk-power transmission interconnection queue를 집계한 annual snapshot이다.
- what it establishes: AI data-center build-out이 전력원과 grid capacity를 두고 경쟁하는 환경에서는, generator interconnection backlog와 withdrawal dynamics가 power availability ceiling을 함께 만든다는 점을 보여 준다.
- transfer limits: generation-side queue report라 data-center load interconnection 자체를 직접 다루지는 않고, queue entry가 실제 상업운전으로 이어진다는 보장도 없다.

## Summary
`Queued Up: 2025 Edition`은 미국 transmission interconnection queue가 여전히 매우 크고 느리며, reform-driven withdrawal이 커도 backlog 구조 자체는 남아 있음을 보여 준다. 보고서에 따르면 2024년 말 기준 active queue에는 약 `2,290GW` 용량이 남아 있었고, 이는 `10,303` active projects, `1,400GW` generation, `890GW` storage에 해당한다. 2024년에는 `700GW` 이상이 withdraw되고 약 `500GW`가 새로 신청돼 cumulative active volume은 전년 대비 `12%` 줄었지만, 여전히 active queue capacity는 미국 installed power plant fleet `1,320GW`의 거의 두 배 수준이다. 핵심은 AI infrastructure build-out을 뒷받침할 generation과 storage도 이미 queue congestion, withdrawal, reform transition 속에서 움직이고 있어, data-center power bottleneck은 부지와 송전선 문제가 아니라 `bulk-power project pipeline`의 속도 문제이기도 하다는 점이다.

## Why it matters
AI infra corpus에서 전력 문제는 종종 `충분한 MW를 계약할 수 있는가`로만 읽히기 쉽다. 하지만 이 보고서는 generation과 storage project가 transmission interconnection 단계에서 얼마나 오래 묶이고 얼마나 많이 중도 철회되는지를 보여 주어, `data center가 전력을 사오려는 순간 이미 upstream queue bottleneck과 경쟁하고 있다`는 점을 더 또렷하게 만든다.

## What this source adds to the corpus
- data-center power bottleneck을 발전·저장 project queue backlog와 연결하는 quantitative background를 제공한다.
- queue volume 감소가 공급 ease가 아니라 historic withdrawal과 process reform의 결과일 수 있음을 보여 준다.
- gas request 급증과 solar/storage/wind 감소를 함께 보여 주어, AI load 증가가 어떤 generation mix tension과 만나는지도 암시한다.

## How strong is the evidence
증거 강도는 strong for U.S. transmission-queue scale and trend reading이다. 매년 반복되는 공개 queue dataset 정리라 규모와 방향을 읽는 데는 유용하다. 다만 queue request가 곧 buildable supply나 data-center usable capacity를 뜻하는 것은 아니다.

## What this source does not establish
이 source는 queue backlog가 특정 AI data-center 프로젝트의 전력 조달 지연으로 정확히 얼마나 번역되는지까지 보여 주지 않는다. 또한 withdrawal이 규제 개혁의 건강한 정리 효과인지, 실제 투자 철회의 심화인지도 추가 source 없이 단정할 수 없다.

## Key points
- 2024년 말 active queue volume은 약 `2,290GW`였고, 이 중 `1,400GW`는 generation, `890GW`는 storage다.
- historic withdrawals가 크게 늘어 2024년에만 `700GW` 이상이 withdraw됐고, 새 신청은 약 `500GW`였다.
- cumulative active queue capacity는 전년 대비 `12%` 줄었지만, 여전히 U.S. installed power fleet보다 크다.
- active gas requests는 전년 대비 `72%` 증가한 `136GW`였고, solar는 `956GW`, storage는 `890GW`, wind는 `271GW`로 모두 감소했다.
- dataset 전체로는 `4,432` operational projects(`511.8GW`), `20,921` withdrawn projects(`3,924GW`)가 집계돼 queue churn이 매우 크다는 점도 드러난다.

## Limitations / caveats
- queue entry는 상업운전 보장이 아니며, withdrawn capacity가 크기 때문에 headline GW를 그대로 future supply로 읽으면 안 된다.
- generation-side queue snapshot이라, hyperscaler 부지의 local substation, distribution, tariff 문제는 별도 source가 필요하다.
- 미국 transmission provider dataset에 기반하므로 다른 국가 grid regime에 바로 일반화하긴 어렵다.

## Related pages
- [[index]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[concept--ai-compute-infrastructure-buildout-stack]]
- [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]
- [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- [[source--energy-and-ai-demand-and-data-center-power-2026-04-14]]
- [[source--large-load-electricity-rate-designs-and-data-center-tariffs-2026-04-15]]
- [[source--virginia-data-center-policy-and-local-grid-impacts-2026-04-15]]

## Open questions
- generation/storage interconnection backlog가 AI data-center build-out의 실제 commissioning delay로 얼마나 빠르게 번역되는가?
- reform-driven withdrawals는 비효율적 queue cleanup인지, 실제 supply pipeline 약화 신호인지 어떻게 구분해야 하는가?
- gas request 급증은 data-center load 증가에 대한 near-term reliability response인가, 아니면 transitional artifact인가?

## Source trace
- `raw/Queued Up 2025 Edition.pdf`
- `system/system-raw-registry.md`
- `wiki/concept--ai-compute-infrastructure-buildout-stack.md`
- `wiki/synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18.md`
- `wiki/synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14.md`
