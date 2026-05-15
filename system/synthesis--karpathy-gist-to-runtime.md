---
title: "Karpathy Gist to Runtime"
page_type: "synthesis"
corpus: "system"
source_count: 4
created: "2026-04-12"
aliases:
  - "synthesis--karpathy-gist-to-runtime"
tags:
  - "corpus/system"
  - "type/synthesis"
---

# synthesis--karpathy-gist-to-runtime

## Question
Karpathy식 최소 autoresearch 패턴을 어떻게 실제 LLM Wiki runtime으로 확장할 수 있는가?

## Short answer
출발점은 Karpathy의 최소 루프를 그대로 따른다: baseline 측정, one-unit mutation, fixed eval, keep/discard, result logging. 다만 wiki로 확장할 때는 mutation 대상이 `train.py`가 아니라 page / template / policy / script가 되고, metric이 val_bpb가 아니라 binary eval suite + lint report가 된다.

## Evidence considered
- [[source--karpathy-autoresearch-repo]]
- [[source--autoresearch-skill-repo]]
- [[source--kevinrgu-autoagent-repo]]
- [[source--stage1-planning-harness-mvp]]
- [[concept--artifact-contracts]]
- [[concept--binary-evals]]

## Analysis
### 최소 autoresearch에서 이미 충분한 것
- baseline first
- dedicated branch / run tag 사고
- 단순 logging
- improved only if metric improves
- simplicity criterion

### runtime으로 가기 위해 필요한 추가물
- page type별 artifact contract
- source trace와 raw snapshot
- signoff / freeze 같은 상태 전이
- lint/eval script
- planning gate
- changelog / ledger
- fixed adapter boundary와 editable harness boundary

### 실무적 해석
`program.md` 하나로 돌리던 연구 루프를, wiki에서는 아래처럼 분해한다.
- page template
- eval suite
- lint script
- policy file
- log / manifest
- optional planning bundle

즉 “작은 keep/discard 엔진”은 유지하고, 주변을 contract layer로 감싼다.

AutoAgent는 여기서 한 걸음 더 나아가, repo-under-test를 `single-file harness + tasks + jobs/results artifact`로 묶고 인간은 `program.md`를, meta-agent는 harness file을 수정하게 만든다. 이 패턴은 wiki runtime에서도 steering artifact와 editable mechanism surface를 더 명확히 분리해야 한다는 힌트를 준다.

## What this synthesis excludes
- 이 synthesis는 full-history trace diagnosis나 multi-agent collaboration topology 전체를 설명하지 않는다.
- production scheduler, branch orchestration, CI wiring까지 현재 답의 범위에 포함하지 않는다.
- Karpathy 패턴을 그대로 복제하자는 주장도 아니다.

## Tensions / contradictions
- Karpathy식 minimalism은 강력하지만, wiki runtime은 page/policy/script/artifact 층이 더 많아 단일 `program.md` 감각만으로는 부족하다.
- simplicity criterion을 유지하려면 contract layer가 얇아야 하지만, persistent wiki는 provenance와 state artifact를 요구해 표면적 복잡도가 늘어난다.
- AutoAgent식 harness 분리는 명확하지만, 과도한 artifactization은 작은 실험 속도를 떨어뜨릴 수 있다.

## Implications for future ingest
- 후속 mechanism source를 읽을 때는 `minimal keep/discard loop`, `editable harness boundary`, `artifactized orchestration` 중 어디를 보강하는지 먼저 표시하면 좋다.
- 새 runtime 제안이 들어오면 Karpathy line의 단순성에 실제로 필요한 것만 추가하는지, 아니면 unrelated control plane을 섞는지 이 synthesis 기준으로 판단할 수 있다.
- planning bundle이나 run artifact를 더 늘릴 때는 “minimal loop를 깨지 않는가”를 검토 포인트로 삼아야 한다.

## Decision / takeaway
LLM Wiki는 처음부터 거대한 multi-agent runtime으로 가지 않는다. 먼저:
1. page contract
2. binary eval
3. lint
4. log / manifest
5. optional seed freeze
만 갖춘다. 이 다섯 가지가 안정화되면 그 다음에 outer-loop automation을 붙인다.

## Follow-up questions
- 언제부터 branch/tag 개념을 실제 vault 운영에 도입할 것인가?
- human signoff와 automatic keep/discard의 경계를 어떻게 자를 것인가?

## Related pages
- [[concept--binary-evals]]
- [[concept--artifact-contracts]]
- [[concept--planning-gates]]
- [[source--kevinrgu-autoagent-repo]]
- [[synthesis--stage1-planning-harness-bridge]]
- [[synthesis--research-insights-to-practical-wiki-rules]]

## Source trace
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md`
- `raw/web-snapshots/autoresearch-skill-skill-and-eval-guide-2026-04-12.md`
- `raw/web-snapshots/kevinrguautoagent autonomous harness engineering.md`
- `ops/evals/wiki-quality-evals.md`
- `ops/schemas/run-ledger.schema.json`
