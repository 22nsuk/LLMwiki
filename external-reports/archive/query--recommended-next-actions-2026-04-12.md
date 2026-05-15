# Historical Bootstrap Note: Recommended Next Actions 2026-04-12

## Status
이 문서는 2026-04-12 시점의 **bootstrap-stage onboarding note**를 보존한 historical archive다.
현재 runtime의 canonical entry point로는 더 이상 쓰지 않으며, 당시 패키지가 `bootstrap stabilize -> lint/eval baseline -> planning gate 시범 -> meta-improvement 1회` 순서로 올라가야 한다고 보던 초기 판단을 기록용으로만 남긴다.

현재 운영 상태는 이 문서보다 앞서 있다.
- `system_mechanism` 자동 개선 루프와 scoped routing이 추가됐다.
- raw-first ingest order와 raw markdown normalization contract가 명시됐다.
- release packaging gate에서 Stage 2 check까지 통과하도록 source-page shape가 보강됐다.

## Original question
이 패키지를 받은 뒤, 가장 먼저 어떤 순서로 진행하는 것이 좋은가?

## Original short answer
바로 구현으로 뛰어들기보다, **path 정리 -> canonical page 검토 -> lint/eval 실행 -> planning gate 시범 도입 -> meta-loop 소규모 실험** 순서가 가장 안전하다고 봤다.

## Why archived
- 현재 `system/` corpus는 bootstrap advice보다 live router와 current mechanism surface에 집중하는 편이 낫다.
- 이 노트는 여전히 package 초기 상태와 당시 maintainer 판단을 이해하는 데는 유용하지만, 현재 실행 가이드로 쓰면 stale하다.
- 그래서 corpus page가 아니라 external archive로 옮겨 historical context만 보존한다.

## Original note
### bootstrap stabilize
- raw path와 index catalog부터 맞춘다.
- 현재 package의 canonical pages를 읽고 용어를 정렬한다.
- 특히 `source--stage1-planning-harness-mvp`, `synthesis--llm-wiki-self-improvement-architecture`를 기준 문서로 삼는다.

### run the checks
- `python ops/scripts/wiki_lint.py --vault .`
- `python ops/scripts/wiki_eval.py --vault .`
- 결과를 별도 artifact로 저장하고 첫 baseline score로 삼는다.

### choose one live workflow
- 새 논문/source ingest workflow
- planning harness request -> seed -> validate workflow

### introduce signoff only where needed
- planning bundle
- stage handoff
- controversial synthesis

### run first meta-improvement experiment
- template tightening
- lint rule 추가
- source trace formatting 개선
- query artifact promotion rule 추가

## Current replacements
- current quickstart query: [query--runtime-quickstart-2026-04-15](../system/query--runtime-quickstart-2026-04-15.md)
- current system router: [system-index](../system/system-index.md)
- current architecture synthesis: [synthesis--llm-wiki-self-improvement-architecture](../system/synthesis--llm-wiki-self-improvement-architecture.md)
- current planning bridge: [synthesis--stage1-planning-harness-bridge](../system/synthesis--stage1-planning-harness-bridge.md)
- current chronology: [system-log](../system/system-log.md)

## Source trace
- `system/lint--initial-review-2026-04-12.md`
- `system/synthesis--llm-wiki-self-improvement-architecture.md`
- `system/synthesis--stage1-planning-harness-bridge.md`
- `system/system-log.md`
