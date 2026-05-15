---
title: "karpathy/autoresearch repository"
page_type: "source"
corpus: "system"
registry_id: "W-001"
raw_path: "raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md"
source_type: "github-snapshot"
domain: "autoresearch-loop"
created: "2026-04-12"
aliases:
  - "source--karpathy-autoresearch-repo"
tags:
  - "corpus/system"
  - "type/source"
---

# source--karpathy-autoresearch-repo

## Title
karpathy/autoresearch repository

## Source
- `raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md`
- `raw/web-snapshots/AutoResearch Explained How Karpathy's AI Research Agent Works.md`

## Type
github-repository

## Summary
이 저장소는 Karpathy식 autoresearch의 최소 구현이다. 핵심은 **작은 코드베이스 + 한 파일만 수정 + 고정 시간 budget + keep/discard**다. 모델을 직접 튜닝하기보다, agent가 반복 실험을 운영하게 만드는 “program.md as lightweight skill” 접근이 중심이다. Verdent explainer raw는 이 패턴을 `ratchet loop`, git rollback, scalar metric, fixed hardware budget의 결합으로 풀어 설명하며, 왜 이 구조가 general AutoML이 아니라 constrained autonomous code-improvement loop인지 보강한다.

## Why it matters
LLM Wiki 초안도 처음부터 과도한 multi-agent runtime으로 가기보다, **작고 강한 inner loop**를 먼저 가져가는 편이 낫다. 이 저장소는 그 최소 단위를 보여준다.

## Key points
- `prepare.py`는 고정, `train.py`만 수정 대상으로 두어 diff와 책임 범위를 단순화한다.
- 모든 실험은 baseline 측정부터 시작하고 TSV로 결과를 기록한다.
- val_bpb라는 단일 metric과 fixed 5-minute budget이 keep/discard 판단을 단순화한다.
- `program.md`는 setup, logging, loop rules, crash handling, reset policy를 명확히 적어둔다.
- Simplicity criterion을 두어, 미세한 개선이 복잡성을 크게 올리면 promotion하지 않도록 한다.
- 실험 branch를 진전시키는 방식은 future state를 하나의 accepted lineage로 유지한다.
- 후속 explainer는 git rollback이 단순 convenience가 아니라 regression을 영구화하지 않는 ratchet mechanism이라고 해석한다.
- same explainer는 AutoResearch가 성공하려면 single file, scalar metric, repeatable run처럼 search surface가 좁아야 한다고 강조한다.

## Limitations / caveats
- single-metric setting이라 multi-objective wiki maintenance에는 그대로 옮기기 어렵다.
- one-file modification 전략은 wiki나 harness runtime처럼 여러 artifact가 얽힌 환경에서는 더 넓은 unit이 필요하다.
- 강한 autonomy는 useful하지만, stopping rule과 approval gate가 약하면 위험하다.
- ratchet loop는 local improvement에는 강하지만, 일시적 regress를 감수해야 하는 multi-step research plan에는 구조적으로 불리하다.

## Related pages
- [[source--autoresearch-skill-repo]]
- [[source--bilevel-autoresearch]]
- [[concept--binary-evals]]
- [[concept--self-improving-wiki-loop]]
- [[synthesis--karpathy-gist-to-runtime]]

## Open questions
- wiki maintenance에서 `train.py only`에 대응하는 최소 mutation unit은 page 하나인가, template 하나인가, policy 하나인가?
- val_bpb처럼 단순한 단일 score 대신 wiki에서는 어떤 multi-objective score를 쓸 것인가?
- fixed-time budget 대신 fixed-artifact budget이 더 적절한가?
- git rollback 기반 ratchet을 wiki mechanism experiment에 적용한다면, `source fidelity`, `lint`, `eval score`, `complexity` 중 어떤 gate를 hard rollback 기준으로 삼아야 하는가?

## Source trace
- `raw/web-snapshots/karpathy-autoresearch-readme-and-program-2026-04-12.md`
- `raw/web-snapshots/AutoResearch Explained How Karpathy's AI Research Agent Works.md`
