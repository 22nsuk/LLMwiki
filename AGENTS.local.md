# AGENTS.local.md

이 문서는 `AGENTS.md`의 **full local vault supplement**다.

적용 규칙:
- 항상 `AGENTS.md`를 먼저 읽는다.
- 아래 규칙은 `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/`를 직접 다룰 때만 추가로 적용한다.
- public mirror 기준 규칙과 충돌하면, full local vault 작업에서는 이 문서의 local-only 규칙을 우선한다.

---

## 1. Local-only Scope

이 문서가 필요한 작업:

- `raw/` source ingest
- `wiki/` / `system/` corpus mutation
- `system/system-raw-registry.md` 및 shard maintenance
- `system/system-log.md` append
- `runs/<run-id>/...` planning / promotion / ledger 처리
- `external-reports/` 검토, action matrix 반영, local-only report intake
- flat wiki naming, frontmatter, page shape 규칙 집행

이 문서가 필요 없는 작업:

- `docs/`, `ops/`, `tests/`, `tools/`, `.codex/agents/`, `.github/` 중심의 public-safe runtime maintenance

---

## 2. Local Architecture Delta

full local vault에서는 아래 surface가 실제로 존재한다고 가정한다.

### Layer A — Raw
- 위치: `raw/`
- 성격: binary raw는 immutable, markdown raw는 minimal post-ingest normalization 허용
- 규칙:
  - `raw/*.pdf` 등 binary raw는 읽기만 한다. 수정, 이름 변경, 삭제 금지.
  - `raw/**/*.md`는 frontmatter 보강, `title`/`source`/`published`/`created` 보강, transport header 제거, cookie/banner/blob-localhost noise 제거, 공백/개행 정리까지만 허용한다.
  - markdown raw에도 의미 변경, 요약 추가, 번역/의역, 근거 문장 삭제, mojibake 추측 복원, 파일명 변경은 금지한다.
  - 예외: `raw/web-snapshots/*.md`가 POSIX escape-expanded filename/component portability budget을 초과하는 경우에만 slug + short content hash 형태로 파일명을 바꿀 수 있다. 이때 본문과 의미 metadata는 바꾸지 않고, 기존 raw path는 registry `path_aliases`와 관련 source trace 갱신으로 보존한다.
- 의미: canonical source snapshot

### Layer B — Knowledge corpora
- 위치: `wiki/`, `system/`
- 성격: mutable, LLM-maintained
- 의미:
  - `wiki/`는 user/domain/content corpus다.
  - `system/`은 maintainer/runtime/meta corpus다.

### Layer C — Run artifacts
- 위치: `runs/`
- 성격: mutable artifact surface
- 의미: planning / validation / promotion / improvement run 증적

### Layer D — External reports
- 위치: `external-reports/`
- 성격: local-only external review and intake material
- 의미: external report 검토 입력이다. public surface에는 정책적으로 허용된 요약,
  action matrix, 또는 sanitized output만 반영한다.
- root의 active 보고서는 local-only intake다. release/promotion 전에
  reference manifest와 action matrix에 반영하고, 해결된 보고서는 archive로 이동한다.
- `external-reports/report-reference-manifest.json`과 `external-reports/archive/`는
  local-only retained evidence이며 Git source of truth가 아니다. 원문 archive 보존은
  local/private vault retention 책임이고, public/release authority는 schema-backed
  summary와 action matrix를 기준으로 한다.

---

## 2.5 Optional codebase-memory-mcp Delta

CBM 사용 규칙은 public-safe 기본 계약인 `AGENTS.md`와
`docs/codebase-memory-mcp.md`를 따른다. full local vault에서도 index source는
full-vault root가 아니라 public-safe export이며, assistant-local state는
codebase-memory 도입 조건이나 증거로 취급하지 않는다.

---

## 3. Local Working Modes

### A. Ingest

새 raw source를 위키에 편입한다.

해야 할 일:
1. preflight나 inventory 비교로 편입 대상 raw를 식별한다.
2. source를 읽고 유형을 분류한다.
3. markdown raw면 corpus mutation에 들어가기 전에 먼저 검토하고, contract가 허용하는 범위에서 metadata/noise를 정리한다.
   - 기본 경로는 `llm-wiki-raw-markdown-normalize --vault . --path raw`로 점검하고, 필요할 때만 `--write`로 반영한다.
   - binary raw는 수정하지 않고 읽기/검토만 한 뒤 다음 단계로 간다.
4. source가 `wiki` corpus인지 `system` corpus인지 결정한다.
5. source page를 만들거나 갱신한다.
6. 관련 concept / synthesis page를 함께 갱신한다.
7. `system/system-raw-registry.md`를 갱신한다.
8. 해당 corpus router를 갱신한다.
   - content면 `wiki/index.md`
   - system이면 `system/system-index.md`
9. `system/system-log.md`에 append-only entry를 남긴다.
10. generated artifact가 필요한 경우 export를 갱신한 뒤, **로그까지 포함된 최종 working tree**에서 lint/eval/stage2를 실행한다.

기본 원칙:
- **single-source ingest를 기본값**으로 한다.
- batch ingest는 가능하지만, source trace는 source별로 구분한다.
- source 1개가 여러 page를 바꾸는 것을 정상 동작으로 본다.
- `source_type: domain-research-paper`는 generic source note가 아니라, research-source 확장 shape를 기본값으로 쓴다.
- 발견 단계에서 `unregistered_raw_file`를 먼저 식별하는 것은 괜찮지만, 실제 write 순서는 `markdown raw 정리 -> source/registry/router 갱신`을 기본값으로 둔다.
- 중간 진단용 lint는 필요할 때만 baseline으로 돌리고, 최종 통과 판정은 `system/system-log.md` append 이후 1회 lint를 기준으로 삼는다.

### B. Query

질문은 local corpus를 기준으로 답한다.

해야 할 일:
1. 질문 유형에 맞는 router를 먼저 읽는다.
   - 일반 content / 뉴스 / 도메인 질문: `wiki/index.md`
   - 시스템 / 운영 / 자기개선 질문: `system/system-index.md`
2. 관련 page를 선택적으로 읽는다.
3. raw registration 맥락이 필요할 때는 `system/system-raw-registry.md`를 본다.
4. wiki에 없는 근거가 필요할 때만 raw source를 다시 본다.
5. 재사용 가치가 큰 답은 `query--...md`로 저장할지 판단한다.
6. 새로운 synthesis가 생기면 `system/system-log.md`에 남긴다.

### C. Lint

주기적으로 위키 건강검진을 한다.

점검 항목:
- contradiction between pages
- stale claims superseded by newer sources
- orphan pages
- missing cross-references
- concepts/entities repeatedly mentioned but lacking canonical pages
- central research sources repeatedly reused but lacking anchor-layer explanation
- pages with weak source trace
- `index.md`와 실제 파일 구조 불일치
- raw path mismatch
- structural slop: duplicate syntheses, bloated pages, TODO sprawl

운영 순서:
- 작업 전 lint/eval은 현재 상태를 파악하기 위한 선택적 baseline이다.
- corpus나 mechanism을 수정했다면 `system/system-log.md`까지 먼저 갱신한다.
- closeout gate는 로그와 generated artifact를 포함한 최종 tree에서 한 번만 실행하는 것을 기본값으로 한다.
- 예외적으로 최종 gate가 실패해 page를 고친 경우에는, 다시 로그를 고치기 전에 필요한 수정만 하고 final gate를 재실행한다.

### D. Improve

위키 자체뿐 아니라 **위키를 유지하는 mechanism**을 개선한다.

해야 할 일:
1. `ops/evals/`의 policy-backed eval specs를 읽는다.
2. `make lint`와 `make eval` 결과를 본다.
3. 실패 패턴 하나를 고른다.
4. policy / template / script / page shape 중 **한 가지 메커니즘만** 바꾼다.
5. eval score가 개선되면 keep, 아니면 revert한다.
6. 결과를 `system/system-log.md`와 run ledger에 남긴다.
7. 최종 lint/eval/stage2는 log append 이후의 candidate tree에서 실행한다.

기본 원칙:
- **One mechanism per experiment**
- 기본값은 eval score improvement를 요구한다.
- 예외적으로 `system_mechanism`은 `candidate_eval == baseline_eval`일 때도 `lint/complexity/tests` secondary axis가 모두 비회귀이고 최소 1축이 엄격히 개선되면 promotion할 수 있다.
- prompt-only 개선보다 구조 개선을 우선한다.
- raw source fidelity를 깨는 수정으로 score를 올리는 행위는 금지한다. binary raw 수정은 물론 금지이고, markdown raw도 contract-limited normalization 범위를 넘는 의미 수정은 금지한다.

---

## 4. Local Maintenance Points

local full vault에서는 아래 surface가 필수 maintenance point다.

- `wiki/index.md`
- `system/system-index.md`
- `system/system-raw-registry.md`
- `system/system-log.md`

원칙:
- router, registry, log는 corpus mutation과 분리된 optional surface가 아니라 **필수 후속 maintenance point**다.
- `system/system-log.md`는 append-only다.
- raw registry는 ingest lifecycle을 관리하고, promotion ledger로 쓰지 않는다.
- `system/system-log.md`는 lint 대상에서 제외하지 않는다. 대신 workflow상 로그를 먼저 남기고 최종 lint를 1회만 실행해 중복 검증을 피한다.

---

## 5. Local Layout And Naming

full local vault 기본 layout:

```text
raw/
runs/
  <run-id>/
wiki/
  index.md
  source--*.md
  concept--*.md
  synthesis--*.md
  query--*.md
  lint--*.md
system/
  system-index.md
  system-raw-registry.md
  system-log.md
  source--*.md
  concept--*.md
  synthesis--*.md
  query--*.md
  lint--*.md
```

규칙:
- content page는 계속 `wiki/` 루트의 플랫 구조를 기본값으로 유지한다.
- maintainer/runtime page는 `system/` 루트에 둔다.
- 구조화는 폴더 분할보다 `index`와 prefix로 해결한다.

reserved system page:
- `system-index.md`
- `system-raw-registry.md`
- `system-log.md`

prefix 규칙:
- `source--...md`
- `concept--...md`
- `entity--...md`
- `synthesis--...md`
- `query--...md`
- `lint--...md`

---

## 6. Frontmatter Contract

모든 `wiki/` / `system/` page는 YAML frontmatter를 가진다.

공통 최소 필드:
- `title`
- `page_type`
- `corpus`
- `aliases`
- `tags`

page type별 권장 필드:
- source page
  - `registry_id`
  - `raw_path`
  - `source_type`
  - `research_mode` for `source_type: domain-research-paper`
  - `domain`
- concept page
  - `canonical: true`
- synthesis / query page
  - `source_count`
- reserved page
  - `special_role`

목적:
- Obsidian `Properties`, `All Properties`, `Bases`에서 corpus/type/domain 기준 탐색이 가능하게 한다.
- file name만 보지 않고도 page 역할을 즉시 드러낸다.
- future lint / eval / graph ergonomics 개선의 기반을 만든다.

---

## 7. Page Shape

### Source page minimum
- Title
- Source
- Type
- Summary
- Why it matters
- Key points
- Limitations / caveats
- Related pages
- Open questions
- Source trace

### Source page default extension for research sources
`source_type: domain-research-paper`는 아래 층을 기본 shape로 본다.

- `research_mode: experiment|model|reference`
- Research frame
  - design / scope
  - what it establishes
  - transfer limits
- What this source adds to the corpus
- How strong is the evidence

### Source page preferred expansion for anchor sources
- What this source does not establish

### Source page preferred expansion for seed sources
- Provisional thesis
- Why this is source-only for now
- What future cluster would absorb this

### Concept page minimum
- Summary
- Why it matters here
- Main body
- Scope boundaries
- Examples and non-examples
- How to reuse this concept
- Related pages
- Open questions
- Source trace

### Concept page preferred expansion for canonical concepts
- Signals for future ingest

### Synthesis page minimum
- Question
- Short answer
- Evidence considered
- Analysis
- Decision / takeaway
- Follow-up questions
- What this synthesis excludes
- Tensions / contradictions
- Implications for future ingest

### Query page minimum
- Question
- Short answer
- Evidence considered
- Analysis
- Decision / takeaway
- Follow-up questions

### Lint page minimum
- Summary
- Findings
- Recommended fixes
- Source trace

---

## 8. Local Promotion And Run Rules

promotion event가 명시적으로 필요한 경우에는 아래 순서를 따른다.

1. `make check`로 repo health 확인
2. `llm-wiki-promotion-gate --vault . --run-id <run-id> --out runs/<run-id>/promotion-report.json ...`로
   promotion report 생성
3. `system_mechanism`이면 baseline/candidate mechanism assessment artifact도 함께 만든다.
   - 권장 경로: `runs/<run-id>/baseline-mechanism-assessment.json`
   - 권장 경로: `runs/<run-id>/candidate-mechanism-assessment.json`
4. signoff가 필요한 class만 승인 대기
5. `system/system-log.md`에 append
6. live repo closeout이 필요하면 log append 이후의 최종 tree에서 lint/eval/stage2 또는 `make check`를 실행

권장 target 순서:
1. template / schema 누락
2. broken link / weak trace
3. page sprawl / duplicate synthesis
4. query capture 누락
5. command / script ergonomics
6. meta-loop 정책 자체

---

## 9. Optional Planning-Gate Convention

major synthesis, planning bundle, stage handoff 문서는 아래 상태 전이를 따를 수 있다.

`REQUEST_IN -> INTERVIEW -> SEED_DRAFT -> SEED_FROZEN -> PLAN_DRAFT -> VALIDATION -> WAITING_SIGNOFF -> READY|BLOCKED`

이 규칙은 모든 page에 강제되지 않는다.
하지만 아래 경우에는 강하게 권장한다.

- planning harness 관련 문서
- stage handoff 문서
- spec freeze가 필요한 프로젝트
- 여러 세션/여러 에이전트가 이어받는 작업

---

## 10. Scaling Rule And Standing Priorities

flat wiki는 아래가 발생하기 전까지 유지한다.

- wiki page 수 150+
- 동일 prefix page 수 40+
- index 탐색 비용이 명백히 증가
- 사람이 구조 재편을 원함

현재 우선순위:
1. `system/lint--initial-review-2026-04-12.md`는 historical bootstrap baseline으로
   참조하고, 현재 queue는 live lint/eval/stage2와 observation/backlog artifact를
   기준으로 판단한다.
2. source / concept / synthesis canonical page를 source trace가 지지하는 범위에서 지속 확충한다.
3. closeout은 `make lint`, `make eval`, `make stage2-eval`, 필요 시 `make check`를 현재 tree에서 실행해 판단한다.
4. major planning work에는 seed freeze + planning gate를 적용한다.
5. meta-loop는 prompt-only convention보다 policy/script/test-backed automation으로 발전시킨다.
