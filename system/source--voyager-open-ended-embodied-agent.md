---
title: "An Open-Ended Embodied Agent with Large Language Models"
page_type: "source"
corpus: "system"
registry_id: "W-062"
raw_path: "raw/web-snapshots/An Open-Ended Embodied Agent with Large Language Models.md"
source_type: "web-snapshot"
domain: "embodied-agent-skill-library"
created: "2026-04-13"
aliases:
  - "source--voyager-open-ended-embodied-agent"
tags:
  - "corpus/system"
  - "type/source"
---

# source--voyager-open-ended-embodied-agent

## Title
An Open-Ended Embodied Agent with Large Language Models

## Source
- `raw/web-snapshots/An Open-Ended Embodied Agent with Large Language Models.md`
- `raw/2305.16291v2.pdf`

## Type
web-snapshot + research-paper

## Summary
Voyager는 Minecraft 안에서 GPT-4를 사용해 자동 curriculum, reusable skill library, iterative prompting loop를 결합한 open-ended embodied lifelong learning agent를 제안한다. 핵심은 low-level action을 직접 최적화하기보다 code-like skill 단위로 행동을 저장·검색·재조합하고, environment feedback과 self-verification을 다시 prompt loop에 넣어 능력을 누적시키는 구조다. 추가 PDF raw는 이 page가 project-page snapshot만이 아니라 paper 원문 artifact까지 추적하도록 보강한다.

## Why it matters
현재 system corpus의 meta-improvement 논의는 harness optimization, memory organization, trace-first diagnostics에 더 치우쳐 있었다. Voyager는 여기에 `automatic task proposal`, `skill library reuse`, `iterative self-improvement loop`라는 embodied-agent 관점을 더해, 장기적으로 maintainer runtime이 어떤 형태의 reusable behavior library를 가질 수 있는지 생각하게 만든다.

## Key points
- Voyager combines automatic curriculum generation, skill-library storage, and iterative prompting.
- code is treated as the action space, which makes behaviors interpretable and composable.
- the system stores mastered behaviors for later retrieval instead of relying only on transient context.
- self-verification and execution-error feedback are first-class loop inputs.
- the overall design is oriented toward open-ended exploration rather than a single fixed task.
- the paper reports large gains in unique item discovery, travel distance, and milestone unlocking versus prior baselines, but those results remain Minecraft-specific.

## Limitations / caveats
- the environment is Minecraft, so transfer to document-maintenance or repo-maintenance workflows is indirect.
- the work depends on strong model reasoning and environment APIs that do not map 1:1 to wiki maintenance.
- open-ended exploration can generate sprawl if there is no explicit gate, contract, or human signoff layer.

## Related pages
- [[concept--harness-optimization]]
- [[concept--self-improving-wiki-loop]]
- [[source--a-mem-agentic-memory]]
- [[source--meta-harness]]
- [[source--kevinrgu-autoagent-repo]]

## Open questions
- wiki maintenance에서는 automatic curriculum이 raw ingest priority queue와 어떤 관계가 되는가?
- reusable skill library를 page template, command recipe, or lint repair playbook 중 무엇으로 구현하는 편이 좋은가?

## Source trace
- `raw/web-snapshots/An Open-Ended Embodied Agent with Large Language Models.md`
- `raw/2305.16291v2.pdf`
- `system/concept--harness-optimization.md`
- `system/concept--self-improving-wiki-loop.md`
