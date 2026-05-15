---
title: "AI에 프리미어리그 베팅 시켜봤더니...\"대부분 파산\""
page_type: "source"
corpus: "wiki"
registry_id: "W-027"
raw_path: "raw/web-snapshots/AI에 프리미어리그 베팅 시켜봤더니…대부분 파산.md"
source_type: "news-snapshot"
domain: "ai-long-horizon-evaluation"
created: "2026-04-13"
aliases:
  - "source--ai-kelly-bench-and-long-horizon-failure-2026-04-13"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--ai-kelly-bench-and-long-horizon-failure-2026-04-13

## Title
AI에 프리미어리그 베팅 시켜봤더니..."대부분 파산"

## Source
- `raw/web-snapshots/AI에 프리미어리그 베팅 시켜봤더니…대부분 파산.md`

## Type
news-snapshot

## Summary
이 기사에 따르면 여러 frontier AI 모델을 프리미어리그 모의 베팅에 투입한 결과, 대부분이 장기적으로 손실을 보거나 파산했다. 핵심 메시지는 모델들이 전략을 설명하거나 코드로 표현할 수는 있어도, 불확실한 환경에서 장기 목표를 일관되게 수행하고 성과를 스스로 조정하는 데는 여전히 약하다는 점이다.

## Why it matters
이 문서는 AI 능력 평가가 정답형 benchmark와 코드 생성 능력에 치우칠 때 놓치기 쉬운 `장기 수행`, `지식-행동 격차`, `불확실성 하의 전략 조정` 문제를 드러낸다. 현재 `wiki`의 AI capability 검증 축을 벤더 주장 비판에서 한 걸음 더 넓혀, 실전형 장기 과업 평가까지 연결하는 source로 쓸 수 있다.

## Key points
- 기사에 따르면 KellyBench는 2023~2024 프리미어리그 시즌을 재현해 8개 AI 모델에 가상 자금을 주고 베팅 전략을 수행하게 했다.
- GPT-5.4와 Claude Opus 4.6만 세 번의 시도에서 모두 파산을 면했지만, 각각 손실을 기록했다.
- 나머지 모델들은 최소 한 번 이상 전액 손실이나 베팅 미완수로 실패했다고 소개된다.
- 연구진은 상위 모델도 전략 정교도가 만점의 3분의 1 수준에 못 미쳤다고 평가한다.
- 기사 본문은 모델들이 전략을 말로는 설명하지만 실제 행동으로는 일관되게 실행하지 못하는 `지식-행동 격차`를 강조한다.
- 결론적으로 정해진 해법이 없는 장기 목표 수행 과제에서는 현재 모델의 강점이 크게 약화된다는 메시지를 남긴다.

## Limitations / caveats
- 이 문서는 스타트업이 공개한 KellyBench 논문을 요약한 2차 기사이며, 평가 프로토콜과 재현 조건을 기사만으로 완전히 검증할 수는 없다.
- 스포츠 베팅 환경은 일반 agent 업무와 다르므로, 이 결과를 모든 장기 과업으로 그대로 일반화할 수는 없다.
- 인터넷 차단, 과거 데이터 제공, 자금 규칙 같은 세부 설정이 모델별 성과에 큰 영향을 줄 수 있다.

## Related pages
- [[index]]
- [[concept--ai-capability-claims-verification]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[source--anthropic-mythos-security-claims-critique-2026-04-12]]
- [[source--openai-research-intern-and-continual-learning-2026-04-12]]
- [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]

## Open questions
- KellyBench가 드러낸 실패는 스포츠 베팅 특수성보다 장기 불확실 과업 일반의 문제로 볼 수 있는가?
- 모델의 전략 설명 능력과 실제 장기 수행 능력 사이의 격차를 더 직접적으로 측정하는 평가는 무엇이 있는가?
- frontier model 간 장기 수행 안정성 차이는 어떤 architecture 혹은 training signal과 연결되는가?

## Source trace
- `raw/web-snapshots/AI에 프리미어리그 베팅 시켜봤더니…대부분 파산.md`
- `system/system-raw-registry.md`
- `wiki/query--news-snapshot-roundup-2026-04-12.md`
- `wiki/synthesis--ai-capability-claims-and-validation-gap-2026-04-12.md`
