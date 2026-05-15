# LLM Wiki vNext 정밀 검토 및 개선 방안 보고서 — 추가 리뷰 반영판

- 파일명: `llm_wiki_vnext_review_improvement_plan_revised_20260425.md`
- 작성일: 2026-04-25
- 작성 언어: 한국어
- 검토 대상: `LLM Wiki vNext(36).zip`
- 반영 대상 리뷰:
  - `anti_slop_self_improvement_review_20260425(1).md`
  - `llm_wiki_vnext_reaudit_report_20260425_v2.md`
  - `llm_wiki_vnext_integrated_report_20260425.md`
  - `llm_wiki_vnext_integrated_review_report_20260425.md`
- 기준 보고서: `llm_wiki_vnext_review_improvement_plan_20260425.md`
- 검토 원칙: 압축본 전체 해제, 코드·정책·스키마·테스트·생성 산출물의 상호 검증, private corpus 본문 비복사, 실행 증거 기반 보고

---

## 1. 이번 개선판의 결론

추가로 제공된 두 통합 리뷰에는 기존 보고서에 그대로 복사할 새 사실이 대량으로 있는 것은 아니다. 두 문서는 기존 상세 리뷰와 재감사 리뷰를 다시 통합한 성격이 강하며, 핵심 수치와 P0 항목 대부분은 이미 기준 보고서에 반영되어 있었다. 다만 아래 네 가지는 기존 보고서의 우선순위와 표현을 더 강화할 가치가 있었다.

1. **산출물 진실성(output truthfulness)을 P0로 격상**해야 한다. 단순히 JSON envelope를 붙이는 수준이 아니라, 보고서 생성 후 링크 제공 전 파일 존재 여부·크기·SHA-256을 검증하고, 보고서 상단에 Evidence Manifest를 자동 삽입하며, “확인됨/추론/미검증” 상태를 명시해야 한다.
2. **테스트 진입점 단순화는 fast-tier 개선과 분리된 P1 과제**로 다뤄야 한다. fast suite가 무거운 문제와, `pytest -q`가 환경 정렬 없이 실행될 때 실패하는 문제는 원인이 다르다. 전자는 duration/marker 설계 문제이고, 후자는 bootstrap UX와 패키지 경로 contract 문제다.
3. **CLI cold-start는 재현된 버그가 아니라 회귀 방지 budget**으로 다뤄야 한다. 추가 리뷰는 `mechanism_review.py --help` 타임아웃을 언급하지만, 기준 보고서의 재검증에서는 5개 CLI help가 0.99~2.07초 내 응답했다. 따라서 “현재 결함”으로 단정하지 않고, help path에서 heavy import/IO를 금지하는 soft budget과 profiling artifact를 두는 방식이 맞다.
4. **self-improvement loop의 품질 증거를 ledger/ROI 체계로 묶어야 한다.** 기존 보고서의 anti-slop scoreboard에 더해, Proposal → Execution → Outcome → Regression Check를 하나의 ID로 연결하고, 채택되지 않은 제안의 기각 사유까지 negative memory로 남기는 구조가 필요하다.

따라서 개선판의 최종 우선순위는 다음이다.

- **P0:** 산출물 진실성, generated artifact envelope/currentness, 직접 시간 호출 제거, release smoke timeout, strict preview 오류 수정, optional JSON diagnostic.
- **P1:** self-improvement 입력 신뢰도, 테스트 진입 단순화, fast-smoke tier, CLI cold-start budget, closed-loop ledger.
- **P2:** runtime surface 분해, output path policy 명시화, policy exact enumeration drift 축소, report CLI helper 통합.
- **P3:** domain package 전환, semantic mechanism classifier, public export 후 leak/schema 검증 강화, anti-slop scoreboard 자동화.

---

## 2. Evidence Manifest

### 2.1 직접 확인한 입력 파일

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| `LLM Wiki vNext(36).zip` | 190,497,560 bytes | `153854374b5e43ae4ac67185695b1974000bd537e5430db746f83bd776b650c8` |
| `anti_slop_self_improvement_review_20260425(1).md` | 40,751 bytes | `c13bfa022d96d6e1200de5b370e1579f8518e7d700977796639d2757fe96f9cd` |
| `llm_wiki_vnext_reaudit_report_20260425_v2.md` | 9,993 bytes | `b127eba04f8315ae3e33215357e7553b89adfeff8e38d944e91f4d41d19a4d7d` |
| `llm_wiki_vnext_integrated_report_20260425.md` | 40,033 bytes | `4af0edc6e0177b0cf76a20b8ed479d901ec3aa5d46e37d70ed39ceabf1fcfdbc` |
| `llm_wiki_vnext_integrated_review_report_20260425.md` | 50,733 bytes | `261a9d339ec3678455226360868dad2c60c0531b7f4982ae96c7f48f5bf77d12` |
| `llm_wiki_vnext_review_improvement_plan_20260425.md` | 39,414 bytes | `2918e4de5ba483c5ad0f9e1855b41fcc5649186e562ae1ab0e086ce8e13b5097` |

### 2.2 기존 ZIP/저장소 검증 상태

기준 보고서의 실행 검증은 그대로 유지한다.

| 검증 항목 | 결과 | 판정 |
|---|---|---|
| ZIP 엔트리 수 | 1,595 | 전체 해제 대상과 일치 |
| ZIP CRC 검사 | 오류 없음 | 무결성 기본 조건 충족 |
| 해제 후 실파일 수 | 1,526 | 기존 리뷰 수치와 일치 |
| Python 파일 | 276 | 전체 compile/import 검증 대상 |
| Python LOC | 약 71,885 | runtime 규모 판단 기준 |
| `ops/scripts` 모듈 import | 153개 실패 0 | 기본 import surface 양호 |
| 핵심 저장소 gate | raw registry, wiki lint/eval/stage2, planning, warning budget 통과 | 기능적 기반은 안정 |
| artifact freshness | gate 통과이나 attention/debt 큼 | P0 개선 필요 |
| structural complexity | failure 없음, attention 있음 | P1~P2 개선 필요 |
| full fast/release smoke | 완료 주장 불가 | 별도 CI/로컬 장시간 검증 필요 |

### 2.3 주장 상태 구분

| 주장 유형 | 본 보고서 처리 |
|---|---|
| 직접 재검증된 사실 | 압축 해제, 파일 수, 해시, 주요 static/import/gate 결과, 기준 보고서의 실행 로그 기반 수치 |
| 독립 리뷰와 상호 확인된 판단 | artifact currentness debt, runtime surface 과밀, fast tier 비대화, self-improvement scoreboard 부족 |
| 이번 환경에서 갱신된 판단 | `mechanism_review --help` 지연은 재현되지 않았으므로 현재 결함이 아니라 cold-start regression budget으로 유지 |
| 미완료/미검증 | 전체 fast suite와 release smoke 완주, 모든 legacy artifact migration 가능성, 실제 개선 PR 적용 후 효과 |

---

## 3. 추가 두 리뷰에서 가져올 내용 판정

### 3.1 즉시 반영한 내용

| 반영 내용 | 반영 위치 | 이유 |
|---|---|---|
| Evidence Manifest 자동 삽입 | P0 산출물 진실성 | 보고서와 실물의 불일치를 막는 가장 실용적인 장치 |
| 파일 존재/크기/SHA-256 링크 gate | P0 산출물 진실성 | 다운로드 링크 제공 전 물리적 산출물 검증을 강제 |
| 확인됨/추론/미검증 문장 상태 분리 | Evidence Manifest, acceptance criteria | “그럴듯한 보고”와 “검증된 보고”를 분리 |
| `make test`/bootstrap 단일화 | P1 테스트 진입 단순화 | fast tier와 별개의 developer UX 문제 |
| CLI `--help` cold-start budget | P1 CLI 운영성 | 재현 여부와 관계없이 회귀 방지 가치가 큼 |
| `filesystem_runtime.py`, `auto_improve_session_runtime.py`, `codex_exec_executor.py` 분해 후보 추가 | P2 구조 개선 | 기존 후보보다 더 넓은 runtime surface 관리 필요 |
| Proposal → Execution → Outcome → Regression Check ledger | P1 self-improvement 품질 | 개선안의 실제 효과를 추적 가능하게 함 |
| rejected proposal negative memory | P1 self-improvement 품질 | 반복 제안과 무의미한 재시도를 줄임 |
| 새 runtime 모듈 추가 전 registry/reuse gate | P2 구조 관리 | self-improvement 계층 자체의 비대화를 방지 |

### 3.2 이미 기준 보고서에 반영되어 있어 중복만 제거한 내용

| 내용 | 처리 |
|---|---|
| JSON artifact 143개 중 envelope/currentness debt 다수 | 기존 P0 currentness/envelope 부채에 이미 반영되어 유지 |
| `source_slug_curation.py` 직접 `datetime.now()` | 기존 P0 유지 |
| `release_smoke.py` timeout 없는 `subprocess.run()` | 기존 P0 유지 |
| strict ruff preview import 정렬 I001 | 기존 P0 유지 |
| optional JSON load silent fallback | 기존 P0~P1 유지 |
| output path resolver 구분 필요 | 기존 P1 유지 |
| public/private export 후 leak 검증 | 기존 P2 유지 |
| policy exact enumeration drift | 기존 P2 유지 |
| fast-smoke tier와 pytest duration artifact | 기존 P1 유지 |

### 3.3 반영하지 않거나 낮은 우선순위로 둔 내용

| 내용 | 판단 |
|---|---|
| `mechanism_review.py --help`가 현재도 무겁다는 단정 | 기준 보고서 재검증에서 재현되지 않았으므로 버그로 단정하지 않음. soft budget/benchmark로만 반영 |
| `review/` 빈 디렉터리를 독립 P0 리스크로 격상 | 빈 디렉터리는 혼동 가능성이 있으나, 실제 pipeline sink로 쓰인다는 증거가 없으므로 P3 hygiene로 분류 |
| 모든 legacy generated artifact를 단번에 migration | scope가 크고 회귀 위험이 큼. 신규/touched canonical report부터 강제하고 legacy는 trend로 관리 |
| “전체 테스트 실패”라는 표현 | 환경/시간 제한과 suite 규모 문제를 분리해야 하므로 “전체 통과 미주장”으로 표현 |

---

## 4. 최종 핵심 진단

### 4.1 저장소 성격

`LLM Wiki vNext(36).zip`은 단순 위키 파일 묶음이 아니다. 실제 성격은 다음이 결합된 운영형 저장소다.

1. persistent wiki maintainer runtime
2. self-improvement proposal/evaluation/promotion loop
3. public/private mirror export contract
4. schema-backed generated report system
5. raw/wiki/system/runs를 포함한 full-vault corpus
6. 서브에이전트 routing과 policy-driven validation

이 저장소의 개선 전략은 “기능 추가”가 아니라 **이미 있는 계약과 runtime safety 장치를 더 좁고 일관되게 강제하는 것**이어야 한다.

### 4.2 가장 큰 리스크: generated artifact 신뢰성

현 상태의 최대 리스크는 코드가 전혀 동작하지 않는 것이 아니다. 오히려 기본 gate는 상당수 통과한다. 문제는 report와 generated artifact가 self-improvement loop의 입력으로 쓰이기에는 최신성·생성 맥락·schema 소유권이 균일하지 않다는 점이다.

| 항목 | 관찰 | 리스크 |
|---|---:|---|
| JSON artifact | 143개 | 판단 입력이 많음 |
| missing artifact envelope | 136개 | 생성자·명령·입력 fingerprint 불명확 |
| unknown currentness | 136개 | 현재 상태 판단 근거로 쓰기 어려움 |
| missing generated_at | 58개 | 시계열 비교 불안정 |
| missing schema | 47개 | 구조 drift 탐지 어려움 |
| stale artifact | 84~85개 | 수동 수정/미재생성 가능성 |

### 4.3 두 번째 리스크: feedback loop의 실제 사용성

테스트와 CLI가 “존재한다”는 것과 “자주, 안전하게, 예측 가능하게 돌릴 수 있다”는 것은 다르다. 현재는 targeted gate는 강하지만 full fast/release smoke 완주를 이번 환경에서 주장할 수 없고, `pytest -q` 직접 실행 시 bootstrap 전제 때문에 오판이 생길 수 있다.

따라서 `make dev-install && make smoke` 또는 `make fast-smoke` 같은 단일 경로를 강화하고, full fast는 duration artifact와 top slow test warning으로 관리해야 한다.

### 4.4 세 번째 리스크: self-improvement loop의 입력/출력 추적성

자가 개선 루프는 구조적으로 풍부하지만, 현재 readiness가 runnable하지 않거나 history/proposal 신뢰도가 부족한 상태에서는 loop를 더 돌리는 것이 곧 개선을 뜻하지 않는다. 먼저 proposal ledger, run history validity, artifact freshness, outcome/regression 연결을 복구해야 한다.

---

## 5. 개선 방안 상세

### 5.1 P0 — 산출물 진실성 gate 도입

**문제:** 보고서와 실물 파일의 불일치가 생기면, 이후 판단 전체가 오염된다.

**개선:**

1. 모든 보고서 생성 command는 최종 출력 전에 다음을 기록한다.
   - output path
   - file exists
   - byte size
   - SHA-256
   - generated_at
   - producer command
2. 다운로드/배포 링크를 출력하기 전 위 정보를 검증한다.
3. 보고서 상단에는 Evidence Manifest를 자동 삽입한다.
4. 문장 또는 섹션 단위로 `확인됨`, `상호확인`, `추론`, `미검증` 상태를 구분한다.
5. 미검증 주장은 본문 핵심 결론에 섞지 않고 “검증 한계” 또는 “추가 확인 필요” 섹션으로 분리한다.

**완료 기준:**

- 새로 생성되는 보고서 100%가 파일 크기와 SHA-256을 포함한다.
- 링크 제공 전 존재하지 않는 파일을 감지하면 실패한다.
- evidence manifest가 없는 신규 canonical report는 CI에서 실패한다.

### 5.2 P0 — generated artifact envelope/currentness 통일

**문제:** artifact freshness debt가 self-improvement 판단의 가장 큰 slop 원천이다.

**개선:**

1. 공통 report envelope를 새 canonical report에 강제한다.
2. legacy artifact는 바로 실패시키지 않고 `legacy_report`로 분류한다.
3. artifact freshness report는 top debt list와 owner surface를 출력한다.
4. stale artifact는 단순 오래됨이 아니라 `generated_at_older_than_file_mtime` severity로 분리한다.
5. `generated_artifact_index`는 `canonical/current/legacy/ephemeral` role을 가진다.

**공통 envelope 예시:**

```json
{
  "$schema": "ops/schemas/<schema>.json",
  "artifact_kind": "<kind>",
  "generated_at": "<iso8601-z>",
  "producer": "ops.scripts.<module>",
  "source_command": "python -m ops.scripts.<module> ...",
  "source_tree_fingerprint": "<hash>",
  "input_fingerprints": {},
  "schema_version": "1",
  "artifact_status": "current",
  "retention_policy": "canonical",
  "currentness": {"status": "known"}
}
```

### 5.3 P0 — direct datetime 제거

**문제:** `source_slug_curation.py`가 직접 `datetime.now(dt.timezone.utc)`를 사용한다.

**개선:**

- `scaffold_manifest(..., context: RuntimeContext | None = None)` 형태로 변경한다.
- CLI 경로는 policy-derived `RuntimeContext`를 사용한다.
- frozen-clock regression test를 추가한다.
- production path에서 `datetime.now(`, `utcnow(` 사용을 정적 검사로 차단하되 `runtime_context.py`만 allowlist 처리한다.

### 5.4 P0 — release smoke timeout 적용

**문제:** `release_smoke.py`가 이미 존재하는 `command_runtime.run_with_timeout()`을 쓰지 않고 timeout 없는 `subprocess.run()`을 호출한다.

**개선:**

- smoke command 실행을 `run_with_timeout()` 기반으로 교체한다.
- timeout, timed_out, signal/termination reason, stdout/stderr tail을 report schema에 포함한다.
- timeout regression test를 추가한다.

### 5.5 P0 — optional JSON diagnostic variant

**문제:** optional JSON load 실패가 `{}`로 조용히 흡수되면 missing과 malformed를 구분할 수 없다.

**개선:**

- 기존 `load_optional_json_object()`는 compatibility를 위해 유지한다.
- `load_optional_json_object_with_diagnostics()`를 추가한다.
- 반환값에 `missing`, `decode_error`, `type_error`, `path`, `message`를 포함한다.
- mutation proposal, mechanism review, artifact freshness처럼 provenance-heavy caller부터 사용한다.

### 5.6 P1 — 테스트 진입 단순화

**문제:** `pytest -q` 직접 실행은 개발 설치/PYTHONPATH 전제를 모르면 코드 실패처럼 보일 수 있다.

**개선:**

1. README 최상단에 다음 경로를 고정한다.
   - `make dev-install`
   - `make smoke` 또는 `make fast-smoke`
   - `make check` 또는 CI full gate
2. `pytest -q` 직접 실행 시 필요한 editable install/PYTHONPATH 조건을 명시한다.
3. CI와 로컬 명령을 가능한 한 동일하게 둔다.
4. 빠른 실패 메시지를 제공하는 `scripts/dev_test` 또는 Make target을 추가한다.

### 5.7 P1 — fast-smoke와 duration artifact

**문제:** unmarked fast test 545개는 “fast”라는 이름에 비해 feedback loop로 무겁다.

**개선:**

- `fast-smoke` 또는 `contract-smoke` tier를 만든다.
- 포함 범위: schema sample, public surface, path/output/runtime context, artifact IO, raw registry preflight core, wiki eval minimal fixture.
- full fast tier는 유지하되 duration report를 생성한다.
- top slow fast tests를 warning budget과 연결한다.

### 5.8 P1 — CLI cold-start budget

**문제:** 이번 환경에서는 `mechanism_review --help` 지연이 재현되지 않았지만, help path가 heavy import/IO를 가져가면 사용성이 급격히 나빠진다.

**개선:**

- `--help` path는 filesystem scan, policy load, large report parse를 하지 않는다는 contract test를 둔다.
- 2~3초 soft budget으로 시작한다.
- cold-start profiling artifact를 optional report로 남긴다.
- 예산 초과 시 즉시 failure보다 warning budget으로 먼저 연결한다.

### 5.9 P1 — self-improvement ledger와 ROI

**문제:** mutation proposal과 outcome이 흩어져 있으면, 개선이 실제 slop을 줄였는지 판단하기 어렵다.

**개선:**

1. Proposal → Execution → Outcome → Regression Check를 하나의 `improvement_id`로 연결한다.
2. 각 개선안에 ROI 필드를 둔다.
   - `latency_saved`
   - `files_touched`
   - `tests_added`
   - `defect_prevented`
   - `artifact_debt_reduced`
   - `complexity_delta`
3. rejected proposal도 이유와 함께 남긴다.
4. 같은 follow-up을 새 파일로 반복 생성하지 않고 기존 ledger row를 갱신한다.
5. promotion gate는 currentness unknown artifact만 근거로 한 promotion을 hold한다.

### 5.10 P2 — runtime surface 분해

**문제:** runtime module이 커질수록 변경 영향 범위 추론과 테스트 실패 원인 파악이 어려워진다.

**우선 후보:**

| 파일 | 권장 분해 경계 |
|---|---|
| `auto_improve_readiness_runtime.py` | collector / evaluator / recommender / renderer / writer |
| `mutation_proposal_runtime.py` | evidence collection / scoring / blocker diagnostics / report assembly |
| `filesystem_runtime.py` | path guard / atomic write / copy tree / cleanup / diagnostics |
| `auto_improve_session_runtime.py` | session state / run history / retry policy / report output |
| `codex_exec_executor.py` | command construction / process execution / result parsing / artifact write |
| `raw_intake_promotion_validation_runtime.py` | profile별 rule table과 small predicate |

**원칙:** 파일을 무조건 쪼개는 것이 아니라, 상태 전이 경계와 side-effect boundary를 기준으로 분해한다.

### 5.11 P2 — output path policy 명시화

**문제:** `resolve_output_path()`와 `resolve_repo_output_path()`의 의도 차이가 CLI help에서 바로 보이지 않는다.

**개선:**

- 각 command help에 output class를 표시한다.
  - `repo_report`: vault 내부만 허용
  - `external_export`: 외부 출력 허용
  - `ephemeral_temp`: report 내부 path는 `<tmp>`로 sanitize
- resolver 사용 inventory를 생성한다.
- public/private boundary 관련 report는 기본적으로 repo-local resolver를 쓴다.
- 외부 export는 `--allow-outside-vault`처럼 의도를 드러낸다.

### 5.12 P2 — self-improvement 계층 비대화 방지

**문제:** `auto_improve_*`, `mechanism_*`, `promotion_*`, `review_*`, `runtime_*` 계열이 늘어날수록 자가 개선 구조 자체가 slop을 만들 수 있다.

**개선:**

- 새 runtime module 추가 전 기존 module 재사용 가능성을 점검한다.
- 동일 prefix module군의 목적/입력/출력/부작용을 registry table로 관리한다.
- “파일 추가”보다 “기존 파일 분해/역할 정리”를 먼저 검토한다.
- mechanism experiment는 changed-file semantic classifier로 one-mechanism 원칙을 검사한다.

---

## 6. 우선순위별 실행 로드맵

### P0 — 즉시 처리할 작은 수정

| # | 작업 | 대상 | 완료 기준 |
|---:|---|---|---|
| 1 | 산출물 진실성 gate | report writer / release output | output exists/size/SHA-256 검증 후 링크 제공 |
| 2 | Evidence Manifest 자동 삽입 | report writer helper | 신규 canonical report 상단에 manifest 포함 |
| 3 | artifact envelope 강제 | generated reports | 신규 report missing envelope 0 |
| 4 | artifact freshness top debt 출력 | `artifact_freshness_runtime.py` | owner/action이 보이는 top debt list 생성 |
| 5 | direct datetime 제거 | `source_slug_curation.py` | frozen-clock test 통과 |
| 6 | release smoke timeout | `release_smoke.py` | timeout regression test와 report metadata 포함 |
| 7 | strict ruff preview 수정 | `structural_complexity_budget_runtime.py` | import 정렬 I001 제거 |
| 8 | optional JSON diagnostics | `artifact_io_runtime.py` | missing/malformed 구분 가능 |

### P1 — 입력 신뢰도와 feedback loop 개선

| # | 작업 | 대상 | 완료 기준 |
|---:|---|---|---|
| 1 | generated artifact role taxonomy | artifact index | canonical/current/legacy/ephemeral 분류 |
| 2 | readiness blocker next action | auto-improve readiness | `no_history` 등 blocker별 remediation 명확화 |
| 3 | proposal ledger/ROI | mutation/outcome reports | improvement_id 기반 closed-loop 연결 |
| 4 | test bootstrap 단일화 | README/Makefile | `make dev-install && make fast-smoke` 표준화 |
| 5 | fast-smoke tier | pytest markers/Makefile | 1~2분 내 핵심 contract 검증 |
| 6 | duration artifact | test tooling | top slow fast tests 자동 보고 |
| 7 | CLI cold-start budget | CLI tests | help path 2~3초 soft budget과 no heavy IO contract |

### P2 — 구조 정리

| # | 작업 | 대상 | 완료 기준 |
|---:|---|---|---|
| 1 | readiness runtime 분해 | `auto_improve_readiness_runtime.py` | collector/evaluator/renderer/writer 분리 |
| 2 | mutation proposal 분해 | `mutation_proposal_runtime.py` | evidence/scoring/report assembly 분리 |
| 3 | filesystem/session/executor 분해 | 대형 runtime 3종 | side-effect boundary 명확화 |
| 4 | raw intake validator 단순화 | validation runtime | 복잡도 높은 validator rule table화 |
| 5 | output path inventory | output runtime + CLI | command별 output class 명시 |
| 6 | policy pattern rule | policy/schema/tests | shard exact enumeration 감소 |

### P3 — 장기 운영 개선

| 작업 | 기대 효과 |
|---|---|
| anti-slop scoreboard 자동 첨부 | currentness, complexity, warning, duration을 한 화면에서 판단 |
| mechanism semantic classifier | one-mechanism-per-experiment 원칙 자동 판정 |
| public export post-check 강화 | private path leak, manifest schema, generated report leak 방지 |
| domain package 전환 | flat `ops/scripts` surface 축소, compatibility facade 유지 |
| improvement negative memory | 반복 제안과 무의미한 mutation 감소 |
| 빈/오해 가능 디렉터리 hygiene | `review/`처럼 빈 컨테이너의 역할 명확화 |

---

## 7. 권장 acceptance criteria

향후 개선 PR 또는 mechanism experiment는 다음 기준을 만족해야 한다.

| # | 기준 |
|---:|---|
| 1 | 수정이 하나의 primary mechanism axis에 묶인다 |
| 2 | 필요한 README/test/schema/policy 동반 갱신이 명확하다 |
| 3 | generated report는 schema와 공통 envelope를 가진다 |
| 4 | 보고서/다운로드 artifact는 존재 여부, 크기, SHA-256이 검증된다 |
| 5 | `RuntimeContext`가 필요한 시간 로직은 injected clock으로 테스트된다 |
| 6 | `subprocess` 실행 path는 timeout/termination metadata를 가진다 |
| 7 | optional fallback은 diagnostic으로 관찰 가능하다 |
| 8 | touched surface의 ruff/mypy/pytest가 통과한다 |
| 9 | artifact freshness debt가 신규로 늘지 않는다 |
| 10 | structural complexity touched gate가 새 attention을 만들지 않는다 |
| 11 | public/private boundary를 깨지 않는다 |
| 12 | proposal/outcome/regression artifact가 같은 improvement_id로 연결된다 |
| 13 | 미검증 주장은 본문 핵심 결론에 섞지 않고 별도 상태로 표시된다 |

---

## 8. 파일별 구체 권고

### `ops/scripts/source_slug_curation.py`

- 직접 `datetime.now(dt.timezone.utc)` 호출을 제거한다.
- `RuntimeContext`를 주입하고 frozen-clock test를 추가한다.
- production code direct time call static check의 첫 번째 적용 대상으로 삼는다.

### `ops/scripts/release_smoke.py`

- timeout 없는 `subprocess.run()`을 `command_runtime.run_with_timeout()`으로 교체한다.
- timeout result, signal, stdout/stderr tail, command duration을 report schema에 포함한다.
- release smoke가 hang될 경우도 실패 artifact를 남기게 한다.

### `ops/scripts/artifact_io_runtime.py`

- `load_optional_json_object_with_diagnostics()`를 추가한다.
- 기존 tolerant API는 유지하되, provenance-heavy caller는 diagnostic variant로 이동한다.
- decode/type error는 warning budget 또는 artifact freshness debt로 연결한다.

### `ops/scripts/artifact_freshness_runtime.py`

- pass/fail 외에 top debt list, owner surface, recommended next action을 출력한다.
- `generated_at_older_than_file_mtime`를 별도 severity로 분리한다.
- 신규 canonical report의 envelope missing은 hard fail로 올린다.

### `ops/scripts/auto_improve_readiness_runtime.py`

- readiness 판단을 evidence collection, blocker evaluation, recommendation rendering으로 나눈다.
- `no_history` 같은 blocker에 대해 next smallest action을 report에 직접 노출한다.
- proposal ledger/ROI와 연결해 “개선 가능”의 근거를 다축화한다.

### `ops/scripts/mutation_proposal_runtime.py`

- stale/unknown artifact input을 scoring에서 감점하거나 diagnostic으로 표시한다.
- slop reduction score를 추가한다.
- rejected proposal의 reason을 ledger에 남긴다.

### `ops/scripts/filesystem_runtime.py`

- atomic write, path guard, cleanup, copy tree, diagnostics를 내부 helper 단위로 분리한다.
- public/private path guard contract를 별도 testable surface로 둔다.

### `ops/scripts/auto_improve_session_runtime.py`

- session state, run history validation, retry policy, output artifact write를 분리한다.
- invalid/missing history가 readiness 판단에 어떻게 반영되는지 명시한다.

### `ops/scripts/codex_exec_executor.py`

- command construction, process execution, result parsing, artifact writing을 분리한다.
- timeout-aware command runtime과의 중복/불일치를 줄인다.

### `tests/minimal_vault_seed_core.py`, `tests/minimal_vault_seed_smoke.py`

- 긴 fixture builder를 source page, registry shard, system log, eval fixture 등 의미 단위 mini-builder로 분리한다.
- fixture DSL을 새로 크게 만들기보다 named helper 3~5개로 시작한다.

### `ops/policies/wiki-maintainer-policy.yaml`

- shard-specific exact list와 pattern rule을 분리한다.
- `system/system-raw-registry/wiki/*.md` 공통 section set을 pattern으로 관리한다.
- 예외 shard만 exact override로 남긴다.

---

## 9. 제안하는 다음 8개 PR/experiment

1. **Report output verification PR**
   - 보고서 생성 후 exists/size/SHA-256 확인 helper 추가.
   - Evidence Manifest 자동 삽입.

2. **Generated report envelope PR**
   - 신규 canonical report writer부터 공통 envelope 강제.
   - artifact freshness top debt 출력.

3. **RuntimeContext cleanup PR**
   - `source_slug_curation.py` direct datetime 제거.
   - frozen-clock regression 추가.

4. **Release smoke timeout PR**
   - `run_with_timeout()` 연결.
   - timeout test와 report schema 갱신.

5. **Optional JSON diagnostics PR**
   - diagnostic loader 추가.
   - mutation/mechanism/artifact freshness caller 일부 전환.

6. **Bootstrap and fast-smoke PR**
   - README 3-step bootstrap 고정.
   - `make fast-smoke` 추가.
   - pytest duration artifact 초안 생성.

7. **Self-improvement ledger PR**
   - improvement_id, status, outcome, regression check, ROI, rejected reason 필드 도입.
   - duplicate follow-up 방지 dedupe key 추가.

8. **Runtime surface first split PR**
   - `auto_improve_readiness_runtime.py` 또는 `mutation_proposal_runtime.py` 중 하나만 선택.
   - collector/evaluator/renderer/writer 중 가장 독립적인 부분부터 분리.

---

## 10. 검증 한계

1. 추가로 제공된 두 통합 리뷰는 대부분 기존 두 리뷰의 재통합물이므로, 완전히 독립적인 새로운 실행 증거로 취급하지 않았다.
2. 이번 개선판은 기준 보고서와 추가 리뷰 문서의 교차 검토 결과를 반영한 보고서 개선 작업이며, 저장소 코드에 PR을 적용한 것은 아니다.
3. full fast suite와 release smoke 전체 완주는 이번 보고서에서 주장하지 않는다.
4. `mechanism_review --help` 지연은 추가 리뷰에는 있으나 기준 보고서 재검증에서는 재현되지 않았으므로, 현재 결함이 아니라 회귀 방지 예산으로만 반영했다.
5. private corpus 본문은 보고서에 복사하지 않았고, 구조·코드·테스트·generated artifact 상태 중심으로만 기술했다.
6. 모든 legacy generated artifact의 migration 난이도는 실제 PR 적용 전까지 정확히 산정할 수 없다.

---

## 11. 최종 판단

추가 두 리뷰에서 가져올 핵심은 새로운 대형 리팩터링 목록이 아니라, **보고서와 산출물 자체의 진실성을 P0로 고정하고, 테스트/CLI/self-improvement 루프의 사용성을 더 운영 가능한 형태로 묶는 것**이다.

기준 보고서의 핵심 판단은 유지된다. 다만 이번 개선판에서는 다음 세 가지를 더 강하게 반영했다.

1. 보고서 링크와 generated artifact는 반드시 Evidence Manifest와 물리적 검증을 가져야 한다.
2. fast tier, bootstrap, CLI cold-start는 각각 별도 feedback-loop 문제로 분리해 관리해야 한다.
3. self-improvement는 proposal을 더 많이 만드는 것이 아니라, proposal의 근거·실행·결과·회귀 검증을 같은 ledger로 묶을 때 품질이 올라간다.

따라서 다음 작업은 “전체 구조를 한 번에 갈아엎기”가 아니라, P0의 8개 작은 수정부터 순차적으로 적용하는 것이다. 그중에서도 **산출물 진실성 gate, artifact envelope, RuntimeContext cleanup, release smoke timeout**이 가장 먼저 처리되어야 한다.
