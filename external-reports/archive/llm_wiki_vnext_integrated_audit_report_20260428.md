# LLM Wiki vNext 통합 감사 보고서

---

- **작성일**: 2026-04-28 (Asia/Seoul)
- **출력 파일명**: `llm_wiki_vnext_integrated_audit_report_20260428.md`
- **검토 대상 ZIP SHA-256**: `9ef226df11d92848d5ca1f5cdcb3a7ae40763472053c643a856cad0abb9de999`
- **비교 기준 리뷰**: `llm_wiki_vnext_integrated_unified_report_20260427.md`
- **기준 리뷰 ZIP SHA-256**: `982007cc09a430708216306b454875f4f810822f5d9ae61ad012645cdd5d37d4`
- **통합 원본 리뷰 목록**:
  - `llm_wiki_vnext_post_review_audit_report_20260428.md`
  - `llm_wiki_vnext_v49_post_review_audit_report_20260428.md`
  - `llm_wiki_vnext_v50_detailed_reaudit_report_20260428.md`
- **작성 목적**: 동일한 체크포인트를 독립적으로 검토한 세 개의 감사 보고서를 누락 없이 통합하고, 공통 발견 사항·독립 발견 사항·우선순위별 권장 실행 계획을 단일 보고서로 정리한다.

---

## 목차

1. [메타 노트: 세 리뷰의 관계](#1-메타-노트-세-리뷰의-관계)
2. [최종 종합 결론](#2-최종-종합-결론)
3. [검토 대상 ZIP 구조 프로필](#3-검토-대상-zip-구조-프로필)
4. [세 리뷰의 검증 범위 및 환경 차이](#4-세-리뷰의-검증-범위-및-환경-차이)
5. [기준 리뷰(v47) 대비 현재 스냅샷의 실질 진전](#5-기준-리뷰v47-대비-현재-스냅샷의-실질-진전)
6. [잔여 핵심 작업 — P0 (Release Blocker)](#6-잔여-핵심-작업--p0-release-blocker)
7. [잔여 핵심 작업 — P1 (단기 필수)](#7-잔여-핵심-작업--p1-단기-필수)
8. [잔여 핵심 작업 — P2 (중기 권장)](#8-잔여-핵심-작업--p2-중기-권장)
9. [v50 재실행에서 새로 식별된 P0 신규 이슈](#9-v50-재실행에서-새로-식별된-p0-신규-이슈)
10. [공통 신규 개선 방안 (세 리뷰 교차 도출)](#10-공통-신규-개선-방안-세-리뷰-교차-도출)
11. [테스트 절차 및 CI 병목 분석](#11-테스트-절차-및-ci-병목-분석)
12. [통합 Acceptance Criteria 판정표](#12-통합-acceptance-criteria-판정표)
13. [권장 실행 순서 (PR 로드맵)](#13-권장-실행-순서-pr-로드맵)
14. [현재 상태 라벨 요약](#14-현재-상태-라벨-요약)
15. [기준 리뷰(v47) 주요 판단 보정 요약](#15-기준-리뷰v47-주요-판단-보정-요약)

---

## 1. 메타 노트: 세 리뷰의 관계

세 개의 감사 보고서는 모두 **동일한 ZIP SHA-256 체크포인트** (`9ef226df11d92848d5ca1f5cdcb3a7ae40763472053c643a856cad0abb9de999`)를 각각 독립적으로 검토한 결과물이다. 파일명에 포함된 번호(v49, v50 등)는 리뷰 간 우열이나 순서를 나타내지 않는다. 세 리뷰는 서로 다른 검증 환경과 접근 방식을 취했으며, 그 결과 각 리뷰가 독립적으로 발견한 내용의 합집합이 이 보고서의 핵심 분석 재료가 된다.

| 구분 | 검토 대상 ZIP | 주요 특징 |
|---|---|---|
| 리뷰 A (`post_review`) | 동일 SHA | Python CRC·extractall·C-locale 검증, artifact freshness 재생성, 의존성 오프라인 설치 실패 환경에서의 결과 |
| 리뷰 B (`v49`) | 동일 SHA | dev dependency venv 설치 성공, ruff·mypy 직접 실행 확인, AST 기반 테스트 수 검증 |
| 리뷰 C (`v50`) | 동일 SHA | **라이브 재실행** 강조, `raw_registry_preflight` 실패 등 신규 P0 이슈 발견, 체크인 리포트와 라이브 재현성 불일치 규명 |

세 리뷰가 공통적으로 확인한 사항은 **사실로 확정**하고, 리뷰 간 차이가 있는 사항은 각주와 함께 병기했다.

---

## 2. 최종 종합 결론

현재 체크포인트는 기준 리뷰(`v47` 기준) 이후 **실질적인 진전이 분명히 존재**한다. artifact contract debt가 `106/106/17`에서 `79/79/17`로 감소했고, session/loop-health 관측 산출물이 추가되었으며, full release-smoke pass report가 체크인 산출물로 존재한다.

그러나 세 리뷰를 교차 분석한 결과 **현재 스냅샷은 아직 release-ready가 아니다**. 이를 판단하는 근거는 다음 세 가지다.

첫째, **stable artifact contract debt** `missing_artifact_envelope=79`, `unknown_currentness=79`, `missing_schema=17`이 여전히 남아 있다. 특히 missing schema 17건은 기준 리뷰 시점과 동일하게 해소되지 않았다.

둘째, **learning readiness** 가 `learning_uncertain` 상태를 유지하고 있다. `attempts_considered=7`은 최소 기준인 10에 미치지 못하고, `session_calibration_status=no_session_context`가 그대로이며, `telemetry_coverage_ratio=0.0`으로 텔레메트리 coverage가 전무하다.

셋째, 리뷰 C(v50)의 **라이브 재실행 결과**, 현재 트리에서 `raw_registry_preflight`가 46건의 `raw_path_mismatch`로 실패하며 `make check`가 통과하지 않는다. 이는 체크인된 full pass release-smoke report와 라이브 재현성 간에 불일치가 존재함을 의미하는 P0 수준의 신규 이슈다.

**권장 현재 상태 라벨**: `progressed_but_not_release_ready`  
**권장 다음 단계**: raw registry 경로 정합성 복구 → contract debt 완결 → learning evidence 강화 → test gate de-duplication

---

## 3. 검토 대상 ZIP 구조 프로필

세 리뷰가 동일하게 확인한 현재 ZIP의 실제 구조는 다음과 같다.

### 3.1 기본 무결성

| 항목 | 결과 |
|---|---|
| ZIP SHA-256 | `9ef226df11d92848d5ca1f5cdcb3a7ae40763472053c643a856cad0abb9de999` |
| ZIP 크기 | 191,170,571 bytes |
| `zipfile.testzip()` | `None` (CRC 오류 없음) |
| Python `extractall()` | 성공 |
| `LC_ALL=C LANG=C unzip -q` | 성공, return code 0 |

### 3.2 내부 구조 수치

| 항목 | 값 |
|---|---:|
| entry 수 | 1,648 |
| 파일 수 | 1,570 |
| 디렉터리 수 | 78 |
| 압축 해제 전체 바이트 합 | 240,325,896 |
| non-ASCII entry 수 | 334 |
| 최대 UTF-8 component 길이 | 167 bytes |
| root 직접 파일 수 | 17 |
| root 직접 0-byte 파일 수 | 0 |
| `runs/` 하위 0-byte placeholder | 15건 |

### 3.3 최상위 경로별 파일 분포

| 최상위 경로 | 파일 수 |
|---|---:|
| `raw` | 446 |
| `wiki` | 417 |
| `ops` | 283 |
| `runs` | 156 |
| `tests` | 122 |
| `system` | 71 |
| `external-reports` | 35 |
| root 직접 파일 | 17 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |
| `.vscode` | 1 |

### 3.4 확장자 분포

| 확장자 | 파일 수 |
|---|---:|
| `.md` | 942 |
| `.py` | 278 |
| `.json` | 218 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.yaml` | 13 |
| `.toml` | 10 |
| `.jsonl` | 8 |
| 확장자 없음 | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

### 3.5 기준 리뷰(v47) 대비 구조 변화

| 항목 | 기준 v47 | 현재 | 변화 |
|---|---:|---:|---:|
| ZIP 크기 (bytes) | 191,262,121 | 191,170,571 | -91,550 |
| entry 수 | 1,638 | 1,648 | **+10** |
| 파일 수 | 1,564 | 1,570 | **+6** |
| 디렉터리 수 | 74 | 78 | **+4** |
| 압축 해제 바이트 합 | 240,720,640 | 240,325,896 | -394,744 |
| `external-reports` 파일 수 | 34 | 35 | +1 |
| `ops` 파일 수 | 278 | 283 | +5 |
| `tests` 파일 수 | 122 | 122 | 동일 |
| `.md` 파일 수 | 941 | 942 | +1 |
| `.py` 파일 수 | 278 | 278 | 동일 |
| `.json` 파일 수 | 215 | 218 | +3 |
| `.jsonl` 파일 수 | 6 | 8 | +2 |

이 변화는 단순 재패키징이 아니라 **운영 리포트 계층이 실제로 추가·갱신된 후속 스냅샷**임을 수치로 확인해 준다. 특히 `ops/reports/release-smoke-report.json`, `ops/reports/auto-improve-sessions/`, `ops/reports/routing-provenance-aggregates/`, `ops/reports/runtime-events/` 계열이 핵심 판단 근거다. 또한 현재 ZIP에는 기존 통합 리뷰 파일(`llm_wiki_vnext_integrated_unified_report_20260427.md`)이 `external-reports/` 아래 self-included 형태로 포함되어 있으며, 업로드본과 SHA-256이 일치함을 세 리뷰 모두 확인했다.

---

## 4. 세 리뷰의 검증 범위 및 환경 차이

### 4.1 공통 검증 항목

세 리뷰가 공통으로 수행한 검증은 다음과 같다.

| 검증 | 공통 결과 |
|---|---|
| ZIP SHA-256 계산 | `9ef226df...e999` 일치 |
| Python CRC 검증 (`testzip()`) | pass |
| Python `extractall()` | 성공 |
| C-locale Info-ZIP 추출 | 성공 |
| `artifact-freshness-report.json` 파싱 | 일치 (`79/79/17`) |
| `auto-improve-readiness.json` 파싱 | 일치 |
| `release-smoke-report.json` 파싱 | 일치 (체크인 full pass) |
| pytest 수집 (collection) | 110개 파일, 662개 테스트 |
| `tests/test_release_smoke.py` 테스트 수 | 14개 (AST/실행 기준) |

### 4.2 리뷰별 추가 검증 및 환경 특이사항

| 항목 | 리뷰 A | 리뷰 B (v49) | 리뷰 C (v50) |
|---|---|---|---|
| dev dependency 설치 | 오프라인 실패 (pip 44.1초 후 실패) | venv 별도 생성 후 **설치 성공** | editable install + dev extras 성공 |
| `ruff check` 직접 실행 | 미완료 | **pass (2.40초)** | **pass** |
| `mypy` 직접 실행 | 미완료 | **pass (15.10초, 155 files)** | **pass** |
| `tests/test_release_smoke.py` 직접 실행 | 14개 pass (21.29초) | 14개 pass (13.91초) | **pass** |
| `tests/test_report_schemas.py` | 미실행 | 27개 pass (9.77초) | **pass** |
| `artifact_freshness` 재생성 | pass (17.4초, stable `79/79/17` 유지) | pass (7.87초) | pass |
| `make check` 전체 | 미실행 | 환경 제한으로 미완료 | **실패** (raw_registry_preflight 단계) |
| `raw_registry_preflight` 라이브 실행 | 미실행 | 미완료 | **실패 (46건 raw_path_mismatch)** |
| full release-smoke 라이브 재실행 | 미실행 | 미완료 | **partial failure 확인** |
| `pytest -q` (plain) | 미실행 | 미완료 | **collection 실패 (65 errors, ModuleNotFoundError)** |

### 4.3 환경 제한 공통 사항

리뷰 A와 B는 공통적으로 장시간 무출력 작업에 대해 약 60초 전후의 자동 인터럽트가 적용되는 환경에서 수행되었다. 리뷰 C는 라이브 재실행을 적극적으로 수행했으나 full pytest 완주는 동일하게 도구 제한 시간 내 미완료로 남았다. 이 제한은 결론에서 배제하지 않고 검증 한계로 기록했다.

---

## 5. 기준 리뷰(v47) 대비 현재 스냅샷의 실질 진전

세 리뷰가 교차 확인한 진전 사항을 항목별로 정리한다.

### 5.1 Artifact Contract Debt 감소

가장 뚜렷한 진전 항목이다. 세 리뷰 모두 동일한 수치를 확인했다.

| debt 축 | 기준 v47 | 현재 | 변화 |
|---|---:|---:|---:|
| `missing_artifact_envelope_count` | 106 | **79** | **-27** |
| `unknown_currentness_artifact_count` | 106 | **79** | **-27** |
| `missing_schema_count` | 17 | 17 | 0 (정체) |
| `missing_generated_at` | 59 | **30** | **-29** |
| `schema_invalid_artifact_count` | 0 | 0 | 유지 |
| `safe_to_backfill_artifact_count` | 86 | 84 | -2 |
| `stale_artifact_count` | 60 | 65 | +5 (악화) |
| `mtime_sensitive_artifact_count` | 60 | 65 | +5 (악화) |

현재 저장본 summary:

```json
{
  "artifact_count": 149,
  "json_artifact_count": 149,
  "scanned_text_artifact_count": 181,
  "stale_artifact_count": 65,
  "mtime_sensitive_artifact_count": 65,
  "run_log_placeholder_count": 15,
  "unknown_currentness_artifact_count": 79,
  "missing_artifact_envelope_count": 79,
  "missing_schema_count": 17,
  "schema_invalid_artifact_count": 0,
  "safe_to_backfill_artifact_count": 84,
  "stable_contract_debt_artifact_count": 79,
  "stable_contract_debt_issue_count": 175
}
```

**중요 해석**: `stale_artifact_count`와 `mtime_sensitive_artifact_count`는 실행 시점·추출 방식에 따라 크게 달라지는 mtime-sensitive 지표다. 리뷰 A는 artifact freshness 재생성 시 이 수치가 65에서 119로 변하는 것을 직접 확인했다. 따라서 이 축은 **release gate KPI로 사용해서는 안 되며**, `stable_contract_debt_artifact_count`와 `stable_contract_debt_issue_count`만 release gate 기준으로 삼아야 한다.

### 5.2 Learning/Session 관측 산출물 보강

기준 리뷰에서 "session report 0건 / loop health missing"으로 지적됐던 항목이 일부 진전됐다.

| 항목 | 기준 v47 | 현재 | 판정 |
|---|---:|---:|---|
| `session_reports_considered` | 0 | 1 | **개선** |
| `loop_health_summary.status` | missing | available | **개선** |
| `telemetry_coverage_ratio` | 해당 없음 | 0.0 | 미흡 (loop health flag: `missing_telemetry_coverage`) |
| `session_calibration_status` | `no_session_context` | `no_session_context` | 정체 |

추가된 관측 산출물 파일:

| 파일 경로 | 의미 |
|---|---|
| `ops/reports/auto-improve-sessions/auto-improve-20260428-readiness-preflight.json` | readiness preflight session artifact |
| `ops/reports/routing-provenance-aggregates/auto-improve-20260428-readiness-preflight.json` | loop health source report |
| `ops/reports/runtime-events/auto-improve-session/auto-improve-20260428-readiness-preflight.jsonl` | session runtime event |
| `ops/reports/runtime-events/observability-artifacts/auto-improve-20260428-readiness-preflight.jsonl` | observability runtime event |
| `ops/reports/outcome-metrics.json` | outcome metrics |
| `ops/reports/task-improvement-observations/` 계열 | task-level observation pipeline 산출물 |

이 변화는 "evidence plumbing이 시작됐다"고 볼 수 있지만, learning confidence를 통과 판정으로 올리기에는 아직 충분하지 않다. `loop_health_summary.status=available`이지만 `telemetry_coverage_ratio=0.0`이므로 loop health 자체가 `missing_telemetry_coverage` flag를 내고 있다.

### 5.3 Full Release-Smoke Pass Report 체크인

기준 리뷰에서 "full E2E 미확정"으로 남아 있던 항목이 체크인 산출물 기준으로 부분적으로 닫혔다.

`ops/reports/release-smoke-report.json` 내용 요약:

| 항목 | 값 |
|---|---|
| `profile` | `full` |
| `status` | `pass` |
| `generated_at` | `2026-04-28T00:28:56Z` (KST 09:28:56) |
| `packed_file_count` | 1,322 |
| manifest comparison | pass (missing/unexpected/sha/size mismatch 모두 0) |
| archive budget | pass |
| archive zip component max bytes | 167 / 255 |
| POSIX escape expanded filename max bytes | 240 / 255 |

smoke command별 결과:

| command | returncode | duration_ms |
|---|---:|---:|
| `raw_registry_preflight` | 0 | 18,975 |
| `wiki_lint` | 0 | 42,242 |
| `wiki_eval` | 0 | 19,613 |
| `wiki_stage2_eval` | 0 | 5,854 |
| `planning_gate_validate` | 0 | 1,526 |
| **합계** | | **88,210 ms** |

**단, 리뷰 C(v50)는 이 체크인 리포트를 라이브 재실행으로 재현하지 못했다.** 이에 대한 상세 분석은 §9에 기술한다. "체크인 산출물로서 full pass 존재"와 "현재 트리에서 재현 가능"은 분리해서 판단해야 한다.

### 5.4 Release-Smoke 테스트 확장

기준 리뷰가 `tests/test_release_smoke.py`를 13개로 기록했으나, 현재 AST/직접 실행 기준 **14개**로 증가했다. 세 리뷰 모두 이 파일을 직접 실행하여 14개 all pass를 확인했다.

### 5.5 기타 후속 작업 흔적 확인

리뷰 C(v50)가 추가 확인한 후속 작업 흔적:

- `ops/scripts/release_smoke.py` 갱신
- `ops/schemas/release-smoke-report.schema.json` 갱신
- `tests/test_generated_report_contracts.py` 갱신
- `tests/test_makefile_static_gates.py` 갱신
- `tests/test_manifest_export_symlink_safety.py` 추가/강화
- `.github/workflows/ci.yml` 갱신
- Makefile `PYTEST_DISABLE_PLUGIN_AUTOLOAD ?= 1` export, parallel pytest flags `-p xdist.plugin -n auto --dist=loadfile` 명시

---

## 6. 잔여 핵심 작업 — P0 (Release Blocker)

### 6.1 Raw Registry 경로 동기화 깨짐 ← **리뷰 C 신규 발견 P0**

세 리뷰 중 리뷰 C(v50)만 라이브 재실행을 수행했고, 그 결과 **현재 트리에서 `raw_registry_preflight`가 실패**한다는 사실이 발견됐다.

| 항목 | 값 |
|---|---|
| 실행 명령 | `python -m ops.scripts.raw_registry_preflight --vault .` |
| 종료 코드 | 1 |
| 오류 수 | 46건 |
| 오류 유형 | 전부 `raw_path_mismatch` |

page별 오류 분포:

| page | 오류 수 |
|---|---:|
| `system/system-raw-registry/wiki/middle-east.md` | 17 |
| `system/system-raw-registry/wiki.md` | 15 |
| `system/system-raw-registry/wiki/ai-compute-control.md` | 8 |
| `system/system-raw-registry/wiki/ai-capability.md` | 3 |
| `system/system-raw-registry/wiki/ai-infra-compute-intake-2026-04-21.md` | 1 |
| `system/system-raw-registry/wiki/ai-execution.md` | 1 |
| `system/system-raw-registry/wiki/europe-tech-sovereignty.md` | 1 |

**문제의 본질**: 파일명은 이미 POSIX-safe escaped 형태(예: `raw/web-snapshots/Anthropic#U2019s... .md`)로 바뀌어 있지만, raw registry page의 `storage_path`에는 여전히 Unicode 원제(예: `raw/web-snapshots/Anthropic's... .md`)가 기재된 항목이 남아 있다. 즉, **파일명 canonicalization/escape migration은 완료됐지만 registry storage path 동기화가 완결되지 않았다.**

**연쇄 영향**:

1. `raw_registry_preflight` 실패
2. `make check` 전체 실패 (`ruff`·`mypy`·`artifact_freshness`는 통과하지만 `raw_registry_preflight` 단계에서 중단)
3. release-smoke live rerun 조기 실패 (2개 command 이후 partial report 생성)
4. 체크인된 full pass report의 재현성 신뢰 하락
5. unpacked release tree에서 `raw_registry_preflight` 오류가 332건까지 확대됨

이 문제는 단순한 경고나 운영상 불편의 수준이 아니라, **현재 패키지의 첫 번째 실질 blocker가 코드 품질이 아니라 content-registry consistency**임을 의미한다.

### 6.2 Artifact Contract Debt 79/79/17 미해소

envelope/currentness 항목은 줄었지만 release-ready 수준에는 미치지 못한다.

| issue | count | 주요 surface | 권장 action |
|---|---:|---|---|
| `missing_artifact_envelope` | 79 | `ops_reports=11`, `runs=68` | `backfill_artifact_envelope` |
| `unknown_currentness` | 79 | `ops_reports=11`, `runs=68` | `backfill_currentness_metadata` |
| `missing_schema` | 17 | `ops_reports=4`, `runs=13` | schema 추가 또는 machine-readable legacy 분류 |
| `missing_generated_at` | 30 | `runs=30` | `backfill_generated_at` 또는 `mark_legacy_noncanonical` |

권장 acceptance 기준(stable 분리):

```text
stable acceptance gate:
  missing_artifact_envelope_count  < 50
  unknown_currentness_artifact_count < 50
  missing_schema_count              = 0 또는 17건 모두 machine-readable classification 존재
  schema_invalid_artifact_count     = 0 유지 (현재 충족)

non-stable, observation only (gate 제외):
  stale_artifact_count
  mtime_sensitive_artifact_count
  safe_to_backfill_artifact_count
```

### 6.3 Missing Schema 17건 미해소 (P0/P1 경계)

기준 리뷰와 완전히 동일한 17건이 남아 있다. 리뷰 B(v49)는 각 파일의 `safe_to_backfill`과 `mtime_sensitive` 여부를 구체적으로 분류했다.

| 파일 | surface | safe_to_backfill | mtime_sensitive | 주요 이슈 |
|---|---|---:|---:|---|
| `ops/reports/eval-initial-2026-04-12.json` | ops_reports | true | false | envelope/schema/currentness |
| `ops/reports/lint-initial-2026-04-12.json` | ops_reports | true | false | envelope/schema/currentness |
| `ops/reports/manifest-2026-04-12.json` | ops_reports | true | false | envelope/schema/currentness |
| `ops/reports/review-archive-report.json` | ops_reports | false | true | envelope/schema/currentness/mtime |
| `runs/run-20260415-.../raw-markdown-normalization-report.json` | runs | false | true | envelope/schema/currentness/mtime |
| `runs/run-20260422-.../absorption/raw-intake-absorption-matrix-2026-04-22.json` | runs | true | false | envelope/schema/currentness |
| `runs/run-20260422-.../promotion/concept-continuity-integration-2026-04-22.json` | runs | true | false | envelope/generated_at/schema/currentness |
| `runs/run-20260422-.../promotion/raw-intake-promotion-profiles-2026-04-22.json` | runs | true | false | envelope/generated_at/schema/currentness |
| `runs/run-20260422-.../promotion/raw-intake-promotion-render-after-...-2026-04-22.json` | runs | true | false | envelope/generated_at/schema/currentness |
| `runs/run-20260422-.../promotion/raw-intake-promotion-validate-after-...-2026-04-22.json` | runs | true | false | envelope/generated_at/schema/currentness |
| `runs/run-20260422-.../registration/source-english-summary-reregistration-2026-04-22.json` | runs | false | true | envelope/schema/currentness/mtime |
| `runs/run-20260422-.../registration/source-english-summary-slug-manifest-2026-04-22.json` | runs | false | true | envelope/schema/currentness/mtime |
| `runs/run-20260422-.../validation/raw-intake-promotion-validate-final-tree-2026-04-22.json` | runs | true | false | envelope/generated_at/schema/currentness |
| `runs/run-20260422-.../validation/raw-registry-preflight-final-tree-2026-04-22.json` | runs | true | false | envelope/schema/currentness |
| `runs/run-20260422-.../validation/source-english-summary-slug-validate-final-tree-2026-04-22.json` | runs | true | false | envelope/generated_at/schema/currentness |
| `runs/run-20260422-.../validation/wiki-lint-final-tree-2026-04-22.json` | runs | true | false | envelope/schema/currentness |
| `runs/run-20260422-.../validation/wiki-stage2-final-tree-2026-04-22.json` | runs | true | false | envelope/schema/currentness |

세 리뷰가 공통으로 권장하는 처리 우선순위:

1. `safe_to_backfill=true`, `mtime_sensitive=false`인 **13건을 먼저** 처리한다.
2. mtime-sensitive 4건은 regenerate 또는 explicit legacy classification을 먼저 결정한다.
3. `raw-intake promotion` 계열은 개별 schema 13개가 아니라 **shared family schema**를 우선 검토한다.
4. historical로 남길 경우 `legacy_noncanonical`, `archived_run_artifact`, `bootstrap_artifact` 등 machine-readable reason을 artifact record에 기록한다.

### 6.4 Learning Readiness 미해결

execution readiness는 통과하지만 learning confidence는 여전히 미충족 상태다.

| 항목 | 현재 값 | 목표 | 판정 |
|---|---|---|---|
| `execution_readiness.status` | `pass` | `pass` | **충족** |
| `execution_readiness.can_run` | `true` | `true` | **충족** |
| `runnable_proposal_count` | 1 | ≥1 | **충족** |
| `learning_readiness.status` | `learning_uncertain` | confirmed 또는 명시적 block | **미충족** |
| `likely_to_learn` | `false` | `true` 또는 operator override | **미충족** |
| `attempts_considered` | 7 | ≥10 | **미충족** |
| `session_reports_considered` | 1 | ≥1 | 충족 (0→1 개선) |
| `session_calibration_status` | `no_session_context` | no_session_context 탈출 | **미충족** |
| `hold_moving_average` | 0.2857 | <0.25 또는 예외 근거 | **미충족** |
| `rework_count` | 5 | threshold 이하 | **미충족** |
| `defect_escape_pair_count` | 3 | threshold 이하 | **미충족** |
| `telemetry_coverage_ratio` | 0.0 | >0 또는 명시적 예외 | **미충족** |

권장 readiness 상태 라벨:

```text
execution_status          = pass
learning_status           = learning_uncertain
session_evidence_status   = partial_available (0→1 개선, 미완결)
loop_health_status        = available_but_telemetry_missing
release_confidence        = not_release_ready
```

---

## 7. 잔여 핵심 작업 — P1 (단기 필수)

### 7.1 Proposal Lifecycle Ledger 미완결

현재 runnable proposal은 1건이다.

| 항목 | 값 |
|---|---|
| `candidate_id` | `mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime` |
| `proposal_id` | `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime` |
| `family` | `contract_regression_signals` |
| `priority` | 70 |
| `primary target` | `ops/scripts/auto_improve_iteration_persistence_runtime.py` |
| `supporting target` | `ops/schemas/run-telemetry.schema.json` |
| `required artifacts` | `promotion-report.json`, `baseline-mechanism-assessment.json`, `candidate-mechanism-assessment.json` |

"queue가 열려 있다"는 사실은 improvement loop의 품질을 증명하지 않는다. 필요한 완결 체인:

```text
candidate_id
  -> proposal_id
    -> operator decision
      -> run_id
        -> baseline assessment
        -> candidate assessment
          -> promotion / hold / discard outcome
            -> follow-up signal
              -> readiness next action
```

이 체인이 닫히지 않으면 `runnable_proposal_count=1`은 queue 존재만 의미하며, learning loop의 품질 증거가 되지 못한다.

### 7.2 Release-Smoke Profile 분리 미완료

현재 `ops/scripts/release_smoke.py`의 `--profile` choices는 `full` 하나뿐이다. 체크인 full smoke는 88.21초이며, archive build/extract까지 포함하면 PR fast path에 넣기 무겁다. 세 리뷰가 모두 동일한 profile 분리를 권장했다.

| profile | 목적 | 권장 실행 위치 |
|---|---|---|
| `fast` | tiny fixture vault archive/build/extract/manifest/schema smoke | PR 기본 |
| `full` | 실제 vault 전체 archive + lint/eval/stage2/planning 검증 | nightly/release branch 전용 |
| `interruption-unit` | archive failure, command timeout, partial report 검증 | PR 기본 unit |

### 7.3 Pytest 진입점 계약 불안정

리뷰 C(v50)에서 직접 확인:

- `pytest -q` → collection 단계에서 **65 error** (`ModuleNotFoundError: No module named 'tests'`)
- `python -m pytest -q` → 정상 진행

`pytest.ini`에 `pythonpath = .`가 없는 상태이며, Makefile은 `$(PYTHON) -m pytest`를 사용한다. 현재처럼 "암묵적으로 깨지는 상태"는 신규 기여자 경험을 해친다.

세 리뷰의 공통 권장:

| 선택지 | 내용 | 특징 |
|---|---|---|
| **A (권장)** | `python -m pytest` / Makefile을 공식 진입점으로 명시, plain `pytest`는 unsupported 문서화 | 보수적, import contract 명확 |
| B | `pytest.ini`에 `pythonpath = .` 추가하여 plain `pytest` 지원 | 기여자 UX 개선, contract 느슨해질 수 있음 |

### 7.4 Dependency Bootstrap Reproducibility 미완성

리뷰 A에서 `uv pip install --offline -r requirements-dev.txt`가 44.1초 후 실패했다. 실패 이유는 오프라인 캐시에 `pytest>=8.3,<9`가 없고 네트워크가 비활성화됐기 때문이다.

현재 `requirements-dev.txt` 요구사항:

```text
pytest>=8.3,<9
pytest-xdist>=3.6,<4
ruff>=0.15,<1
mypy>=1.20,<2
types-PyYAML>=6.0,<7
```

Makefile 기본 `PYTEST_FLAGS`는 xdist parallel을 사용하므로, xdist 없는 환경에서 `make test`가 실패할 가능성이 높다. 또한 `pytest>=8.3,<9` 요구사항과 다른 리뷰 환경의 `pytest 9.0.2`의 호환 여부를 명시적으로 결정해야 한다.

### 7.5 체크인 Report의 Reproducibility Stale 판정 로직 부재

리뷰 C(v50) 신규 식별 항목이다. 현재는 `release-smoke-report.json`이 들어 있다는 사실만 보면 full pass처럼 보이지만, 라이브 재실행은 실패했다. 이 불일치를 자동으로 감지하는 메커니즘이 없다.

권장 개선:

- release-smoke report에 raw-registry fingerprint, manifest fingerprint를 source tree fingerprint와 함께 강하게 연결한다.
- tree 변경 후에는 이전 release-smoke report를 `stale`로 자동 간주하거나 재생성 요구 상태로 표시한다.
- `make check` 또는 `artifact_freshness`에서 "checked-in report reproducibility stale" 경고를 낼 수 있도록 한다.

---

## 8. 잔여 핵심 작업 — P2 (중기 권장)

### 8.1 Run Log Placeholder 정책 문서화 미완료

0-byte 파일 15건은 모두 `runs/` 하위 stdout/stderr placeholder다. root 직접 0-byte 파일은 없어서 실제 결함은 아니지만, release hygiene report에서 오탐되지 않도록 `run_log_placeholder` allowlist policy를 명문화해야 한다.

### 8.2 Path Budget Margin 관리

현재 archive budget은 pass지만, POSIX escape expanded filename max가 240 bytes로 255 byte limit에 가깝다. full release-smoke report의 top offenders는 한국어 긴 제목 파일들이다. 새 raw/web-snapshot이 추가될 때 slug policy가 자동으로 budget을 넘지 않게 막는 가드가 필요하다.

### 8.3 Release-Smoke Report의 Host-Local Path Leak

리뷰 A 신규 식별 항목이다. 저장된 full release-smoke report의 `command` field에 `/mnt/c/Users/Administrator/Desktop/...`, `/mnt/c/Users/ADMINI~1/AppData/Local/Temp/...` 같은 실행 host-local 경로가 기록되어 있다. 기능상 실패는 아니지만 public-safe artifact hygiene 관점에서 문제가 된다.

권장 개선:

- `display_command` 또는 `relative_command` 필드를 별도로 저장한다.
- host-local absolute path는 `debug_command`로 분리하고 public export에서 redaction한다.
- temp path는 `<tmp>/unpacked/...`로 normalize한다.

---

## 9. v50 재실행에서 새로 식별된 P0 신규 이슈

이 섹션은 리뷰 C(v50)의 라이브 재실행 검증에서 새로 발견된 사항을 상세히 기술한다. 리뷰 A, B는 이 문제를 발견하지 못했는데, 그 이유는 `raw_registry_preflight` 라이브 실행을 환경 제한 등으로 완료하지 못했기 때문이다.

### 9.1 `raw_registry_preflight` 라이브 실패 전체 상황

```
python -m ops.scripts.raw_registry_preflight --vault .
  exit code: 1
  error_count: 46
  error_type: raw_path_mismatch (100%)
```

파일명 escape migration이 완료되었으나 registry `storage_path`는 Unicode 원제 그대로다.

**예시**:
- 실제 파일명: `raw/web-snapshots/Anthropic#U2019s ... .md`
- registry 기재값: `raw/web-snapshots/Anthropic's ... .md`

### 9.2 `make check` 실패 시퀀스

```
make static  → 통과 (ruff pass, mypy pass)
make check:
  [1] ruff          → 통과
  [2] mypy          → 통과
  [3] artifact_freshness → 통과
  [4] raw_registry_preflight → 실패 (46건)
  → make check 중단 및 실패
```

코드 품질 문제가 아니라 content-registry consistency가 첫 번째 blocker임을 확인했다.

### 9.3 Release-Smoke Rerun의 Partial Failure

라이브 재실행 시 `/tmp/release-smoke-rerun.json` partial report가 생성됐다:

- `phase = smoke_commands`
- `completed_command_count = 2` (`raw_registry_preflight`, `wiki_lint` 실패)
- unpacked release tree에서는 `raw_registry_preflight` 오류가 **332건**으로 확대

체크인 report(`status=pass`)와 live rerun(`partial failure`) 사이의 불일치가 명확하게 드러났다.

### 9.4 `tests/test_raw_registry_preflight.py` 커버리지 한계

리뷰 C(v50) 추가 관찰: 해당 테스트 파일은 직접 실행 시 pass했지만, 실제 저장소에서 라이브 preflight는 실패했다. 즉 테스트 fixture가 실제 회귀 시나리오(escaped filename ↔ Unicode registry path 혼용)를 충분히 대변하지 못한다.

추가해야 할 테스트 시나리오:

- escaped filename으로 rename된 실제 raw/web-snapshot 샘플 포함
- registry에는 Unicode `storage_path`가 남아 있는 상태 재현
- `path_aliases`가 비어 있을 때 fail해야 함
- alias를 backfill하면 pass해야 함

---

## 10. 공통 신규 개선 방안 (세 리뷰 교차 도출)

### 10.1 Stable KPI와 mtime-sensitive KPI 분리

세 리뷰가 모두 동일하게 지적한 사항이다. 현재 artifact freshness report는 두 종류의 지표를 혼재시키고 있다.

| KPI 종류 | 포함 항목 | 용도 |
|---|---|---|
| **stable contract KPI** (release gate) | `missing_artifact_envelope`, `unknown_currentness`, `missing_schema`, `schema_invalid` | release gate 통과/실패 기준 |
| **operational attention KPI** (trend) | `stale`, `generated_at older than mtime`, `safe_to_backfill` | trend/triage 참고 |
| **environment-sensitive KPI** (참고) | `local mtime drift`, `regenerated timestamp drift` | 참고 정보, gate 제외 |

### 10.2 Raw Path Drift 전용 경량 사전 게이트 추가

리뷰 C(v50) 제안이며 세 리뷰의 취지와 정합한다. release-smoke까지 가기 전에 훨씬 싼 비용으로 path drift를 먼저 막아야 한다.

```text
make raw-path-sync-check (제안 신규 타깃):
  - registry storage_path가 실파일에 resolve되는지 확인
  - resolve되지 않으면 path_aliases로라도 resolve되는지 확인
  - escaped/unescaped 혼용 drift가 있는지 확인
```

이렇게 하면 88초대 full smoke 이전에 drift를 빠르게 탐지할 수 있다.

### 10.3 Proposal Lifecycle 상태를 Readiness에 직접 연결

`auto-improve-readiness.json`이 proposal lifecycle 상태를 다음과 같이 요약하면 운영 판단이 단순해진다.

```json
{
  "proposal_lifecycle": {
    "proposal_id": "...",
    "decision_status": "missing",
    "run_status": "not_started",
    "outcome_status": "missing",
    "readiness_effect": "queue_open_but_learning_unconfirmed"
  }
}
```

### 10.4 Dependency Bootstrap Preflight 추가

리뷰 A 제안이며 나머지 두 리뷰의 환경 관찰과도 일치한다.

```text
make dependency-preflight (제안 신규 타깃):
  - Python 버전 검사
  - pytest major version 검사 (>=8.3,<9 범위 확인)
  - pytest-xdist 존재 여부 검사
  - ruff, mypy 존재 여부 검사
  - 총 소요시간 5초 이내 목표
  - xdist 없을 때 make test가 serial fallback 또는 명확한 fail-fast 제공
```

---

## 11. 테스트 절차 및 CI 병목 분석

### 11.1 핵심 결론

세 리뷰가 공통으로 내린 결론: **병목의 원인은 "테스트 수가 많다(662개)"가 아니라, "동일한 전체-vault 검증을 여러 경로에서 반복하는 구조"다.**

현재 테스트 규모 참고:

| 항목 | 수량 |
|---|---:|
| `tests/test_*.py` 중 테스트 보유 파일 | 110 |
| 테스트 함수/메서드 합계 | 662 |
| `tests/test_report_schemas.py` | 27개 |
| `tests/test_mutation_proposal.py` | 20개 |
| `tests/test_auto_improve_readiness_runtime.py` | 13개 |
| `tests/test_release_smoke.py` | 14개 |
| `tests/test_artifact_freshness_runtime.py` | 10개 |

pytest 마커 기준 수집 수 (리뷰 C 실측):

| tier | 파일 수 | 테스트 수 |
|---|---:|---:|
| fast | 93 | 572 |
| slow | 8 | 16 |
| integration | 2 | 22 |
| integration-heavy | 1 | 8 |
| public | 6 | 44 |

### 11.2 실측 시간 데이터

| 항목 | 리뷰 A | 리뷰 B (v49) | 리뷰 C (v50) |
|---|---:|---:|---:|
| `tests/test_release_smoke.py` | 21.29초 | **13.91초** | 통과 (확인) |
| `tests/test_generated_report_contracts.py` | 5.30초 | 2.68초 | 통과 |
| `tests/test_makefile_static_gates.py` | 4.41초 | - | 통과 |
| `tests/test_report_schemas.py` | - | **9.77초** | 통과 |
| `artifact_freshness_runtime` 재생성 | 17.4초 | 7.87초 | 통과 |
| `ruff` | - | **2.40초** | 통과 |
| `mypy` (155 files) | - | **15.10초** | 통과 |
| 저장본 full smoke 합계 | 88.21초 | 88.21초 | 88.21초 |
| pytest collection | 4.48초 | - | **4초대** |

### 11.3 병목의 세 가지 구조적 원인

**병목 A — Whole-vault smoke 계열 반복**

`raw_registry_preflight`, `wiki_lint`, `wiki_eval`, `wiki_stage2_eval`, `planning_gate_validate`, `release_smoke --profile full`은 전체 vault를 다시 읽고 다시 계산한다. raw/web-snapshot 파일이 446개인 현재 구조에서 이 축이 압도적으로 무겁다.

**병목 B — CI Matrix Fan-out**

현재 CI는 Linux에서 Python 2종 × tier 5종 = **10개 job**, 여기에 Windows release-smoke 1개, supply-chain gate 1개 = 총 **12개 job**이 존재한다(리뷰 C(v50) 확인). 이 구조는 신뢰성을 높이지만, 의존성 설치 반복, gate 반복 실행, public export 후 별도 static/test 재실행, release-smoke와 content gate 중복 검증을 동반한다.

**병목 C — Release-Smoke와 Live Content Drift의 결합**

release-smoke가 마지막 gate이면서 동시에 drift detector 역할을 한다. raw registry 경로 동기화가 깨진 순간 전체 파이프라인이 조기 중단된다. 이를 분리하지 않으면 content drift와 packaging smoke가 하나의 긴 파이프라인에서 함께 실패한다.

### 11.4 병목 완화 권장안

세 리뷰가 각각 제안한 내용을 통합한 권장 게이트 구조:

| profile | 목적 | 포함 항목 | 권장 실행 시점 |
|---|---|---|---|
| `dev-fast` | 로컬 빠른 피드백 | ruff, 핵심 schema tests, generated report contracts, selected unit tests | 매 PR/로컬 |
| `contract` | artifact/report contract 안정성 | artifact freshness, report schemas, generated report contracts, readiness report unit | PR required |
| `raw-path-sync-check` | registry path drift 조기 탐지 | registry storage_path ↔ escaped filename 정합성만 | PR required |
| `release-smoke-fast` | fixture/tiny vault archive smoke | archive build/extract/manifest comparison (fixture 기반) | PR required |
| `release-smoke-full` | 실제 vault full release gate | 현재 full release-smoke 전체 (88초+) | nightly/release branch 전용 |

추가 권장 사항:

- `check-all` 실행 결과를 phase artifact로 저장하고 `release-smoke`에서 재사용 가능하게 한다.
- CI에서 generated artifact 생성 job을 1개로 통합하고, downstream job이 산출물을 받아 재사용한다.
- pytest 결과를 `ops/reports/test-execution-summary.json`으로 저장해 장기적으로 느린 테스트를 추적한다.
- `--durations=25`를 기본 report artifact로 저장한다.
- subprocess fan-out 제어: command runtime 테스트는 subprocess mock/fake executor를 기본으로 하고 실제 subprocess 테스트는 별도 marker로 분리한다.

---

## 12. 통합 Acceptance Criteria 판정표

세 리뷰의 AC 항목을 통합하고 현재 판정을 부여한다.

| ID | 기준 | 판정 | 근거 요약 |
|---:|---|---|---|
| AC-01 | ZIP CRC 오류 없음 | ✅ 충족 | 세 리뷰 모두 `zipfile.testzip()==None` 확인 |
| AC-02 | Python extractall 성공 | ✅ 충족 | 세 리뷰 모두 확인 |
| AC-03 | C-locale unzip 성공 | ✅ 충족 | 세 리뷰 모두 `LC_ALL=C LANG=C unzip -q` 성공 |
| AC-04 | root 0-byte placeholder 없음 | ✅ 충족 | 0-byte 15건 전부 `runs/` log placeholder |
| AC-05 | 긴 파일명 path budget 관리 | ✅ 충족 | max UTF-8 component 167, POSIX escape 240, 모두 255 미만 |
| AC-06 | schema_invalid = 0 유지 | ✅ 충족 | `schema_invalid_artifact_count=0` 유지 |
| AC-07 | execution readiness pass | ✅ 충족 | `can_run=true`, `runnable_proposal_count=1` |
| AC-08 | ruff pass | ✅ 충족 | 리뷰 B·C에서 직접 실행 확인 |
| AC-09 | mypy pass | ✅ 충족 | 리뷰 B·C에서 155 files pass 확인 |
| AC-10 | release-smoke unit tests pass | ✅ 충족 | 14개 all pass (세 리뷰 모두 확인) |
| AC-11 | generated report contracts pass | ✅ 충족 | 8개 pass (리뷰 A·B 확인) |
| AC-12 | report schemas pass | ✅ 충족 | 27개 pass (리뷰 B·C 확인) |
| AC-13 | session report evidence 존재 | ✅ 충족 | `session_reports_considered=0→1` |
| AC-14 | loop health summary 존재 | ✅ 충족 | `missing→available` |
| AC-15 | release-smoke full pass evidence | ⚠️ 조건부 충족 | 체크인 산출물 존재, 라이브 재실행 재현 실패 (리뷰 C) |
| AC-16 | raw_registry_preflight live pass | ❌ 미충족 | 46건 raw_path_mismatch 실패 (리뷰 C) |
| AC-17 | make check 전체 통과 | ❌ 미충족 | raw_registry_preflight 단계에서 실패 (리뷰 C) |
| AC-18 | artifact envelope/currentness debt < 50 | ❌ 미충족 | 현재 79/79 |
| AC-19 | missing schema 해소 | ❌ 미충족 | 17건 미해소 |
| AC-20 | learning readiness confirmed | ❌ 미충족 | `learning_uncertain` 유지 |
| AC-21 | attempts_considered ≥ 10 | ❌ 미충족 | 현재 7 |
| AC-22 | session context 연결 | ❌ 미충족 | `no_session_context` 정체 |
| AC-23 | telemetry coverage > 0 | ❌ 미충족 | 0.0, `missing_telemetry_coverage` |
| AC-24 | proposal lifecycle closed-loop | ❌ 미충족 | queue는 있으나 outcome trace 불완전 |
| AC-25 | release-smoke fast profile | ❌ 미충족 | full profile만 존재 |
| AC-26 | pytest 진입점 계약 명확화 | ❌ 미충족 | plain `pytest -q` 실패, 정책 문서화 필요 |
| AC-27 | dependency bootstrap reproducibility | ❌ 미충족 | 오프라인 설치 실패 (리뷰 A), pytest 9 호환 미확정 |
| AC-28 | 체크인 report reproducibility stale 판정 | ❌ 미충족 | 메커니즘 없음 (리뷰 C 신규 식별) |
| AC-29 | run log placeholder policy 문서화 | ⚠️ 부분 충족 | 존재 자체는 확인, 정책 명문화 필요 |
| AC-30 | CI gate 중복 de-duplication | ⚠️ 부분 충족 | tier 마커 존재하나 full/fast profile 분리 미완료 |

**충족**: 14개 | **조건부 충족/부분 충족**: 3개 | **미충족**: 13개

---

## 13. 권장 실행 순서 (PR 로드맵)

### 즉시 수행 — PR-1. Raw Registry Path Sync 복구 (P0)

**이 작업이 모든 후속 작업의 선결 조건이다.**

| 항목 | 내용 |
|---|---|
| 목표 | raw registry `storage_path` ↔ 실제 escaped filename 정합성 100% 복구 |
| 방법 | registry page의 `storage_path`를 escaped filename 기준으로 일괄 정규화; 사람이 읽는 제목은 `display_path`/frontmatter에 보존; 기존 Unicode 경로는 `path_aliases`로 이관 |
| 완료 기준 | live tree `raw_registry_preflight` pass, unpacked archive `raw_registry_preflight` pass, `raw_path_mismatch=0` |
| 부수 작업 | `artifact_freshness`, `generated artifact index` 재생성 및 체크인 report 갱신 |

### PR-2. Make Check 전체 통과 및 Release-Smoke 재실행 (P0)

| 항목 | 내용 |
|---|---|
| 목표 | PR-1 완료 후 `make check` 전체 통과, release-smoke full 재실행 후 체크인 report 갱신 |
| 완료 기준 | `make check` 0 exit code; `release-smoke-report.json` 재생성 후 `status=pass`; 체크인 report fingerprint가 현재 트리와 일치 |

### PR-3. Artifact Contract Debt 다음 Tranche (P0)

| 항목 | 내용 |
|---|---|
| 목표 | `missing_artifact_envelope=79`, `unknown_currentness=79`를 50 미만으로 낮추고, missing schema 17건을 schema 추가 또는 machine-readable classification으로 완결 |
| 방법 | `ops_reports` 11건에 envelope/currentness/schema 부여; `runs` 68건은 family 단위로 `backfill_artifact_envelope`; raw-intake 계열 13건은 shared family schema 또는 `archived_run_artifact` classification |
| 완료 기준 | `missing_artifact_envelope_count < 50`; `unknown_currentness_artifact_count < 50`; `missing_schema_count = 0` 또는 17건 모두 machine-readable reason 존재; `schema_invalid = 0` 유지 |

### PR-4. Checked-in Report Reproducibility Stale 판정 로직 추가 (P1)

| 항목 | 내용 |
|---|---|
| 목표 | 체크인 report가 현재 트리와 일치하지 않을 때 자동 경고 |
| 방법 | release-smoke report에 raw-registry fingerprint, manifest fingerprint 강하게 연결; tree 변경 시 이전 report `stale` 자동 표시; `make check`에서 "stale report" 경고 |
| 완료 기준 | registry path 변경 후 `make check`가 reproducibility stale 경고를 출력함 |

### PR-5. Raw Path Drift 전용 경량 게이트 추가 (P1)

| 항목 | 내용 |
|---|---|
| 목표 | full smoke 전에 경량 path drift 탐지 |
| 방법 | `make raw-path-sync-check` 타깃 추가; escaped ↔ Unicode 혼용 검사 |
| 완료 기준 | PR-1 회귀 재발 시 `make raw-path-sync-check`가 즉시 탐지 |

### PR-6. Learning Readiness Evidence 강화 (P0/P1)

| 항목 | 내용 |
|---|---|
| 목표 | `learning_uncertain`을 구체적 pass 또는 named block 상태로 전환 |
| 방법 | telemetry coverage 0.0 탈출; session calibration `no_session_context` 해소; attempts history 10건 이상 확보; proposal outcome trace를 readiness에 연결 |
| 완료 기준 | `attempts_considered ≥ 10`; `session_calibration_status != no_session_context`; `telemetry_coverage_ratio > 0` |

### PR-7. Proposal Lifecycle Ledger 완결 (P1)

| 항목 | 내용 |
|---|---|
| 목표 | candidate → proposal → run → decision → outcome → learning signal을 단일 trace로 연결 |
| 완료 기준 | proposal별 latest outcome 표시; required artifacts placeholder가 실제 run artifact로 resolve됨; held/discarded/promoted 결과가 readiness next action에 반영됨 |

### PR-8. Test Gate De-duplication 및 Release-Smoke Profile 분리 (P0/P1)

| 항목 | 내용 |
|---|---|
| 목표 | PR feedback loop 단축, full smoke를 nightly/release 전용으로 분리 |
| 방법 | `make dev-fast`, `make contract-check`, `make release-smoke-fast` 추가; `release-smoke-full`을 nightly/release branch 전용으로 명시; pytest durations report 저장; CI 캐시/분리 설계 |
| 완료 기준 | PR 기본 gate가 30초 이내 완료; full smoke는 nightly에서만 수행 |

### PR-9. Pytest 진입점 계약 문서화 및 Dependency Preflight (P1)

| 항목 | 내용 |
|---|---|
| 목표 | plain `pytest -q` 실패 상태 해소 및 dependency bootstrap 재현성 확보 |
| 방법 | 진입점 선택 A 또는 B 확정 및 문서화; `make dependency-preflight` 추가; pytest 9 지원 여부 명시적 결정; xdist 없을 때 serial fallback 또는 명확한 error |
| 완료 기준 | README/CONTRIBUTING/CI/Makefile이 동일한 공식 진입점 계약을 사용 |

### PR-10. Archive Hygiene 정리 (P2)

| 항목 | 내용 |
|---|---|
| 목표 | run log placeholder false positive 방지, path budget offender 자동 guard, host-local path redaction |
| 완료 기준 | `run_log_placeholder` policy 문서화; slug policy guard 유지/강화; release-smoke report의 host-local path redaction 구현 |

---

## 14. 현재 상태 라벨 요약

```text
snapshot_status                 = post_unified_review_snapshot
zip_integrity_status            = pass
c_locale_extract_status         = pass
artifact_contract_status        = improved_but_open_79_79_17
schema_status                   = schema_invalid_zero_missing_schema_17
execution_status                = pass
learning_status                 = learning_uncertain
session_evidence_status         = partial_available (0→1 개선, 미완결)
loop_health_status              = available_but_telemetry_missing
raw_registry_status             = LIVE_FAILURE_46_path_mismatch  ← 신규 P0
make_check_status               = FAILING_at_raw_registry_preflight  ← 신규 P0
release_smoke_status            = checkin_pass_but_live_rerun_failed  ← 신규 P0
proposal_lifecycle_status       = queue_open_outcome_trace_missing
dependency_status               = dev_dependency_bootstrap_unverified
pytest_entrypoint_status        = plain_pytest_broken_python_m_pytest_required
test_bottleneck_status          = whole_vault_gates_need_profile_separation
report_reproducibility_status   = stale_detection_mechanism_missing  ← 신규 P1
release_confidence              = not_release_ready
recommended_phase               = registry_sync_restoration → contract_completion → learning_hardening
```

---

## 15. 기준 리뷰(v47) 주요 판단 보정 요약

기존 통합 리뷰(`llm_wiki_vnext_integrated_unified_report_20260427.md`)의 결론 중, 세 리뷰 교차 검증 결과 보정이 필요한 항목과 그대로 유효한 항목을 정리한다.

### 15.1 보정이 필요한 항목

| 기준 리뷰 판단 | 현재 보정 |
|---|---|
| ZIP SHA: `982007cc...37d4` | 현재 ZIP SHA: `9ef226df...e999` (후속 스냅샷) |
| stable debt: `106/106/17` | 현재 stable debt: `79/79/17` (`-27/-27/0`) |
| `session_reports_considered=0` | 현재: 1 |
| `loop_health_summary.status=missing` | 현재: available (단, `telemetry_coverage=0.0`) |
| release-smoke full E2E 미확정 | 체크인 산출물로 존재 (단, 라이브 재현 불일치 신규 확인) |
| `tests/test_release_smoke.py` 13개 | 현재: 14개 |
| external-reports 34개 | 현재: 35개 |
| `missing_generated_at` 59건 | 현재: 30건 (`-29`) |
| `safe_to_backfill_artifact_count` 86건 | 현재: 84건 |
| `make check` 통과 여부 미확인 | 현재: **실패** 확인 (raw_registry_preflight 단계) |

### 15.2 기준 리뷰에서 여전히 유효한 항목

| 기준 판단 | 현재 유효 여부 |
|---|---|
| root 0-byte placeholder 없음 | **유지** |
| schema_invalid = 0 | **유지** |
| runnable proposal 1건 | **유지** |
| learning readiness는 confirmed가 아님 | **유지** |
| proposal lifecycle trace 불완전 | **유지** |
| missing schema 17건 미해소 | **유지** |
| pytest 진입점 계약 명확화 필요 | **유지** |
| run log placeholder policy 문서화 필요 | **유지** |
| full release-smoke가 PR fast path에 넣기 무거움 | **유지** |

---

## 한 줄 요약

현재 스냅샷은 기준 리뷰 이후 artifact contract debt 감소, session/loop-health 관측 보강, full release-smoke 체크인 등 실질적 진전을 이뤘지만, **raw registry 경로 동기화 깨짐으로 인해 `make check`가 통과하지 않고 체크인 release-smoke report의 라이브 재현이 실패하는** P0 신규 이슈가 드러났으며, missing schema 17건·learning uncertainty·telemetry coverage 0·proposal lifecycle trace 미완결이 함께 남아 있어 다음 단계는 기능 추가가 아니라 **registry sync 복구 → contract debt 완결 → learning evidence 강화** 순서로 진행해야 한다.
