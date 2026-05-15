---
title: "AI Compute Control"
page_type: "concept"
corpus: "wiki"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--ai-compute-control"
tags:
  - "corpus/wiki"
  - "type/concept"
---

# concept--ai-compute-control

## Summary
AI compute control은 모델 품질 자체보다 `누가 계산 자원 접근권과 조달 경로를 잠그는가`를 설명하는 개념이다. 장기 silicon alliance, sovereign procurement, export-control perimeter, license review, local substitution, scarcity pass-through는 모두 이 통제권을 다른 층위에서 보여 준다.

## Why it matters here
현재 `wiki`의 AI infra cluster는 execution surface, physical bottleneck, market rerating, compute control이 섞이면 quickly broad해진다. 이 concept는 [[concept--ai-compute-infrastructure-buildout-stack]] 안에서 `누가 access gate를 쥐는가`만 좁게 맡는다.

## Main body
### 계약과 alliance 차원의 통제
AI compute control은 먼저 장기 계약과 alliance에서 드러난다. hyperscaler와 silicon vendor가 multi-year 공급 계약으로 rail을 잠그면, 특정 모델 회사나 cloud 고객이 쓸 수 있는 compute path도 함께 사실상 고정된다.

### sovereign procurement 차원의 통제
둘째는 국가·공공 조달과 strategic asset ownership이다. 공공 GPU 조달, 외국계 CSP의 정책 시장 진입 여부, AIDC 특별법처럼 permitting과 power rule을 바꾸는 제도, SK AI data center처럼 private-capital consortium이 지분과 운영권을 나누는 deal은 `누가 국가 단위 compute access를 설계하는가`를 가른다. 이 층에서는 기술보다 procurement rule, policy market entry, build-out permitting, GP/LP ownership split이 중요해진다.

### policy perimeter와 license architecture도 같은 질문의 일부다
셋째는 export-control perimeter와 license review다. advanced chip parameter rule, diversion guidance, case-by-case license architecture는 국경을 넘는 compute access를 어떤 조건으로 허용하거나 차단할지 결정한다. [[synthesis--ai-compute-control-us-china-geopolitical-choke-2026-04-18]]는 이 층을 US-China geopolitical choke의 second-order synthesis로 좁혀, policy perimeter가 local substitution과 ally supplier exposure로 번지는 경로를 맡는다.

### local substitution과 scarcity pass-through
넷째는 policy perimeter가 만든 반작용과 scarcity price다. export-control은 상대의 access를 막지만, 동시에 local chip vendor share를 키울 수 있다. capacity가 모자라면 GPU rental inflation, 장기계약, service rationing, product prioritization으로 부족분이 전가된다.

### physical bottleneck은 인접 렌즈로 분리한다
전력, grid, interconnection, switchgear, memory, component, equipment capacity는 compute access의 현실 조건이지만, 1차 질문이 `무엇이 실제 build-out 속도를 막는가`라면 [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]가 더 정확하다.

export rule, sovereign procurement, Chinese substitution을 통해 compute access gate가 어디서 생기는지 설명했다. Google-Marvell inference TPU source는 그 gate가 이제 allied design partnership와 inference deployment rail을 누가 묶는가의 문제로도 이동하고 있음을 보여 준다.

## Scope boundaries
이 concept는 `누가 capacity와 조달 경로를 장악하는가`를 묻는 데 쓴다. 그래서 AI-RAN, KV cache efficiency, HBM bypass처럼 실행 위치나 runtime efficiency가 중심인 기사에는 과하게 붙이지 않는 편이 좋다.

반대로 장기 alliance, sovereign GPU procurement, policy-market entry, export-control perimeter, license review, local substitution, scarcity pass-through가 핵심이면 이 concept를 먼저 여는 편이 맞다. 핵심 질문은 `어디서 돌리는가`나 `무엇이 막는가`가 아니라 `누가 접근권을 쥐는가`다.

## Examples and non-examples
example은 Broadcom-Google custom chip alliance, 한국 공공 GPU 조달전, AIDC 특별법, 미국 chip export controls, H200 license review, 중국 local AI chip share 상승처럼 장기 계약이나 정책 rule이 compute access를 사실상 재배분하는 기사다.

non-example은 AI-RAN, TriAttention, HBM bypass처럼 실행 surface나 runtime design을 직접 설명하는 기사, 그리고 large-load tariff, interconnection queue, switchgear slot reservation처럼 물리 병목 자체가 1차 질문인 기사다. compute economics에 간접 영향은 주지만, 1차 질문이 통제권이나 procurement가 아니면 각각 execution surface나 physical bottleneck route가 우선이다.

## How to reuse this concept
후속 source를 읽을 때는 먼저 `누가 계약을 묶는가`, `누가 공공 조달 rule을 설계하는가`, `누가 license나 export-control gate를 설계하는가`, `부족한 access가 누구에게 가격·계약 페널티로 전가되는가`를 보면 된다. 이 질문들이 함께 등장하면 AI compute control concept를 붙이는 편이 유용하다.

새 synthesis에서 이 concept를 재사용할 때는 `silicon alliance`, `sovereign procurement`, `policy perimeter`, `local substitution`, `scarcity pass-through` 중 어느 층을 다루는지 함께 적어 두면 future session이 같은 축 안의 하위 차이를 더 빨리 파악할 수 있다.

## Related pages
- [[index]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[concept--ai-compute-infrastructure-buildout-stack]]
- [[synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13]]
- [[synthesis--ai-compute-control-us-china-geopolitical-choke-2026-04-18]]
- [[synthesis--ai-physical-buildout-bottlenecks-and-supplier-leverage-2026-04-18]]
- [[synthesis--ai-infrastructure-rerating-power-bottlenecks-and-transition-risk-2026-04-14]]
- [[source--broadcom-google-custom-ai-chip-alliance-2026-04-13]]
- [[source--korea-aidc-special-act-and-power-permitting-2026-04-15]]
- [[source--korea-public-ai-gpu-tender-and-cloud-sovereignty-2026-04-13]]
- [[source--sk-ai-data-center-private-capital-and-strategic-asset-control-2026-04-18]]
- [[source--us-chip-export-controls-prc-background-2026-04-13]]
- [[source--us-ai-diffusion-rule-rescission-and-chip-export-reset-2026-04-13]]
- [[source--us-h200-license-review-policy-for-china-2026-04-13]]
- [[source--ai-memory-boom-and-supply-constraints-2026-04-13]]
- [[source--samsung-electro-mechanics-ai-server-components-upcycle-2026-04-13]]
- [[query--raw-intake-absorption-decisions-2026-04-22]]
- [[source--google-marvell-inference-tpu-collaboration-2026-04-21]]
- [[source--google-marvell-dual-ai-chip-plans-2026-04-21]]

## Open questions
- hyperscaler alliance와 sovereign procurement 가운데 어느 층이 장기적으로 compute access를 더 강하게 재배분하는가?
- memory와 component bottleneck은 contract power를 상쇄할 만큼 강한 제약으로 남는가?

## Source trace
- `raw/web-snapshots/Broadcom signs long-term deal to develop Google’s custom AI chips.md`
- `raw/web-snapshots/유미's 픽 2조 GPU 사업 오늘 마감…네이버·삼성 양강 속 AWS 참전하나.md`
- `raw/web-snapshots/BIS updated public information page on export controls imposed on advanced computing and semiconductor manufacturing items to the People’s Republic of China (PRC).md`
- `raw/web-snapshots/Department of Commerce Announces Rescission of Biden-Era Artificial Intelligence Diffusion Rule, Strengthens Chip-Related Export Controls.md`
- `raw/web-snapshots/Department of Commerce Revises License Review Policy for Semiconductors Exported to China.md`
- `raw/web-snapshots/배경훈 약속한 'AI 방주' AIDC 특별법 7부 능선 넘었다.md`
- `raw/web-snapshots/'5부 능선' 넘은 AI데이터센터 특별법…기후부와 전력 특례 조율 '쟁점'.md`
- `system/system-raw-registry.md`
- `wiki/synthesis--ai-compute-control-and-sovereign-procurement-2026-04-13.md`
- `wiki/query--raw-intake-absorption-decisions-2026-04-22.md`
- `raw/web-snapshots/'탈 엔비디아'…구글, 마벨과 신규 AI 추론 TPU 공동 개발 협의.md`
- `raw/web-snapshots/구글, 마벨과 AI 칩 2종 개발 논의 중...추론 수요 확대 대비.md`
