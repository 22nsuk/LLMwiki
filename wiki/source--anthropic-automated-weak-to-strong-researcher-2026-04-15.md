---
title: "Automated Weak-to-Strong Researcher"
page_type: "source"
corpus: "wiki"
registry_id: "W-120"
raw_path: "raw/web-snapshots/Automated Weak-to-Strong Researcher.md"
source_type: "domain-web-article"
domain: "ai-automated-alignment-research-and-weak-to-strong-supervision"
created: "2026-04-15"
aliases:
  - "source--anthropic-automated-weak-to-strong-researcher-2026-04-15"
tags:
  - "corpus/wiki"
  - "type/source"
---

# source--anthropic-automated-weak-to-strong-researcher-2026-04-15

## Title
Automated Weak-to-Strong Researcher

## Source
- `raw/web-snapshots/Automated Weak-to-Strong Researcher.md`

## Type
domain-web-article

## Summary
Anthropic의 이 글은 Claude 기반 Automated Alignment Researcher(AAR) 팀이 `weak-to-strong supervision`이라는 outcome-gradable research problem에서 아이디어 제안, 실험 실행, 결과 해석, 반복 개선을 자율적으로 수행했다고 주장한다. 글에 따르면 9개의 AAR가 약 800 cumulative hours 동안 작업해 held-out test set 기준 `PGR 0.97`에 도달했고, 이는 저자 두 명이 7일 동안 prior method를 튜닝해 얻은 `0.23`보다 크게 높다. 핵심은 이 문서가 단순 전망이나 벤더 benchmark가 아니라, `automated research가 특정 형태의 연구 문제에서는 이미 실용적일 수 있다`는 직접 실험형 capability claim을 내놓는다는 점이다.

## Why it matters
현재 AI capability corpus는 vendor benchmark, executive vision, critique, long-horizon failure signal에 강하지만, `모델이 실제 연구 과정을 얼마나 자동화할 수 있는가`를 직접 다루는 source는 얕았다. 이 문서는 automated research claim을 `막연한 전망`이 아니라 outcome-gradable task 위의 실행 사례로 끌어내려, capability validation route의 증거 층을 한 단계 더 촘촘하게 만든다.

## Key points
- Anthropic는 독립 sandbox에서 병렬로 돌아가는 AAR 팀이 아이디어 제안, 코드 작성, 실험 실행, 결과 해석, 동료 간 정보 공유를 수행했다고 설명한다.
- 문제 설정은 weak teacher와 strong student 사이의 성능 격차를 회복하는 weak-to-strong supervision이며, 평가 지표는 held-out test set의 `performance gap recovered (PGR)`다.
- 글에 따르면 AAR는 chat preference dataset에서 `PGR 0.97`에 도달했고, 수동 튜닝 prior-method baseline `0.23`를 크게 웃돌았다.
- 총 작업량은 `800 cumulative hours` across `9 AARs`, 비용은 대략 `18,000달러`와 `AAR-hour당 22달러` 수준으로 제시된다.
- Anthropic는 weak-to-strong supervision sandbox, dataset, baseline code를 공개한다고 적어, 적어도 artifact surface는 vendor blog 평균보다 두껍다.

## Limitations / caveats
- 벤더가 직접 작성한 연구 소개 글이라 task framing과 성공 지표 선택에 vendor bias가 들어갈 수 있다.
- weak-to-strong supervision은 outcome-gradable problem이라, 더 모호한 open-ended research 전반으로 일반화하기에는 무리가 있다.
- 보고된 수치는 독립 재현 결과가 아니라 저자 실험에 기반하므로, 동일 비용과 시간 대비 재현성을 별도로 확인해야 한다.
- raw capture에는 base64 이미지 blob이 크게 포함돼 있어, 본문 해석은 텍스트 주장과 수치 중심으로 제한하는 편이 안전하다.

## Related pages
- [[index]]
- [[query--news-snapshot-roundup-2026-04-12]]
- [[concept--ai-capability-claims-verification]]
- [[synthesis--ai-capability-claims-and-validation-gap-2026-04-12]]
- [[source--anthropic-advisor-strategy-2026-04-13]]
- [[source--openai-research-intern-and-continual-learning-2026-04-12]]
- [[source--ai-kelly-bench-and-long-horizon-failure-2026-04-13]]

## Open questions
- outcome-gradable research problem에서의 automated success가 더 모호한 alignment research나 empirical science task로 얼마나 옮겨가는가?
- AAR의 성능 개선은 모델 능력 자체, sandbox 설계, parallelism, evaluation loop 중 어디에서 가장 크게 오는가?
- 공개된 sandbox와 code를 기준으로 third-party reproduction이 어느 정도까지 가능한가?

## Source trace
- `raw/web-snapshots/Automated Weak-to-Strong Researcher.md`
- `system/system-raw-registry.md`
- `wiki/concept--ai-capability-claims-verification.md`
- `wiki/synthesis--ai-capability-claims-and-validation-gap-2026-04-12.md`
