---
title: "Initial Review 2026-04-12"
page_type: "lint"
corpus: "system"
maintenance_scope: "repo"
created: "2026-04-12"
aliases:
  - "lint--initial-review-2026-04-12"
tags:
  - "corpus/system"
  - "type/lint"
---

# lint--initial-review-2026-04-12

## Summary
기존 초안은 bootstrap 품질이 높지만, **등록만 되고 실제 ingest가 없는 상태**였다. 가장 중요한 결함은 raw path mismatch, canonical page 부재, 자동 lint/eval 부재, query capture 부재였다.

## Findings
### F-01 — raw path mismatch (FAIL)
- `system/system-index.md`의 등록 source 경로는 실제 파일명과 맞지 않았다.
- 예: `2603.23420v1(1).pdf`로 등록되어 있지만 실제 raw에는 `2603.23420v1.pdf`가 있었다.
- 이 문제는 source of truth 탐색 자체를 깨므로 fail 수준이다.

### F-02 — canonical page backlog only (WARN)
- `source--...`, `concept--...`, `synthesis--...`가 TODO만 있고 실제 page가 없었다.
- index가 설계 의도는 보여줬지만 reusable knowledge layer는 아직 시작되지 않은 상태였다.

### F-03 — repo sources not snapshotted (WARN)
- 논문 PDF는 raw에 있었지만 GitHub repo들은 raw snapshot이 없었다.
- live web에만 의존하면 future session reproducibility가 약해진다.

### F-04 — no deterministic lint / eval (WARN)
- 규칙은 좋았지만, required heading / broken link / source trace를 검사하는 스크립트가 없었다.
- 품질 판정이 사람 기억에 의존하게 되는 상태였다.

### F-05 — no reflect / query artifact habit (WARN)
- log에는 backlog가 있었지만, reusable query artifact나 reflective close-out page는 없었다.
- 세션 경계에서 decision rationale가 빠르게 사라질 수 있었다.

### F-06 — self-improvement target undefined (WARN)
- “wiki를 유지한다”는 목표는 있었지만, 무엇을 mutation 대상으로 보고 어떤 score로 keep/discard 할지가 정의되지 않았다.

### F-07 — strong bootstrap decisions already present (PASS)
- raw / wiki 분리
- flat wiki 전략
- prefix naming
- append-only log
- source fidelity 강조
이 네 가지는 그대로 유지할 가치가 있다.

## Recommended fixes
1. raw path mismatch를 즉시 수정한다.
2. source / concept / synthesis canonical page를 실제로 생성한다.
3. GitHub repo와 project page 핵심 문서를 raw snapshot으로 저장한다.
4. `ops/` layer를 추가해 lint/eval/schema/policy를 외부화한다. 특히 [[concept--binary-evals]], [[concept--anti-slop-wiki-governance]], [[concept--cross-reference-maintenance]]를 baseline rule로 삼는다.
5. query artifact와 reflect artifact를 정식 page type으로 사용한다.
6. meta-improvement는 page보다 먼저 template / policy / script부터 시작한다.

## Related pages
- [[system-index]]
- [[system-raw-registry]]
- [[concept--binary-evals]]
- [[concept--anti-slop-wiki-governance]]
- [[concept--cross-reference-maintenance]]

## Source trace
- `system/system-index.md`
- `system/system-log.md`
- `AGENTS.md`
- `ops/scripts/wiki_lint.py`
