---
title: "AI Compute Infrastructure Build-out Stack"
page_type: "concept"
corpus: "wiki"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--ai-compute-infrastructure-buildout-stack"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--ai-compute-infrastructure-buildout-stack

## Summary
AI compute infrastructure build-out stack은 같은 AI 인프라 source를 세 가지 렌즈로 나눠 읽기 위한 routing concept다. 첫째는 `access/control`: 누가 compute capacity, license, procurement gate를 잠그는가. 둘째는 `physical bottleneck`: 전력, grid, interconnection, switchgear, memory, component, equipment가 실제 build-out 속도를 어디서 막는가. 셋째는 `financing/rerating`: 시장과 credit investor가 어떤 operator, supplier, 국가 exposure를 re-rate하거나 discount하는가.

## Why it matters here
기존 [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]와 [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]는 Oracle backlog와 data-center power source를 공유하면서 overlap처럼 보이기 쉬웠다. 이 concept는 두 문서를 합쳐 거대한 synthesis로 만들지 않고, 같은 build-out chain을 `control`, `bottleneck`, `rerating` 세 질문으로 분리해 준다.

## Main body
이 concept의 본문 역할은 AI compute infra source를 하나의 거대한 theme로 흡수하지 않고, 아래 네 가지 route 중 어디에 먼저 붙일지 결정하는 것이다.

### 1. Access / control lens
핵심 질문이 `누가 capacity나 access gate를 잠그는가`라면 [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]로 보낸다. 장기 silicon alliance, sovereign GPU procurement, AIDC permitting, export-control perimeter, license review, 중국 local substitution, scarcity pass-through가 이 렌즈에 들어간다. 그중 US-China export-control과 local substitution, ally supplier exposure가 중심이면 [[synthesis--ai-compute-control-us-china-geopolitical-choke-2026-04-18]]가 더 좁은 entry point다.

### 2. Physical bottleneck lens
핵심 질문이 `무엇이 실제 build-out 속도를 막는가`라면 [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]로 보낸다. data-center power demand, tariff design, interconnection queue, local grid backlash, switchgear lead time, slot reservation, memory/component/equipment capacity가 이 렌즈에 들어간다.

### 3. Financing / rerating lens
핵심 질문이 `누가 시장에서 re-rate되거나 discount되는가`라면 [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]로 보낸다. Oracle backlog, Google-linked off-balance-sheet financing, SK AI data center private-capital consortium, Cerebras IPO, IREN transition risk, Stargate tenant substitution, SK Hynix ADR, Taiwan semiconductor market-cap rerating이 이 렌즈에 들어간다.

### 4. Neighboring but separate execution lens
AI-RAN, KV cache compression, reasoning-token efficiency, recurrent memory, HBM bypass처럼 `어디서 어떻게 더 효율적으로 돌리는가`가 핵심이면 [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]가 우선이다. 그 효율이 consumer pricing, GPU rental inflation, token budget, service rationing으로 번역되는 질문이면 [[synthesis--ai-inference-economics-and-pricing-2026-04-18]]를 함께 본다.

## Scope boundaries
이 concept의 범위는 AI compute capacity가 만들어지고, 배분되고, 금융시장에 가격화되는 stack이다. 따라서 model architecture 자체의 효율 개선, 범용 전력시장 정책, 일반 반도체 업황, 국가별 디지털 주권 의제는 primary route가 아니다.

power나 semiconductor source라도 AI data-center build-out의 속도, access, valuation에 직접 연결될 때만 이 concept로 들어온다. 연결이 약하면 sector source 또는 다른 synthesis의 Related page로만 남긴다.

## Examples and non-examples
Korea public GPU tender와 US export-control/license source는 access/control example이다. Interconnection queue, large-load tariff, switchgear lead time, memory/component capacity source는 physical bottleneck example이다. Oracle backlog, IREN transition, Google-linked off-balance-sheet financing, SK AI data center private-capital consortium, Cerebras IPO, semiconductor market-cap rerating source는 financing/rerating example이다.

KV cache compression, AI-RAN execution, recurrent memory scaling은 non-example이며 [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]로 보낸다. EU digital sovereignty와 public-sector Linux migration은 non-example이며 [[synthesis--european-tech-regulation-and-digital-sovereignty-2026-04-12]]로 보낸다.

## How to reuse this concept
새 AI infra source가 들어오면 먼저 다음 문장을 채운다. `이 source의 1차 질문은 access/control인가, physical bottleneck인가, financing/rerating인가?` 하나만 고를 수 없으면, source page의 `Why it matters`에서 primary lens와 secondary lens를 명시한다. synthesis에는 primary lens 기준으로만 흡수하고, secondary lens는 Related pages로만 남기는 편이 overlap을 줄인다.

## Related pages
- [[index]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[concept--ai-compute-control]]
- [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]
- [[synthesis--ai-compute-control-us-china-geopolitical-choke-2026-04-18]]
- [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]
- [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]
- [[synthesis--ai-inference-economics-and-pricing-2026-04-18]]

## Open questions
- Oracle backlog 같은 source는 access control보다 financing/rerating lens가 우선인가, 아니면 두 lens의 shared anchor로 계속 둘 것인가?
- memory supplier capital access는 physical bottleneck에 붙일지, financing/rerating에 붙일지 후속 source 밀도에 따라 다시 나눌 필요가 있는가?
- power bottleneck이 policy gate와 valuation gate를 동시에 만들 때 source page에서 primary lens를 어떻게 표준화할 것인가?

## Source trace
- `wiki/synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13.md`
- `wiki/synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14.md`
- `wiki/synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13.md`
- `wiki/query--news-snapshot-roundup-2026-04-12.md`
- `wiki/index.md`
- `system/system-raw-registry.md`
