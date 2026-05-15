---
title: "olelehmann100kMRR/autoresearch-skill repository"
page_type: "source"
corpus: "system"
registry_id: "W-002"
raw_path: "raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md"
source_type: "github-snapshot"
domain: "binary-eval-runtime"
created: "2026-04-12"
aliases:
  - "source--autoresearch-skill-repo"
tags:
  - "corpus/system"
  - "type/source"
---

# source--autoresearch-skill-repo

## Title
olelehmann100kMRR/autoresearch-skill repository

## Source
- `raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md`

## Type
github-repository

## Summary
이 저장소는 Karpathy식 autoresearch를 **skill prompt optimization**으로 옮긴 구현이다. 핵심은 binary eval suite, baseline snapshot, 결과 로그, changelog, dashboard를 갖춘 반복 실험 루프다.

## Why it matters
LLM Wiki의 자기개선은 결국 page quality, link quality, trace quality를 평가해야 한다. 이 저장소는 “좋아 보인다” 대신 **yes/no eval**과 changelog 중심으로 improvement를 다루는 좋은 operational pattern을 준다.

## Key points
- target skill, test inputs, eval criteria, run count, budget cap를 먼저 명시하게 한다.
- 모든 eval을 yes/no로 정의하고, scale-based judgment를 피한다.
- baseline run을 먼저 찍고 이후 mutation은 keep / discard / revert 구조로 관리한다.
- `results.tsv`, `results.json`, `dashboard.html`, `changelog.md`를 산출해 실험을 추적 가능하게 만든다.
- mutation 전략은 one-change-at-a-time을 강하게 권한다.
- eval guide는 too many evals, overlapping evals, subjective evals의 위험을 설명한다.

## Limitations / caveats
- prompt mutation 중심이므로, script/policy/schema 자체를 바꾸는 meta-loop까지 직접 다루지는 않는다.
- binary eval 설계가 나쁘면 skill이 test를 game할 위험이 있다.
- dashboard가 있다고 해서 improvement quality가 자동으로 보장되지는 않는다.

## Related pages
- [[concept--binary-evals]]
- [[concept--self-improving-wiki-loop]]
- [[concept--trace-store-and-run-ledger]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Open questions
- wiki maintenance의 default eval 5~7개는 무엇으로 시작하는 것이 좋은가?
- page-level eval과 vault-level eval을 같은 report에 합칠 것인가 분리할 것인가?
- changelog를 `system/system-log.md`와 별도 TSV/JSON ledger 중 어디에 두는 것이 좋은가?

## Source trace
- `raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md`
