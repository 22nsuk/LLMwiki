---
title: "Binary Evals"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--binary-evals"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--binary-evals

## Summary
binary eval은 quality judgment를 yes/no 질문으로 고정하는 방식이다. scale이나 vibe보다 signal이 안정적이고, keep/discard loop에 바로 연결하기 쉽다.

## Why it matters here
LLM Wiki의 자기개선은 “더 좋아 보인다”가 아니라 “broken link가 사라졌는가”, “source trace가 존재하는가”, “required headings가 채워졌는가” 같은 **deterministic 또는 near-deterministic 질문**으로 측정되어야 한다.

## Main body
### 장점
- score variance가 낮다.
- mutation 전후 비교가 간단하다.
- log, TSV, dashboard와 결합하기 쉽다.
- future agent가 과거 실험을 이해하기 쉽다.

### 주의점
- eval이 너무 많으면 gaming risk가 커진다.
- 중복 eval은 같은 실패를 두 번 세게 한다.
- 너무 좁은 eval은 이상한 최적화를 유도한다.
- 측정 불가능한 subjective eval은 agent가 거의 항상 통과시킨다.

### wiki용 기본 eval 후보
- required sections present
- source trace present
- broken-link free
- at least two related links
- no unresolved placeholder
- synthesis ends in operational takeaway
- continuous evaluation should re-run these checks on every meaningful repo change

### assistant-internal verification으로의 확장
binary eval은 꼭 offline lint checklist만 뜻하지 않는다. `semantic check`나 `execution feedback`처럼 assistant loop 안에서 후보를 되돌려 보는 방식도 결국 **yes/no에 가까운 검증 surface**로 환원될 수 있다. 이 repo의 Stage 2 eval이나 promotion gate도 같은 방향으로, output이 그럴듯한지보다 계약과 역할을 통과하는지 먼저 묻는 쪽이 자연스럽다.

## Scope boundaries
- 이 개념은 promotion/gating judgment를 yes/no 질문으로 고정하는 방법을 다룬다.
- exploratory note나 초기 브레인스토밍까지 모두 binary 형식으로 강제하자는 뜻은 아니다.
- human signoff가 필요한 고위험 결정까지 완전히 대체하는 개념도 아니다.

## Examples and non-examples
- example: `broken_link_free`, `required_sections_present`, `declared_source_count_matches_evidence`는 binary eval이다.
- example: “broad synthesis가 boundary section을 모두 갖췄는가” 같은 질문도 binary eval이다.
- non-example: “문서가 좀 더 좋아 보인다”는 binary eval이 아니다.
- non-example: 서로 다른 실패를 같은 점수 축에 섞어 한 번에 감으로 판단하는 방식은 binary eval discipline과 거리가 있다.

## How to reuse this concept
- 새 quality gate를 추가할 때는 먼저 질문을 one-bit 형태로 다시 쓸 수 있는지 본다.
- mechanism experiment를 설계할 때는 baseline/candidate 모두에 같은 eval을 재실행해 keep/discard 판단에 사용한다.
- subjective review가 필요하더라도 최종 승격 판정은 가능한 한 explicit fail/pass surface로 내린다.

## Related pages
- [[source--autoresearch-skill-repo]]
- [[source--openai-evaluation-best-practices]]
- [[source--semantic-checks-and-execution-feedback-for-llm-assistants]]
- [[concept--planning-gates]]
- [[concept--self-improving-wiki-loop]]
- `ops/evals/wiki-quality-evals.md`

## Open questions
- 어떤 eval은 deterministic parser로, 어떤 eval은 model judge로 보조할지?
- vault-level score와 page-level score의 비중을 어떻게 둘지?

## Source trace
- `raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md`
- `raw/web-snapshots/Evaluation best practices  OpenAI API.md`
- `raw/2601.00224v2.pdf`
- `ops/evals/wiki-quality-evals.md`
