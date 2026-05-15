---
title: "Natural-Language Agent Harnesses"
page_type: "source"
corpus: "system"
registry_id: "W-192"
raw_path: "raw/2603.25723v1.pdf"
source_type: "research-paper"
domain: "natural-language-agent-harnesses"
created: "2026-04-17"
aliases:
  - "source--natural-language-agent-harnesses-2026-04-17"
tags:
  - "corpus/system"
  - "type/source"
---

# source--natural-language-agent-harnesses-2026-04-17

## Title
Natural-Language Agent Harnesses

## Source
- `raw/2603.25723v1.pdf`

## Type
research-paper

## Summary
이 paper는 agent 성능이 모델 자체보다 harness engineering에 점점 더 의존하지만, 실제 harness logic은 controller code, runtime defaults, adapter convention 안에 흩어져 있어 비교와 이전이 어렵다고 본다. 제안은 Natural-Language Agent Harnesses(NLAH)로 harness behavior를 편집 가능한 자연어 artifact로 외부화하고, Intelligent Harness Runtime(IHR)이 명시적 contract, durable artifact, lightweight adapter를 통해 실행하게 만드는 것이다.

## Why it matters
이 system corpus는 이미 AGENTS.md, skill, policy, eval gate, run artifact를 runtime contract로 다룬다. NLAH/IHR는 이 저장소의 maintainer runtime 방향을 이론적으로 정리해 주는 가까운 source다. 특히 harness를 코드 내부 구현이 아니라 `contract + stage + state semantics + failure taxonomy`를 가진 실행 가능한 문서 객체로 보자는 점이 [[concept--harness-optimization]]와 바로 맞물린다.

## Key points
- paper는 harness를 multi-step reasoning, tool use, memory, delegation, stopping rule을 구조화하는 control stack으로 정의한다.
- NLAH는 harness-wide contracts, roles, stage structure, adapters, scripts, state semantics, failure taxonomy를 자연어로 드러내야 실행 가능하다고 본다.
- IHR는 shared runtime charter와 task-family harness logic을 분리해, harness pattern을 비교·이전·ablate할 수 있게 만드는 runtime layer다.
- 저자들은 coding과 computer-use benchmark에서 shared-runtime effect, module ablation, code-to-text harness migration fidelity를 평가한다.
- AGENTS.md와 skill bundles를 reusable control knowledge의 선례로 보되, 이 paper는 그보다 더 명시적인 executable harness representation을 목표로 한다.

## Limitations / caveats
- paper의 목표는 harness representation을 scientific object로 만드는 것이므로, 특정 production agent platform의 안정성을 보장하지 않는다.
- natural-language harness는 수정과 검토가 쉬운 대신 ambiguity와 runtime interpretation drift가 생길 수 있다.
- IHR 같은 shared runtime을 도입하면 code scaffolding을 줄일 수 있지만, runtime charter 자체의 권한·상태·검증 contract가 약하면 실패가 문서 밖에서 발생할 수 있다.

## What this source adds to the corpus
이 source는 local maintainer runtime에서 이미 쓰고 있는 `AGENTS.md + policy + page shape + validation` 조합을 넓은 연구 언어로 설명한다. 앞으로 harness profile이나 subagent routing contract를 개선할 때, 코드가 아니라 자연어 contract 자체를 실험 단위로 삼을 근거가 된다.

## How strong is the evidence
증거 강도는 conceptual + controlled evaluation이다. paper는 harness를 first-class artifact로 다루는 formulation을 제공하고, 일부 benchmark에서 migration과 ablation을 테스트한다. 다만 이 repo의 wiki-maintainer task에 직접 재현된 것은 아니므로, 이 source는 즉시 채택할 blueprint라기보다 mechanism design vocabulary로 읽는 편이 안전하다.

## Related pages
- [[system-index]]
- [[concept--harness-optimization]]
- [[concept--artifact-contracts]]
- [[concept--wiki-failure-mode-taxonomy]]
- [[concept--self-improving-wiki-loop]]
- [[source--meta-harness]]
- [[source--karpathy-autoresearch-repo]]
- [[source--kevinrgu-autoagent-repo]]

## Open questions
- 이 repo의 `AGENTS.md`, policy YAML, source page shape를 하나의 NLAH-like executable harness artifact로 표현할 수 있는가?
- current lint/eval gates는 IHR의 durable artifact contract로 충분한가, 아니면 state semantics와 failure taxonomy가 더 필요할까?
- natural-language harness migration을 검증하려면 baseline/candidate runtime replay를 어떤 최소 fixture로 만들면 좋은가?

## Source trace
- `raw/2603.25723v1.pdf`
- `system/concept--harness-optimization.md`
- `system/source--meta-harness.md`
- `system/source--karpathy-autoresearch-repo.md`
- `system/system-raw-registry.md`
