---
title: "Trace Store and Run Ledger"
page_type: "concept"
corpus: "system"
canonical: true
created: "2026-04-13"
aliases:
  - "concept--trace-store-and-run-ledger"
tags:
  - "corpus/system"
  - "type/concept"
---

# concept--trace-store-and-run-ledger

## Summary
trace store는 prior code, page diff, evaluation score, execution log를 남겨 future diagnosis에 쓰는 저장소고, run ledger는 상태 변화와 signoff를 chronological event로 기록하는 파일이다.

## Why it matters here
Meta-Harness와 Stage 1 spec이 공통으로 말하는 것은 summary만으로는 부족하다는 점이다. wiki self-improvement도 어떤 page가 왜 promoted 됐는지, 어떤 lint failure가 반복됐는지, 어떤 signoff로 seed가 frozen 됐는지 **원시 trace**가 남아야 한다.

## Main body
### trace store가 필요한 이유
- failure 원인을 뒤늦게 국소화할 수 있다.
- summary가 지워 버리는 confound를 다시 볼 수 있다.
- meta-loop가 policy나 template 수정 전후를 비교할 수 있다.
- trace를 단순 append-only pile이 아니라 note network로 재조직할 여지를 남긴다.

### run ledger가 필요한 이유
- 상태 전이와 승인 이벤트를 append-only로 남긴다.
- future session이 현재 상태를 재구성할 수 있다.
- “왜 이 방향을 채택했는가”에 대한 lightweight provenance가 된다.

### wiki에 적용
- `system/system-log.md`는 human-readable chronological ledger다.
- `ops/manifest.json`은 file-level snapshot이다.
- future 단계에서는 JSON `run-ledger.json`을 planning bundle과 meta-improvement run 모두에 둘 수 있다.
- A-Mem 같은 memory design을 참고하면, 그 다음 단계에서는 historical run을 tag/link/update 가능한 trace graph로 다루는 것도 검토할 수 있다.
- RO-Crate 같은 provenance packaging reference를 보면, trace store를 local debug surface에만 두지 않고 portable research object처럼 묶는 방향도 future option이 된다.
- [[concept--memory-management-strategies]] 관점에서는 trace store와 run ledger가 주로 episodic/provenance/telemetry memory를 담당하고, concept/synthesis page는 semantic memory를 담당한다.

## Scope boundaries
- trace store는 diagnosis와 provenance를 위해 남기는 raw-ish artifact surface를 뜻한다.
- run ledger는 상태 전이와 signoff chronology를 기록하는 artifact이지, raw ingest inventory 전체를 대신하지 않는다.
- trace를 많이 남긴다는 이유로 정리되지 않은 dump를 무한히 쌓는 것이 목표는 아니다.

## Examples and non-examples
- example: `runs/<run-id>/run-ledger.json`, eval report, changed-files manifest는 trace store/ledger 개념에 직접 들어간다.
- example: `system/system-log.md`는 human-readable ledger로 작동한다.
- non-example: `system/system-raw-registry.md`는 raw inventory router이지 promotion ledger가 아니다.
- non-example: 최종 decision만 짧게 적고 baseline/candidate evidence를 남기지 않는 것은 trace-first 운영과 거리가 있다.

## How to reuse this concept
- planning run이나 mechanism experiment를 시작할 때는 어떤 trace artifact를 남길지 먼저 정하고 들어간다.
- signoff가 필요한 상태 전이는 ledger entry와 human-readable log entry를 분리해서 관리한다.
- later diagnosis가 중요해 보이는 변경일수록 summary보다 원본 diff/report/snapshot 접근성을 우선 보장한다.

## Related pages
- [[source--meta-harness]]
- [[source--a-mem-agentic-memory]]
- [[source--ro-crate]]
- [[source--stage1-planning-harness-mvp]]
- [[concept--artifact-contracts]]
- [[concept--memory-management-strategies]]
- [[concept--self-improving-wiki-loop]]

## Open questions
- 어떤 trace는 raw로, 어떤 trace는 report artifact로 승격해야 하는가?
- query trace와 improvement trace를 같은 ledger에 합칠지 분리할지?

## Source trace
- `raw/2603.28052v1.pdf`
- `raw/V2 stage1_mvp_specification.pdf`
- `raw/2502.12110v11.pdf`
- `raw/web-snapshots/Research Object Crate (RO-Crate).md`
- `ops/schemas/run-ledger.schema.json`
