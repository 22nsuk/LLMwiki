---
title: "Talk Less, Verify More: Improving LLM Assistants with Semantic Checks and Execution Feedback"
page_type: "source"
corpus: "system"
registry_id: "R-026"
raw_path: "raw/2601.00224v2.pdf"
source_type: "research-paper"
domain: "semantic-verification-and-execution-feedback"
created: "2026-04-13"
aliases:
  - "source--semantic-checks-and-execution-feedback-for-llm-assistants"
tags:
  - "corpus/system"
  - "type/source"
---

# source--semantic-checks-and-execution-feedback-for-llm-assistants

## Title
Talk Less, Verify More: Improving LLM Assistants with Semantic Checks and Execution Feedback

## Source
- `raw/2601.00224v2.pdf`

## Type
research-paper

## Summary
이 논문은 LLM assistant가 자연어 질의를 코드로 바꾼 뒤 바로 답을 내놓는 선형 파이프라인 대신, **semantic check(Q*)**와 **execution-grounded feedback(Feedback+)**를 loop 안에 넣어 사용자에게 가기 전 검증을 수행해야 한다고 주장한다. 핵심은 “사용자가 나중에 확인하는 것”을 줄이고, assistant가 **의도 정합성과 실행 가능성**을 먼저 검사하게 만드는 것이다.

## Why it matters
현재 system corpus는 binary eval, Stage 2 eval, promotion gate를 통해 deterministic check surface를 강화해 왔지만, assistant loop 안에 semantic verification과 execution feedback를 어떻게 배치할지 설명하는 external research anchor는 얇았다. 이 논문은 `binary eval over vibes`를 단순 offline grading 습관이 아니라 **assistant-internal verification design**으로 확장해서 보게 만든다.

## Key points
- Q*는 생성된 code를 다시 자연어로 reverse translate한 뒤 원래 질의와 semantic alignment를 비교한다.
- Feedback+는 실행 결과와 error surface를 다음 round prompt에 직접 넣어 code를 수정하게 한다.
- Spider, Bird, GSM8K 실험에서 Feedback+가 대체로 가장 강했고, Q*는 structured SQL류에는 유효하지만 stepwise logic이 중요한 문제에서는 한계가 있었다.
- 저자들은 semantic matching 자체보다 reverse translation fidelity가 더 큰 병목이라고 해석한다.
- verification을 user-side burden이 아니라 assistant-side design requirement로 재정의한다.
- runtime cost는 올라가지만, poor candidate를 빨리 거르는 효과 때문에 overall completion time을 줄일 수 있다고 주장한다.

## Limitations / caveats
- 실험은 enterprise assistant generality보다 text-to-SQL / math-code benchmark에 더 가깝다.
- Q*는 semantic alignment를 보강하지만, step-by-step reasoning correctness를 완전히 보장하지는 못한다.
- reverse translation과 critic prompt 품질에 결과가 민감하다.

## Related pages
- [[source--openai-evaluation-best-practices]]
- [[concept--binary-evals]]
- [[concept--trace-store-and-run-ledger]]
- [[concept--self-improving-wiki-loop]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Open questions
- 이 repo에서 semantic verification을 model-based advisory check로 둘지, deterministic Stage 2 gate로 더 밀어 넣을지?
- execution feedback는 현재 lint/eval/promotion artifact와 어떻게 가장 자연스럽게 연결되는가?
- reverse translation 같은 semantic check는 언제 useful한 safety layer이고, 언제 prompt noise만 늘리는가?

## Source trace
- `raw/2601.00224v2.pdf`
