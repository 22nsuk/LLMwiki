---
title: "kevinrgu/autoagent repository"
page_type: "source"
corpus: "system"
registry_id: "W-031"
raw_path: "raw/web-snapshots/kevinrguautoagent autonomous harness engineering.md"
source_type: "github-snapshot"
domain: "autonomous-harness-engineering"
created: "2026-04-13"
aliases:
  - "source--kevinrgu-autoagent-repo"
tags:
  - "corpus/system"
  - "type/source"
---

# source--kevinrgu-autoagent-repo

## Title
kevinrgu/autoagent repository

## Source
- `raw/web-snapshots/kevinrguautoagent autonomous harness engineering.md`

## Type
github-repository

## Summary
이 저장소는 `agent.py` 하나를 harness-under-test로 두고, 인간은 `program.md`를 수정하며 meta-agent는 benchmark를 돌려 score를 보고 harness를 계속 고치는 구조를 제안한다. `tasks/`는 Harbor task format을 따르고, loop는 benchmark score를 기준으로 keep/discard 식 hill-climb를 수행한다.

## Why it matters
현재 system corpus에는 Karpathy식 최소 autoresearch, autoresearch-skill, Meta-Harness가 들어 있지만, **single-file harness + fixed adapter boundary + Harbor task harness**를 한 저장소 안에 묶은 operational pattern은 없었다. 이 source는 self-improving wiki runtime을 더 실제 benchmark harness 쪽으로 번역하는 데 유용하다.

## Key points
- 인간은 `program.md`를 수정하고, meta-agent는 `agent.py`를 수정하는 역할 분리를 둔다.
- `agent.py` 안에서 editable harness section과 fixed adapter section을 분리한다.
- benchmark task는 Harbor format을 따르며, 총 score가 outer loop의 selection signal이 된다.
- repo는 `tasks/`, `jobs/`, `results.tsv`, `run.log` 같은 실험 artifact를 전제로 설계된다.
- 목표는 모델 weights가 아니라 prompt, tools, orchestration, agent configuration을 포함한 harness engineering이다.
- project page는 이를 `autonomous harness engineering`이라고 직접 부른다.

## Limitations / caveats
- Harbor task와 Docker workflow에 강하게 의존하므로, wiki 같은 문서형 runtime에 그대로 복제하기엔 adaptation layer가 필요하다.
- score hill-climbing 구조는 강력하지만, benchmark leakage나 task-specific overfitting 위험도 함께 커질 수 있다.
- `program.md` 중심 steering은 유용하지만, artifact contract와 signoff가 약하면 uncontrolled autonomy로 기울 수 있다.

## Related pages
- [[source--karpathy-autoresearch-repo]]
- [[source--meta-harness]]
- [[source--autoresearch-skill-repo]]
- [[concept--harness-optimization]]
- [[concept--self-improving-wiki-loop]]
- [[synthesis--karpathy-gist-to-runtime]]

## Open questions
- wiki runtime에서 `program.md`에 대응하는 steering artifact는 policy file인가, run-ledger prompt인가?
- Harbor task처럼 deterministic benchmark를 갖지 못하는 wiki maintenance에서는 어떤 outer-loop score를 써야 하는가?
- fixed adapter boundary와 editable harness boundary를 wiki에서는 어떤 파일 단위로 나눌 것인가?

## Source trace
- `raw/web-snapshots/kevinrguautoagent autonomous harness engineering.md`
