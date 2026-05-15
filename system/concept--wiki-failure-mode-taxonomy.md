---
title: "Wiki Failure Mode Taxonomy"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-18"
aliases:
  - "concept--wiki-failure-mode-taxonomy"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--wiki-failure-mode-taxonomy

## Summary
wiki failure mode taxonomy는 lint/eval/stage2가 발견하는 개별 증상을 recurring cause family로 묶는 분류 체계다. structural contract failure, routing/provenance failure, content quality failure, mechanism/process failure를 나누어 장기 품질 저하를 더 빨리 진단하게 한다.

## Why it matters here
현재 lint/eval은 broken link, missing section, broad synthesis watch, shard pressure 같은 신호를 잘 잡지만, 같은 문제가 왜 반복되는지까지 항상 설명하지는 않는다. self-improving wiki에서는 실패를 단순 pass/fail로만 보면 다음 mechanism change가 또 다른 complexity drift가 될 수 있다. taxonomy는 [[concept--long-horizon-quality-guard]]가 trend를 읽고, [[concept--anti-slop-wiki-governance]]가 구조 개입을 고를 때 쓰는 원인 언어다.

## Main body
### Tier 1: structural contract failures
- broken wikilink
- malformed frontmatter
- missing required heading
- missing or weak `Source trace`
- raw path / registry mismatch
- generated artifact drift

이 tier는 deterministic gate로 잡기 가장 쉽고, 가능하면 hard fail에 가깝게 다룬다.

### Tier 2: routing and provenance failures
- orphan page or weak related-page graph
- router drift
- duplicate synthesis route
- single-source seed가 적절한 concept/synthesis로 흡수되지 않음
- broad synthesis가 machine-readable boundary 없이 계속 커짐
- source family가 잘못된 corpus나 shard로 라우팅됨

이 tier는 lint candidate와 maintainer review가 함께 필요하다.

### Tier 3: content quality failures
- unsupported quantitative claim
- stale or superseded claim
- weak evidence strength labeling
- over-compressed synthesis
- scope creep
- source trace는 있지만 claim-to-source fidelity가 약함

이 tier는 domain/source reread가 필요할 수 있으며, 단순 structural fix로 해결되지 않는다.

### Tier 4: mechanism and process failures
- one-mechanism discipline 위반
- eval overfitting
- policy branch growth without test growth
- log/update/validation ordering이 중복 gate를 만든 상태
- prompt/source boundary failure
- subagent routing or integration contract가 불명확한 상태

이 tier는 page 고침보다 ops/policy/process intervention 후보가 된다.

### Use in loops
lint/eval/stage2는 failure instance를 찾고, 이 taxonomy는 instance를 cause family로 라벨링한다. long-horizon guard는 같은 family가 여러 작업에서 반복되는지 추적한다. improvement experiment는 한 번에 한 family와 한 mechanism만 줄이는 방향으로 설계한다.

## Scope boundaries
- 이 taxonomy는 severity ranking 자체가 아니다.
- 개별 domain claim의 참거짓을 직접 판정하지 않고, claim-to-source failure를 분류한다.
- 모든 warning을 실패로 승격하자는 문서가 아니다.
- lint script에 즉시 hard-coded rule을 추가하라는 implementation plan도 아니다.

## Examples and non-examples
- example: broken wikilink는 Tier 1 structural contract failure다.
- example: 같은 질문이 두 synthesis에 반복되면 Tier 2 routing failure 또는 Tier 3 content redundancy로 분류한다.
- example: source text가 maintainer instruction처럼 실행되는 위험은 Tier 4 prompt/source boundary failure다.
- non-example: 명확한 boundary와 source trace가 있는 큰 synthesis는 line count만으로 failure가 아니다.
- non-example: `Open questions`에 명시적으로 남은 미해결점은 uncontrolled placeholder sprawl과 다르다.

## How to reuse this concept
- lint report를 읽을 때 각 candidate에 Tier label을 붙여 repeated family를 본다.
- mechanism improvement를 고를 때 page-level symptom보다 recurring cause family를 먼저 선택한다.
- new policy rule을 추가하기 전, 이미 Tier 1 deterministic fix인지 Tier 2/3 review 후보인지 구분한다.
- review artifact를 만들 때 `failure_mode`, `evidence`, `suggested_mechanism`, `validation_gate`를 분리한다.

## Related pages
- [[source--natural-language-agent-harnesses-2026-04-17]]
- [[source--slopcodebench]]
- [[concept--anti-slop-wiki-governance]]
- [[concept--long-horizon-quality-guard]]
- [[concept--binary-evals]]
- [[concept--cross-reference-maintenance]]
- [[concept--prompt-contract-robustness]]
- [[lint--broad-synthesis-watch-review-2026-04-14]]
- [[lint--raw-unregistered-file-review-2026-04-16]]

## Open questions
- taxonomy labels를 lint/review report frontmatter의 machine-readable field로 승격할 것인가?
- 어느 Tier와 signal이 hard fail, warn, watch candidate에 대응해야 하는가?
- Tier 4 process failure를 ops policy로 고칠지 AGENTS text로 고칠지 가르는 기준은 무엇인가?

## Source trace
- `raw/2603.25723v1.pdf`
- `raw/2603.24755v1.pdf`
- `raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md`
- `system/source--natural-language-agent-harnesses-2026-04-17.md`
- `system/concept--anti-slop-wiki-governance.md`
- `system/concept--long-horizon-quality-guard.md`
- `system/lint--broad-synthesis-watch-review-2026-04-14.md`
- `system/lint--raw-unregistered-file-review-2026-04-16.md`
- `ops/policies/wiki-maintainer-policy.yaml`
