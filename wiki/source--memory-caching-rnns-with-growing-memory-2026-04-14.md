---
title: "Memory Caching: RNNs with Growing Memory"
page_type: "source"
corpus: "wiki"
registry_id: "W-096"
raw_path: "raw/Memory Caching_ RNNs with Growing Memory.pdf"
source_type: "domain-research-paper"
research_mode: "model"
domain: "recurrent-memory-scaling-for-long-context"
created: "2026-04-14"
aliases:
  - "source--memory-caching-rnns-with-growing-memory-2026-04-14"
tags:
  - "corpus/wiki"
  - "research/model"
  - "type/source"
---

# source--memory-caching-rnns-with-growing-memory-2026-04-14

## Title
Memory Caching: RNNs with Growing Memory

## Source
- `raw/Memory Caching_ RNNs with Growing Memory.pdf`

## Type
domain-research-paper

## Research frame
- design / scope: 이 논문은 recurrent model의 hidden-state checkpoint를 cache하는 `Memory Caching (MC)` 기법을 제안하고, language modeling과 long-context understanding에서 transformer 및 기존 recurrent baseline과 비교한다.
- what it establishes: recurrent architecture도 memory state checkpoint를 누적하면 고정 메모리 병목을 완화하며, long-context recall-intensive task에서 transformer와의 격차를 줄일 수 있음을 보인다.
- transfer limits: arXiv 단계의 modeling paper라서 production serving stack 통합 비용, latency profile, large-scale deployment 안정성은 별도 검증이 필요하다.

## Summary
이 논문은 fixed-size memory 때문에 recall-intensive task에서 transformer보다 약하다고 여겨진 recurrent model에 `growing memory`를 부여하는 간단한 route를 제안한다. 핵심은 hidden state checkpoint를 cache해 sequence length와 함께 effective memory capacity가 늘어나게 만드는 것이다. 저자들은 이를 통해 standard RNN의 `O(L)` memory behavior와 transformer attention의 `O(L^2)` growing memory 사이를 잇는 중간 지대를 만들 수 있다고 주장한다. 현재 corpus의 runtime efficiency 축이 KV cache compression headline에 기울어 있는 만큼, 이 source는 `compression`이 아니라 `recurrent memory scaling`이라는 대안을 제공한다.

## Why it matters
AI runtime efficiency를 단순히 KV cache를 얼마나 잘 압축하느냐로만 읽으면, transformer stack을 유지한 채 절약하는 방법만 보게 된다. 이 논문은 아예 recurrent route를 다시 강화해 `fixed-memory weakness`를 줄이는 방향도 실행 가능한 경쟁 축임을 보여 준다.

## What this source adds to the corpus
- execution/runtime cluster에 `recurrent-memory scaling`이라는 독립 설계군을 추가한다.
- TriAttention, TurboQuant, Attention Matching처럼 transformer-side optimization 기사와 다른 비교축을 만든다.
- HBM 부족을 `압축`만이 아니라 `model family 선택과 memory growth 설계`의 문제로 다시 읽게 해 준다.

## How strong is the evidence
증거 강도는 promising but early로 보는 편이 맞다. long-context와 recall task에서 recurrent baseline 대비 개선은 분명하지만, transformer를 production scale에서 대체할 만큼 충분한지까지는 아직 열려 있다.

## Key points
- Memory Caching은 hidden-state checkpoint를 저장해 recurrent model의 effective memory capacity를 sequence length와 함께 늘리려 한다.
- 저자들은 gated aggregation과 sparse selective mechanism을 포함한 여러 MC variant를 제안한다.
- 논문 초록 기준으로 language modeling과 long-context understanding task에서 recurrent model 성능이 개선되고, recall task에서 transformer와의 격차를 줄였다고 보고한다.
- framing 자체가 `fixed memory vs growing memory`를 연속선으로 다루기 때문에, recurrent model을 transformer의 완전한 반대편이 아니라 trade-off point로 본다.
- 이 route는 runtime memory pressure와 quadratic attention cost를 동시에 문제 삼는 현재 infra discourse와 잘 맞물린다.

## What this source does not establish
이 논문은 transformer가 long-context task에서 이미 가진 정확도 우위를 뒤집었다고 말하지 않는다. 또한 실제 serving latency, engineering complexity, cache management overhead를 production 수준에서 해결했다고 증명하지도 않는다.

## Limitations / caveats
- arXiv preprint라 peer-reviewed canonical result로 고정해 읽기엔 이르다.
- abstract 수준에서 확인되는 개선은 benchmark setup와 baseline 선택에 민감할 수 있다.
- hidden-state cache 관리가 실제 시스템에서 얼마나 복잡한지는 논문 외부 자료가 더 필요하다.

## Related pages
- [[index]]
- [[concept--ai-ran]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]
- [[source--google-turboquant-kv-cache-compression-2026-04-13]]
- [[source--mit-attention-matching-kv-cache-compression-2026-04-13]]
- [[source--nvidia-triattention-kv-cache-efficiency-2026-04-13]]
- [[source--hbm-challengers-and-ai-memory-architecture-race-2026-04-13]]
## Open questions
- recurrent-memory scaling은 실제 serving stack에서 transformer-side KV compression보다 구현 복잡도 대비 효용이 큰가?
- hidden-state checkpoint caching이 agentic long-running workload에서 어떤 latency/accuracy trade-off를 보이는가?

## Source trace
- `raw/Memory Caching_ RNNs with Growing Memory.pdf`
- `system/system-raw-registry.md`
- `wiki/synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13.md`
