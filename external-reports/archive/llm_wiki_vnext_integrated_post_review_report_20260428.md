# LLM Wiki vNext 리뷰 후속 통합 보고서

- **작성일**: 2026-04-28 (Asia/Seoul)
- **출력 파일명**: `llm_wiki_vnext_integrated_post_review_report_20260428.md`
- **통합 대상 리뷰 3건**:
  1. `llm_wiki_vnext_post_review_status_report_20260428.md` (이하 **리뷰-A**)
  2. `llm_wiki_vnext_v51_post_review_status_report_20260428.md` (이하 **리뷰-B**)
  3. `llm_wiki_vnext_post_review_current_state_report_20260428.md` (이하 **리뷰-C**)
- **작성 목적**: 동일한 릴리스 체크포인트에 대해 독립적으로 수행된 위 세 건의 리뷰를 누락 없이 교차 대조하여, 합의된 사실·쟁점·신규 발견·통합 권장 행동을 단일 문서로 정리한다. 세 리뷰 간에 순위나 우열은 없으며, 내용의 충돌이 발생하는 지점은 양립 가능한 해석을 우선 모색하고, 구조적으로 다른 경우에는 그 차이를 명시적으로 기술한다.

---

## 목차

1. [집행 요약](#1-집행-요약)
2. [세 리뷰의 메타 비교](#2-세-리뷰의-메타-비교)
3. [기준 리뷰 두 건의 핵심 판단 재정리](#3-기준-리뷰-두-건의-핵심-판단-재정리)
4. [세 리뷰 공통 합의 사항](#4-세-리뷰-공통-합의-사항)
   - 4.1 현황 라벨 및 전체 상태
   - 4.2 리뷰 이후 완료된 작업
   - 4.3 잔여 Artifact Contract Debt (71/71/13)
   - 4.4 Learning Readiness 미완결
5. [세 리뷰 간 주요 쟁점 분석](#5-세-리뷰-간-주요-쟁점-분석)
   - 5.1 핵심 쟁점: Raw Registry 상태 — 추출 로케일에 따른 재현성 분기
   - 5.2 Bare Pytest Collection Error 수의 차이
   - 5.3 전체 게이트 재현성 기록의 범위 차이
6. [리뷰별 고유 발견 사항](#6-리뷰별-고유-발견-사항)
   - 6.1 리뷰-A 고유 발견
   - 6.2 리뷰-B 고유 발견
   - 6.3 리뷰-C 고유 발견
7. [기준 리뷰 두 건에 대한 현재 시점 재판정](#7-기준-리뷰-두-건에-대한-현재-시점-재판정)
8. [통합 잔여 과제 목록](#8-통합-잔여-과제-목록)
9. [통합 신규 개선 방안](#9-통합-신규-개선-방안)
10. [통합 권장 실행 순서](#10-통합-권장-실행-순서)
11. [최종 통합 판정](#11-최종-통합-판정)
12. [부록: 리뷰 간 핵심 수치 비교표](#12-부록-리뷰-간-핵심-수치-비교표)

---

## 1. 집행 요약

세 리뷰는 동일한 릴리스 체크포인트를 독립적으로 검토했으며, 큰 방향에서는 강한 합의를 형성하고 있다. 현재 스냅샷은 기준 리뷰(통합 감사 보고서, 이중 리뷰 대조 보고서)가 작성된 이후에도 후속 작업이 실질적으로 반영된 더 진전된 상태이며, 동시에 아직 release-ready는 아니다.

세 리뷰가 **만장일치로 확인한 사실**은 다음과 같다.

- **Stable artifact contract debt**: `79/79/17` → `71/71/13`으로 추가 감소했으나 아직 충분히 크다.
- **Learning readiness**: 여전히 `learning_uncertain`이며 `attempts_considered=7`(최소 10 미달), `telemetry_coverage_ratio=0.0`, `session_calibration_status=no_session_context`다.
- **Release-smoke 구조 개선**: fast/full profile 이중 구조와 command sanitization이 실질적으로 반영됐다.
- **리뷰 이후 완료된 후속 작업 여섯 가지**: review-archive parity guard, learning evidence hardening, raw-registry reproduction protocol, pytest entrypoint contract 명시, historical bootstrap backfill, archived run artifact backfill.

세 리뷰 사이에서 **가장 중요한 쟁점**은 raw registry preflight 상태다. 리뷰-A와 리뷰-B는 현재 추출본에서 `error_count=46`, `warning_count=46`으로 실패를 재현한 반면, **리뷰-C는 동일한 ZIP SHA(`b33fed42...`)에서 `error_count=0`, `warning_count=0`으로 완전한 pass를 확인했다.** 이 분기는 모순이 아니라 **추출 로케일(locale) 차이**에 의한 현상이다. 리뷰-B는 `LC_ALL=C LANG=C` C-로케일로 추출하여 Unicode 파일명이 `#Uxxxx` 이스케이프 형식으로 변환됐고, 리뷰-C는 UTF-8 환경에서 정상 추출하여 Unicode 파일명이 그대로 유지됐다. 이 사실은 "raw registry 실패가 repository 자체의 구조적 결함인가, 아니면 특정 추출 환경에서만 발생하는 artifact인가"라는 질문을 열어두며, 세 리뷰 전체를 통틀어 **가장 긴급하게 재현 프로토콜을 고정해야 하는 지점**으로 수렴한다.

리뷰-C만이 새로 식별한 결함으로는 `make fast-smoke`의 **stale pytest node id 실패**와 `generated-artifact-index.json`의 **review provenance drift**가 있으며, 이 두 항목은 다른 두 리뷰에서 다루지 않은 신규 발견이다.

전체 판정:

```text
progressed_after_reviews_but_not_release_ready
```

---

## 2. 세 리뷰의 메타 비교

| 항목 | 리뷰-A | 리뷰-B | 리뷰-C |
|---|---|---|---|
| 파일명 | `llm_wiki_vnext_post_review_status_report_20260428.md` | `llm_wiki_vnext_v51_post_review_status_report_20260428.md` | `llm_wiki_vnext_post_review_current_state_report_20260428.md` |
| 검토 대상 ZIP | `LLM Wiki vNext(52).zip` | `LLM Wiki vNext(51).zip` | `LLM Wiki vNext.zip` |
| ZIP SHA-256 | (명시 없음) | `b33fed4266d8c25ca0acd2d4bbd84603cddad5ec1c54fbfdef644a2dad3465e5` | `b33fed4266d8c25ca0acd2d4bbd84603cddad5ec1c54fbfdef644a2dad3465e5` |
| ZIP 파일 수 | (직접 집계 없음) | 1583개 | 1583개 |
| 추출 방법 | 명시 없음 (escaped 결과 관찰) | `LC_ALL=C LANG=C unzip -q` (C-로케일) | "안전 추출" (UTF-8 환경) |
| 현황 라벨 | `progressed_after_reviews_but_not_release_ready` | `progressed_but_not_release_ready_raw_registry_blocked` | `post_20260428_review_progressed_snapshot` |
| raw registry 판정 | **FAIL** (46 errors / 46 warnings) | **FAIL** (46 errors / 46 warnings) | **PASS** (0 errors / 0 warnings) |
| release-smoke 저장본 | pass (full) | pass (full) | pass (full, sanitized) |
| make release-smoke-fast | (직접 실행 결과 미기재) | (단위테스트 16개 통과 확인) | **PASS** (54.11s) |
| make fast-smoke | (언급 없음) | (언급 없음) | **FAIL** (stale node id) |
| python -m pytest collect-only | (집계 없음) | 성공 (689 tests) | 성공 (689 tests 등가) |
| bare pytest collect-only | FAIL (106 errors) | FAIL (67 errors) | (직접 측정 없음) |
| make unit-tests | (완주 미확정) | (완주 미확정) | TIMEOUT (55.48s) |
| artifact debt (stable) | 71/71/13 | 71/71/13 | 71/71/13 |
| learning readiness | learning_uncertain | learning_uncertain | learning_uncertain |
| generated-artifact-index drift | (언급 없음) | (언급 없음) | **식별** (16 표시 vs 실제 18) |

> **비고**: 리뷰-B와 리뷰-C는 ZIP SHA가 동일하다. 즉 두 리뷰는 바이트 단위로 동일한 ZIP을 서로 다른 환경에서 추출하여 검토한 것이며, raw registry 결과의 차이는 ZIP 내용물이 아닌 추출 환경(로케일 설정)의 차이에서 비롯된다.

---

## 3. 기준 리뷰 두 건의 핵심 판단 재정리

세 리뷰는 모두 다음 두 기준 문서를 공통 전제로 삼아 현재 스냅샷을 재판정했다.

### 3.1 `llm_wiki_vnext_integrated_audit_report_20260428.md` (통합 감사 보고서)

이 보고서는 세 개의 독립 감사 결과를 합산하여 v47 기준선 대비 현재 스냅샷의 진전과 잔여 P0/P1/P2를 판정했다.

| 영역 | 통합 감사 보고서의 판단 |
|---|---|
| 전체 상태 | `progressed_but_not_release_ready` |
| stable artifact debt | `79/79/17` — P0 수준으로 크다 |
| raw registry | v50 재실행에서 46건 mismatch → **P0 blocker** |
| learning readiness | `learning_uncertain` — 미해결 |
| release-smoke | full profile 저장본 pass 존재, 단 live rerun과 불일치 |
| pytest 진입점 | bare `pytest` 불안정, 정리 필요 |
| release-smoke tiering | fast/full 분리 미완료 |

### 3.2 `llm_wiki_vnext_dual_review_improvement_report_20260428.md` (이중 리뷰 대조 보고서)

이 보고서는 통합 감사 보고서와 방향을 공유하면서, 아래 핵심 보정을 강하게 제시했다.

| 영역 | 이중 리뷰 보고서의 보정 |
|---|---|
| raw registry failure | v50 실제 추출본에서는 **재현되지 않았음** → 확정 blocker로 단정 불가 |
| bare pytest failure | repository 버그가 아니라 **지원되지 않는 진입점 계약 문제**로 재분류 |
| 진짜 핵심 과제 | `79/79/17` debt, learning readiness, gate tiering, report hygiene |
| raw registry 접근 권고 | 복구보다 **재현 프로토콜 고정이 먼저** |

---

## 4. 세 리뷰 공통 합의 사항

### 4.1 현황 라벨 및 전체 상태

세 리뷰는 라벨 표현 방식이 다소 다르지만 본질적으로 같은 판정에 도달했다.

| 리뷰 | 현황 라벨 |
|---|---|
| 리뷰-A | `progressed_after_reviews_but_not_release_ready` |
| 리뷰-B | `progressed_but_not_release_ready_raw_registry_blocked` |
| 리뷰-C | `post_20260428_review_progressed_snapshot` / `release_confidence = not_release_ready` |

**세 리뷰 공통 결론**: 현재 스냅샷은 두 기준 리뷰가 작성된 이후에도 실질적인 후속 보강이 계속 이루어진, 더 진전된 상태다. 그러나 stable artifact debt, learning readiness, raw registry 관련 불확실성이 남아 있어 release-ready 판정은 어렵다.

### 4.2 리뷰 이후 완료된 작업

다음 여섯 가지 후속 작업은 세 리뷰 모두에서 실제 완료로 인정된 항목이다.

#### 4.2.1 Review-Archive Canonicalization 및 Parity Guard

| 항목 | 내용 |
|---|---|
| 반영 파일 | `ops/scripts/review_archive.py`, `ops/schemas/review-archive-report.schema.json`, `ops/reports/review-archive-report.json`, `tests/test_generated_report_contracts.py`, `tests/fixtures/report_schema_samples.json` |
| 완료 내용 | review-archive 보고서가 canonical schema-backed artifact로 정리됨. producer/checked-in baseline/shared schema sample 간 parity guard 자동화 완료. |
| 현재 저장본 상태 | `status=pass`, `packed_file_count=387` |
| 판정 | **완료** — 두 기준 리뷰가 공통으로 요구한 generated report contract drift 방지가 실제 구현됨 |

#### 4.2.2 Learning Evidence Hardening

| 항목 | 내용 |
|---|---|
| 반영 파일 | `ops/scripts/auto_improve_readiness_runtime.py`, `ops/schemas/auto-improve-readiness-report.schema.json`, `ops/reports/auto-improve-readiness.json`, `tests/test_auto_improve_readiness_runtime.py`, `tests/test_generated_report_contracts.py` |
| 완료 내용 | readiness 보고서가 `telemetry_coverage_ratio`를 learning readiness 평가 신호에 명시적으로 반영. generated contract test가 learning metrics와 loop-health aggregate 간 정합성 고정. cross-artifact learning ledger parity guard 추가. |
| 중요 구분 | 이 작업은 learning readiness 문제를 **해결**한 것이 아니라, 미해결 상태를 **더 정확하고 깨지기 어렵게 드러낸** 것이다. |
| 판정 | **관측·계약 강화 완료 / 실제 readiness 개선은 미완료** |

#### 4.2.3 Raw Registry Extracted-Zip Reproduction Protocol

| 항목 | 내용 |
|---|---|
| 반영 파일 | `tests/test_raw_registry_preflight.py` (신규 테스트 추가), `ops/reports/task-improvement-observations/task-20260428-raw-registry-reproduction-protocol/...` |
| 완료 내용 | seeded vault → raw-registry export → full zip roundtrip → extracted vault preflight parity를 고정하는 결정론적 재현 프로토콜 fixture 추가. |
| 판정 | **재현 체계 강화 완료 / 실제 live production-scale mismatch 해소는 별개** |

#### 4.2.4 Release-Smoke Fast/Full Profile 이중 구조 도입

| 항목 | 내용 |
|---|---|
| 반영 파일 | `ops/scripts/release_smoke.py`, `Makefile`, `README.md`, `.github/workflows/ci.yml`, `tests/test_release_smoke.py`, `ops/schemas/release-smoke-report.schema.json`, `tests/test_makefile_static_gates.py`, `tests/test_ci_workflow_static.py` |
| 완료 내용 | `FAST_PROFILE="fast"` / `FULL_PROFILE="full"` 분리 구현. Makefile에 `release-smoke-fast` target 추가. README에 fast/full 역할 차이 명문화. CI fast tier 정비. stored command에서 host-local 절대경로 누출 제거. release-smoke 단위 테스트 14 → 16개로 확장. |
| 이전 판정 뒤집음 | 통합 감사 보고서의 "release-smoke는 full profile만 존재한다"는 지적은 현재 ZIP 기준으로 더 이상 유효하지 않다. |
| 판정 | **완료** — 리뷰 지적이 코드/CI/문서 수준에서 모두 반영됨 |

#### 4.2.5 Pytest Entrypoint Contract 명시

| 항목 | 내용 |
|---|---|
| 반영 파일 | `README.md`, `pytest.ini`, `tests/test_makefile_static_gates.py`, `.github/workflows/ci.yml` |
| 완료 내용 | 공식 진입점을 `make test*` / `make check*` / `.venv/bin/python -m pytest`로 명시. `pytest.ini`에 `pythonpath = .`를 넣지 않는 정책을 static guard로 고정. |
| 판정 | **계약 명시 완료 / 기능 지원 확장은 미완료** |

#### 4.2.6 Historical Bootstrap Report 및 Archived Run Artifact Backfill

| 항목 | 내용 |
|---|---|
| 반영 파일 | `ops/reports/eval-initial-2026-04-12.json`, `ops/reports/lint-initial-2026-04-12.json`, `ops/reports/manifest-2026-04-12.json`, `runs/archive/run-20260415-mechanism-planning-gate-second-retry/*`, `ops/scripts/backfill_historical_bootstrap_reports.py`, `ops/scripts/backfill_archived_run_artifacts.py` |
| 완료 내용 | 2026-04-12 bootstrap 보고서 3건을 `artifact_status=archived`, `retention_policy=archive` 상태의 schema-backed artifact로 정규화. 엄격한 schema로 인해 top-level envelope를 직접 넣기 어려웠던 archived run artifact에 embedded archived envelope 전략 적용. |
| 판정 | **두 기준 리뷰 이후 가장 가시적인 수치 개선의 직접 원인** |

### 4.3 잔여 Stable Artifact Contract Debt — 71/71/13

세 리뷰 모두 현재 stable debt가 `71/71/13`임을 확인했다. 이는 두 기준 리뷰 시점의 `79/79/17`에서 줄어든 것이지만 아직 충분히 크다.

#### 현재 debt 상세

| 이슈 유형 | 건수 | owner 분포 | 비고 |
|---|---:|---|---|
| `missing_artifact_envelope` | 71 | `ops_reports: 7`, `runs: 64` | 최우선 잔여 debt |
| `unknown_currentness` | 71 | ops_reports/runs 중심 | envelope와 연동 |
| `generated_at_older_than_file_mtime` | 34 | `ops_reports: 8`, `runs: 26` | mtime-sensitive |
| `missing_generated_at` | 27 | `runs: 27` | 전부 safe_to_backfill |
| `missing_schema` | 13 | `runs: 13` | safe 10건 + sensitive 3건 |
| `stable_contract_debt_issue_count` | 155 | — | 175에서 감소 |

> **중요 관찰**: 리뷰-B는 저장본과 live 재생성 사이에서 mtime-sensitive 지표가 크게 달라진다는 점을 지적했다. `stale_artifact_count`는 저장본 34건에서 live 재생성 시 90건으로 급증한다. 이는 mtime-sensitive 지표를 release gate KPI로 직접 사용하기 어렵다는 것을 의미하며, stable debt 지표만을 required gate로 두는 분리가 필요하다.

#### ops_reports 측 미해결 7건

- `ops/reports/auto-improve-sessions/auto-improve-20260428-readiness-preflight.json`
- `ops/reports/promotion-decision-trends.json`
- `ops/reports/routing-provenance-aggregates/auto-improve-20260428-readiness-preflight.json`
- `ops/reports/sbom-export-mapping.json`
- `ops/reports/sbom-readiness-gate-report.json`
- `ops/reports/supply-chain-gate-report.json`
- `ops/reports/supply-chain-provenance.json`

#### missing schema 13건 (모두 `runs/` 하위)

| safe_to_backfill | mtime_sensitive | 건수 | 처리 방향 |
|---|---|---:|---|
| true | false | 10 | family schema 또는 archived classification 우선 적용 |
| false | true | 3 | deterministic regeneration 또는 legacy archived classification 선택 |

### 4.4 Learning Readiness 미완결

세 리뷰 모두 현재 `ops/reports/auto-improve-readiness.json` 기준 다음 상태를 확인했다.

| 항목 | 현재 값 | 판정 |
|---|---|---|
| `execution_readiness.status` | `pass` | 실행 queue는 열림 |
| `learning_readiness.status` | **`learning_uncertain`** | 핵심 미완료 |
| `likely_to_learn` | `false` | 미충족 |
| `attempts_considered` | **7** | 최소 기준 10 미달 |
| `session_reports_considered` | 1 | v47 대비 소폭 개선 |
| `session_calibration_status` | `no_session_context` | 미해결 |
| `telemetry_coverage_ratio` | **0.0** | 미해결 |
| `rework_count` | 5 | 높음 |
| `hold_moving_average` | 0.2857 | 높음 |
| `defect_escape_pair_count` | 3 | 높음 |

리뷰-A의 분석이 가장 명확히 표현했듯이, 두 기준 리뷰 이후 **관측 방식은 강화됐지만 실제 readiness 값은 개선되지 않았다.** learning evidence hardening은 산출물 간 parity를 개선했을 뿐, 실제 learning 증거(attempts ≥10, session context, telemetry coverage >0)는 여전히 채워지지 않은 상태다.

---

## 5. 세 리뷰 간 주요 쟁점 분석

### 5.1 핵심 쟁점: Raw Registry 상태 — 추출 로케일에 따른 재현성 분기

이 항목이 세 리뷰 전체에서 가장 중요한 발산 지점이다.

#### 판정 요약

| 리뷰 | raw_registry_preflight 결과 | 추출 방법 |
|---|---|---|
| 리뷰-A | **FAIL** — error 46건, warning 46건 | 명시 없음 (escaped 결과 관찰됨) |
| 리뷰-B | **FAIL** — error 46건, warning 46건 | `LC_ALL=C LANG=C unzip -q` (C-로케일 명시) |
| 리뷰-C | **PASS** — error 0건, warning 0건, entry 446건 | "안전 추출" (UTF-8 환경으로 추정) |

리뷰-B와 리뷰-C는 동일한 ZIP SHA(`b33fed42...`)를 사용했다. 따라서 이 차이는 ZIP 내용물이 아닌 **추출 환경의 로케일(locale) 설정** 차이에서 비롯된다.

#### 분기 메커니즘

C-로케일(`LC_ALL=C`)로 ZIP을 추출하면 **Unicode 파일명이 `#Uxxxx` 이스케이프 형식**으로 변환된다. 예를 들어 `Anthropic's Long-Term Benefit Trust appoints Vas Narasimhan to Board of Directors.md`는 `Anthropic#U2019s Long-Term Benefit Trust appoints Vas Narasimhan to Board of Directors.md`로 추출된다. 이때 raw registry의 `storage_path`는 여전히 원본 Unicode 표기를 유지하므로, preflight가 **path_aliases가 없는 상태에서 46건 mismatch**를 보고한다. UTF-8 환경에서 추출하면 파일명이 Unicode 그대로 유지되고, registry의 `storage_path`와 일치하여 pass가 된다.

#### 이 쟁점이 의미하는 바

이 메커니즘은 세 리뷰에서 각기 다른 각도로 다루어진 raw registry 논쟁 전체를 일관되게 설명한다.

- **통합 감사 보고서**의 "P0 blocker" 판단은 C-로케일 추출 환경에서 재현되는 실제 실패였다.
- **이중 리뷰 보고서**의 "현재 ZIP에서는 재현되지 않는다"는 보정은 UTF-8 환경에서 추출했기 때문에 pass가 관측된 것이다.
- **리뷰-A**의 "이번 재실행에서 재확인됐다"는 판단도 C-로케일 환경의 결과다.
- **리뷰-C**의 pass 확인은 UTF-8 환경의 결과다.

따라서 raw registry의 실제 리스크는 두 층으로 나누어야 한다.

| 층 | 내용 |
|---|---|
| **환경 의존 리스크** | C-로케일 추출 환경(예: 일부 Linux CI, Windows, legacy 스크립트)에서는 raw path mismatch가 즉시 발생한다. 이 환경에서는 `make check`와 release gate가 차단된다. |
| **구조적 리스크** | registry `storage_path`가 Unicode 표기를 사용하는 한, C-로케일 환경에서의 재현성이 보장되지 않는다. path_aliases 또는 canonical escaped path로의 migration이 없으면 이 취약성이 잠재적으로 남는다. |

#### 통합 판정

raw registry 문제는 **"존재하는 실패인가 vs 존재하지 않는 실패인가"가 아니라 "어떤 환경에서 발생하는가"의 문제**다. 세 리뷰의 결과는 서로 모순되지 않으며, 추출 환경을 통일했을 때 결과가 수렴한다. 따라서 다음 단계는 raw registry failure의 실제 재현 조건을 명시적으로 고정하고, 모든 지원 환경에서 pass가 보장되도록 path alias 또는 canonical migration을 진행하는 것이다.

### 5.2 Bare Pytest Collection Error 수의 차이

| 리뷰 | bare pytest 결과 |
|---|---|
| 리뷰-A | `pytest --collect-only -q` → **106 collection errors**, 대표 오류: `ModuleNotFoundError: No module named 'ops'` |
| 리뷰-B | `pytest --collect-only -q` → **67 collection errors**, 대표 오류: `ModuleNotFoundError: No module named tests` |
| 리뷰-C | 직접 측정 없음 |

두 수치의 차이(106 vs 67)는 ZIP 버전이 약간 다를 가능성(52.zip vs 51.zip)이나 테스트 파일 구성의 미세한 차이에서 비롯된 것으로 보인다. 대표 오류 메시지도 다른데, 이 역시 동일한 근본 원인(bare `pytest` 실행 시 `PYTHONPATH`에 `ops` 모듈이 없음)의 서로 다른 발현이다.

세 리뷰 모두 이 현상의 **본질적 처리 방향**에는 동의한다: bare `pytest`는 지원되지 않는 진입점임을 명시하는 현재 contract가 유지되거나, `pythonpath = .` 지원으로 전환되거나, 둘 중 하나를 명확히 결정해야 한다.

### 5.3 전체 게이트 재현성 기록의 범위 차이

세 리뷰는 실제 실행한 검증의 폭이 서로 다르다. 이 차이는 각 리뷰의 결론 신뢰도와 커버리지를 이해하는 데 중요하다.

| 검증 항목 | 리뷰-A | 리뷰-B | 리뷰-C |
|---|---|---|---|
| raw_registry_preflight 직접 실행 | ✅ fail 재현 | ✅ fail 재현 | ✅ pass 확인 |
| dev-install | — | ✅ 성공 | ✅ 성공 (38.82s) |
| ruff/mypy | — | ✅ 성공 (157 source files) | ✅ pass (make static) |
| release-smoke unit tests | ✅ 16 passed | ✅ 16 passed | — |
| python -m pytest collect-only | — | ✅ 689 tests | ✅ 가능 |
| artifact freshness live 재생성 | ✅ debt 71/71/13 재확인 | ✅ 저장본/live 분리 확인 | ✅ 저장본 확인 |
| make release-smoke-fast | — | — | ✅ pass (54.11s) |
| make fast-smoke | — | — | ✅ fail (stale node id) |
| make unit-tests | — | — | ✅ timeout |
| make static / lint / eval / stage2 | — | — | ✅ pass (각각 pass) |
| make planning-gate | — | — | ✅ pass |

리뷰-C가 가장 넓은 gate별 실행 범위를 커버했고, `make fast-smoke` 실패라는 새로운 결함을 이 과정에서 식별했다. 리뷰-A는 raw registry 분석과 기준 리뷰 대비 재판정에 집중했고, 리뷰-B는 ZIP 구조 프로필과 타임라인 분석에 강점이 있다.

---

## 6. 리뷰별 고유 발견 사항

### 6.1 리뷰-A 고유 발견

#### Raw Registry Page별 Error 분포

리뷰-A는 46건 mismatch의 registry page별 분포를 가장 상세히 분석했다.

| registry page | 오류 수 |
|---|---:|
| `system/system-raw-registry/wiki/middle-east.md` | 17 |
| `system/system-raw-registry/wiki.md` | 15 |
| `system/system-raw-registry/wiki/ai-compute-control.md` | 8 |
| `system/system-raw-registry/wiki/ai-capability.md` | 3 |
| `system/system-raw-registry/wiki/ai-infra-compute-intake-2026-04-21.md` | 1 |
| `system/system-raw-registry/wiki/ai-execution.md` | 1 |
| `system/system-raw-registry/wiki/europe-tech-sovereignty.md` | 1 |

오류의 구조적 원인은 명확하다. registry의 `storage_path`는 `raw/web-snapshots/Anthropic's Long-Term Benefit Trust appoints Vas Narasimhan to Board of Directors.md`처럼 **사람이 읽는 Unicode 파일명**을 기억하고 있으나, 실제 파일 시스템에는 `raw/web-snapshots/Anthropic#U2019s Long-Term Benefit Trust appoints Vas Narasimhan to Board of Directors.md`처럼 **이스케이프된 canonical 경로**가 존재하며, 두 사이를 연결하는 `path_aliases`가 비어 있다.

#### 실데이터 Migration 3단계 분리 권고

리뷰-A는 이 문제를 해결하기 위한 3단계 작업 구분을 제안했다.

1. **실데이터 migration**: 실제 escaped filename 기준 canonical 경로 결정
2. **registry alias/backfill**: 기존 `storage_path`와 새 canonical path 사이 alias 기록
3. **shard audit**: `system/system-raw-registry/**` 전체를 page별 diff artifact로 보존

#### Release-Smoke Report Profile 분리 권고

현재 단일 `release-smoke-report.json` 경로는 fast/full 중 어느 profile이 마지막으로 덮어썼는지 혼동을 일으킬 수 있다. 리뷰-A는 다음을 권고했다.

- `ops/reports/release-smoke-report-fast.json`
- `ops/reports/release-smoke-report-full.json`

두 파일로 profile을 명시적으로 분리하는 것이 운영상 더 안전하다.

#### Current-Vault Raw Registry 결과의 Canonical Artifact화 필요

현재 raw registry 문제는 stdout 재실행으로는 즉시 드러나지만, 체크인된 canonical artifact로는 기록되지 않는다. `ops/reports/raw-registry-preflight-report.json`과 같은 canonical artifact가 없으면 machine-readable 상태 추적이 어렵다.

### 6.2 리뷰-B 고유 발견

#### ZIP 구조 전체 프로필

리뷰-B는 세 리뷰 중 유일하게 ZIP 내부 구조를 정량적으로 완전 분석했다.

| 항목 | 값 |
|---|---|
| ZIP SHA-256 | `b33fed4266d8c25ca0acd2d4bbd84603cddad5ec1c54fbfdef644a2dad3465e5` |
| ZIP 크기 | 191,236,219 bytes |
| 전체 entry 수 | 1665 |
| 파일 수 | 1583 |
| 디렉터리 수 | 82 |
| 압축 해제 총 바이트 | 240,559,534 |
| non-ASCII entry 수 | **334** |
| 최대 UTF-8 component 길이 | 167 bytes |
| root 직접 0-byte 파일 수 | 0 |
| runs 하위 0-byte placeholder | 15 |

non-ASCII entry가 334건에 달한다는 점은 이스케이프 처리 문제가 특정 파일에 국한되지 않고 구조적으로 광범위하게 관련됨을 시사한다.

#### 리뷰 이후 수정 파일 53개 타임라인 (상세)

리뷰-B는 `llm_wiki_vnext_dual_review_improvement_report_20260428.md` (mtime: 2026-04-28 11:38) 이후 수정된 53개 파일의 타임라인을 복원하여, 두 기준 리뷰 이후 실제로 이루어진 작업의 시간적 순서를 가장 상세하게 기록했다. 주요 구간은 다음과 같다.

| 시간대 | 주요 변경 |
|---|---|
| 12:30~12:41 | review_archive.py, schema, report 갱신 |
| 13:39~13:54 | auto-improve readiness runtime, schema, test, task observation |
| 13:54~13:57 | raw registry reproduction protocol test 추가 |
| 14:04~14:09 | release-smoke report, CI, README, schema, test 갱신 |
| 14:19~14:20 | bootstrap backfill (eval/lint/manifest 2026-04-12) |
| 14:37~14:53 | artifact freshness runtime, backfill scripts, archived run artifacts |
| 15:00~15:14 | Makefile, pyproject, schemas, final test surface |

#### Stored vs Live Stale 지표 분기 분석

리뷰-B는 mtime-sensitive 지표가 실행 시점에 따라 크게 달라짐을 구체적으로 수치화했다.

| 지표 | 저장본 | live 재생성 |
|---|---:|---:|
| `stale_artifact_count` | 34 | **90** |
| `mtime_sensitive_artifact_count` | 34 | **90** |
| `safe_to_backfill_artifact_count` | 121 | 65 |

이 분기는 mtime-sensitive 지표를 release gate의 required KPI로 사용하는 것이 부적합함을 명확히 보여준다.

#### 신규 개선 방안 9가지 (리뷰-B 독자 제안)

| 제안 | 내용 | 우선순위 |
|---|---|---|
| Raw path canonicalizer + alias migrator | registry `storage_path`를 escaped path 기준으로 정규화, Unicode 제목은 `display_path`/alias로 보존 | P0 |
| Current-tree report freshness gate | 모든 checked-in report에 source tree fingerprint 강제, 불일치 시 stale 판정 | P0 |
| Real-failure fixture generation | 46건 mismatch 중 3~5건을 축약 fixture로 고정 (synthetic healthy zip parity와 별도) | P0 |
| Stable-only artifact freshness required gate | `stable_contract_debt_*`만 required gate, mtime-sensitive는 advisory 분리 | P1 |
| Test execution summary artifact | command/진입점/profile/tree fingerprint/duration/timeout/interrupted 등을 `ops/reports/test-execution-summary.json`으로 저장 | P1 |
| Pytest entrypoint guardrail | 미지원 선택 시 친절한 실패 메시지, 지원 선택 시 `pythonpath=.` 또는 packaging strategy 변경 | P1 |
| Release-smoke partial report semantics | interrupted/partial report가 `status=fail`만 남기지 않도록 `phase`, `completed_command_count`, `termination_reason` 분리 | P1 |
| Clean-tree archive preflight | release archive 생성 전 `.pytest_cache`, `__pycache__`, `*.egg-info` 등 제외 검사 | P2 |
| Learning confidence SLO | attempts/session context/telemetry coverage/rework/defect escape 기준을 release confidence SLO로 명문화 | P1 |

### 6.3 리뷰-C 고유 발견

#### `make fast-smoke` 실패 — Stale Pytest Node ID

이 결함은 세 리뷰 중 **리뷰-C만이 식별한 신규 결함**으로, 즉각적인 수정이 필요한 항목이다.

```text
ERROR: not found:
tests/test_release_smoke.py::ReleaseSmokeTest::test_build_smoke_commands_matches_release_gate_contract
```

**실제 현재 테스트 이름**: `test_build_smoke_commands_match_release_gate_profiles`

release-smoke profile tiering 작업 이후 테스트 이름이 변경됐지만, Makefile의 `FAST_SMOKE_TESTS` 변수와 이를 기대하는 static test가 함께 갱신되지 않았다. `tests/test_makefile_static_gates.py`는 fast-smoke 목록의 존재를 점검하지만, 각 node id가 실제 pytest collection에서 유효한지는 검증하지 않는다.

이 결함은 `make release-smoke-fast`(pass, 54.11s)와 `make fast-smoke`(fail, 8.51s)가 다른 결과를 내는 이유이기도 하다. 두 명령이 다른 경로로 동일 내용을 검증하는 것처럼 보이지만, `make fast-smoke`는 stale node id로 즉시 실패한다.

**수정 방법**: Makefile의 `FAST_SMOKE_TESTS`에서 stale node id를 현재 이름(`test_build_smoke_commands_match_release_gate_profiles`)으로 갱신하고, `tests/test_makefile_static_gates.py`가 node id 실존성까지 검증하도록 보강한다.

#### `generated-artifact-index.json` Review Provenance Drift

이 항목 역시 **리뷰-C만이 식별한 신규 결함**이다.

현재 실제 `external-reports/` root 파일 수는 **18개**이지만, `ops/reports/generated-artifact-index.json` 저장본은 다음을 유지한다.

```json
{
  "external_reports_root_file_count": 16,
  "canonical_report_count": 30,
  "archive_candidate_count": 17
}
```

두 대상 리뷰 파일이 ZIP에 추가된 이후 index가 갱신되지 않아 발생한 drift다.

| 파일 | 실제 ZIP 존재 | generated-artifact-index canonical report 포함 |
|---|---:|---:|
| `external-reports/llm_wiki_vnext_integrated_audit_report_20260428.md` | ✅ | ❌ |
| `external-reports/llm_wiki_vnext_dual_review_improvement_report_20260428.md` | ✅ | ❌ |

artifact freshness는 해당 파일을 schema-backed currentness 관점에서는 `current`로 분류하지만, record에는 `mtime_status=stale`, `generated_at_older_than_file_mtime`이 남아 있다. 이는 단순 mtime warning이 아니라 **review provenance index freshness gap**으로 별도 처리해야 한다.

#### Gate 실행 결과 전체 (리뷰-C 기준)

리뷰-C가 직접 실행하여 결과를 확보한 게이트 전체 목록이다.

| 검증 항목 | 결과 | 소요 | 해석 |
|---|---|---:|---|
| `make dev-install` | pass | 38.82s | uv 기반 dev dependency 및 editable install 성공 |
| `make registry-preflight` | **pass** | 6.05s | raw registry mismatch 없음 (UTF-8 추출 환경) |
| `make static` | pass | 10.11s | ruff, mypy allowlist 통과 |
| `make artifact-freshness-check` | pass | 17.21s | fail-on-fail 통과 |
| `make lint` | pass | 40.80s | error/warning 0, review candidates 51 |
| `make eval` | pass | 11.51s | max score requirement 통과 |
| `make stage2-eval` | pass | 5.10s | stage2 source-count check 통과 |
| `make planning-gate` | pass | 4.11s | starter artifact schema/cross-check 통과 |
| `make release-smoke-fast` | **pass** | 54.11s | fast archive/manifest profile 통과 |
| `make fast-smoke` | **fail** | 8.51s | stale pytest node id |
| `make unit-tests` | timeout | 55.48s | 현재 도구 제한 내 미완주 |

---

## 7. 기준 리뷰 두 건에 대한 현재 시점 재판정

### 7.1 통합 감사 보고서에 대한 재판정

| 판단 항목 | 현재 시점 판정 |
|---|---|
| "이전 기준선보다 실질 진전이 있다" | **유지** — 세 리뷰 모두 동의 |
| "stable artifact debt 79/79/17이 문제다" | **부분 유지** — 현재는 71/71/13으로 일부 해소됐으나 여전히 크다 |
| "learning readiness는 아직 미해결" | **그대로 유지** — 세 리뷰 모두 동의 |
| "raw_registry_preflight 46건 mismatch는 실제 P0 blocker" | **조건부 유지** — C-로케일 추출 환경에서는 재현됨, UTF-8 환경에서는 미재현 |
| "release-smoke는 full profile만 존재한다" | **폐기** — fast/full 분리가 현재 코드/CI/문서에 실질 반영됨 |
| "pytest 진입점 정리가 필요하다" | **부분 반영 완료** — 계약 명시 완료, make fast-smoke의 stale node id라는 새 문제 발생 |

### 7.2 이중 리뷰 대조 보고서에 대한 재판정

| 판단 항목 | 현재 시점 판정 |
|---|---|
| "진전된 후속 스냅샷이다" | **유지** — 세 리뷰 모두 동의 |
| "artifact debt / learning readiness / gate tiering이 핵심 과제다" | **유지** — 세 리뷰 모두 동의 |
| "bare pytest는 contract mismatch로 봐야 한다" | **유지** — 현재 README/pytest.ini/static test 기준과 일치 |
| "raw registry live failure는 현재 ZIP에서 재현되지 않는다" | **조건부 유지** — UTF-8 추출 환경에서는 재현되지 않음(리뷰-C 확인). C-로케일 환경에서는 재현됨(리뷰-A/B 확인). 추출 환경에 따라 결과가 달라지므로, 추출 환경 통일과 재현 프로토콜 고정이 먼저 필요하다. |
| "raw registry 이슈는 복구보다 재현 프로토콜 고정이 먼저" | **유지** — 현재 fixture 추가 방향과 일치. 단, 실데이터 수준의 mismatch fixture 포괄이 아직 부족. |

---

## 8. 통합 잔여 과제 목록

세 리뷰의 모든 지적을 항목 중복 없이 통합한 전체 잔여 과제다.

### P0 — Release Blocker

| ID | 과제 | 근거 | 완료 기준 |
|---|---|---|---|
| P0-1 | Raw registry 추출 환경별 재현성 고정 + canonical path migration | C-로케일 추출 시 46건 mismatch 발생. registry `storage_path`와 파일 시스템 경로의 alias 불일치. | 모든 지원 추출 환경(C-locale/UTF-8)에서 `raw_registry_preflight` pass. mismatch 0, warning 0. |
| P0-2 | 체크인 release-smoke pass report의 current-tree fingerprint 검증 | 저장본 full pass report가 이후 수정된 소스 트리 전체를 대표하지 않음. live raw preflight와 충돌. | report에 source_tree_fingerprint 포함. 현재 tree와 불일치 시 `stale_report`로 자동 fail/warn. |
| P0-3 | Stable artifact debt 추가 감축 | `71/71/13`, stable issue 155건 잔존. | missing_schema=0 또는 명시적 noncanonical classification. missing_envelope/currentness < 50. |
| P0-4 | Learning readiness `confirmed` 전환 | attempts 7, no_session_context, telemetry 0.0, likely_to_learn=false. | attempts ≥10, session context 연결, telemetry coverage >0, `likely_to_learn=true` 또는 named blocker 명시. |

### P1 — 단기 필수

| ID | 과제 | 근거 | 권장 처리 |
|---|---|---|---|
| P1-1 | `make fast-smoke` stale node id 즉시 수정 (신규, 리뷰-C) | `test_build_smoke_commands_matches_release_gate_contract`가 없음. 실제 이름은 `test_build_smoke_commands_match_release_gate_profiles`. | Makefile `FAST_SMOKE_TESTS` 갱신 + static gate node id 실존성 검증 추가. |
| P1-2 | `generated-artifact-index.json` 재생성 및 drift guard 추가 (신규, 리뷰-C) | external-reports root 실제 18개 vs index 16개 표시. 두 기준 리뷰 파일 미인덱스. | `generated_artifact_index` 재실행. 실제 파일 수와 summary 불일치 시 CI 실패. |
| P1-3 | Bare pytest 진입점 계약 최종 결정 및 UX 개선 | 현재 "미지원"으로 분류됐지만 기여자 혼동 가능성 지속. | 미지원 유지 시 더 친절한 실패 메시지 제공. 지원 전환 시 `pythonpath=.` 또는 packaging strategy 변경. |
| P1-4 | Release-smoke full live 재실행 증적 최신화 | 저장된 full pass report(2026-04-28T05:04:20Z)가 이후 변경된 소스 트리 전체를 대표하지 않음. | 최신 소스 tree fingerprint 기준 full pass 재생성. 가능하면 fast/full report 파일 분리. |
| P1-5 | Proposal lifecycle ledger 완결 | execution readiness는 pass지만 learning confidence와 분리된 상태. | candidate→proposal→run→decision→outcome→learning signal 단일 trace 완성. |
| P1-6 | Missing schema 13건 tranche 처리 | `safe_to_backfill=true`, `mtime_sensitive=false` 10건이 명확한 처리 후보. | safe 10건 우선 family schema 또는 archived classification. sensitive 3건은 별도 기준 수립. |
| P1-7 | Artifact freshness stable/mtime-sensitive gate 분리 | stored 34건 vs live 90건 분기. mtime-sensitive 지표를 required gate KPI로 사용 불가. | stable_contract_debt만 required gate, mtime-sensitive는 advisory channel로 완전 분리. |
| P1-8 | Test execution summary artifact 도입 | make unit-tests timeout vs failure 구분 불가. 리뷰 간 상충 해소 수단 부재. | `ops/reports/test-execution-summary.json` 또는 `runs/<run-id>/test-execution-summary.json` 도입. |

### P2 — 중기 권장

| ID | 과제 | 기대 효과 |
|---|---|---|
| P2-1 | `raw-registry-preflight-report.json` canonical artifact 추가 (리뷰-A) | machine-readable 상태 추적 가능. page별 mismatch / alias gap / warning count 구조화 저장. |
| P2-2 | Release-smoke `release-smoke-full` alias 추가 (리뷰-C) | Makefile/CI/README 용어 일관성. `release-smoke-fast`와 대칭 구조 완성. |
| P2-3 | Run log placeholder 0-byte 파일 정책 문서화 | runs 하위 15개 0-byte placeholder의 false positive 방지. |
| P2-4 | Path budget margin 지속 모니터링 | non-ASCII entry 334건, max UTF-8 component 167 bytes. 255bytes 한계 접근 시 알림. |
| P2-5 | Clean-tree archive preflight 추가 | `.pytest_cache`, `__pycache__`, `*.egg-info`, 외부 venv/캐시가 archive에 섞이지 않도록 함. |
| P2-6 | Review self-inclusion 정책 명문화 | 외부 리뷰와 checkpoint 내부 산출물의 포함 기준을 manifest로 명확히 함. |
| P2-7 | Real-failure fixture generation (리뷰-B) | 46건 mismatch 중 3~5건을 축약 fixture로 고정. synthetic healthy zip parity와 분리 보존. |

---

## 9. 통합 신규 개선 방안

세 리뷰에서 제안된 개선 방안을 중복 제거 후 통합했다.

| 제안 | 출처 | 내용 | 우선순위 |
|---|---|---|---|
| Raw path canonicalizer + alias migrator | 리뷰-A, 리뷰-B | registry `storage_path`를 escaped path 기준으로 정규화. Unicode 제목은 `display_path`/alias로 보존. preflight가 mismatch에 대해 자동 patch 후보 출력. | P0 |
| Current-tree report freshness gate | 리뷰-A, 리뷰-B | 모든 checked-in report에 source tree fingerprint 강제. 현재 tree와 불일치 시 `stale_report` 판정. | P0 |
| Real-failure fixture generation | 리뷰-B | 현재 46건 mismatch 중 3~5건을 C-로케일 추출 환경 기준 축약 fixture로 고정. | P0 |
| FAST_SMOKE_TESTS node id 실존성 검사 | 리뷰-C | `FAST_SMOKE_TESTS`에 들어간 node가 실제 pytest collection 결과에 존재하는지 dedicated contract test 추가. | P1 (즉시) |
| Generated artifact index drift guard | 리뷰-C | 실제 `external-reports/` root file count와 index summary 불일치 시 CI fail. | P1 |
| Test execution summary artifact | 리뷰-B, 리뷰-C | command/진입점/profile/tree fingerprint/duration/timeout/collected/failed를 구조화 저장. timeout과 assertion failure를 명확히 구분. | P1 |
| Stable-only artifact freshness required gate | 리뷰-B | `stable_contract_debt_*`만 required gate에 사용. stale/mtime-sensitive는 advisory channel 분리. | P1 |
| Release-smoke profile report 파일 분리 | 리뷰-A | `release-smoke-report-fast.json` / `release-smoke-report-full.json`으로 명시적 분리. | P1 |
| release-smoke-full alias 추가 | 리뷰-C | `release-smoke-full: release-smoke` target을 Makefile에 추가하여 fast/full 대칭 구조 완성. | P1 |
| Pytest entrypoint guardrail | 리뷰-A, 리뷰-B | 미지원 선택 시 README 강화 + helper script 친절한 안내. 지원 전환 시 `pythonpath=.` 설정 또는 packaging contract 재설계. | P1 |
| Learning confidence SLO 명문화 | 리뷰-B | attempts/session context/telemetry coverage/rework/defect escape 기준을 release confidence SLO 문서로 확정. | P1 |
| Artifact freshness KPI 4-묶음 분리 리포트 | 리뷰-C | stable release blocker / safe backfill queue / mtime-sensitive regenerate queue / archived/legacy accepted debt의 4개 구분 출력. | P1 |
| Clean-tree archive preflight | 리뷰-B | `.pytest_cache`, `__pycache__`, `*.egg-info` 등 로컬 산출물을 archive에서 사전 제거. | P2 |
| Run log placeholder 정책 문서화 | 리뷰-B | 0-byte placeholder 15건이 false positive debt가 되지 않도록 retention 정책 명문화. | P2 |

---

## 10. 통합 권장 실행 순서

세 리뷰의 권장 순서를 통합하여 단일 PR 시퀀스로 재구성했다.

### PR-1. `make fast-smoke` 즉시 복구 *(리뷰-C 신규 식별)*

- Makefile `FAST_SMOKE_TESTS`에서 stale node id를 현재 이름으로 갱신.
- `tests/test_makefile_static_gates.py`가 node id 실존성까지 검증하도록 보강.
- **완료 기준**: `make fast-smoke` pass.

### PR-2. Generated Artifact Index 재생성 및 Drift Guard *(리뷰-C 신규 식별)*

- `python -m ops.scripts.generated_artifact_index --vault . --out ops/reports/generated-artifact-index.json` 재실행.
- 두 기준 리뷰 파일이 canonical 또는 archive candidate 정책에 맞게 분류되었는지 확인.
- 실제 `external-reports/` 파일 수와 summary 불일치 시 CI 실패하도록 guard 추가.
- **완료 기준**: index가 실제 18개를 반영하고, 두 기준 리뷰 파일이 적절히 분류됨.

### PR-3. Raw Registry 추출 환경 통일 + Canonical Path Migration

- 추출 로케일 표준을 UTF-8로 지정하고, C-로케일 추출 방지 또는 alias bridge 보강.
- registry `storage_path`를 실제 escaped filename 기준 canonical path로 정규화.
- Unicode 제목은 `display_path` 또는 alias로 보존.
- path_aliases bridge 생성으로 두 환경에서 모두 pass 보장.
- Real-failure fixture(3~5건)를 C-로케일 환경 재현 보증용으로 고정.
- **완료 기준**: UTF-8 및 C-로케일 추출 환경 모두에서 `raw_registry_preflight` pass. error 0, warning 0.

### PR-4. Artifact Debt 다음 Tranche

- missing schema 13건 중 safe 10건(`safe_to_backfill=true`, `mtime_sensitive=false`)을 family schema 또는 archived classification으로 먼저 닫기.
- `ops_reports` 측 envelope/currentness 미해결 7건 처리.
- envelope/currentness 71건 중 safe_to_backfill 42건을 owner family별로 tranche 분리.
- **완료 기준**: `missing_schema_count ≤ 3`, `missing_artifact_envelope_count < 50`.

### PR-5. Learning Evidence Closure

- bounded auto-improve run 1개를 operator-approved trial로 명시적 실행.
- run outcome을 proposal lifecycle ledger에 연결.
- routing provenance aggregate에 runtime event telemetry 채우기.
- **완료 기준**: `attempts_considered ≥ 10`, `session_calibration_status ≠ no_session_context`, `telemetry_coverage_ratio > 0`, `likely_to_learn = true` 또는 named blocker 명시.

### PR-6. Release-Smoke Full Live 재실행 및 증적 갱신

- PR-3 완료 이후 최신 소스 tree fingerprint 기준 full release-smoke 재실행.
- 가능하면 `release-smoke-report-fast.json` / `release-smoke-report-full.json` 분리.
- **완료 기준**: 최신 코드 + 최신 contract 기준 canonical full pass evidence 체크인.

### PR-7. Test/Gate Tiering 및 UX 정비

- dev-fast / contract-check / release-smoke-fast / release-smoke-full을 CI와 Makefile에서 명확히 분리.
- `test-execution-summary.json` 도입.
- bare pytest 미지원/지원 중 하나 완전 확정 + 사용자-facing 실패 메시지 개선.
- `release-smoke-full` alias 추가.
- stable-only artifact freshness required gate 분리 완성.

### PR-8. Archive Hygiene 및 중기 개선

- clean-tree archive preflight 추가.
- run log placeholder 정책 문서화.
- path budget margin 모니터링 자동화.
- review self-inclusion 정책 명문화.

---

## 11. 최종 통합 판정

### 11.1 현재 스냅샷 상태

현재 ZIP은 두 기준 리뷰 이후에도 실질적인 보강 작업이 계속된 더 진전된 스냅샷이다. 다음 항목들은 명확한 후속 반영으로 인정된다.

| 완료 항목 | 세 리뷰 공통 확인 여부 |
|---|---|
| Review-archive canonical parity guard | ✅ |
| Learning evidence hardening (관측 강화) | ✅ |
| Raw-registry extracted-zip reproduction fixture | ✅ |
| Release-smoke fast/full profile 이중 구조 도입 | ✅ |
| Pytest entrypoint contract 명시 | ✅ |
| Historical bootstrap / archived run backfill | ✅ |
| Stable artifact debt 추가 감축 (79/79/17 → 71/71/13) | ✅ |

### 11.2 Release-Ready 판정 불가 이유

현재 스냅샷이 release-ready라고 보기 어려운 이유는 세 가지다.

1. **Raw registry 재현성 불확실성**: C-로케일 추출 환경에서는 46건 mismatch가 실제로 발생한다. 이 조건에서는 release gate가 차단된다. 추출 환경을 통일하거나 alias bridge가 완성되기 전까지 환경에 따라 결과가 달라지는 취약성이 남는다.

2. **Learning readiness 미완결**: `attempts_considered=7`, `telemetry_coverage_ratio=0.0`, `session_calibration_status=no_session_context`, `likely_to_learn=false` 상태가 그대로다.

3. **Stable artifact debt 잔존**: `71/71/13`은 감소 추세에 있지만 아직 충분히 크다.

### 11.3 세 리뷰 간 합의 및 쟁점 최종 정리

| 항목 | 합의 수준 |
|---|---|
| "두 기준 리뷰 이후 실질 진전이 있다" | **세 리뷰 만장일치** |
| "stable artifact debt 71/71/13이 핵심 잔여 과제다" | **세 리뷰 만장일치** |
| "learning readiness는 아직 미완결이다" | **세 리뷰 만장일치** |
| "release-smoke fast/full profile 개선은 완료됐다" | **세 리뷰 만장일치** |
| "pytest entrypoint contract 명시는 완료됐다" | **세 리뷰 만장일치** |
| "raw registry는 모든 환경에서 blocker다" | **불일치** — C-로케일 환경에서는 blocker, UTF-8 환경에서는 pass. 추출 환경 통일 후 재판정 필요. |
| "`make fast-smoke` stale node id 실패" | **리뷰-C만 식별** — 즉각 수정 필요 |
| "generated-artifact-index drift" | **리뷰-C만 식별** — PR-2로 즉시 처리 필요 |

### 11.4 최종 한 줄 요약

> **현재 스냅샷은 두 기준 리뷰 이후 실질적 보강이 누적된 더 진전된 상태이나, raw registry 추출 환경 의존성·learning confidence 미달·stable artifact debt 잔존이 release-ready를 막고 있다. 다음 단계는 `make fast-smoke` 즉시 복구, generated index drift 정정, raw registry canonical path migration 순으로 진행하는 것이 가장 안전한 경로다.**

---

## 12. 부록: 리뷰 간 핵심 수치 비교표

### 12.1 검증 실행 결과 종합

| 검증 항목 | 리뷰-A | 리뷰-B | 리뷰-C |
|---|---|---|---|
| ZIP 무결성 | — | CRC 오류 없음 | 안전 추출 완료 |
| 파일 수 | — | 1583 | 1583 |
| non-ASCII entry 수 | — | 334 | — |
| dev-install | — | ✅ success | ✅ success (38.82s) |
| ruff | — | ✅ All checks passed | ✅ pass |
| mypy | — | ✅ 157 source files | ✅ pass |
| raw_registry_preflight | ❌ fail (46/46) | ❌ fail (46/46) | ✅ pass (0/0) |
| python -m pytest collect-only | — | ✅ 689 tests | ✅ 가능 |
| bare pytest collect-only | ❌ 106 errors | ❌ 67 errors | — |
| release-smoke unit tests | ✅ 16 passed | ✅ 16 passed | — |
| report schema tests | — | ✅ 28 passed | — |
| artifact freshness live | ✅ 71/71/13 | ✅ 71/71/13 | ✅ 71/71/13 |
| make release-smoke-fast | — | — | ✅ pass (54.11s) |
| make fast-smoke | — | — | ❌ fail (stale node) |
| make unit-tests | — | — | ⏱ timeout |

### 12.2 Artifact Debt 변화 추적

| 지표 | v47 기준선 | 기준 리뷰 시점 | 현재 | 변화 |
|---|---:|---:|---:|---:|
| `missing_artifact_envelope` | 106 | 79 | **71** | -8 |
| `unknown_currentness` | 106 | 79 | **71** | -8 |
| `missing_schema` | 17 | 17 | **13** | -4 |
| `missing_generated_at` | — | 30 | **27** | -3 |
| `stable_contract_debt_issue_count` | — | 175 | **155** | -20 |
| `mtime_sensitive_artifact_count` | — | 65 | **34 (stored)** / 90 (live) | -31 (stored) |

### 12.3 Learning Readiness 상태 비교

| 항목 | 기준 리뷰 시점 | 현재 |
|---|---|---|
| `execution_readiness.status` | — | pass |
| `learning_readiness.status` | `learning_uncertain` | `learning_uncertain` |
| `attempts_considered` | 7 | 7 |
| `session_calibration_status` | `no_session_context` | `no_session_context` |
| `telemetry_coverage_ratio` | 0.0 | 0.0 |
| `rework_count` | 5 | 5 |
| `defect_escape_pair_count` | 3 | 3 |

> learning readiness는 기준 리뷰 시점과 현재 사이에 수치 변화가 없다. 관측 및 계약 구조는 강화됐지만 실제 evidence는 아직 채워지지 않았다.

---

*본 보고서는 리뷰-A, 리뷰-B, 리뷰-C 세 건의 내용을 전문 기준으로 교차 검토하여 작성했다. 세 리뷰 간에 순위 및 우열은 없으며, 발산 지점은 양립 가능한 해석을 우선 제시하고 구조적 차이는 명시적으로 기술했다.*
