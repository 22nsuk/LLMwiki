---
title: "붙이고 압축하고...HBM에 맞서는 메모리 전쟁 [김창영의 실리콘밸리Look]"
page_type: "source"
corpus: "wiki"
registry_id: "W-026"
raw_path: "raw/web-snapshots/붙이고 압축하고...HBM에 맞서는 메모리 전쟁김창영의 실리콘밸리Look.md"
source_type: "news-snapshot"
domain: "ai-memory-architecture-competition"
created: "2026-04-13"
aliases:
  - "source--hbm-challengers-and-ai-memory-architecture-race-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--hbm-challengers-and-ai-memory-architecture-race-2026-04-13

## Title
붙이고 압축하고...HBM에 맞서는 메모리 전쟁 [김창영의 실리콘밸리Look]

## Source
- `raw/web-snapshots/붙이고 압축하고...HBM에 맞서는 메모리 전쟁김창영의 실리콘밸리Look.md`

## Type
news-snapshot

## Summary
이 기사에 따르면 AI 반도체 성능 경쟁은 이제 HBM 하나로 수렴하지 않고, 온칩 SRAM, 웨이퍼스케일 메모리, KV 캐시 압축, 장기적으로는 온칩형 HBM까지 포함한 메모리 아키텍처 경쟁으로 번지고 있다. 핵심 메시지는 AI 인프라 병목의 중심이 연산보다 메모리 대역폭과 지연, 패키징 구조로 이동하면서 `HBM vs challenger` 구도가 생기고 있다는 점이다.

## Why it matters
현재 `wiki`의 AI 인프라 축은 advisor economics, AI-RAN, runtime efficiency, 메모리 공급 제약, 서버 부품 공급망까지 포괄한다. 이 문서는 그 위에 `메모리 구조 자체를 어떻게 바꿔 병목을 피할 것인가`라는 기술 축을 추가해, 공급 부족 문제를 단순 수급이 아니라 architecture competition으로도 읽게 만든다.

## Key points
- 기사에 따르면 무어의 법칙 둔화 이후 AI 칩 성능 향상의 핵심은 트랜지스터 축소보다 메모리 대역폭과 병목 해소로 이동했다.
- 엔비디아의 그록3 LPU와 세레브라스는 HBM 대신 대용량 또는 저지연 SRAM, 웨이퍼스케일 설계를 통해 다른 경로를 제시한다.
- 세레브라스는 웨이퍼를 자르지 않고 프로세서와 메모리를 함께 올리는 WSE 구조와 칩 연결 방식으로 용량 한계를 우회하려 한다.
- 구글의 TurboQuant는 KV 캐시를 강하게 압축해 메모리 사용량과 연산 비용을 줄이는 소프트웨어적 대안으로 제시된다.
- 기사 후반은 장기적으로 HBM 자체도 칩 위로 올라가는 온칩형 구조로 진화할 가능성을 언급한다.
- 전체적으로 이 문서는 AI 메모리 경쟁이 `HBM 대세` 하나가 아니라 연결, 적층, 압축, 온칩 통합이 동시에 경쟁하는 다층 구조임을 보여준다.

## Limitations / caveats
- 기사에는 기업 발표, 컨퍼런스 메시지, 과거 공개 자료가 함께 섞여 있어 실제 상용 성능과 가격 경쟁력을 직접 비교한 것은 아니다.
- 그록, 세레브라스, 구글의 기술은 각각 목표 워크로드와 구현 방식이 달라 단순 비교가 어렵다.
- 장기적으로 HBM이 칩 위에 올라갈 수 있다는 전망은 업계 관측에 가깝고, 구체적인 제품 일정으로 확인된 것은 아니다.

## Related pages
- [[index]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[source--ai-memory-boom-and-supply-constraints-2026-04-13]]
- [[source--nvidia-triattention-kv-cache-efficiency-2026-04-13]]
- [[source--samsung-electro-mechanics-ai-server-components-upcycle-2026-04-13]]
- [[synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13]]

## Open questions
- HBM 대항마로 제시되는 SRAM, 웨이퍼스케일, KV 캐시 압축 중 실제 상용 추론 비용을 가장 크게 바꾸는 것은 무엇인가?
- 메모리 architecture 경쟁은 HBM 공급 부족을 완화하는가, 아니면 다른 병목을 새로 만드는가?
- 장기적으로 온칩형 HBM이나 통합 메모리 구조가 GPU·메모리 업체의 권력 관계를 어떻게 바꾸는가?

## Source trace
- `raw/web-snapshots/붙이고 압축하고...HBM에 맞서는 메모리 전쟁김창영의 실리콘밸리Look.md`
- `system/system-raw-registry.md`
- `wiki/query--news-snapshot-roundup-2026-04-12.md`
- `wiki/synthesis--ai-execution-surface-and-runtime-efficiency-2026-04-13.md`
