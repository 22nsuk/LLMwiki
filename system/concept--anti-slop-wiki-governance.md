---
title: "Anti Slop Wiki Governance"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-14"
aliases:
  - "concept--anti-slop-wiki-governance"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--anti-slop-wiki-governance

## Summary
anti-slop wiki governance는 wiki가 반복 편집될수록 생기는 구조적 열화를 통제하는 규칙 묶음이다. code benchmark의 slop를 그대로 복사하는 것이 아니라, wiki에 맞는 **document-level structural discipline**으로 번역하는 것이 핵심이다.

## Why it matters here
현재 초안은 시작점으로 아주 좋지만, canonical page가 늘어나면 duplicate synthesis, weak trace, orphan page, placeholder sprawl, oversized page 같은 문서형 slop가 생길 가능성이 크다. 이것을 조기에 제어해야 위키가 “메모덤프”가 아니라 knowledge runtime으로 남는다.

## Main body
### wiki의 대표적 slop 형태
- 같은 주제를 다른 synthesis page에서 반복 정리
- raw path mismatch
- source trace 없는 assertions
- related pages 섹션이 비어 있는 isolated page
- 질문은 많은데 decision이 없는 요약성 문서
- page 하나가 여러 질문을 섞어 과도하게 비대해짐

### 대응 원칙
- update canonical page before creating new page
- broken link는 fail, orphan page는 warn
- required heading과 source trace는 gate로 강제
- placeholder는 backlog나 open questions에만 국한
- 큰 page는 split review 대상으로 표시
- query artifact를 재사용 가치 기준으로 승격

### prompt-only intervention이 아닌 구조 intervention
SlopCodeBench의 시사점은 “좋은 프롬프트”만으로는 저하 속도를 멈추기 어렵다는 것이다. wiki에서도 template, schema, lint, signoff, mutation unit이 함께 있어야 한다.

### long-horizon guard와의 경계
anti-slop governance는 어떤 상태가 문서형 slop인지 이름 붙이는 taxonomy다. [[concept--wiki-failure-mode-taxonomy]]는 이 문서형 slop를 structural, routing/provenance, content quality, mechanism/process family로 더 세분한다. 반면 [[concept--long-horizon-quality-guard]]는 그 slop가 여러 ingest, lint, eval, mechanism run을 거치며 증가하는지 보는 trend/cadence layer다. 즉 이 문서는 failure mode를 정의하고, long-horizon guard는 refactor trigger와 debt budget을 결정한다.

## Scope boundaries
- 이 개념은 wiki 문서 구조와 운영 열화를 다룬다.
- 개별 domain claim의 진위 판정이나 source 내용 자체의 품질 평가는 이 개념의 직접 범위가 아니다.
- style polish나 문장 미세수정보다, duplicate synthesis·weak trace·router drift 같은 구조 문제를 먼저 본다.

## Examples and non-examples
- example: 같은 질문을 여러 synthesis가 중복 정리하는 상태를 structural slop로 본다.
- example: `Source trace` 없이 단정 서술만 남는 page를 governance failure로 본다.
- non-example: 새 raw cluster가 들어와 기존 synthesis를 둘로 나누는 것은 page sprawl이 아니라 정당한 refactor일 수 있다.
- non-example: `Open questions`에 명시적으로 남긴 미해결점은 uncontrolled placeholder sprawl과 다르다.

## How to reuse this concept
- 새 page를 만들기 전, 기존 canonical page를 두껍게 갱신하는 편이 더 나은지 판단할 때 이 개념을 기준점으로 쓴다.
- lint나 review candidate를 읽을 때는 “이 문제가 routing/trace/duplication 차원의 slop인가”를 먼저 분류한다.
- mechanism improvement를 설계할 때는 prompt 수정부터 보지 말고 policy/template/script 같은 구조 intervention을 먼저 검토한다.

## Related pages
- [[source--slopcodebench]]
- [[concept--cross-reference-maintenance]]
- [[concept--binary-evals]]
- [[concept--wiki-failure-mode-taxonomy]]
- [[concept--long-horizon-quality-guard]]
- [[lint--initial-review-2026-04-12]]

## Open questions
- duplicate synthesis를 탐지하는 가장 가벼운 휴리스틱은 무엇인가?
- page length / heading count / link graph를 어떤 refactor trigger로 조합할 것인가?
- 어떤 slop signal을 long-horizon quality guard의 first-class trend metric으로 승격할 것인가?

## Source trace
- `raw/2603.24755v1.pdf`
- `raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md`
- `ops/policies/wiki-maintainer-policy.yaml`
