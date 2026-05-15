---
title: "Research Insights to Practical Wiki Rules"
page_type: "synthesis"
corpus: "system"
source_count: 9
created: "2026-04-12"
aliases:
  - "synthesis--research-insights-to-practical-wiki-rules"
tags:
  - "corpus/system"
  - "type/synthesis"
---

# synthesis--research-insights-to-practical-wiki-rules

## Question
첨부 논문과 GitHub들에서 나온 자기개선 방향을 LLM Wiki 운영 규칙으로 번역하면 무엇이 되는가?

## Short answer
핵심 번역은 일곱 가지다: **spec before page**, **binary eval over vibes**, **trace before mutation**, **keep/discard over silent drift**, **anti-slop governance**, **long-horizon quality guard**, **log every promotion**. 이 일곱 가지를 지키면 초안이 지식 저장소에서 self-improving runtime으로 올라간다.

## Evidence considered
- [[source--bilevel-autoresearch]]
- [[source--slopcodebench]]
- [[source--meta-harness]]
- [[source--karpathy-autoresearch-repo]]
- [[source--autoresearch-skill-repo]]
- [[source--semantic-checks-and-execution-feedback-for-llm-assistants]]
- [[source--jangpm-meta-skills-repo]]
- [[source--ouroboros-repo]]
- [[source--stage1-planning-harness-mvp]]

## Analysis
### 1. spec before page
Ouroboros와 Stage 1 spec의 교훈이다.
- major synthesis나 planning 문서는 seed / scope / acceptance가 먼저다.
- ambiguity가 크면 먼저 deep-dive를 하고 page를 쓴다.

### 2. binary eval over vibes
autoresearch-skill과 Talk Less, Verify More의 교훈이다.
- “좋아 보임”은 score가 아니다.
- required sections, broken links, source trace, decisionability 같은 yes/no 질문으로 본다.
- semantic check와 execution feedback도 user가 사후 확인하는 대신 assistant loop 안에서 verification을 앞당기는 구조로 읽어야 한다.

### 3. trace before mutation
Meta-Harness의 교훈이다.
- score summary만 보지 않는다.
- prior page, failing outputs, lint report, log를 먼저 읽고 원인을 좁힌다.

### 4. keep/discard over silent drift
Karpathy와 Bilevel의 교훈이다.
- mechanism 수정은 baseline 대비 개선될 때만 유지한다.
- 좋아 보인다는 이유로 template나 policy를 조용히 덮어쓰지 않는다.

### 5. anti-slop governance
SlopCodeBench의 교훈이다.
- prompt hygiene만으로는 열화가 멈추지 않는다.
- page sprawl, duplicate synthesis, orphan link, weak trace를 구조적으로 관리해야 한다.

### 6. long-horizon quality guard
SlopCodeBench와 local mechanism review surface를 함께 읽은 교훈이다.
- 단기 eval pass만으로는 장기 품질을 보장할 수 없다.
- architecture entropy, complexity drift, redundancy growth를 run history와 lint trend로 추적해야 한다.
- 일정 임계치에서는 새 ingest보다 periodic refactor loop를 먼저 예약해야 한다.

### 7. reflect as a first-class operation
jangpm-meta-skills의 교훈이다.
- 큰 query나 ingest 뒤에는 reflect가 있어야 한다.
- 다음 액션을 기록하지 않으면 세션 경계에서 정보가 사라진다.

## What this synthesis excludes
- 이 문서는 repo 전체의 세부 운영 매뉴얼이나 command reference를 대체하지 않는다.
- 각 rule을 어떤 script가 어떻게 구현하는지의 file-by-file 설명도 범위 밖이다.
- 연구 source 각각의 세부 실험 설계를 재요약하는 anchor page 역할까지 하지는 않는다.

## Tensions / contradictions
- binary eval discipline을 강하게 걸수록 human nuance와 예외 처리가 숨을 공간이 줄 수 있다.
- anti-slop compactness를 추구하면서도 reusable section을 늘리면 문서 길이가 길어질 수 있어, density와 brevity 사이에 긴장이 생긴다.
- long-horizon metric을 너무 많이 늘리면 guard 자체가 운영 복잡도와 verbosity source가 될 수 있다.
- reflect/log를 촘촘히 남길수록 trace quality는 좋아지지만, operator friction도 함께 올라간다.

## Implications for future ingest
- 새 system source를 읽을 때는 먼저 `spec`, `eval`, `trace`, `anti-slop`, `long-horizon guard`, `reflection/log` 중 어떤 rule family를 강화하는지 매핑하면 좋다.
- 동일 family의 evidence가 더 쌓이면 concept page를 두껍게 만들고, 서로 다른 family를 묶을 때만 broad synthesis를 확장하는 편이 낫다.
- rule을 구현하는 메커니즘을 바꿀 때는 이 synthesis 자체보다 대응 concept/policy/script를 직접 갱신하는 쪽이 유지보수성이 높다.

## Decision / takeaway
이 패키지의 실제 운영 규칙은 아래 일곱 줄로 요약된다.
1. major artifact는 질문부터 얼린다.
2. page promotion은 binary eval로만 한다.
3. mutation 전에 trace를 본다.
4. improve 안 되면 revert한다.
5. duplicate / orphan / weak trace를 슬롭으로 취급한다.
6. 반복 lint/eval/run-history signal은 long-horizon guard로 refactor 여부를 판단한다.
7. 모든 중요한 변화는 append-only log에 남긴다.

## Follow-up questions
- reflect와 log를 하나로 합칠지 분리할지?
- binary eval 중 어떤 것은 future model judge로 보강할지?

## Related pages
- [[concept--binary-evals]]
- [[concept--anti-slop-wiki-governance]]
- [[concept--long-horizon-quality-guard]]
- [[concept--cross-reference-maintenance]]
- [[synthesis--llm-wiki-self-improvement-architecture]]
- [[synthesis--meta-harness-vs-bilevel-autoresearch]]

## Source trace
- `raw/2603.23420v1.pdf`
- `raw/2603.24755v1.pdf`
- `raw/2603.28052v1.pdf`
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/web-snapshots/slopcodebench-design-philosophy-2026-04-12.md`
- `raw/web-snapshots/meta-harness-project-page-2026-04-12.md`
- `raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md`
- `raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md`
- `raw/2601.00224v2.pdf`
- `raw/web-snapshots/jangpm-meta-skills-readme-2026-04-12.md`
- `raw/web-snapshots/ouroboros-readme-and-claude-2026-04-12.md`
