# LLM Wiki vNext 통합 검토 보고서

- **작성일**: 2026-04-27
- **출력 파일명**: `llm_wiki_vnext_integrated_unified_report_20260427.md`
- **통합 대상 리뷰 A**: `llm_wiki_vnext_v47_reconciliation_improvement_report_20260427.md`
- **통합 대상 리뷰 B**: `llm_wiki_vnext_followup_review_verification_improvement_report_20260427.md`
- **공통 검토 기준 ZIP**: `LLM Wiki vNext(47).zip`
- **ZIP SHA-256**: `982007cc09a430708216306b454875f4f810822f5d9ae61ad012645cdd5d37d4`
- **작성 언어**: 한국어
- **통합 원칙**: 두 리뷰는 동일한 체크포인트를 서로 독립적으로 검토한 산출물이며, 숫자 순서에 따른 우열이 없다. 각 리뷰의 판단을 동등하게 취급하여 교차 대조 후 하나의 일관된 결론으로 합성했다.

---

## 목차

1. [최종 결론 요약](#1-최종-결론-요약)
2. [검토 범위 및 공통 검증 내역](#2-검토-범위-및-공통-검증-내역)
3. [체크포인트 동일성 및 Snapshot Drift 확정](#3-체크포인트-동일성-및-snapshot-drift-확정)
4. [현재 ZIP 실제 프로필 (공통 확정값)](#4-현재-zip-실제-프로필-공통-확정값)
5. [두 리뷰의 공통 합의 항목](#5-두-리뷰의-공통-합의-항목)
6. [완료된 항목 상세 판정](#6-완료된-항목-상세-판정)
7. [미완료 핵심 잔여 작업 상세](#7-미완료-핵심-잔여-작업-상세)
8. [두 리뷰 간 관점 차이 및 보완점](#8-두-리뷰-간-관점-차이-및-보완점)
9. [원본 리뷰 보정 필요 문장 목록](#9-원본-리뷰-보정-필요-문장-목록)
10. [통합 Acceptance Criteria 판정표](#10-통합-acceptance-criteria-판정표)
11. [권장 실행 순서 (통합 Backlog)](#11-권장-실행-순서-통합-backlog)
12. [현재 체크포인트 상태 라벨](#12-현재-체크포인트-상태-라벨)
13. [한 줄 요약](#13-한-줄-요약)

---

## 1. 최종 결론 요약

두 리뷰는 서로 독립적으로 동일한 ZIP에 접근했음에도 핵심 판단에서 높은 수준의 일치를 보인다. 이하는 교차 대조를 통해 확정된 통합 결론이다.

### 1.1 체크포인트 정체성

현재 `LLM Wiki vNext(47).zip`은 두 리뷰가 공통으로 검토한 follow-up 보고서(`llm_wiki_vnext_integrated_reconciliation_followup_report_20260427.md`)가 기준으로 삼은 ZIP보다 **한 단계 더 진행된 후속 스냅샷**이다. 원본 follow-up 리뷰가 헤더에 기재한 ZIP SHA-256(`daca2ea1f9f22645103e4b4b69f74271c27f3906a4e39648f6c00d2476319064`)과 현재 ZIP의 실제 SHA-256(`982007cc09a430708216306b454875f4f810822f5d9ae61ad012645cdd5d37d4`)이 다르며, 이 차이는 단순 표기 오류가 아니다. 현재 ZIP 안에 해당 follow-up 리뷰 파일이 `external-reports/`에 포함되어 있고, 파일 수와 바이트 합계도 증가했다는 사실이 두 리뷰를 통해 모두 확인된다. 이 snapshot drift는 프로젝트 운영의 구조적 패턴, 즉 "리뷰 → 후속 구현 → 리뷰 포함 재패키징"을 반영한 결과다.

### 1.2 이미 닫힌 항목

두 리뷰 모두 다음 항목이 **현재 ZIP 기준으로 해소됨**을 독립적으로 확인했다.

| 해소된 항목 | 공통 판정 |
|---|---|
| POSIX C-locale ZIP 해제 실패 | 닫힘 |
| root 0-byte placeholder 파일 | 닫힘 |
| self-improve queue empty / `can_run=false` | 닫힘 (`can_run=true`, `runnable_proposal_count=1`) |
| `schema_invalid_artifact_count` > 0 | 닫힘 (현재 0건) |
| skipped run 1건 | 닫힘 (archived/excluded로 재분류, `runs_skipped=0`) |
| stored `missing_generated_at` action drift | 닫힘 (저장본 action이 `backfill_generated_at_or_mark_legacy_noncanonical`으로 갱신됨) |
| 긴 한글 파일명 POSIX offender | 닫힘 (slug 처리 + frontmatter 원제목 보존 확인) |

### 1.3 여전히 열려 있는 핵심 병목

두 리뷰가 공통으로 지목한 잔여 병목은 다음 다섯 개 축이다.

| 축 | 핵심 지표 | 우선순위 |
|---|---|---|
| **Artifact contract debt** | `missing_artifact_envelope=106`, `unknown_currentness=106`, `missing_schema=17` | P0 |
| **Learning/session/loop-health evidence 부족** | `attempts_considered=7`, `session_reports_considered=0`, `loop_health_summary.status=missing` | P0 |
| **Release-smoke full E2E 미확정** | partial report 표면 존재, full 완료 증거 없음 | P0/P1 |
| **Proposal lifecycle ledger 미연결** | proposal 1건 존재, decision→outcome trace 없음 | P1 |
| **Pytest 진입점 계약 미확정** | `pytest.ini`에 `pythonpath=.` 없음, 공식 경로 불명확 | P1 |

### 1.4 현재 체크포인트 단 한 줄의 상태

> 현재 ZIP은 v44/v45 이후 누적된 portability, root placeholder, skipped run, stored report drift 문제를 실질적으로 닫은 후속 스냅샷이다. 그러나 artifact contract debt 106/106/17, learning evidence 부재, release-smoke full gate 미확정, proposal lifecycle trace 부재가 남아 있어 **stabilization phase**로 분류해야 하며, release-ready 상태는 아니다.

---

## 2. 검토 범위 및 공통 검증 내역

### 2.1 두 리뷰가 공통으로 확인한 입력 파일

| 구분 | 경로/식별자 | 비고 |
|---|---|---|
| 검토 대상 follow-up 리뷰 | `llm_wiki_vnext_integrated_reconciliation_followup_report_20260427.md` | SHA-256: `95d4b1216328942e...` |
| 현재 실제 ZIP | `LLM Wiki vNext(47).zip` | SHA: `982007cc09a43070...` |
| artifact freshness report | `ops/reports/artifact-freshness-report.json` | 두 리뷰 모두 직접 파싱 |
| mechanism review candidates | `ops/reports/mechanism-review-candidates.json` | 두 리뷰 모두 직접 확인 |
| mutation proposals | `ops/reports/mutation-proposals.json` | 두 리뷰 모두 직접 확인 |
| auto-improve readiness | `ops/reports/auto-improve-readiness.json` | 두 리뷰 모두 직접 확인 |
| release-smoke runtime | `ops/scripts/release_smoke.py` | 두 리뷰 모두 텍스트 표면 확인 |
| release-smoke schema | `ops/schemas/release-smoke-report.schema.json` | 두 리뷰 모두 확인 |
| test files | `tests/test_release_smoke.py`, `tests/test_generated_report_contracts.py` | 두 리뷰 모두 확인 |
| backfill 3개 slice | `manual-mutate-defect-registry.json`, `cyclonedx-bom.json`, `openvex-draft.json` | 두 리뷰 모두 확인 |

### 2.2 리뷰 A만 확인한 추가 파일

| 파일 | 주요 내용 |
|---|---|
| `pytest.ini` 전체 내용 | `pythonpath=.` 부재 직접 확인 |
| `Makefile` 내부 `PUBLIC_PYTHON` 계산 | `$(firstword $(PYTHON))` 사용 확인 |
| ZIP 내부 기존 리뷰 목록 (3건) | SHA 대조 후 세대 체계 확인 |

### 2.3 리뷰 B만 수행한 추가 검증

| 검증 항목 | 결과 |
|---|---|
| Python `zipfile.testzip()` | `None` (CRC 오류 없음) |
| `LC_ALL=C LANG=C unzip -q` 전체 해제 | 성공 |
| Python `extractall()` | 성공 |
| `tests/test_release_smoke.py` 테스트 메서드 수 계산 | 13개 |

### 2.4 두 리뷰 공통 한계

| 항목 | 내용 |
|---|---|
| full release-smoke E2E | 직접 실행 완료 증거 없음 |
| ruff, mypy, public export 전체 재실행 | 직접 수행하지 않음 |
| 전체 pytest 스위트 통과 | 직접 수행하지 않음 |
| CRC 전체 zip testzip (장시간) | 리뷰 A에서 종료 지연으로 보류; 리뷰 B에서 Python API로 별도 확인 |

---

## 3. 체크포인트 동일성 및 Snapshot Drift 확정

### 3.1 세대 체계 정리

두 리뷰가 교차 확인한 결과, 현재까지의 ZIP 세대 체계는 다음과 같이 정리된다.

| 세대 | ZIP SHA-256 (참조) | 주요 특징 |
|---|---|---|
| 초기 세대 | `6f2c8f491b75...` | `integrated_review_report_20260426.md` 기준 |
| 중간 세대 | `86596f5054ee...` | `review_improvement_report_20260427.md` 기준 |
| follow-up 리뷰 기준 세대 | `daca2ea1f9f226...19064` | follow-up 리뷰 헤더에 기재된 ZIP |
| **현재 업로드 ZIP (최신)** | **`982007cc09a430...37d4`** | follow-up 리뷰 포함 후 재패키징 |

### 3.2 수치 불일치 항목 비교

| 항목 | Follow-up 리뷰 기재값 | 현재 실제 ZIP | 차이 |
|---|---:|---:|---:|
| ZIP SHA-256 | `daca2ea1...` | `982007cc...` | 불일치 |
| ZIP 크기 (bytes) | 191,242,525 | 191,262,121 | +19,596 |
| entry 수 | 1,636 | 1,638 | +2 |
| 파일 수 | 1,562 | 1,564 | +2 |
| 디렉터리 수 | 74 | 74 | 동일 |
| `external-reports` 파일 수 | 33 | 34 | +1 |
| `tests` 파일 수 | 121 | 122 | +1 |
| `.md` 파일 수 | 940 | 941 | +1 |
| `.py` 파일 수 | 277 | 278 | +1 |
| 압축 해제 바이트 합 | 240,648,910 | 240,720,640 | +71,730 |

이 차이는 follow-up 리뷰 파일 자체가 `external-reports/`에 추가되고 연관 테스트 파일이 1개 추가된 데 기인한다고 보는 것이 두 리뷰의 공통 결론이다.

---

## 4. 현재 ZIP 실제 프로필 (공통 확정값)

두 리뷰가 독립적으로 계산한 값이 일치하므로 이하 수치를 이 보고서의 기준값으로 확정한다.

### 4.1 기본 수치

| 항목 | 확정값 |
|---|---|
| ZIP SHA-256 | `982007cc09a430708216306b454875f4f810822f5d9ae61ad012645cdd5d37d4` |
| ZIP 크기 | 191,262,121 bytes |
| entry 수 | 1,638 |
| 파일 수 | 1,564 |
| 디렉터리 수 | 74 |
| 압축 해제 전체 바이트 합 | 240,720,640 bytes |
| non-ASCII entry 수 | 334 |
| 최대 UTF-8 component 길이 | 167 bytes |
| Python CRC 검증 (`zipfile.testzip()`) | `None` (오류 없음) |
| C-locale Info-ZIP 해제 | 성공 |

### 4.2 최상위 경로별 파일 분포

| 최상위 경로 | 파일 수 |
|---|---:|
| `raw` | 446 |
| `wiki` | 417 |
| `ops` | 278 |
| `runs` | 156 |
| `tests` | 122 |
| `system` | 71 |
| `external-reports` | 34 |
| root 직접 파일 | 17 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |
| `.vscode` | 1 |
| `review` (빈 디렉터리) | 0 |
| `tmp` (빈 디렉터리) | 0 |

> **참고**: `review/`와 `tmp/`는 파일 수 표에는 0으로 나타나지만 ZIP 최상위 명시적 디렉터리로 존재한다. 리뷰 A는 이를 P2 hygiene 이슈로, 리뷰 B는 별도 정책 명시가 필요한 문서화 항목으로 분류했다.

### 4.3 확장자 분포

| 확장자 | 파일 수 |
|---|---:|
| `.md` | 941 |
| `.py` | 278 |
| `.json` | 215 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.yaml` | 13 |
| `.toml` | 10 |
| `.jsonl` | 6 |
| 확장자 없음 | 5 |
| `.docx` | 2 |
| `.yml` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

### 4.4 root 직접 파일 17개 (확정 목록)

| 파일명 |
|---|
| `.gitattributes` |
| `.gitignore` |
| `AGENTS.local.md` |
| `AGENTS.md` |
| `ARCHITECTURE.md` |
| `CHANGELOG.md` |
| `CONTRIBUTING.md` |
| `LICENSE` |
| `Makefile` |
| `pyproject.toml` |
| `pytest.ini` |
| `README.md` |
| `requirements-dev.txt` |
| `requirements.txt` |
| `SECURITY.md` |
| `THIRD_PARTY_NOTICES.md` |
| `uv.lock` |

### 4.5 0-byte 파일 (15개, runs/ 하위 전용)

0-byte 파일은 모두 `runs/` 하위의 stdout/stderr placeholder다. root 직접 0-byte 파일은 없다.

| 경로 |
|---|
| `runs/archive/run-20260415-mechanism-planning-gate-second-retry/mutation-command.stderr.txt` |
| `runs/archive/run-20260415-mechanism-planning-gate-second-retry/repo-health.stderr.txt` |
| `runs/run-20260415-mechanism-planning-gate-second-clean/mutation-command.stderr.txt` |
| `runs/run-20260415-mechanism-planning-gate-second-clean/repo-health.stderr.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry/mutation-command.stderr.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry/mutation-command.stdout.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry/repo-health.stderr.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry2/mutation-command.stderr.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry2/mutation-command.stdout.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp/mutation-command.stderr.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp/mutation-command.stdout.txt` |
| `runs/run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp/repo-health.stderr.txt` |
| `runs/run-20260422-auto-improve-timeout-telemetry-fallback/mutation-command.stderr.txt` |
| `runs/run-20260422-auto-improve-timeout-telemetry-fallback/mutation-command.stdout.txt` |
| `runs/run-20260422-auto-improve-timeout-telemetry-fallback/repo-health.stderr.txt` |

---

## 5. 두 리뷰의 공통 합의 항목

이하는 두 리뷰가 방법론적으로 독립하여 동일한 결론에 도달한 사항들이다. 교차 합의가 이루어진 항목은 신뢰도가 높다.

### 5.1 현재 ZIP은 follow-up 리뷰 이후 후속 패키징 상태다

두 리뷰 모두 SHA 불일치의 원인이 단순한 표기 오류가 아니라, follow-up 리뷰 파일이 archive에 self-included된 후 재패키징이 이루어진 결과임을 독립적으로 판정했다.

### 5.2 `artifact-freshness-report.json`의 stable debt는 106/106/17이다

두 리뷰가 동일 파일을 직접 파싱하여 동일한 수치를 확인했다. 원본 follow-up 리뷰의 109/109/17은 이전 snapshot 기준값이며, 현재 ZIP에서는 envelope/currentness debt가 3건 감소했다.

### 5.3 `auto-improve-readiness.json`의 이중 구조: execution pass, learning uncertain

두 리뷰 모두 execution readiness(`can_run=true`)와 learning readiness(`learning_uncertain`)를 명확히 분리해야 한다고 판정했다. "큐가 열렸다"와 "반복 실행하면 실제로 개선될 것이다"는 전혀 다른 질문이다.

### 5.4 release-smoke 표면 강화, full E2E는 미확정

두 리뷰 모두 `tests/test_release_smoke.py`와 `ops/scripts/release_smoke.py`에 partial report 관련 코드/테스트 표면이 존재함을 확인했다. 그러나 두 리뷰 모두 full release-smoke E2E 완료를 직접적인 증거로 확보하지 않았음을 명시했다.

### 5.5 plain `pytest` 진입점 계약은 미확정이다

두 리뷰 모두 `pytest.ini`에 `pythonpath = .`가 없다는 사실을 확인했다. 다만 두 리뷰 모두 plain `pytest` 실패를 직접 재현한 것이 아니라 "공식 진입점 계약이 불명확하다"는 수준으로 표현했다. 리뷰 A는 이를 P1 정책 결정 필요로, 리뷰 B는 "신규 기여자 UX 리스크"로 표현했다.

---

## 6. 완료된 항목 상세 판정

### 6.1 POSIX C-locale ZIP 해제 문제

**리뷰 A 판정**: 타당, full C-locale unzip smoke는 별도 CI 고정 필요.
**리뷰 B 판정**: `LC_ALL=C LANG=C unzip -q` 직접 실행 성공으로 확인.

**통합 판정**: 현재 ZIP 기준으로 닫힘. 다만 CI 상시 고정 여부는 별도 확인 필요.

### 6.2 root 0-byte placeholder 제거

두 리뷰 모두 root 직접 파일 17개 중 0-byte 파일이 없음을 확인했다. 0-byte 파일 15건은 모두 `runs/` 하위 log placeholder이며, 이는 root placeholder와 성격이 다른 운영 기록 파일이다. `run_log_placeholder`로 분류하는 것이 두 리뷰의 공통 권장 사항이다.

### 6.3 stored `missing_generated_at` action drift

**이전 상태 (follow-up 리뷰 기준 snapshot)**: `missing_generated_at` 항목의 `recommended_next_action`이 `none`으로 잔존.
**현재 ZIP 상태**: `backfill_generated_at_or_mark_legacy_noncanonical`으로 갱신됨.

두 리뷰 모두 현재 ZIP 기준 해소 완료를 독립적으로 확인했다. 다만 개별 artifact record 레벨에서는 더 높은 우선순위의 `missing_artifact_envelope` action이 먼저 노출되므로, 실제 artifact record 차원의 action string은 `backfill_artifact_envelope`로 표시될 수 있다.

### 6.4 skipped run 1건

두 리뷰가 공통으로 확인한 `excluded_runs` 기록은 다음과 같다.

| 항목 | 값 |
|---|---|
| run_id | `run-20260422-auto-improve-decision-record-fallback` |
| status | `archived` |
| reason | `missing promotion inputs; superseded by later retry runs` |
| `runs_skipped` | 0 |
| `runs_excluded` | 1 |

이 run은 active skipped run이 아니라 정책적 excluded 분류 항목으로, 두 리뷰 모두 닫힌 항목으로 판정했다. 단, 리뷰 B가 보완한 바와 같이 "디렉터리 이동 완료"가 아니라 "mechanism review policy상 archived excluded로 분류 완료"라는 표현이 더 정확하다.

### 6.5 artifact contract bounded backfill 3개 slice

두 리뷰 모두 다음 3개 파일에 대한 backfill이 현재 ZIP에 실제 반영됨을 확인했다.

| 파일 | schema 검증 | 잔여 이슈 | recommended_next_action |
|---|---|---|---|
| `ops/reports/manual-mutate-defect-registry.json` | pass | 없음 | `none` |
| `ops/reports/cyclonedx-bom.json` | pass | `generated_at_older_than_file_mtime` | `regenerate_artifact_or_refresh_timestamp` |
| `ops/reports/openvex-draft.json` | pass | 없음 | `none` |

`cyclonedx-bom.json`은 완전한 no-issue 상태가 아니라 "contract debt 해소, timestamp drift 잔존" 상태임을 리뷰 B가 정확히 보완했다. CycloneDX 외부 표준 top-level shape를 유지하기 위해 embedded envelope(`metadata.properties[urn:openai:artifact-envelope]`) 방식을 채택하고 있으며, 이 embedded envelope policy는 별도 문서화가 권장된다.

### 6.6 release-smoke partial report 장치 강화

두 리뷰 모두 `ops/scripts/release_smoke.py`와 `ops/schemas/release-smoke-report.schema.json`에 partial report 관련 표면이 존재함을 확인했다. 리뷰 B는 추가로 `tests/test_release_smoke.py`에 총 13개의 테스트 메서드가 존재하며, 그 중 5개가 partial/smoke/failure 관련임을 확인했다. 리뷰 A는 `tests/test_generated_report_contracts.py`가 3개 backfill slice에 대한 regression assertion을 포함함을 확인했다.

---

## 7. 미완료 핵심 잔여 작업 상세

### 7.1 P0 — Artifact Contract Debt: 106/106/17

현재 `ops/reports/artifact-freshness-report.json`의 확정된 수치는 다음과 같다.

| 지표 | 현재 값 | 성격 | Acceptance 활용 가능 여부 |
|---|---:|---|---|
| `artifact_count` | 146 | 참조값 | 참조 전용 |
| `json_artifact_count` | 146 | 참조값 | 참조 전용 |
| `scanned_text_artifact_count` | 177 | 참조값 | 참조 전용 |
| `stale_artifact_count` | 60 | mtime-sensitive | stable acceptance에 부적합 |
| `mtime_sensitive_artifact_count` | 60 | mtime-sensitive | stable acceptance에 부적합 |
| **`missing_artifact_envelope_count`** | **106** | **stable contract debt** | **stable KPI** |
| **`unknown_currentness_artifact_count`** | **106** | **stable contract debt** | **stable KPI** |
| **`missing_schema_count`** | **17** | **stable contract debt** | **stable KPI** |
| `schema_invalid_artifact_count` | 0 | stable | 유지 확인 요소 |
| `safe_to_backfill_artifact_count` | 86 | mtime-sensitive operational queue | trend 참조만 허용 |

**중요 해석**: `stale_artifact_count`와 `safe_to_backfill_artifact_count`는 실행 시점 및 mtime에 민감하므로 stable release KPI로 삼으면 안 된다. stable acceptance는 `missing_artifact_envelope`, `unknown_currentness`, `missing_schema`, `schema_invalid` 네 개 축으로만 관리해야 한다. 두 리뷰가 이 점을 공통으로 강조했다.

`top_debt` 상세:

| issue | count | safe_to_backfill | mtime_sensitive | recommended_next_action |
|---|---:|---:|---:|---|
| `missing_artifact_envelope` | 106 | 77 | 29 | `backfill_artifact_envelope` |
| `unknown_currentness` | 106 | 77 | 29 | `backfill_currentness_metadata` |
| `generated_at_older_than_file_mtime` | 60 | 0 | 60 | `regenerate_artifact_or_refresh_timestamp` |
| `missing_generated_at` | 59 | 59 | 0 | `backfill_generated_at_or_mark_legacy_noncanonical` |
| `missing_schema` | 17 | 13 | 4 | `add_schema_or_exclude_noncanonical_json` |

### 7.2 P0 — Missing Schema 17건

두 리뷰가 동일한 목록을 확인했다.

| 파일 경로 | 분류 방향 |
|---|---|
| `ops/reports/eval-initial-2026-04-12.json` | historical/bootstrap, canonical 여부 결정 필요 |
| `ops/reports/lint-initial-2026-04-12.json` | historical/bootstrap, canonical 여부 결정 필요 |
| `ops/reports/manifest-2026-04-12.json` | historical/bootstrap, canonical 여부 결정 필요 |
| `ops/reports/review-archive-report.json` | canonical artifact 여부 결정 필요 |
| `runs/run-20260415-raw-markdown-normalization/raw-markdown-normalization-report.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/concept-continuity-integration-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-profiles-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-render-after-concept-integration-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-validate-after-concept-integration-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-reregistration-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-slug-manifest-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/raw-intake-promotion-validate-final-tree-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/raw-registry-preflight-final-tree-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/source-english-summary-slug-validate-final-tree-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/wiki-lint-final-tree-2026-04-22.json` | run artifact, family schema 검토 |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/wiki-stage2-final-tree-2026-04-22.json` | run artifact, family schema 검토 |

처리 방향은 두 갈래다. `ops/reports/` 계열 4건은 canonical artifact인지 historical bootstrap artifact인지를 먼저 결정해야 한다. `runs/run-20260422-raw-intake-*` 계열 13건은 같은 run family에 속하므로 shared family schema를 먼저 만들 수 있는지 검토해야 한다. 어느 경우든 "schema가 없는 이유"를 artifact record에 기계 판독 가능한 형태로 남기는 것이 수치 감소보다 더 중요하다.

### 7.3 P0 — Learning/Session/Loop-Health Evidence 부족

두 리뷰가 공통으로 확인한 `auto-improve-readiness.json`의 핵심 상태:

| 항목 | 현재 값 | 목표 | 달성 여부 |
|---|---|---|---|
| `execution_readiness.status` | `pass` | `pass` | 달성 |
| `execution_readiness.can_run` | `true` | `true` | 달성 |
| `runnable_proposal_count` | 1 | 1 이상 | 달성 |
| `learning_readiness.status` | `learning_uncertain` | `learning_confirmed` 또는 동등 | **미달성** |
| `learning_readiness.likely_to_learn` | `false` | `true` 또는 review-cleared | **미달성** |
| `attempts_considered` | 7 | 10 이상 | **미달성** |
| `session_reports_considered` | 0 | 1 이상 | **미달성** |
| `session_calibration.status` | `no_session_context` | `no_session_context` 탈출 | **미달성** |
| `loop_health_summary.status` | `missing` | `missing` 아님 | **미달성** |
| `rework_count` | 5 | threshold 아래 | 미달성 |
| `hold_moving_average` | 0.2857 | 0.25 미만 또는 명시적 예외 | 미달성 |
| `defect_escape_pair_count` | 3 | 1 미만 또는 명시적 예외 | 미달성 |

execution queue가 열려 있다는 사실과 반복 실행 시 실제로 개선될 것이라는 신뢰 사이에는 현재 상당한 간격이 있다. 권장 상태 표현:

```text
execution_status          = pass
learning_status           = learning_uncertain
overall_status            = execution_pass_learning_review_required
release_confidence        = not_release_ready
```

### 7.4 P1 — Proposal Lifecycle Ledger 미연결

현재 runnable proposal 1건의 상태:

| 항목 | 값 |
|---|---|
| proposal_id | `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime` |
| source_candidate_id | `mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime` |
| family | `contract_regression_signals` |
| priority | 70 |
| primary_targets | `ops/scripts/auto_improve_iteration_persistence_runtime.py` |
| supporting_targets | `ops/schemas/run-telemetry.schema.json` |
| required_artifacts | `promotion-report.json`, `baseline-mechanism-assessment.json`, `candidate-mechanism-assessment.json` |

필요한 lifecycle 연결 체인:

```
source_candidate_id
  └─→ proposal_id
        └─→ operator decision
              └─→ run_id
                    ├─→ baseline assessment
                    ├─→ candidate assessment
                    └─→ promotion / hold / discard outcome
                              └─→ follow-up defect or learning signal
                                        └─→ readiness next step
```

이 체인이 닫히지 않으면 `runnable_proposal_count=1`은 queue 상태만을 보여줄 뿐, improvement loop의 품질을 증명하지 못한다.

### 7.5 P1 — Release-Smoke Full E2E 미확정

두 리뷰 모두 partial report 레이어는 강해졌으나 full 완료 레이어는 미확정이라고 판정했다.

| 레이어 | 현재 상태 |
|---|---|
| partial report builder 코드 | 확인됨 |
| partial report schema 정의 | 확인됨 |
| timeout/interruption command 표현 | 테스트 존재 |
| archive phase failure partial report | 테스트 존재 |
| full vault archive build | **미확정** |
| extracted vault manifest rebuild | **미확정** |
| extracted vault lint/eval/stage2/planning full pass | **미확정** |
| full profile 완료 report 생성 | **미확정** |

권장 profile 분리 설계:

| profile | 목적 | CI 기본 여부 |
|---|---|---|
| `fast` | tiny fixture vault로 build/extract/manifest/basic smoke 검증 | 예 |
| `full` | 실제 vault 전체 release path 검증 | nightly 또는 release gate |
| `interruption-unit` | timeout/failure 시 partial report schema-valid 보장 | 예 |

### 7.6 P1 — Plain `pytest` 진입점 계약 미확정

두 리뷰가 공통으로 확인한 `pytest.ini` 상태:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q --capture=sys
markers = ...
```

`pythonpath = .`는 없다. README는 공식 경로를 `make test*`, `make check*`, `.venv/bin/python -m pytest` 계열로 안내한다. 두 리뷰가 제시한 선택지는 동일하다.

| 선택지 | 권장도 | 이유 |
|---|---:|---|
| `python -m pytest` / `make test`를 유일 공식 경로로 명시 | 높음 | packaging/import path drift 방지 |
| `pytest.ini`에 `pythonpath = .` 추가 | 중간 | 신규 기여자 UX 개선, 단 import contract 느슨해질 가능성 |

실무적으로는 README와 Makefile이 이미 `python -m pytest` 계열을 강하게 밀고 있으므로, plain `pytest`를 지원하지 않는다면 이를 정책 문서에 명시하는 편이 안전하다.

### 7.7 P2 — Empty Directory 및 Run Log Placeholder Policy

| 항목 | 현재 상태 | 권장 처리 |
|---|---|---|
| `runs/` 하위 0-byte stdout/stderr placeholder 15건 | 존재 | `run_log_placeholder`로 policy 분류 |
| `.github/prompts` 빈 디렉터리 | 존재 | 의도된 scaffold면 allowlist에 명시 |
| `review/` 빈 디렉터리 | 존재 | release ZIP에서 제외 검토 |
| `tmp/` 빈 디렉터리 | 존재 | release ZIP에서 제외 권장 |

---

## 8. 두 리뷰 간 관점 차이 및 보완점

두 리뷰는 핵심 판단에서 높은 일치를 보이지만, 각자가 독자적으로 발견하거나 더 상세히 다룬 영역이 있다. 이를 정리하면 다음과 같다.

### 8.1 리뷰 B의 고유 발견 및 보완 사항

**② `zipfile.testzip()` 및 C-locale 해제 직접 수행**: 리뷰 A가 장시간 종료되지 않아 결론적 증거로 사용하지 못한 전체 CRC 검증을 리뷰 B는 Python API를 통해 별도로 수행하여 `None` 결과를 확보했다. 이는 두 리뷰가 검증 도구를 보완적으로 사용한 사례다.

**③ `tests/test_release_smoke.py` 테스트 메서드 수 확정**: 리뷰 B는 총 13개의 테스트 메서드 존재와 partial/smoke 관련 5개 메서드 목록을 명시했다. 리뷰 A는 테스트 범주를 설명했으나 메서드 수를 명시하지 않았다.

**④ CycloneDX embedded envelope policy 구분**: 리뷰 B는 `cyclonedx-bom.json`이 "contract debt 해소, timestamp drift 잔존"이라는 두 상태를 명확히 구분했다. 리뷰 A는 동일 파일에 대해 "mtime-sensitive timestamp drift만 남아 있다"고 표현하여 사실상 동일한 판단을 내렸으나, 이를 외부 표준 shape 준수 맥락과 연결한 설명은 리뷰 B에서 더 명시적이었다.

**⑤ `review/`, `tmp/` 빈 최상위 디렉터리 존재 명시**: 리뷰 B는 이 두 디렉터리가 파일 수 표에 0으로 나타나지만 ZIP 최상위 명시적 디렉터리로 존재함을 명시했다. 이후 보고서에서 "root 직접 파일 + 숨은 디렉터리 구조"를 구분해 표시해야 한다는 권고도 포함됐다.

### 8.2 리뷰 A의 고유 발견 및 보완 사항

**① Makefile interpreter flag 처리 확인**: 리뷰 A는 `Makefile`의 `PUBLIC_PYTHON` 계산에 `$(firstword $(PYTHON))` 사용을 직접 확인했다. 이는 multi-word interpreter flag 처리 개선과 관련된 세부 사항으로, 리뷰 B에서는 다루지 않았다.

**② ZIP 내부 기존 리뷰 3건의 SHA 세대 체계 확립**: 리뷰 A는 `external-reports/` 내 기존 리뷰 파일 3건의 SHA와 각 리뷰가 기준으로 삼은 ZIP SHA를 교차 확인하여 세대 체계를 명확히 구조화했다.

**③ `tests/test_generated_report_contracts.py` 내용 직접 확인**: 리뷰 A는 이 파일이 5개 테스트 의도(missing_generated_at action currentness, CycloneDX debt free, manual mutate registry currentness, OpenVEX currentness, reconciliation observation)로 구성됨을 명시했다.

**④ proposal lifecycle 연결 체인의 7단계 상세화**: 리뷰 A는 proposal lifecycle의 필요 연결 체인을 source candidate → proposal → operator decision → run id → baseline/candidate assessment → outcome → follow-up signal → readiness next step의 7단계로 상세히 구조화했다.

### 8.3 두 리뷰가 표현을 달리한 항목

| 항목 | 리뷰 A 표현 | 리뷰 B 표현 | 통합 채택 표현 |
|---|---|---|---|
| plain pytest 실패 가능성 | P1 정책 결정 필요, 두 선택지 제시 | 신규 기여자 UX 리스크, 실패 확정 아님 | "공식 진입점 계약 미확정 및 신규 기여자 UX 리스크" |
| `cyclonedx-bom.json` 상태 | mtime-sensitive timestamp drift만 남음 | contract debt 해소, timestamp drift 잔존 | "contract debt 해소, timestamp drift 잔존 (mtime-sensitive)" |
| `review/`, `tmp/` 빈 디렉터리 | P2 hygiene 이슈 | 정책 명시 필요 문서화 항목 | P2 archive hygiene + 정책 문서화 필요 |

---

## 9. 원본 리뷰 보정 필요 문장 목록

두 리뷰가 공통으로 식별하거나 리뷰 B가 추가로 식별한, 검토 대상 follow-up 리뷰(`llm_wiki_vnext_integrated_reconciliation_followup_report_20260427.md`)의 보정 필요 항목이다.

### 9.1 ZIP SHA-256 및 구조 수치

| 항목 | 보정 전 | 보정 후 |
|---|---|---|
| ZIP SHA-256 | `daca2ea1f9f22645103e4b4b69f74271c27f3906a4e39648f6c00d2476319064` | `982007cc09a430708216306b454875f4f810822f5d9ae61ad012645cdd5d37d4` |
| ZIP 크기 | `191,242,525 bytes` | `191,262,121 bytes` |
| entry 수 | `1,636` | `1,638` |
| 파일 수 | `1,562` | `1,564` |
| `external-reports` 파일 수 | `33` | `34` |
| `tests` 파일 수 | `121` | `122` |

### 9.2 stored `missing_generated_at` action drift

- **보정 전**: 현재 ZIP에 저장된 `artifact-freshness-report.json`에는 `missing_generated_at` action이 아직 `none`으로 남아 있다.
- **보정 후**: 이전 snapshot에서는 해당 action drift가 있었으나, 현재 업로드 ZIP의 저장본에서는 `top_debt` action이 `backfill_generated_at_or_mark_legacy_noncanonical`으로 보정됐다. 다만 개별 artifact record 레벨에서는 더 높은 우선순위의 `backfill_artifact_envelope` action이 먼저 표시될 수 있다.

### 9.3 skipped run 1건

- **보정 전**: `run-20260422-auto-improve-decision-record-fallback`이 skipped run으로 남아 있고 operator decision이 필요하다.
- **보정 후**: 해당 run은 `archived` / `superseded by later retry runs`로 excluded 분류됐다. `runs_skipped=0`, `runs_excluded=1`. "디렉터리 이동 완료"가 아니라 "mechanism review policy상 archived excluded로 분류 완료"가 정확하다.

### 9.4 artifact debt 수치

- **보정 전**: artifact contract debt `109/109/17`
- **보정 후**: 현재 ZIP 기준 stable debt는 `106/106/17`. envelope/currentness debt가 3건 감소했고 missing schema는 17건 그대로다.

### 9.5 safe-to-backfill 수치

- **보정 전**: `safe_to_backfill_artifact_count=87` (또는 runtime 재생성 시 64, 61 등)
- **보정 후**: 현재 ZIP 저장본 기준 `safe_to_backfill_artifact_count=86`. 이 값은 mtime-sensitive operational queue 지표이므로 stable acceptance 기준에서 제외하고 trend 참조값으로만 활용해야 한다.

### 9.6 bounded backfill slice 수

- **보정 전**: "두 개의 safe-to-backfill artifact contract slice"로 보일 수 있는 표현
- **보정 후**: 현재 ZIP 기준 확인 가능한 backfill slice는 `manual-mutate-defect-registry`, `cyclonedx-bom`, `openvex-draft`의 세 개다.

### 9.7 release-smoke 판정

- **보정 전**: partial report 장치가 반영됐다.
- **보정 후**: partial report 장치 반영에 더해, timeout/failure partial report에 대한 tests도 존재한다 (총 13개 테스트 메서드, partial/smoke 관련 5개). 다만 full E2E pass 증거는 여전히 없다.

---

## 10. 통합 Acceptance Criteria 판정표

두 리뷰의 AC 목록을 교차 대조하여 중복을 제거하고 통합한 판정표다. 항목별 출처와 현재 판정을 병기한다.

| ID | 기준 | 현재 판정 | 출처 |
|---:|---|---|---|
| AC-01 | Python CRC 검증 통과 (`zipfile.testzip() == None`) | **충족** | 리뷰 B 직접 수행 |
| AC-02 | Python `extractall()` 성공 | **충족** | 리뷰 B 직접 수행 |
| AC-03 | C-locale Info-ZIP 추출 성공 | **충족** | 리뷰 B 직접 수행 |
| AC-04 | root 0-byte placeholder 파일 없음 | **충족** | 리뷰 A/B 공통 |
| AC-05 | 긴 한글 파일명 offender 제거 및 slug/frontmatter 보존 | **충족** | 리뷰 B |
| AC-06 | self-improve candidates/proposals 존재 | **충족** | 리뷰 A/B 공통 |
| AC-07 | execution readiness `can_run=true` | **충족** | 리뷰 A/B 공통 |
| AC-08 | skipped run이 0이거나 classified excluded로 분류됨 | **충족** | 리뷰 A/B 공통 |
| AC-09 | stored artifact freshness `missing_generated_at` action drift 해소 | **충족** | 리뷰 A/B 공통 |
| AC-10 | `schema_invalid_artifact_count = 0` | **충족** | 리뷰 A/B 공통 |
| AC-11 | missing schema 17건 schema 추가 또는 legacy 분류 완료 | **미충족** | 리뷰 A/B 공통 |
| AC-12 | artifact envelope/currentness debt 유의미 감소 지속 | **부분 충족** — 109→106 확인, 여전히 106 | 리뷰 A/B 공통 |
| AC-13 | `attempts_considered >= 10` | **미충족** — 현재 7 | 리뷰 A/B 공통 |
| AC-14 | `session_reports_considered >= 1` | **미충족** — 현재 0 | 리뷰 A/B 공통 |
| AC-15 | `loop_health_summary.status != missing` | **미충족** — 현재 missing | 리뷰 A/B 공통 |
| AC-16 | release-smoke partial report 장치 존재 및 테스트 통과 | **충족에 가까운 부분 충족** — 코드/schema/tests 표면 확인, full E2E는 별도 | 리뷰 A/B 공통 |
| AC-17 | release-smoke full E2E 완료 report 생성 | **미확인** | 리뷰 A/B 공통 |
| AC-18 | proposal lifecycle ledger 연결 (proposal→decision→outcome) | **미충족** | 리뷰 A/B 공통 |
| AC-19 | plain pytest 또는 공식 pytest 진입점 계약 안정화 | **미충족/미확정** — `pytest.ini`에 `pythonpath=.` 없음 | 리뷰 A/B 공통 |
| AC-20 | run log placeholder(`runs/` 0-byte) policy 분류 | **미충족** — policy 명시 없음 | 리뷰 A (P2) |
| AC-21 | empty dir allowlist 또는 exclusion policy 존재 | **미충족** | 리뷰 A (P2) |
| AC-22 | POSIX C-locale unzip CI 상시 고정 | **미충족** — 직접 실행 성공, CI gate 여부 미확인 | 리뷰 A 보완 |

---

## 11. 권장 실행 순서 (통합 Backlog)

두 리뷰의 개선 권고를 통합하여 실행 순서로 재배열했다. 각 PR의 완료 기준은 두 리뷰 중 더 구체적인 기준을 채택했다.

---

### PR-1. Artifact Contract Backfill 다음 Cluster (P0)

**목표**: `missing_artifact_envelope_count`와 `unknown_currentness_artifact_count`를 106에서 유의미하게 감소시킨다.

**실행 방식**:
1. artifact records를 family별로 묶는다 (`ops_reports`, `runs` 분리).
2. canonical report는 envelope/currentness/schema를 부여한다.
3. historical/run artifact는 `legacy_noncanonical` 또는 `archived_run_artifact`로 분류한다.
4. CycloneDX처럼 외부 표준 top-level shape가 있는 형식은 embedded envelope policy를 문서화한다.
5. `tests/test_generated_report_contracts.py`에 family별 regression assertion을 추가한다.

**완료 기준**:
- `missing_artifact_envelope_count < 100`
- `unknown_currentness_artifact_count < 100`
- `schema_invalid_artifact_count = 0` 유지
- mtime-sensitive drift와 stable contract debt를 별도 acceptance 기준으로 분리 기록

---

### PR-2. Missing Schema 17건 정책 결정 (P0/P1)

**목표**: 17건 각각에 대해 "schema 추가" 또는 "legacy/noncanonical 분류" 중 하나를 명시적으로 선택한다.

**실행 방식**:
1. `ops/reports/*-initial-2026-04-12.json` 4건: historical/bootstrap artifact인지 canonical artifact인지 결정한다.
2. `runs/run-20260422-raw-intake-*` 13건: 같은 family에 대한 shared schema 생성 가능 여부를 먼저 검토한다.
3. canonical이면 `$schema` + schema file을 추가한다.
4. historical이면 freshness report에서 `legacy_noncanonical` 또는 `excluded_history`로 분류한다.

**완료 기준**:
- `missing_schema_count` 감소, 또는 17건 각각의 classification reason이 machine-readable하게 artifact record에 존재
- schema invalid 0 유지

---

### PR-3. Learning/Session/Loop-Health Evidence 보강 (P0)

**목표**: execution readiness와 learning confidence를 분리된 두 축으로 관리하며, learning 증거를 실질적으로 구축한다.

**완료 기준**:
- `attempts_considered >= 10`
- `session_reports_considered >= 1`
- `session_calibration.status != no_session_context`
- `loop_health_summary.status != missing`
- `learning_readiness.status`가 `learning_uncertain`보다 구체적인 통과/차단 상태로 이동

**권장 구현**:
- session rollup artifact 생성 또는 현재 run artifacts와 outcome metrics 연결
- loop-health aggregate report 생성
- run ledger와 proposal lifecycle 연결
- readiness summary를 `execution_status`, `learning_status`, `overall_status`, `release_confidence`로 명확히 분리

---

### PR-4. Proposal Lifecycle Ledger 연결 (P1)

**목표**: 현재 runnable proposal 1건을 source candidate부터 outcome까지 단일 체인으로 추적 가능하게 만든다.

**완료 기준**:
- `proposal_id` → `source_candidate_id` → `run_id` → `promotion/hold/discard` → `followup_signal` 전체 체인 연결
- archived/excluded run이 lifecycle에서 orphan이 되지 않음
- readiness report가 단순 queue existence가 아니라 outcome feedback을 반영

---

### PR-5. Release-Smoke Profile 분리와 Full E2E Evidence 확보 (P0/P1)

**목표**: partial report unit coverage와 full E2E release gate를 명확히 분리하고 각각을 독립적으로 검증한다.

**완료 기준**:
- tiny fixture 기반 `fast` smoke profile이 CI에서 deterministic하게 완료
- full vault `full` profile은 장시간 gate로 분리 운용
- archive phase 실패, command timeout, keyboard interruption류 partial report가 schema-valid로 저장되는지 자동 확인
- full 완료 report와 partial report의 status semantics가 명확히 구분됨

---

### PR-6. Pytest 진입점 계약 정리 (P1)

**목표**: 신규 기여자와 CI가 동일한 test invocation contract를 사용하도록 정렬한다.

**선호안**: 공식 경로는 `make test`, `make check`, `.venv/bin/python -m pytest`로 고정하고, README에 plain `pytest`가 지원 진입점이 아님을 명시한다.

**완료 기준**:
- README, Makefile, CI, `pytest.ini`가 같은 계약을 가리킴
- plain `pytest` 미지원이 의도된 정책인지, 실제 결함인지 모호하지 않음
- `pythonpath=.`를 추가하는 방향을 선택한 경우, bounded collect smoke로 import 안정성을 검증

---

### PR-7. Release Archive Hygiene P2 정리 (P2)

**목표**: 빈 디렉터리, run log placeholder, POSIX CI gate가 hygiene warning으로 오탐되지 않게 한다.

**완료 기준**:
- `run_log_placeholder` classification policy 문서화
- empty dir allowlist 또는 exclusion policy 존재
- `review/`, `tmp/`가 release ZIP에 포함될 필요가 없다면 제외
- C-locale unzip을 CI에 상시 포함 또는 policy 명시

---

## 12. 현재 체크포인트 상태 라벨

두 리뷰가 공통으로 도출하고 이 통합 보고서가 확정하는 현재 체크포인트의 상태 라벨:

```text
execution_status             = pass
artifact_contract_status     = partial_backfill_in_progress (106/106/17 잔존)
learning_status              = learning_uncertain
release_smoke_status         = partial_coverage_present_full_e2e_unproven
proposal_lifecycle_status    = queue_open_outcome_trace_missing
report_fingerprint_status    = snapshot_drift_present
release_confidence           = not_release_ready
recommended_phase            = stabilization_and_contract_completion
```

---

## 13. 한 줄 요약

**두 리뷰 모두 현재 ZIP이 stored report drift와 skipped run을 실질적으로 닫은 후속 스냅샷임을 독립 확인했다. 보정된 stable debt는 `106/106/17`이며, 다음 개선 초점은 (1) artifact contract debt 축소, (2) learning/session/loop-health evidence 생성, (3) proposal lifecycle 체인 완결, (4) release-smoke full gate 확립, (5) report self-inclusion 이후 ZIP fingerprint 재기록 워크플로 도입이다.**

---

*본 보고서는 `llm_wiki_vnext_v47_reconciliation_improvement_report_20260427.md`와 `llm_wiki_vnext_followup_review_verification_improvement_report_20260427.md` 두 리뷰를 누락 없이 전문 교차 대조하여 작성되었으며, 어느 한 리뷰에도 우열을 두지 않고 독립적 관찰을 동등하게 취급하여 합성했다.*
