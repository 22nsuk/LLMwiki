# LLM Wiki vNext Integrated Reconciliation Follow-up Report

- 작성일: 2026-04-27
- 작성 언어: 한국어
- 출력 파일명: `llm_wiki_vnext_integrated_reconciliation_followup_report_20260427.md`
- 신규 검토 대상 리뷰: `llm_wiki_vnext_integrated_reconciliation_report_20260427.md`
- 대조한 기존 리뷰/보고서:
  - `llm_wiki_vnext_review_improvement_report_20260427.md`
  - `llm_wiki_vnext_post_review_audit_report_20260427.md`
- 실제 대조 대상 ZIP: `LLM Wiki vNext.zip`
- 실제 ZIP SHA-256: `daca2ea1f9f22645103e4b4b69f74271c27f3906a4e39648f6c00d2476319064`

---

## 1. 목적

이 문서는 새로 제공된 `LLM Wiki vNext — 통합 재검증 보고서`를 기존 리뷰 및 실제 ZIP 파일과 다시 대조한 후속 개선 보고서다.

검토 목표는 네 가지다.

1. 새 통합 리뷰의 주요 결론이 실제 파일 기준으로 맞는지 확인한다.
2. 기존 리뷰에서 남아 있던 작업분 중 실제로 완료된 항목과 여전히 남은 항목을 분리한다.
3. 새 통합 리뷰의 표현 중 실제 파일 기준으로 보정해야 할 부분을 명확히 기록한다.
4. 다음 작업 순서를 실행 가능한 개선 항목으로 재정렬한다.

이번 대조의 기본 원칙은 다음과 같다.

- 문서 간 합의보다 실제 ZIP과 실제 저장 artifact를 우선한다.
- runtime 재생성 결과와 ZIP 안에 저장된 canonical report를 분리해서 본다.
- `can_run=true`와 `release-ready`를 동일시하지 않는다.
- 이미 닫힌 문제를 다시 P0로 남기지 않고, 실제 미해결 작업에 집중한다.

---

## 2. 직접 확인한 입력 파일과 범위

현재 작업 디렉터리에서 확인한 입력 파일은 다음과 같다.

| 구분 | 파일 |
|---|---|
| 신규 리뷰 | `llm_wiki_vnext_integrated_reconciliation_report_20260427.md` |
| 기존 리뷰 1 | `llm_wiki_vnext_review_improvement_report_20260427.md` |
| 기존 리뷰 2 | `llm_wiki_vnext_post_review_audit_report_20260427.md` |
| 실제 ZIP | `LLM Wiki vNext.zip` |
| 작업 계약 아카이브 | `Codex-Subagent-Orchestrator.zip` |

직접 수행한 검증은 다음과 같다.

| 검증 | 결과 |
|---|---|
| 작업 계약 아카이브 추출 및 `AGENTS.md`/workflow 파일 확인 | 완료 |
| 실제 ZIP SHA-256 계산 | 완료 |
| Python `zipfile.testzip()` | `None`, CRC 오류 없음 |
| Python `extractall()` | 성공 |
| `LC_ALL=C LANG=C unzip -q` | 성공 |
| ZIP entry/file/dir/size/top-level 분포 계산 | 완료 |
| root 파일 목록 및 0-byte 파일 목록 확인 | 완료 |
| stored self-improve / artifact freshness report 확인 | 완료 |
| portability helper, release-smoke schema/code 표면 확인 | 완료 |
| 신규 리뷰와 기존 리뷰 문장 대조 | 완료 |

장시간 의존성 설치, Ruff, Mypy, public export, release-smoke full E2E 전체 재실행은 이번 후속 재생성 과정에서 반복하지 않았다. 해당 항목은 신규 통합 리뷰 및 기존 리뷰의 실행 기록과 실제 파일 표면을 대조해 판정했다.

---

## 3. 체크포인트 동일성 판정

신규 통합 리뷰는 세 개 리뷰가 모두 동일한 현재 체크포인트를 검증했다고 주장한다. 실제 업로드 ZIP의 SHA-256은 다음과 같다.

| 항목 | 값 |
|---|---|
| 실제 ZIP | `LLM Wiki vNext.zip` |
| SHA-256 | `daca2ea1f9f22645103e4b4b69f74271c27f3906a4e39648f6c00d2476319064` |
| ZIP 크기 | 191,242,525 bytes |

이는 신규 통합 리뷰가 말한 현재 체크포인트 SHA와 일치한다. 따라서 신규 통합 리뷰의 큰 전제, 즉 v45/v46/post-review audit이 같은 실체를 다른 이름으로 본 것이라는 판단은 실제 파일 기준으로 타당하다.

또한 기존 기준선으로 쓰인 v44 계열 SHA `86596f5054ee1b286886c86626e656e002066389e68eb15563152e9c84d5ea30`과 현재 SHA `daca2ea1...9064`는 다르다. 기존 리뷰의 지적을 현재 ZIP에 그대로 적용하면 일부는 과거 이슈를 중복 지적하게 된다.

---

## 4. 실제 ZIP 구조 재검증 결과

### 4.1 기본 구조

| 항목 | 실제 확인값 |
|---|---:|
| ZIP entry 수 | 1,636 |
| 파일 수 | 1,562 |
| 디렉터리 수 | 74 |
| 압축 해제 전체 바이트 합 | 240,648,910 bytes |
| Python `zipfile.testzip()` | `None` |
| Python `extractall()` | 성공 |
| C-locale Info-ZIP 추출 | 성공 |
| non-ASCII entry 수 | 334 |
| 최대 UTF-8 component 길이 | 167 bytes |

신규 통합 리뷰의 ZIP 기본 수치와 거의 일치한다.

### 4.2 최상위 경로별 파일 수

실제 계산값은 다음과 같다.

| 상위 경로 | 파일 수 |
|---|---:|
| `raw` | 446 |
| `wiki` | 417 |
| `ops` | 278 |
| `runs` | 156 |
| `tests` | 121 |
| `system` | 71 |
| `external-reports` | 33 |
| root 직접 파일 | 17 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |
| `.vscode` | 1 |

여기서 신규 통합 리뷰의 표는 `기타 root 파일 18`로 표시되어 있다. 실제 파일 기준으로는 root 직접 파일이 17개이고 `.vscode` 아래 파일이 1개다. 따라서 총량 18이라는 감각은 맞지만, 분류 표현은 아래처럼 보정하는 편이 정확하다.

- 보정 전: `기타 root 파일 18`
- 보정 후: `root 직접 파일 17 + .vscode 1`

### 4.3 확장자 분포

| 확장자 | 실제 확인값 |
|---|---:|
| `.md` | 940 |
| `.py` | 277 |
| `.json` | 215 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.yaml` | 13 |
| `.toml` | 10 |
| `.jsonl` | 6 |
| 확장자 없음 | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

이 값은 신규 통합 리뷰와 일치한다.

### 4.4 root 직접 파일 목록

실제 root 직접 파일 17개는 다음과 같다.

| 파일 |
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

v44에서 지적되었던 root 0-byte placeholder 2개는 현재 ZIP에 없다.

---

## 5. 신규 통합 리뷰의 핵심 결론 평가

신규 통합 리뷰의 큰 결론은 실제 파일 기준으로 대체로 타당하다.

| 신규 리뷰 주장 | 실제 파일 기준 판정 |
|---|---|
| 현재 ZIP은 v44 이후 후속 체크포인트다 | 타당 |
| POSIX C-locale unzip 문제는 해소됐다 | 타당 |
| root 0-byte placeholder는 제거됐다 | 타당 |
| self-improve execution queue는 열려 있다 | 타당 |
| schema invalid artifact는 0건이다 | 저장 report 기준 타당 |
| artifact contract debt는 여전히 크다 | 타당 |
| learning/session/loop-health evidence는 부족하다 | 타당 |
| release-smoke partial report 장치는 반영됐다 | 코드/schema 표면 기준 타당 |
| full release-smoke E2E는 아직 확정되지 않았다 | 타당 |
| plain `pytest` 호출 계약은 추가 개선 대상이다 | `pytest.ini` 기준 타당 |

즉 새 통합 리뷰는 방향성과 우선순위에서 신뢰할 수 있다. 다만 몇몇 항목은 `완료`라는 표현을 조금 더 세분화해야 실제 파일과 완전히 맞는다.

---

## 6. 기존 리뷰 대비 실제 완료 또는 크게 진전된 작업

### 6.1 POSIX ZIP portability 결함 해소

기존 v44 리뷰의 가장 명확한 P0 중 하나였던 C-locale unzip 실패는 현재 ZIP에서 재현되지 않는다.

| 항목 | v44 기준 | 현재 ZIP |
|---|---|---|
| `LC_ALL=C LANG=C unzip -q` | 실패 | 성공 |
| 긴 한글 파일명 offender | 2건 | 0건 |
| slug 변환 파일 | 없음 | 2건 존재 |
| 원제목 보존 | 미완료 | frontmatter에 보존 |

현재 존재하는 slug 파일은 다음과 같다.

| slug 파일 |
|---|
| `raw/web-snapshots/khan-trump-pakistan-talks-strike-escalation-ccd8eb399a.md` |
| `raw/web-snapshots/khan-translator-labor-clickwork-ai-773e5f1cf9.md` |

두 파일 모두 원제목을 frontmatter `title`에 보존하고 있다. 또한 `ops/scripts/path_portability_runtime.py`에는 `infozip_c_locale_escape_byte_len` helper가 존재한다.

### 6.2 root 0-byte placeholder 제거

기존에 root에 있던 다음 두 파일은 현재 ZIP에 없다.

| 제거된 과거 placeholder |
|---|
| `source--global-markets-misc-intake-w-230-2026-04-21.md` |
| `source--global-markets-misc-intake-w-249-2026-04-21.md` |

현재 0-byte 파일 15개는 모두 `runs/` 하위 stdout/stderr placeholder다. 이는 root placeholder와 성격이 다르므로 별도 policy 대상으로 다루는 것이 맞다.

### 6.3 self-improve execution queue 유지

현재 저장된 report 기준 핵심 상태는 다음과 같다.

| report | 핵심 값 |
|---|---|
| `ops/reports/mechanism-review-candidates.json` | `runs_discovered=7`, `runs_considered=6`, `runs_skipped=1`, `candidates_emitted=1` |
| `ops/reports/mutation-proposals.json` | `source_candidates_read=1`, `proposals_emitted=1`, `blocked_proposals=0` |
| `ops/reports/auto-improve-readiness.json` | `execution_readiness.can_run=true`, `runnable_proposal_count=1` |

이는 기존 v42/v44 계열의 `0 candidates -> 0 proposals -> can_run=false` 병목이 현재 상태에서는 재발하지 않았다는 강한 근거다.

### 6.4 release-smoke partial report 표면 반영

`ops/scripts/release_smoke.py`와 `ops/schemas/release-smoke-report.schema.json`에는 다음 계열 필드와 로직이 존재한다.

| 확인 항목 | 실제 파일 기준 |
|---|---|
| partial report 관련 코드 | 존재 |
| `is_partial` schema 필드 | 존재 |
| `partial_report` schema 필드 | 존재 |
| `completed_command_count` 계열 | 존재 |
| POSIX escape budget 관련 필드 | 존재 |
| Info-ZIP C-locale escape bytes 관련 필드 | 존재 |

따라서 partial report 보장 장치가 코드 표면에 반영됐다는 신규 리뷰 판단은 타당하다. 다만 full E2E 완주가 확인됐다는 뜻은 아니다.

### 6.5 Makefile interpreter flag 개선 표면 반영

`Makefile`에는 `firstword` 기반 처리 흔적이 존재한다. 신규 통합 리뷰가 말한 multi-word interpreter flag 처리 개선은 실제 파일 표면과 맞다.

### 6.6 public export count parity 개선

신규 통합 리뷰는 public export에서 forbidden leak 0, count parity 개선을 보고한다. 이번 후속 검토에서는 public export 명령을 반복 실행하지 않았지만, 기존 리뷰와 신규 통합 리뷰의 결론은 서로 일치한다. 실제 ZIP 구조상 `raw`, `runs`, `system`, `external-reports`가 public export 산출물에 포함됐다는 반대 증거는 확인되지 않았다.

---

## 7. 보정이 필요한 부분

### 7.1 root 파일 수 표기

신규 통합 리뷰의 최상위 분포 표에서 `기타 root 파일 18`은 실제 분류 기준으로는 부정확하다.

정확한 표현은 다음과 같다.

| 항목 | 값 |
|---|---:|
| root 직접 파일 | 17 |
| `.vscode` 파일 | 1 |
| root 직접 파일 + `.vscode` | 18 |

이는 큰 결론에는 영향을 주지 않지만, 파일 구조 보고서의 정확도를 위해 보정해야 한다.

### 7.2 `missing_generated_at` action string의 완료 표현

신규 통합 리뷰는 `missing_generated_at`의 action string 정규화를 완료 항목으로 둔다. 그러나 실제 ZIP 안의 저장본 `ops/reports/artifact-freshness-report.json`을 보면 `missing_generated_at`의 `recommended_next_action`은 아직 `none`이다.

저장본 기준 top debt는 다음과 같다.

| issue | count | stored recommended_next_action |
|---|---:|---|
| `missing_artifact_envelope` | 109 | `backfill_artifact_envelope` |
| `unknown_currentness` | 109 | `backfill_currentness_metadata` |
| `missing_generated_at` | 61 | `none` |
| `generated_at_older_than_file_mtime` | 59 | `regenerate_artifact_or_refresh_timestamp` |
| `missing_schema` | 17 | `add_schema_or_exclude_noncanonical_json` |

따라서 이 항목은 다음처럼 표현해야 정확하다.

- runtime 재생성 경로에서는 action string 정규화가 반영됐을 가능성이 높다.
- 하지만 현재 ZIP에 저장된 canonical artifact에는 아직 과거 action string이 남아 있다.
- 그러므로 `완료`가 아니라 `runtime path 개선 완료, stored report 갱신 미완료`로 분류하는 것이 정확하다.

이 보정은 중요하다. report 자체가 작업 큐 역할을 한다면 저장된 canonical report가 여전히 `none`을 제시하는 것은 운영자에게 잘못된 신호를 줄 수 있다.

추가 구현 업데이트(working tree 기준): 이후 후속 구현에서 현재 저장소의 `ops/reports/artifact-freshness-report.json`을 재생성했고, 저장본 `missing_generated_at` action도 `backfill_generated_at_or_mark_legacy_noncanonical`으로 갱신했다. 따라서 이 섹션의 판정은 **이 문서가 검토한 ZIP snapshot 기준으로는 타당했지만, 현재 working tree 기준으로는 해소됨**으로 읽는 것이 맞다.

### 7.3 release-smoke 판정 범위

신규 통합 리뷰는 partial report 보장을 완료로, full E2E를 미확정으로 분리한다. 이 분리는 적절하다. 다만 후속 문서에서는 아래처럼 더 선명히 적는 것이 좋다.

| 구분 | 현재 판정 |
|---|---|
| partial/interruption report 생성 | 확인됨 |
| partial report schema-valid | 확인됨으로 보고됨 |
| release-smoke 생성 ZIP budget 표면 | 코드/schema 반영 |
| extracted archive 전체 lint/eval/stage2/planning gate 완주 | 미확정 |
| timeout/interruption 자동 회귀 테스트 | 미확정 |
| full profile 완료 report | 미확정 |

즉 release-smoke는 `부분 완료`이지 `release gate 완성`이 아니다.

### 7.4 Mypy 검증 강도

신규 통합 리뷰는 Mypy 통과를 통합 판정에 포함한다. 기존 리뷰 중 일부는 Mypy stdout 성공 신호를 확인했고, 일부는 환경 제약 때문에 완전한 프로세스 종료까지는 불확실하다고 기록했다. 따라서 후속 보고서에서는 다음처럼 쓰는 것이 가장 안전하다.

- 정적 타입 검증은 기존 리뷰 기록상 통과 신호가 강하다.
- 다만 현재 후속 검토에서는 Mypy를 반복 실행하지 않았으므로, 이 문서의 직접 증거는 기존 리뷰의 실행 기록과 파일 표면 대조다.

### 7.5 `safe_to_backfill_artifact_count` 수치

신규 통합 리뷰는 runtime 재생성 기준 `safe_to_backfill_artifact_count=61`을 확정값처럼 기록한다. 그러나 실제 저장본은 `87`이고, 기존 리뷰들도 이 값이 mtime 및 재생성 시점에 따라 흔들린다고 지적했다.

따라서 이 수치는 아래처럼 다뤄야 한다.

| 지표 | 판정 |
|---|---|
| `missing_artifact_envelope_count=109` | 안정적인 contract debt |
| `unknown_currentness_artifact_count=109` | 안정적인 contract debt |
| `missing_schema_count=17` | 안정적인 contract debt |
| `schema_invalid_artifact_count=0` | 안정적인 양호 신호 |
| `safe_to_backfill_artifact_count` | 실행 시점/mtime에 민감 |
| `stale_artifact_count` | 실행 시점/mtime에 민감 |
| `mtime_sensitive_artifact_count` | 실행 시점/mtime에 민감 |

### 7.6 plain `pytest` 문제의 성격

`pytest.ini`에는 `pythonpath = .`가 없다. 따라서 신규 리뷰 B가 발견한 `plain pytest` import 실패는 실제 파일 구조상 그럴 가능성이 높다.

이 문제는 runtime 핵심 결함이라기보다 개발자 진입점/CI UX 문제다. 우선순위는 P1이 적절하다.

---

## 8. 아직 남아 있는 작업분

### 8.1 P0 — skipped run 1건 처리

현재 mechanism review 저장본은 여전히 다음 run을 skip한다.

| 항목 | 값 |
|---|---|
| run id | `run-20260422-auto-improve-decision-record-fallback` |
| missing artifact | `runs/run-20260422-auto-improve-decision-record-fallback/candidate-eval.json` |
| 현 상태 | operator decision required |
| recommended action | `restore_missing_artifact_or_archive_run_history` |

진단 품질은 개선됐지만, 실제 상태 전환은 아직 일어나지 않았다. 다음 중 하나로 닫아야 한다.

1. missing artifact 복원
2. historical quarantine 처리
3. superseded non-history 명시

완료 기준은 `runs_skipped=0` 또는 `classified_quarantined`/`superseded_non_history`처럼 skip이 정책적으로 분류되는 것이다.

추가 구현 업데이트(working tree 기준): 이후 후속 구현에서 `run-20260422-auto-improve-decision-record-fallback`를 archived history로 분류했고, 현재 저장소의 `ops/reports/mechanism-review-candidates.json`은 `runs_skipped=0`, `runs_excluded=1`로 갱신됐다. 따라서 이 항목 역시 **ZIP snapshot 기준 미해결이었으나, 현재 working tree 기준으로는 해소됨**이다.

### 8.2 P0 — learning/session/loop-health evidence 부족

현재 readiness 저장본 기준 상태는 다음과 같다.

| 항목 | 현재 값 | 목표 |
|---|---:|---:|
| `attempts_considered` | 7 | 10 이상 |
| `session_reports_considered` | 0 | 1 이상 |
| `session_calibration_status` | `no_session_context` | context 존재 |
| `loop_health_summary.status` | `missing` | missing 아님 |
| `learning_readiness.status` | `learning_uncertain` | 불확실성 완화 |

`execution_readiness.can_run=true`는 실행 큐가 열렸다는 뜻이지 학습 신뢰도가 충분하다는 뜻이 아니다. 따라서 신규 통합 리뷰의 `execution_pass_learning_review_required` 계열 dual-status 제안은 적절하다.

### 8.3 P0 — artifact contract debt

저장본 기준 주요 contract debt는 다음과 같다.

| 항목 | 현재 값 |
|---|---:|
| `missing_artifact_envelope_count` | 109 |
| `unknown_currentness_artifact_count` | 109 |
| `missing_schema_count` | 17 |
| `schema_invalid_artifact_count` | 0 |

`schema_invalid=0`은 좋은 신호지만, envelope/currentness/schema debt가 아직 크다. 특히 `missing_schema` 17건은 신규 통합 리뷰와 실제 저장본이 일치한다.

추가 구현 업데이트(working tree 기준): 첫 세 safe-to-backfill slice로 `ops/reports/manual-mutate-defect-registry.json`, `ops/reports/cyclonedx-bom.json`, `ops/reports/openvex-draft.json`를 각각 canonical contract에 맞게 backfill했다. 재생성된 `ops/reports/artifact-freshness-report.json` 기준 debt는 이제 `missing_artifact_envelope_count=106`, `unknown_currentness_artifact_count=106`, `missing_schema_count=17`이다. 즉 artifact contract debt는 여전히 P0이지만, 저장본 기준으로도 세 개의 canonical `ops/reports/` slice가 실제로 정리됐고, CycloneDX는 현재 envelope/currentness debt 대신 mtime-sensitive timestamp drift로만 남는다.

### 8.4 P0 — stored artifact freshness report 갱신

실제 ZIP의 저장본은 여전히 `missing_generated_at` action을 `none`으로 보유한다. runtime path가 고쳐졌더라도 저장된 canonical report가 갱신되지 않으면 사용자는 오래된 큐를 보게 된다.

완료 기준은 다음이다.

- `ops/reports/artifact-freshness-report.json` 재생성
- `missing_generated_at` action이 실질적인 action string으로 저장됨
- stored report와 runtime regenerated report의 핵심 summary/action diff가 허용 범위 안에 들어옴

### 8.5 P0/P1 — release-smoke full E2E 자동화

partial report 장치는 반영됐지만 full E2E의 deterministic 완료 증거가 부족하다.

필요한 작업은 다음과 같다.

1. tiny fixture vault 기반 fast-smoke 추가
2. full vault profile과 fast profile 분리
3. interruption/timeout partial report unit test 추가
4. full profile 완료 report와 partial report를 명확히 구분
5. CI에서 fast profile을 기본 gate로 운용

### 8.6 P1 — proposal lifecycle ledger 연결

현재 runnable proposal은 1건 존재한다.

| 항목 | 값 |
|---|---|
| proposal id | `repeated_same_eval_or_discard__auto-improve-iteration-persistence-runtime` |
| source candidate | `mechanism_eval_stagnation_candidate__auto-improve-iteration-persistence-runtime` |
| primary target | `ops/scripts/auto_improve_iteration_persistence_runtime.py` |
| supporting target | `ops/schemas/run-telemetry.schema.json` |

하지만 proposal이 decision/outcome/evidence chain과 연결됐다는 증거는 부족하다. proposal lifecycle ledger를 도입하거나 기존 ledger에 연결해야 한다.

### 8.7 P1 — plain `pytest` 호출 계약 정리

현재 `python -m pytest`를 공식 진입점으로 유지할지, `pytest.ini`에 `pythonpath = .`를 추가해 plain `pytest`도 지원할지 결정해야 한다.

권장 방향은 둘 중 하나다.

| 선택지 | 장점 | 단점 |
|---|---|---|
| `python -m pytest` 공식화 | 환경 예측 가능, 변경 작음 | 신규 기여자가 plain `pytest`로 실패 가능 |
| `pytest.ini`에 `pythonpath = .` 추가 | 진입 friction 감소 | import contract를 설정 파일에 추가해야 함 |

### 8.8 P2 — public export count semantics 문서화

count parity 문제는 개선됐지만 `file_count`, `source_file_count`, manifest self inclusion의 의미가 직관적으로 드러나지 않는다.

권장 필드는 다음과 같다.

| 필드 | 의미 |
|---|---|
| `exported_source_file_count` | private vault에서 export 대상으로 선택된 원본 파일 수 |
| `manifest_entry_count` | manifest files 배열 길이 |
| `output_tree_file_count_including_manifest` | manifest 자신을 포함한 최종 출력 tree 파일 수 |
| `manifest_self_included` | manifest 파일이 output count에 포함되는지 여부 |

### 8.9 P2 — run stdout/stderr 0-byte placeholder policy

현재 0-byte 파일 15건은 모두 run stdout/stderr 로그 placeholder다. 이들을 archive hygiene warning으로 오탐하지 않도록 policy class를 명확히 해야 한다.

---

## 9. missing schema 17건 실제 목록

실제 저장본 기준 `missing_schema` 17건은 다음과 같다.

| 경로 |
|---|
| `ops/reports/eval-initial-2026-04-12.json` |
| `ops/reports/lint-initial-2026-04-12.json` |
| `ops/reports/manifest-2026-04-12.json` |
| `ops/reports/review-archive-report.json` |
| `runs/run-20260415-raw-markdown-normalization/raw-markdown-normalization-report.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/concept-continuity-integration-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-profiles-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-render-after-concept-integration-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-validate-after-concept-integration-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-reregistration-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-slug-manifest-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/raw-intake-promotion-validate-final-tree-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/raw-registry-preflight-final-tree-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/source-english-summary-slug-validate-final-tree-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/wiki-lint-final-tree-2026-04-22.json` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/wiki-stage2-final-tree-2026-04-22.json` |

신규 통합 리뷰의 목록과 일치한다.

---

## 10. 신규로 강조할 개선 방안

### 10.1 stored report와 runtime report를 별도 acceptance로 분리

현재 가장 중요한 보정점은 `runtime 재생성 경로가 개선됨`과 `ZIP 안 저장본이 최신임`을 구분하는 것이다.

권장 acceptance는 다음과 같다.

| acceptance | 설명 |
|---|---|
| runtime-action-correct | 새로 생성한 report의 action string이 정확함 |
| stored-action-current | ZIP에 포함된 canonical report가 runtime 결과와 일치함 |
| stored-runtime-drift-bounded | timestamp 외 핵심 summary/action drift가 없음 |

### 10.2 artifact freshness 지표 계층화

권장 지표 계층은 다음과 같다.

| 계층 | 지표 |
|---|---|
| stable contract debt | `missing_artifact_envelope`, `unknown_currentness`, `missing_schema`, `schema_invalid` |
| mtime observation | `generated_at_older_than_file_mtime`, `stale`, `mtime_sensitive` |
| operational queue | `safe_to_backfill`, `recommended_next_action`, `top_debt_files` |

이렇게 나눠야 리뷰마다 숫자가 다르게 보이는 문제를 운영 혼선 없이 처리할 수 있다.

### 10.3 release-smoke profile 분리

`fast`, `full`, `interruption-unit` 세 층으로 분리한다.

| profile | 목적 |
|---|---|
| fast | tiny fixture vault로 archive build/extract/manifest parity/기본 lint를 빠르게 검증 |
| full | 실제 vault 전체 release path 검증 |
| interruption-unit | timeout/interruption 시 schema-valid partial report 보장 |

### 10.4 skipped run quarantine helper

남은 skipped run은 1건뿐이므로 반복 진단보다 상태 전환 helper가 필요하다.

권장 출력은 다음과 같다.

| 필드 | 예시 |
|---|---|
| `run_id` | `run-20260422-auto-improve-decision-record-fallback` |
| `history_status` | `quarantine_candidate` |
| `reason` | `missing_promotion_input_artifact` |
| `operator_decision` | `restore`, `quarantine`, `supersede_non_history` 중 하나 |
| `mechanism_review_effect` | hard skip에서 classified skip으로 전환 |

### 10.5 dual-status readiness summary

상단 summary에 다음처럼 실행 가능성과 학습 신뢰도를 분리해 표시한다.

| 필드 | 현재 값 제안 |
|---|---|
| `execution_status` | `pass` |
| `learning_status` | `learning_uncertain` |
| `overall_status` | `execution_pass_learning_review_required` |
| `release_confidence` | `not_release_ready` |

---

## 11. 권장 실행 순서

### PR-1: stored artifact freshness report 갱신 및 drift gate 추가

목표:

- stored `artifact-freshness-report.json`의 `missing_generated_at` action을 `none`에서 실질 action으로 갱신
- stored/runtime 핵심 drift 검사 추가
- mtime-sensitive 지표와 stable debt 지표 분리

완료 기준:

- stored top debt action이 runtime과 일치
- `schema_invalid_artifact_count=0` 유지
- timestamp 외 핵심 summary/action drift 없음

### PR-2: skipped run 1건 복원 또는 quarantine

목표:

- `runs_skipped=0` 또는 explicit classified skip

완료 기준:

- missing `candidate-eval.json` 복원, 또는
- `history-status.json`/decision artifact로 quarantine/non-history 처리
- mechanism review에서 operator가 해석 가능한 상태로 표시

### PR-3: session/outcome/loop-health evidence 보강

목표:

- `attempts_considered >= 10`
- `session_reports_considered > 0`
- `loop_health_summary.status != missing`

완료 기준:

- readiness summary가 `execution_pass_learning_review_required`에서 더 구체적 상태로 이동
- outcome/session/loop-health artifact가 서로 연결됨

### PR-4: artifact contract backfill 1차

목표:

- `missing_artifact_envelope_count=109` 유의미 감소
- `unknown_currentness_artifact_count=109` 유의미 감소
- `missing_schema_count=17` 감소 또는 historical/noncanonical 분류

완료 기준:

- safe-to-backfill 항목 우선 처리
- missing schema 17건의 처리 정책 확정
- generated artifact contract가 work queue로 기능

추가 구현 업데이트(working tree 기준): 위 PR-4는 이제 세 개의 bounded slice까지 진행됐다. 첫째, `ops/reports/manual-mutate-defect-registry.json`가 shared artifact envelope/currentness contract를 따르도록 backfill됐고 `missing_artifact_envelope_count`와 `unknown_currentness_artifact_count`를 109→108로 줄였다. 둘째, `ops/reports/cyclonedx-bom.json`는 strict CycloneDX top-level shape를 깨지 않도록 `metadata.properties[urn:openai:artifact-envelope]`에 embedded envelope/currentness를 실어 backfill됐고, artifact freshness가 그 embedded envelope를 canonical surface로 읽도록 확장되면서 같은 두 bucket을 다시 108→107로 줄였다. 셋째, `ops/reports/openvex-draft.json`는 repo-local schema를 유지한 채 top-level canonical envelope/currentness contract로 backfill됐고, 같은 두 bucket을 다시 107→106으로 줄였다.

### PR-5: release-smoke fast/full/interruption profile 분리

목표:

- fast profile은 CI에서 deterministic하게 완주
- full profile은 별도 장시간 gate로 운영
- interruption/timeout partial report는 unit test로 고정

완료 기준:

- fast-smoke 완료 summary 확보
- full-smoke 완료 또는 명시적 장시간 gate 분리
- interruption partial report schema validation 자동화

### PR-6: pytest 진입점 계약 정리

목표:

- plain `pytest`와 `python -m pytest` 중 공식 진입점을 명확히 하거나 둘 다 동작하게 함

완료 기준:

- README/Makefile/CI/pytest.ini가 같은 계약을 가리킴
- 신규 기여자 첫 실행 실패 가능성 감소

### PR-7: proposal lifecycle ledger 연결

목표:

- 현재 runnable proposal 1건을 source candidate, decision, outcome, follow-up attempt와 연결

완료 기준:

- proposal id에서 outcome artifact까지 추적 가능
- readiness가 단순 queue 존재보다 outcome feedback을 반영

---

## 12. 보정된 Acceptance Criteria

| ID | 기준 | 현재 판정 |
|---:|---|---|
| AC-01 | ZIP SHA가 신규 통합 리뷰와 일치 | 충족 |
| AC-02 | Python CRC 검증 통과 | 충족 |
| AC-03 | Python extractall 성공 | 충족 |
| AC-04 | C-locale Info-ZIP 추출 성공 | 충족 |
| AC-05 | root 0-byte placeholder 제거 | 충족 |
| AC-06 | 긴 한글 파일명 offender 제거 | 충족 |
| AC-07 | slug 변환 파일의 원제목 frontmatter 보존 | 충족 |
| AC-08 | self-improve candidates/proposals 존재 | 충족 |
| AC-09 | execution readiness `can_run=true` | 충족 |
| AC-10 | local schema invalid 0 | 충족 |
| AC-11 | missing schema 17건 목록이 리뷰와 일치 | 충족 |
| AC-12 | artifact freshness stored report의 `missing_generated_at` action 정규화 | 미충족 |
| AC-13 | skipped run 0 또는 classified skip | 미충족 |
| AC-14 | attempts considered 10 이상 | 미충족 |
| AC-15 | session reports 1 이상 | 미충족 |
| AC-16 | loop health summary present | 미충족 |
| AC-17 | release-smoke partial report 장치 존재 | 부분 충족 |
| AC-18 | release-smoke full E2E 완료 | 미확인/미충족 |
| AC-19 | plain `pytest` import 계약 안정화 | 미충족 |
| AC-20 | public export count semantics 명시 | 부분 충족 |
| AC-21 | proposal lifecycle ledger 연결 | 미충족 |
| AC-22 | run stdout/stderr 0-byte placeholder policy 명시 | 미충족 |

현재 working tree 후속 구현 기준 보정:

- AC-12는 이제 충족이다. 저장본 `ops/reports/artifact-freshness-report.json`의 `missing_generated_at` action이 runtime semantics와 일치한다.
- AC-13도 이제 충족이다. `run-20260422-auto-improve-decision-record-fallback`는 active skipped run이 아니라 archived excluded run으로 분류됐다.

---

## 13. 최종 판단

새 통합 리뷰는 큰 방향에서 정확하다. 실제 ZIP은 기존 v44 리뷰 이후 중요한 개선이 반영된 후속 체크포인트이며, 특히 POSIX portability, root placeholder, self-improve queue, release-smoke partial report 표면은 분명히 개선됐다.

다만 실제 파일 기준으로는 두 가지를 반드시 보정해야 한다.

첫째, 최상위 구조 표에서 root 직접 파일은 18개가 아니라 17개이며, 별도로 `.vscode` 파일 1개가 있다.

둘째, `missing_generated_at` action string 정규화는 runtime 경로 기준 개선으로 보아야 하며, 현재 ZIP에 저장된 `ops/reports/artifact-freshness-report.json`에는 아직 `recommended_next_action: none`이 남아 있다. 따라서 이 항목은 완전 완료가 아니라 stored report 갱신이 남은 상태다.

보정 후 현재 체크포인트의 정확한 상태는 다음과 같다.

> 현재 체크포인트는 기존 리뷰 이후 portability와 release hygiene, execution queue 측면에서 확실히 진전됐다. 그러나 skipped run 1건, artifact contract debt 109/109/17, stored artifact freshness report drift, learning/session/loop-health evidence 부족, release-smoke full E2E 미확정 때문에 아직 release-ready가 아니라 운영 안정화 마무리 단계다.

추가 구현 업데이트(working tree 기준): 현재 저장소는 위 문단이 가리킨 두 개의 즉시 closeout 항목, 즉 **skipped run 1건**과 **stored artifact freshness report drift(`missing_generated_at` action)**를 이미 해소했고, 다음 세 safe-to-backfill slice로 `ops/reports/manual-mutate-defect-registry.json`, `ops/reports/cyclonedx-bom.json`, `ops/reports/openvex-draft.json`의 artifact contract debt도 정리했다. 따라서 현재 working tree 기준의 병목은 artifact contract debt **106/106/17**, learning/session/loop-health evidence 부족, release-smoke full E2E 미확정 쪽으로 더 선명하게 좁혀졌다.

---

## 14. 한 줄 요약

**새 통합 리뷰의 핵심 결론은 대체로 맞았고, 이후 후속 구현으로 stored artifact freshness action drift, skipped run 1건, 그리고 두 개의 safe-to-backfill artifact contract slice까지 현재 working tree 기준으로 해소됐다. 이제 다음 우선순위는 learning evidence 보강, 다음 artifact contract backfill cluster, release-smoke fast/full 자동화다.**
