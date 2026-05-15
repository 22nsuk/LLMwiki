# LLM Wiki vNext Review Improvement Report

- 작성일: 2026-04-27
- 작성 언어: 한국어
- 출력 파일명: `llm_wiki_vnext_review_improvement_report_20260427.md`
- 신규 검토 입력:
  1. `llm_wiki_vnext_integrated_review_report_20260427.md`
  2. `llm_wiki_vnext_unified_review_report_20260427.md`
- 기존 기준선 리뷰:
  1. `llm_wiki_vnext_integrated_review_report_20260426.md`
  2. `llm_wiki_vnext_anti_slop_improvement_report_20260426.md`
- 실제 재검증 대상 ZIP: `LLM Wiki vNext(44).zip`
- 실제 재검증 기준 SHA-256: `86596f5054ee1b286886c86626e656e002066389e68eb15563152e9c84d5ea30`

---

## 1. 목적

이 문서는 2026-04-27에 작성된 두 개의 신규 통합 리뷰를 **누락 없이 교차 검토**하고, 기존 기준선 리뷰(v42 계열) 및 실제 ZIP/실제 산출물 재검증 결과와 대조하여 다음을 정리한다.

1. **신규 리뷰들이 공통으로 옳게 잡아낸 개선점**
2. **기존 리뷰 대비 실제로 완료되었거나 크게 진전된 작업분**
3. **아직 남아 있는 작업분**
4. **신규 리뷰의 서술을 실제 파일 기준으로 보정해야 하는 부분**
5. **이번 대조 과정에서 새로 식별된 개선 방안**

이 보고서의 판단 원칙은 단순하다.

- 리뷰들끼리 합의하더라도 **실제 ZIP/실제 산출물/실제 재실행으로 다시 확인되지 않으면 우선순위를 낮춘다.**
- 좋아 보이는 문장보다 **운영 루프와 release portability를 실제로 바꾸는 항목**을 먼저 잡는다.
- **queue가 열렸는지**, **artifact contract가 정리됐는지**, **release artifact가 이식 가능한지**, **learning evidence가 충분한지**를 서로 다른 층위로 분리해서 본다.

---

## 2. 검토 대상과 동일성 판정

### 2.1 현재 체크포인트와 기존 기준선은 다른 세대다

기존 2026-04-26 리뷰들이 본 기준선 ZIP과 현재 검토 대상 ZIP은 서로 다르다.

| 항목 | 기존 기준선 v42 | 현재 체크포인트 |
|---|---:|---:|
| ZIP SHA-256 | `6f2c8f491b759bdc413455a020d770979deb0566bfc6d8444f72129ba709f0f6` | `86596f5054ee1b286886c86626e656e002066389e68eb15563152e9c84d5ea30` |
| ZIP 크기 | 273,066,366 bytes | 191,228,755 bytes |
| ZIP entry 수 | 11,552 | 1,634 |
| 파일 수 | 10,595 | 1,561 |
| 디렉터리 수 | 957 | 73 |
| `.venv` / `.venv-py312` 포함 | 예 | 아니오 |
| `candidates_emitted` | 0 | 1 |
| `proposals_emitted` | 0 | 1 |
| `can_run` | false | true |
| `schema_invalid_artifact_count` | 12 | 0 |

따라서 기존 리뷰의 결론을 현재 체크포인트에 그대로 옮기면 정확도가 떨어진다. 이번 개선 보고서는 **기존 리뷰를 기준선으로 삼되, 현재 ZIP에 맞게 재판정**한다.

### 2.2 두 신규 리뷰는 같은 현재 체크포인트를 본다

이번에 업로드된 두 신규 리뷰는 모두 SHA-256 `86596f...` 체크포인트를 기준으로 하고 있으며, 서로의 방향성은 거의 같다. 둘 다 다음을 공통으로 주장한다.

- self-improve execution queue는 v42 대비 실제로 복구되었다.
- schema-invalid debt는 해소되었다.
- release hygiene는 크게 나아졌다.
- 그러나 POSIX portability, artifact contract debt, session/outcome evidence 부족은 여전히 남아 있다.

이 큰 방향은 **실제 재검증 결과와 일치**한다.

---

## 3. 실제 ZIP 및 실제 파일 재검증 결과

### 3.1 ZIP 무결성 및 기본 구조

실제 ZIP(`LLM Wiki vNext(44).zip`)을 직접 확인한 결과는 아래와 같다.

| 항목 | 값 |
|---|---:|
| SHA-256 | `86596f5054ee1b286886c86626e656e002066389e68eb15563152e9c84d5ea30` |
| ZIP entry 수 | 1,634 |
| 파일 수 | 1,561 |
| 디렉터리 수 | 73 |
| 압축 해제 전체 바이트 합 | 240,600,720 bytes |
| Python `zipfile.testzip()` | `None` (CRC 오류 없음) |
| Python `zipfile.extractall()` | 성공 |

최상위 파일 분포:

| 상위 경로 | 파일 수 |
|---|---:|
| `raw` | 446 |
| `wiki` | 417 |
| `ops` | 276 |
| `runs` | 156 |
| `tests` | 121 |
| `system` | 71 |
| `external-reports` | 32 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |

확장자 분포:

| 확장자 | 파일 수 |
|---|---:|
| `.md` | 941 |
| `.py` | 276 |
| `.json` | 215 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.yaml` | 13 |
| `.toml` | 10 |
| 확장자 없음 | 5 |
| `.jsonl` | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

### 3.2 정적 위생

직접 검증한 결과:

| 검증 | 결과 |
|---|---|
| 비-venv Python `py_compile` (276개) | 오류 0 |
| repo-owned JSON parse (215개) | 오류 0 |
| `python3 -m ruff check ops/scripts tests tools` | 통과 |
| `python3 tools/ruff_strict_preview.py` | 통과 |
| `python3 -m ops.scripts.auto_improve_readiness --vault . --out ...` | 실행 성공 |
| local schema invalid artifact | 0 |

즉 현재 코드는 **문법/JSON 파싱/기본 lint 차원에서 무너진 상태가 아니다.**

### 3.3 mechanism review 실제 재실행

직접 재실행 결과:

| 항목 | 값 |
|---|---:|
| `runs_discovered` | 7 |
| `runs_considered` | 6 |
| `runs_skipped` | 1 |
| `candidates_emitted` | 1 |
| `candidate_blockers` | 0 |

생성된 candidate:

- `mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime`
- primary target: `ops/scripts/auto_improve_iteration_persistence_runtime.py`

남은 skipped run:

- `run-20260422-auto-improve-decision-record-fallback`
- 문제: `runs/run-20260422-auto-improve-decision-record-fallback/candidate-eval.json` missing artifact
- triage 추천: `restore_missing_artifact_or_archive_run_history`

### 3.4 mutation proposal 실제 재실행

직접 재실행 결과:

| 항목 | 값 |
|---|---:|
| `source_candidates_read` | 1 |
| `log_entries_scanned` | 5 |
| `proposals_emitted` | 1 |
| `blocked_proposals` | 0 |
| `candidate_blocker_count` | 0 |
| `proposal_blocker_count` | 0 |
| `queue_pressure_summary` | `session unavailable | contract_regression_signals 1 proposal` |

생성된 proposal:

- `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime`
- failure mode: `repeated_same_eval_or_discard`
- primary target: `ops/scripts/auto_improve_iteration_persistence_runtime.py`

즉 기존 기준선의 `0 candidates → 0 proposals` 병목은 현재 체크포인트에서 실제로 끊어졌다.

### 3.5 auto-improve readiness 실제 재생성

CLI로 readiness를 다시 생성한 결과:

#### execution readiness

| 항목 | 값 |
|---|---|
| `status` | `pass` |
| `can_run` | `true` |
| `runnable_proposal_count` | 1 |
| `blocked_proposal_count` | 0 |
| `gate_effect` | `active` |

#### learning readiness

| 항목 | 값 |
|---|---|
| `status` | `learning_uncertain` |
| `gate_effect` | `review_required` |
| `attempts_considered` | 7 |
| `min_attempts_considered` | 10 |
| `session_reports_considered` | 0 |
| `session_calibration_status` | `no_session_context` |
| 주요 경고 | `high_rework`, `defect_escape_proxy`, `recent_hold_moving_average` |

#### queue / diagnostics

| 항목 | 값 |
|---|---|
| `queue.ready` | `true` |
| `queue.runnable_proposal_count` | 1 |
| `queue.session_reports_considered` | 0 |
| `queue.attempts_considered` | 7 |
| `diagnostics.loop_health_summary.status` | `missing` |

결론적으로 현재 상태는 아래처럼 읽어야 정확하다.

> **실행 큐는 열렸다. 그러나 학습 근거와 session/loop-health 증거는 아직 약하다.**

즉 `can_run=true`는 맞지만, 이것을 곧바로 “완전 안정화”라고 해석하면 안 된다.

### 3.6 artifact freshness 실제 대조

현재 ZIP 안에 포함된 저장본과, 실제 런타임으로 다시 계산한 값 사이에 차이가 있었다.

#### ZIP 안 저장본 요약

| 항목 | 값 |
|---|---:|
| `stale_artifact_count` | 59 |
| `mtime_sensitive_artifact_count` | 59 |
| `unknown_currentness_artifact_count` | 109 |
| `missing_artifact_envelope_count` | 109 |
| `missing_schema_count` | 17 |
| `schema_invalid_artifact_count` | 0 |
| `safe_to_backfill_artifact_count` | 87 |

#### 현재 환경에서 runtime 재계산 값

| 항목 | 값 |
|---|---:|
| `artifact_count` | 146 |
| `json_artifact_count` | 146 |
| `stale_artifact_count` | 82 |
| `mtime_sensitive_artifact_count` | 82 |
| `unknown_currentness_artifact_count` | 109 |
| `missing_artifact_envelope_count` | 109 |
| `missing_schema_count` | 17 |
| `schema_invalid_artifact_count` | 0 |
| `safe_to_backfill_artifact_count` | 64 |

이 차이는 중요하다. `missing_artifact_envelope` / `unknown_currentness` / `missing_schema`는 안정적으로 같지만, `stale_artifact_count`, `mtime_sensitive_artifact_count`, `safe_to_backfill_artifact_count`는 **실행 시점과 mtime에 민감하게 흔들린다.**

이는 신규 리뷰들이 지적한 `generated_at vs file mtime drift` 문제가 실제로도 재현된다는 뜻이다.

현재 runtime 기준 `top_debt`는 다음과 같다.

| 순위 | issue | count | recommended_next_action |
|---:|---|---:|---|
| 1 | `missing_artifact_envelope` | 109 | `backfill_artifact_envelope` |
| 2 | `unknown_currentness` | 109 | `backfill_currentness_metadata` |
| 3 | `generated_at_older_than_file_mtime` | 82 | `regenerate_artifact_or_refresh_timestamp` |
| 4 | `missing_generated_at` | 61 | `none` |
| 5 | `missing_schema` | 17 | `add_schema_or_exclude_noncanonical_json` |

특히 `missing_generated_at`의 action이 `none`으로 남아 있는 것은 작업 큐 관점에서 부정확하다. 이 항목은 **`backfill_generated_at_or_mark_legacy_noncanonical` 같은 실질 action으로 정규화되어야 한다.**

### 3.7 missing_schema 실제 목록

runtime 기준 `missing_schema` 17건은 다음 성격으로 모인다.

1. 초기 root report
2. review/archive 계열
3. raw intake registration/promotion 계열

대표 파일:

- `ops/reports/eval-initial-2026-04-12.json`
- `ops/reports/lint-initial-2026-04-12.json`
- `ops/reports/manifest-2026-04-12.json`
- `ops/reports/review-archive-report.json`
- `runs/run-20260415-raw-markdown-normalization/raw-markdown-normalization-report.json`
- `runs/run-20260422-raw-intake-registration-and-promotion/...` 하위 다수

즉 현재 남은 missing_schema는 **핵심 auto-improve loop 차단**보다는 **주변 generated artifact contract 정리** 성격이 강하다.

### 3.8 POSIX portability 실제 재검증

실제 ZIP을 대상으로 `LC_ALL=C LANG=C unzip -q`를 수행하면 여전히 실패한다.

오류 핵심:

- `File name too long`
- offender는 `raw/web-snapshots/` 아래 긴 한글 파일명 2개

직접 계산 결과:

| 항목 | 값 |
|---|---:|
| 비ASCII entry | 336 |
| UTF-8 flag bit 11 사용 | 2 |
| Unicode Path extra field 사용 | 336 |
| 최대 UTF-8 component 길이 | 167 bytes |
| 최대 POSIX escape-expanded component 길이 | 258 bytes |
| 최대 POSIX escape-expanded path 길이 | 276 bytes |
| 255 bytes 초과 component offender | 2개 |

잔여 offender:

1. `raw/web-snapshots/속보트럼프 “미 대표단, 20일 협상 위해 파키스탄 간다···합의 안하면 모든 발전소와 다리 파괴”.md`
2. `raw/web-snapshots/“AI가 전부인 줄 아나” 어느 번역가의 혼잣말···‘딸깍’에 시작된 번역가 분투기딸깍, 노동③.md`

따라서 신규 리뷰들의 공통 진단은 맞다.

> 현재 ZIP은 UTF-8 환경이나 Python `zipfile`에서는 열리지만, POSIX C locale unzip 기준으로는 아직 **release portability defect**가 남아 있다.

### 3.9 release-smoke / source code 표면 확인

실제 파일 확인 결과:

- `ops/scripts/release_smoke.py`에 `build_partial_report`, `write_partial` 존재
- `ZIP_COMPONENT_BYTE_LIMIT`, `POSIX_ESCAPE_EXPANDED_FILENAME_BYTE_LIMIT` 상수 존재
- `ops/schemas/release-smoke-report.schema.json`에 `partial_report`, `is_partial`, `elapsed_ms`, `completed_command_count` 존재

즉 신규 리뷰들이 말한 “partial report / portability contract가 코드 표면에는 반영됐다”는 평가는 타당하다. 다만 **E2E 완주와 timeout 회귀 테스트는 여전히 미검증**이다.

### 3.10 public export 실제 검증

실제로 `export_public_repo`를 다시 실행한 결과:

| 항목 | 값 |
|---|---:|
| script reported `file_count` | 384 |
| 실제 export tree 파일 수 | 385 |
| forbidden top-level leak (`raw`, `runs`, `system`, `external-reports`, `.venv*`) | 0 |

즉 **민감 surface leak 방지는 정상**이지만, `file_count` 집계와 실제 출력 파일 수에 1건 차이가 있다. 이건 큰 문제는 아니지만, low-priority 정합성 개선 포인트다.

### 3.11 root 0-byte placeholder 확인

루트에 0-byte 파일 2개가 실제로 남아 있다.

- `source--global-markets-misc-intake-w-230-2026-04-21.md`
- `source--global-markets-misc-intake-w-249-2026-04-21.md`

이 파일들은 제거하거나, 의도된 placeholder라면 manifest/registry에 명시적으로 남겨야 한다.

---

## 4. 두 신규 리뷰에 대한 통합 평가

### 4.1 공통적으로 잘 짚은 점

두 신규 리뷰는 모두 아래 핵심을 정확히 짚었다.

1. **현재 체크포인트는 기존 v42와 다르다.**
2. **queue는 실제로 복구되었다.**
3. **schema-invalid debt는 사라졌다.**
4. **release hygiene는 크게 개선됐다.**
5. **POSIX portability와 artifact contract debt, session evidence 부족은 아직 남았다.**

이 큰 방향은 실제 재검증 결과와 일치한다.

### 4.2 실제 파일 기준으로 보정이 필요한 부분

신규 리뷰들의 상위 결론은 정확하지만, 실제 파일 기준으로 보면 아래 몇 가지는 더 정밀하게 써야 한다.

#### A. readiness의 핵심 session/outcome 수치는 top-level이 아니라 queue / learning_readiness 안에 있다

신규 리뷰들은 `attempts_considered=7`, `session_reports_considered=0`을 정확히 잡았지만, 현재 regenerated artifact에서는 이 값들이 단순 top-level 필드가 아니라 다음 위치에 걸쳐 있다.

- `queue.attempts_considered`
- `queue.session_reports_considered`
- `learning_readiness.metrics.attempts_considered`
- `learning_readiness.metrics.session_reports_considered`

즉 문장 자체는 맞지만, 구현 기준으로는 **field path를 더 정확히 써야 한다.**

#### B. `queue_pressure_summary`, blocker counts는 regenerated artifact에서 `summary` 내부로 정리된다

regenerated `mutation-proposals.json`에서는 다음 값들이 top-level보다 `summary` 내부에 들어간다.

- `queue_pressure_summary`
- `candidate_blocker_count`
- `proposal_blocker_count`

따라서 후속 리뷰에서는 “필드 존재”뿐 아니라 **현재 schema 배치 위치**까지 명확히 적는 편이 좋다.

#### C. artifact freshness의 `stale` / `mtime_sensitive` / `safe_to_backfill` 수치는 저장본과 재생성본 사이에 흔들린다

신규 리뷰는 `59/59/87` 또는 `83/83/63` 식의 차이를 이미 인지하고 있었는데, 실제 재검증에서도 그 차이가 다시 드러났다.

따라서 이 항목은 단순 숫자 비교보다 아래처럼 읽는 것이 더 정확하다.

- `missing_artifact_envelope`, `unknown_currentness`, `missing_schema`, `schema_invalid`은 비교적 안정적이다.
- `stale_artifact_count`, `mtime_sensitive_artifact_count`, `safe_to_backfill_artifact_count`는 **mtime drift에 민감한 관측값**이다.

즉 후속 문서에서는 이 수치를 절대값처럼 쓰기보다 **stored vs regenerated**를 분리해서 쓰는 것이 낫다.

#### D. public export는 보안적으로 pass지만 file_count 정합성은 1건 차이가 있다

신규 리뷰는 leak 0에 초점을 맞췄는데, 실제로는 `file_count=384` vs tree file count `385` 차이가 있다. low priority지만 **report/accounting 정확도** 차원에서 한 번 정리할 가치가 있다.

---

## 5. 기존 리뷰 대비 현재 실제로 완료되거나 크게 개선된 작업분

### 5.1 self-improve execution queue 복구

기존 v42 병목 사슬:

```text
runs_discovered=7
  ↓
runs_considered=2 / runs_skipped=5
  ↓
candidates_emitted=0
  ↓
source_candidates_read=0
  ↓
proposals_emitted=0
  ↓
runnable_proposal_count=0
  ↓
can_run=false
```

현재 실제 상태:

```text
runs_discovered=7
  ↓
runs_considered=6 / runs_skipped=1
  ↓
candidates_emitted=1
  ↓
source_candidates_read=1
  ↓
proposals_emitted=1
  ↓
runnable_proposal_count=1
  ↓
execution_readiness.can_run=true
```

이 변화는 cosmetic improvement가 아니라, 기존 리뷰의 가장 중요한 P0를 실제로 해소한 것이다.

### 5.2 local schema invalid debt 12건 → 0건

기존 리뷰의 강한 잔여 항목이었던 schema invalid debt는 현재 0건이다. 이는 단순 보고서 개편이 아니라 **artifact validity 복구**로 봐야 한다.

### 5.3 run artifact `$schema` / history 품질 대폭 개선

v42 기준 skipped run 5건이 현재는 1건만 남아 있다. 즉 bulk backfill 또는 equivalent cleanup이 상당 부분 반영된 상태다.

### 5.4 release archive hygiene 대폭 개선

`.venv`, `.venv-py312`, `.pyc`, `.pyd`, `.exe` 등이 현재 ZIP에서 제거되었다. entry 수가 11,552에서 1,634로 줄어든 것은 이 변화의 직접 증거다.

### 5.5 portability offender 6개 → 2개

아직 완전 해결은 아니지만, raw/web-snapshot 파일명 canonicalization이 실제로 일부 반영되었다.

### 5.6 public/review archive policy는 작동함

현재 public export / review archive 계열은 민감 surface leak 없이 동작한다. 즉 full-vault portability가 남아 있어도, **archive class 분리 자체는 이미 상당히 진전**된 상태다.

---

## 6. 아직 남아 있는 작업분

### 6.1 P0 — 즉시 닫을 가치가 큰 항목

#### P0-1. POSIX ZIP portability 완전 해소

현재 가장 명확한 남은 blocker다.

완료 기준:

- `LC_ALL=C LANG=C unzip -q <zip>` 성공
- escape-expanded component > 255 bytes offender 0개
- budget gate가 실제 Info-ZIP escape 형식과 일치

#### P0-2. 남은 skipped run 1건 처리

현재 mechanism review가 정확히 한 건을 skip한다. 이건 이미 진단이 잘 되고 있으므로, 다음 단계는 진단이 아니라 **정책적 처리**다.

선택지:

- artifact 복원
- history archive / quarantine
- explicit non-history / superseded 표기

#### P0-3. session / outcome / loop-health evidence 보강

현재는 `can_run=true`지만 `learning_uncertain`이다. 즉 bounded run은 가능해도, “학습적으로 충분히 좋은 상태”라고는 할 수 없다.

즉시 필요한 것:

- narrow mechanism run 추가로 `attempts_considered >= 10`
- session rollup artifact 생성으로 `session_reports_considered > 0`
- `loop_health_summary.status != missing`

#### P0-4. artifact contract debt 감소

현재도 아래 값은 크다.

- `missing_artifact_envelope_count = 109`
- `unknown_currentness_artifact_count = 109`
- `missing_schema_count = 17`

특히 `safe_to_backfill=true` 항목부터 `top_debt_files` 순으로 치우는 것이 맞다.

### 6.2 P1 — 운영 안정화

#### P1-1. generated_at vs mtime drift 분리

`stale_artifact_count`와 `mtime_sensitive_artifact_count`가 재실행 시 흔들리는 이유를 더 이상 그냥 두면 안 된다.

권장 분리:

- `mtime_drift_suspected`
- `content_stale_confirmed`

#### P1-2. release-smoke E2E / timeout 회귀 테스트

코드 표면에 partial report는 있으나, 실제 long-running command 중 heartbeat / timeout / partial write를 아직 E2E로 확정하지 못했다.

#### P1-3. Makefile Python command contract 수정

현재 `PYTHON="python3 -S"` 류 호출은 quoting 때문에 깨질 가능성이 높다.

#### P1-4. proposal lifecycle ledger 연결

현재는 proposal이 실제로 1건 있으므로, lifecycle ID / evidence chain 연결을 더 이상 미루기 어렵다.

#### P1-5. public export file_count 정합성 수정

보안 문제는 아니지만, tool output `384` vs actual file count `385` 차이는 한 번 정리하는 편이 낫다.

#### P1-6. root 0-byte placeholder 처리

의도된 placeholder가 아니라면 제거하고, 의도된 표식이면 registry에 명시한다.

### 6.3 P2 — 이후 품질 상향

- archive class policy 문서화 강화
- `task-improvement-observations` / supply-chain family envelope 통합
- review-archive / generated-artifact-index의 historical/canonical 경계 정리
- readiness summary 상단에 `execution_pass_learning_review_required` 같은 상위 상태 문구 별도 노출

---

## 7. 이번 대조에서 새로 식별된 개선 방안

### 7.1 portability gate를 실제 Info-ZIP escape 기준으로 교체

이건 신규 리뷰 중 특히 reconciliation 리뷰가 가장 잘 짚었고, 실제 파일 기준으로도 타당하다.

현재 `unicode_escape` 류 계산만으로는 false negative가 생길 수 있다. 실제 gate는 아래 mode를 구분해야 한다.

- `utf8_component_bytes`
- `python_unicode_escape_bytes`
- `infozip_c_locale_escape_bytes`

release/full-vault gate에서는 마지막 값을 사용해야 한다.

### 7.2 full-vault와 public/review/release archive class acceptance 분리

현재 public/review는 대체로 pass지만 full-vault는 POSIX unzip에서 실패한다. 따라서 acceptance를 분리해야 한다.

### 7.3 readiness에 `execution`과 `evidence confidence`를 분리 표기

현재처럼 `can_run=true`와 `learning_uncertain`이 함께 있을 때 운영자가 헷갈릴 수 있다. 상위 summary에 예를 들어 아래와 같은 문구를 추가하는 것이 좋다.

- `execution_pass_learning_review_required`
- `execution_blocked`
- `learning_ready`
- `learning_uncertain`

### 7.4 history quarantine helper 자동화

남은 skipped run이 1건으로 줄었기 때문에, 이제는 bulk migration보다 **quarantine helper**가 효율적이다.

추천 동작:

- missing promotion input artifact 발견 시 `history=quarantine_candidate` 표기
- `restore_missing_artifact_or_archive_run_history` scaffold 자동 생성
- mechanism review summary에 `soft-skipped / quarantined / restorable` 분리

### 7.5 artifact freshness action string 정규화

현재 `missing_generated_at`의 `recommended_next_action`이 `none`으로 남아 있는 것은 개선 여지가 크다. report가 work queue 역할을 하려면 **실질 action string** 이어야 한다.

### 7.6 public export count/accounting 정리

현재 leak 방지는 충분히 좋다. 다만 report count와 actual file count가 어긋나는 작은 정합성 이슈는 도구 신뢰도를 위해 고치는 편이 낫다.

---

## 8. 권장 실행 순서

### PR-1: POSIX ZIP portability 완전 해소 + Info-ZIP escape budget 교체

목표:

- `LC_ALL=C LANG=C unzip -q <zip>` 성공
- offender 2개 제거
- `unicode_escape` 기반 false negative 제거

핵심 작업:

1. `raw/web-snapshots/` 잔여 2개 파일명 canonicalization
2. 원제목 frontmatter 보존
3. `path_portability_runtime.py` 공통 helper 도입
4. gate를 `infozip_c_locale_escape_bytes <= 255` 기준으로 변경
5. 실제 `LC_ALL=C LANG=C unzip -q` smoke를 release gate에 추가

### PR-2: 남은 skipped run 1건 복구 또는 quarantine

목표:

- `runs_skipped=0` 또는 explicit non-history 분류

### PR-3: artifact envelope/currentness backfill

목표:

- `missing_artifact_envelope_count` 109 유의미 감소
- `unknown_currentness_artifact_count` 109 유의미 감소
- `missing_schema_count` 17 해소 또는 명시적 noncanonical 분류

핵심 작업:

- `top_debt_files` 순서대로 `safe_to_backfill=true` 항목 우선 처리
- `missing_generated_at` action 정규화
- `mtime_drift_suspected` vs `content_stale_confirmed` 분리

### PR-4: session / outcome / loop-health evidence 보강

목표:

- `attempts_considered >= 10`
- `session_reports_considered > 0`
- `loop_health_summary.status != missing`
- readiness에 confidence 계층 추가

### PR-5: release-smoke E2E / heartbeat / timeout 검증

목표:

- fast/full profile 분리
- long-running command heartbeat 제공
- timeout/interruption에서도 schema-valid partial report 보장

### PR-6: Makefile Python command contract 수정

목표:

- `PYTHON="python3 -S"` 류 호출이 깨지지 않음

### PR-7: proposal lifecycle ledger 연결

목표:

- 현재 runnable proposal 1건을 기준으로 `improvement_id`, `source_run_id`, `evidence_artifact_ids`, decision/outcome chain 연결

### PR-8: release hygiene 잔여 정리

목표:

- root 0-byte placeholder 제거 또는 registry 등록
- archive candidates 정리
- public export count mismatch 해소

---

## 9. 최소 Acceptance Criteria

| ID | 기준 |
|---:|---|
| AC-01 | `mechanism-review-candidates.summary.candidates_emitted > 0` |
| AC-02 | `mutation-proposals.summary.proposals_emitted > 0` |
| AC-03 | `auto-improve-readiness.execution_readiness.can_run == true` |
| AC-04 | local schema invalid artifact count가 0이다 |
| AC-05 | `LC_ALL=C LANG=C unzip -q <zip>` 가 성공한다 |
| AC-06 | POSIX escape-expanded component offender가 0개다 |
| AC-07 | `runs_skipped == 0` 또는 explicit non-history 분류가 완료된다 |
| AC-08 | `missing_artifact_envelope_count` / `unknown_currentness_artifact_count` / `missing_schema_count`가 유의미하게 줄어든다 |
| AC-09 | `attempts_considered >= 10` |
| AC-10 | `session_reports_considered > 0` |
| AC-11 | `loop_health_summary.status != missing` |
| AC-12 | release-smoke가 timeout/interruption에서도 partial report를 남긴다 |
| AC-13 | Makefile Python command contract가 multi-word interpreter flags를 깨뜨리지 않는다 |
| AC-14 | root 0-byte placeholder 2개가 제거되거나 registry에 명시된다 |
| AC-15 | proposal lifecycle ledger가 현재 proposal과 연결된다 |

---

## 10. 최종 판단

두 신규 리뷰는 전체적으로 수준이 높고, 핵심 방향은 실제 파일과 잘 맞는다. 특히 아래 세 가지 판단은 그대로 수용해도 된다.

1. **현재 체크포인트는 v42 기준선과 다른 세대이며, queue는 실제로 복구되었다.**
2. **release hygiene와 schema-invalid debt는 크게 개선되었다.**
3. **남은 핵심은 portability, artifact contract completeness, session/outcome evidence 품질이다.**

다만 실제 재검증을 함께 붙여 보면, 현재 상태를 가장 정확하게 요약하는 문장은 아래와 같다.

> 현재 체크포인트는 **self-improve execution queue가 실제로 복구된 상태**이지만, **release portability defect 2건, skipped run 1건, artifact contract debt 109/109/17, learning evidence 부족** 때문에 아직 release-ready라고 부를 단계는 아니다.

즉 지금의 작업은 더 이상 “멈춘 시스템을 살리는 응급 복구”가 아니다. 오히려 **열린 루프를 운영 가능한 수준으로 안정화하는 마무리 단계**다.

---

## 11. 한 줄 요약

**두 신규 리뷰의 핵심 결론은 대체로 정확하며, 실제 ZIP 재검증 결과도 이를 지지한다. 현재 우선순위는 queue 복구가 아니라, POSIX portability 2건 정리, skipped run 1건 처리, artifact contract debt 축소, session evidence 보강으로 이동해야 한다.**
