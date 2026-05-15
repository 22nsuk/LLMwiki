# LLM Wiki vNext Architecture

이 문서는 이 저장소의 **public-safe architecture overview**다.
실제 private corpus 내용, raw inventory, live run artifact, generated report는 포함하지 않는다.

## Purpose

LLM Wiki vNext는 두 가지를 함께 다룬다.

- raw source를 지속형 wiki corpus로 정리하는 maintainer runtime
- 그 maintainer runtime 자체를 eval과 실험으로 개선하는 meta-maintainer loop

즉, 이 저장소는 content corpus와 운영 메커니즘을 한 workspace 안에서 함께 다루는 구조다.

## Roles

- human: raw source를 큐레이션하고 signoff 또는 운영 판단을 한다
- maintainer agent: raw를 읽고 `wiki/`와 `system/` corpus를 갱신한다
- ops layer: policy, eval, schema, script를 제공한다
- meta-maintainer agent: wiki 내용뿐 아니라 유지 메커니즘 자체를 개선한다

## Layers

### Layer A — Raw

- 위치: `raw/`
- 성격: immutable source of truth
- 역할: PDF, web snapshot, 기타 원문 source를 보관한다

### Layer B — Knowledge Corpora

- 위치: `wiki/`, `system/`
- 역할:
  - `wiki/`: 사용자/도메인/content corpus
  - `system/`: maintainer/runtime/meta corpus

### Layer C — Ops

- 위치: `ops/`
- 역할: policy, eval, schema, template, helper script를 담는 control layer

### Layer D — Operating Rules

- 위치: `AGENTS.md`
- 역할: public-safe operating contract
- full local vault에서는 `AGENTS.local.md`가 이를 보강한다

## Core Loops

### Ingest

- raw source를 읽고 corpus를 결정한다
- 관련 source/concept/synthesis/router/log surface를 함께 갱신한다

### Query

- 질문 유형에 따라 corpus router를 먼저 읽는다
- 필요한 page만 선택적으로 읽고, 부족할 때만 raw로 내려간다

### Improve

- lint/eval/trace로 실패 패턴을 수집한다
- 한 번에 하나의 mechanism만 바꾼다
- binary eval과 deterministic gate로 keep/discard를 결정한다

## Runtime Surfaces

- `README.md`: 루트 사용 설명과 public/private 경계
- `ops/README.md`: runtime command와 contract 설명
- `system/system-index.md`: private system corpus router
- `system/system-raw-registry.md`: private raw inventory summary router
- `system/system-log.md`: append-only 운영 chronology

## Public vs Private

이 저장소는 canonical private vault와 public code/ops mirror를 분리할 수 있다.

public mirror에 포함하기 좋은 것:

- `ops/`
- `tests/`
- `tools/`
- `.codex/agents/`
- `.github/`
- 루트 개발 문서와 설정 파일

public mirror에서 제외하는 것:

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- generated inventory/report artifact

즉, public mirror는 runtime과 testability를 공유하고, private vault는 실제 corpus와 운영 상태를 유지한다.
