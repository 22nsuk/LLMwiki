# AGENTS.md

이 저장소의 공개 루트는 **persistent LLM wiki + self-improving maintainer runtime**의
`code/ops` mirror다.

중요:
- public mirror에서는 `docs/`, `ops/`, `tests/`, `tools/`, `mk/`, `.codex/agents/`, `.github/`, 루트 문서를 기본 작업 surface로 본다.
- 같은 루트에 `AGENTS.local.md`가 있으면, full local vault 세션은 이 문서와 `AGENTS.local.md`를 함께 읽는다.
- public mirror에서는 `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/`가 없거나 비공개일 수 있음을 기본 가정으로 둔다.

---

## 1. Scope

public mirror 기준 기본 작업 범위:

- `ops/`
- `tests/`
- `tools/`
- `mk/`
- `docs/`
- `.codex/agents/`
- `.github/`
- 루트 문서/설정 파일

public mirror 기준 제외 범위:

- `raw/`
- `wiki/`
- `system/`
- `runs/`
- `external-reports/`
- `ops/manifest.json`
- `ops/raw-registry.json`
- `ops/operator/` 아래 generated operator artifact
- `ops/reports/` 아래 generated artifact

원칙:
- public surface 작업은 **corpus 없이도 재현 가능해야 한다.**
- private corpus나 live run artifact를 public 문서, 테스트, fixture 안으로 끌고 오지 않는다.

---

## 2. Roles

역할은 네 가지다.

- 사람은 source를 큐레이션하고 signoff 또는 운영 판단을 한다.
- maintainer agent는 raw를 읽고 wiki corpus를 유지한다.
- ops layer는 policy / eval / lint / schema / script를 제공한다.
- meta-maintainer agent는 runtime mechanism 자체를 개선한다.

public mirror에서 당신의 기본 역할은 **runtime maintainer** 또는 **meta-maintainer**다.
즉, code/ops mirror에서는 주로 아래를 다룬다.

- script / schema / policy / template 개선
- 테스트 보강
- public/private boundary hygiene
- subagent profile과 routing contract 유지

---

## 3. Architecture

이 저장소는 private canonical vault와 public code/ops mirror를 분리할 수 있다.

### Layer A — Raw
- 위치: `raw/`
- 성격: canonical source snapshot layer
- full local vault에서는 binary raw는 immutable이고, markdown raw는 local supplement가 허용하는 최소 post-ingest normalization만 적용할 수 있다.
- public mirror에서는 기본적으로 제외한다.

### Layer B — Knowledge corpora
- 위치: `wiki/`, `system/`
- 역할:
  - `wiki/`: user/domain/content corpus
  - `system/`: maintainer/runtime/meta corpus
- public mirror에서는 기본적으로 제외한다.

### Layer C — Ops
- 위치: `ops/`
- 역할: policy, eval, schema, template, helper script를 담는 control layer
- public mirror의 핵심 작업 surface다.

### Layer D — Documentation and operating rules
- 위치: `AGENTS.md`
- 역할: public-safe operating contract
- full local vault가 있으면 `AGENTS.local.md`가 이를 확장한다.
- `docs/`는 public-safe workflow와 runtime orientation을 담는 첫 진입점이다.

구조 설명의 public-safe canonical surface는 `ARCHITECTURE.md`다.

---

## 4. Working Modes

### A. Runtime maintenance

해야 할 일:
1. `ops/`의 script / schema / policy / template contract를 개선한다.
2. 변경이 있으면 관련 테스트를 함께 갱신한다.
3. public mirror가 corpus 없이도 self-contained하게 동작하는지 확인한다.

### B. Validation

기본 gate:
1. `make dev-install`
2. `make static`
3. `make test`; full-suite 요청이면 `make test-all`, focused selector 검증이면 `.venv/bin/python -m pytest tests/...`
4. 새 public 파일, 새 public prefix, 공개/비공개 경계를 바꾸는 변경이면 `make sync-public-policy`
5. 필요하면 `make public-export`
6. 공개 미러 자체를 재검증할 때 `make public-check`

full local vault가 있을 때만 추가로:
- `make check`
- `make release-check`

### C. Subagent maintenance

- `.codex/agents/`는 public mirror에 포함된다.
- repo-shared ladder와 role intent는 유지해야 한다.
- 실제 rung 선택은 `ops/scripts/core/select_subagent_rung.py`가 맡고, `.toml`은 fallback instruction surface다.

### D. Optional codebase-memory-mcp sidecar

`codebase-memory-mcp`가 operator-local binary 또는 MCP server로 제공되는 세션에서는
이를 **읽기 우선 code/ops 구조 색인 hint**로 사용할 수 있다.

운영 규칙:
- 표준 index source는 full-vault root가 아니라 `make cbm-index-public`이 만드는 public-safe export다.
- repo 수정 후 graph를 신뢰하기 전에는 `make cbm-index-public`로 재색인한다. CBM은 working tree를 자동 감시하지 않는다.
- snippet/search 결과가 `CBM_PUBLIC_OUT` cache 경로를 반환하면 같은 relative path의 repo 원본 파일로 매핑해 수정한다.
- 구조/영향 범위 질문에서는 broad grep/read 전에 `cbm-schema-public`, `cbm-architecture-public`, graph/search/trace/detect_changes 계열 query를 먼저 볼 수 있다.
- 새 세션에서 sidecar 자체가 유효한지 확인해야 하면 `make cbm-smoke-public`로 public-safe export, index, schema, architecture, fixed search probe를 한 번에 검증할 수 있다.
- graph 결과와 `CALLS`/`WRITES`/`CONFIGURES` 같은 edge는 candidate link, not proof이며, live file read와 Make/Pytest gate로 확인한다.
- `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/`, `ops/operator/`, `ops/reports/`는 index/query 대상이 아니다.
- `codebase-memory-mcp install`의 자동 agent config/hook 설정이나 blocking hook으로 Read/Grep/Edit workflow를 막지 않는다.
- 이 sidecar는 dependency, CI/release gate, promotion authority, canonical evidence, 또는 assistant-specific workflow requirement가 아니다.
- 자세한 사용법은 `docs/codebase-memory-mcp.md`를 본다.

---

## 5. Non-Negotiable Rules

1. public mirror에서 private corpus 존재를 전제로 작업하지 않는다.
2. private corpus 내용이나 inventory를 public surface에 복사하지 않는다.
3. generated private artifact를 source of truth처럼 다루지 않는다.
4. deterministic test와 schema-backed contract를 우선한다.
   - `generated_at`를 쓰거나 날짜 기반 policy logic을 가진 runtime/report generator는 `RuntimeContext`를 받아 injected clock으로 재현 가능해야 한다.
5. contract가 바뀌면 관련 docs / tests / schema / policy를 같이 갱신한다.
6. `.codex/agents/` 수정 시 role intent, ladder, routing contract를 함께 본다.
7. 절대경로, temp workspace path, local state leak를 public surface에 남기지 않는다.
8. 새 public 파일이나 공개 경계를 바꾸는 변경은 `make sync-public-policy`까지 포함해 마무리한다.
9. reusable automation 또는 repo hygiene follow-up을 발견하면 closeout 전에 observation artifact를 남긴다.
   - mechanism run이면 `runs/<run-id>/improvement-observations.json`
   - run과 무관한 standalone maintenance task면 `ops/reports/task-improvement-observations/<task-id>/improvement-observations.json`
   - 이미 기록된 follow-up을 해결했다면 새 observation을 중복 생성하기보다 기존 항목의 `status`와 `suggested_followup`를 갱신해 closeout 상태를 남긴다.
10. 작업 과정에서 불필요해진 내용은 최대한 삭제하고, 보존이 불가피한 경우에만 명확한 이유가 있는 상태로 남긴다.

---

## 6. Primary Targets

우선순위:
1. `ops/` runtime contract
2. `tests/` coverage and determinism
3. `.codex/agents/` role surface
4. public export / CI / packaging hygiene
5. public-safe documentation

---

## 7. Local Supplement

아래 작업은 public mirror 기본 계약을 넘어서는 **full-vault** 작업이다.

- `raw/` ingest
- `wiki/` / `system/` corpus mutation
- `system/system-log.md` append
- `system/system-raw-registry.md` maintenance
- `runs/<run-id>/...` promotion / run ledger 처리
- `runs/<run-id>/improvement-observations.json` 또는 `ops/reports/task-improvement-observations/<task-id>/improvement-observations.json`에 follow-up automation/backlog 기록
- flat wiki naming / frontmatter / page shape 규칙 집행

이런 작업을 할 때는 `AGENTS.local.md`를 함께 읽는다.
