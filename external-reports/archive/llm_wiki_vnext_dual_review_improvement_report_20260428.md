# LLM Wiki vNext 이중 리뷰 대조 개선 보고서

- **작성일**: 2026-04-28
- **출력 파일명**: `llm_wiki_vnext_dual_review_improvement_report_20260428.md`
- **검토 대상 리뷰 1**: `llm_wiki_vnext_integrated_audit_report_20260428.md`
- **검토 대상 리뷰 2**: `llm_wiki_vnext_integrated_tri_review_report_20260428.md`
- **비교 기준 기존 리뷰**: `llm_wiki_vnext_integrated_unified_report_20260427.md`
- **실제 대조 ZIP**: `LLM Wiki vNext(50).zip`
- **실제 ZIP SHA-256**: `9ef226df11d92848d5ca1f5cdcb3a7ae40763472053c643a856cad0abb9de999`

---

## 1. 결론 요약

두 신규 리뷰는 큰 방향에서는 서로 거의 동일하다. 둘 다 현재 ZIP이 기존 통합 리뷰 기준선보다 **분명히 진전된 후속 스냅샷**이라고 보며, stable artifact debt가 `106/106/17`에서 `79/79/17`로 감소했고, session/loop-health 증거가 일부 추가됐으며, `ops/reports/release-smoke-report.json`에 `profile=full`, `status=pass`가 저장돼 있다고 정리한다. 이 세 축은 실제 ZIP 내부 파일로 다시 확인해도 일치한다.

다만 두 리뷰가 공통으로 강하게 받아들인 **“raw registry 경로 동기화 깨짐 → raw_registry_preflight 46건 mismatch → make check 실패 → release-smoke live 재현 실패”** 체인은, **현재 업로드된 ZIP을 직접 풀어 검증한 결과로는 재현되지 않았다.** 이번 재검토에서 추출본 기준 `python -m ops.scripts.raw_registry_preflight --vault .`는 `status=pass`, `error_count=0`, `warning_count=0`으로 통과했다. 따라서 이 이슈는 **현재 ZIP의 확정 blocker**로 단정하기보다, **특정 리뷰 환경 또는 당시 라이브 워킹트리에서 관찰된 현상**으로 범위를 다시 좁혀야 한다.

즉, 현재 실제 파일 기준으로 가장 신뢰도 높게 남아 있는 핵심 미완료 항목은 다음 네 가지다.

1. **Artifact contract stable debt 잔존**: `missing_artifact_envelope=79`, `unknown_currentness=79`, `missing_schema=17`
2. **Learning readiness 미완결**: `learning_uncertain`, `attempts_considered=7`, `session_calibration_status=no_session_context`, `telemetry_coverage_ratio=0.0`
3. **테스트 진입점 계약 불안정**: `pytest.ini`에 `pythonpath = .`가 없고, 실제로 plain `pytest` 수집이 깨진다
4. **Gate 구조 병목**: full-vault 검증이 여러 단계에서 중복될 가능성이 높고, fast/full profile 분리가 아직 설계 수준에 가깝다

이번 보고서의 핵심 보정은 다음 한 문장으로 요약된다.

> **두 신규 리뷰의 “진전” 판단은 대체로 맞지만, “현재 ZIP에서 raw registry live failure가 확정적으로 재현된다”는 판단은 실제 파일 대조 결과 그대로 수용하면 안 된다.**

---

## 2. 검토 방법 및 실제 재검증 범위

이번 보고서는 단순 문서 병합이 아니라, 아래 네 층을 교차 검증했다.

1. `llm_wiki_vnext_integrated_audit_report_20260428.md` 전문 재검토
2. `llm_wiki_vnext_integrated_tri_review_report_20260428.md` 전문 재검토
3. `llm_wiki_vnext_integrated_unified_report_20260427.md`와의 기준선 비교
4. `LLM Wiki vNext(50).zip` 실제 내용 직접 검증

이번에 실제로 다시 확인한 항목은 다음과 같다.

- ZIP SHA-256, entry 수, 파일 수, 디렉터리 수, 압축 해제 총 바이트
- `ops/reports/artifact-freshness-report.json`
- `ops/reports/auto-improve-readiness.json`
- `ops/reports/release-smoke-report.json`
- `tests/test_release_smoke.py`의 테스트 함수 수(AST 기준)
- `pytest.ini`, `Makefile`, `requirements-dev.txt`
- ZIP 추출본 기준 `python -m ops.scripts.raw_registry_preflight --vault .`
- 추출본 기준 plain `pytest --collect-only -q`

반면 아래 항목은 이번 실행 환경 제약상 **직접 완주 재검증하지 않았다**.

- full `release_smoke --profile full` 라이브 완주
- `ruff`, `mypy`, `make check` 전체 재실행
- 전체 pytest 스위트 통과 여부
- C-locale Info-ZIP 전체 재실행

따라서 본 보고서는 **문서 내용 + 실제 파일 재현 가능한 범위**에 대해서는 강하게 단정하고, **이번에 직접 완주하지 못한 항목**은 그 한계를 분리해서 기록한다.

---

## 3. 실제 ZIP에서 다시 확인된 공통 사실

### 3.1 구조 및 무결성

| 항목 | 실제값 |
|---|---:|
| ZIP SHA-256 | `9ef226df11d92848d5ca1f5cdcb3a7ae40763472053c643a856cad0abb9de999` |
| entry 수 | 1648 |
| 파일 수 | 1570 |
| 디렉터리 수 | 78 |
| 압축 해제 전체 바이트 합 | 240325896 |
| root 직접 파일 수 | 17 |
| root 직접 0-byte 파일 수 | 0 |
| `runs/` 하위 0-byte placeholder | 15 |
| `external-reports` 파일 수 | 35 |

### 3.2 최상위 경로별 파일 수

| 최상위 경로 | 파일 수 |
|---|---:|
| `.codex` | 10 |
| `(root)` | 17 |
| `.github` | 2 |
| `.obsidian` | 5 |
| `.vscode` | 1 |
| `external-reports` | 35 |
| `ops` | 283 |
| `raw` | 446 |
| `runs` | 156 |
| `system` | 71 |
| `tests` | 122 |
| `tools` | 5 |
| `wiki` | 417 |

### 3.3 확장자 분포 상위

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
| `(none)` | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |

### 3.4 root 직접 파일 목록

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
| `README.md` |
| `SECURITY.md` |
| `THIRD_PARTY_NOTICES.md` |
| `pyproject.toml` |
| `pytest.ini` |
| `requirements-dev.txt` |
| `requirements.txt` |
| `uv.lock` |

위 수치는 두 신규 리뷰가 제시한 `9ef226df11d92848d5ca1f5cdcb3a7ae40763472053c643a856cad0abb9de999`, `entry 1648`, `files 1570`, `dirs 78`, `external-reports 35`, `runs placeholder 15`와 일치한다. 즉, **구조 프로필 자체는 두 리뷰가 정확하게 요약했다.**

---

## 4. 두 신규 리뷰가 맞게 짚은 내용

### 4.1 기존 기준 리뷰 대비 실질 진전

기존 통합 리뷰가 기준으로 삼았던 v47 계열 체크포인트는 stable debt `106/106/17`, `session_reports_considered=0`, `loop_health_summary.status=missing`, full release-smoke 미확정 상태였다. 현재 ZIP의 저장 산출물은 아래처럼 개선돼 있다.

| 항목 | 기존 기준 리뷰 | 현재 실제 ZIP |
|---|---:|---:|
| `missing_artifact_envelope_count` | 106 | 79 |
| `unknown_currentness_artifact_count` | 106 | 79 |
| `missing_schema_count` | 17 | 17 |
| `missing_generated_at` | 59 | 30 |
| `schema_invalid_artifact_count` | 0 | 0 |
| `session_reports_considered` | 0 | 1 |
| `loop_health_summary.status` | missing | available |
| release-smoke full pass 저장본 | 없음/미확정 | 존재 (`status=pass`, `profile=full`) |
| `tests/test_release_smoke.py` 함수 수 | 13 | 14 |

즉, 두 신규 리뷰의 큰 방향성, 곧 **“이 ZIP은 분명히 진전된 후속 스냅샷이다”**라는 평가는 실제 파일로도 지지된다.

### 4.2 Artifact contract debt 관련 판단

`ops/reports/artifact-freshness-report.json` 저장본 summary는 다음과 같다.

```json
{
  "artifact_count": 149,
  "json_artifact_count": 149,
  "scanned_text_artifact_count": 181,
  "stale_artifact_count": 65,
  "mtime_sensitive_artifact_count": 65,
  "root_ephemeral_artifact_count": 0,
  "run_log_placeholder_count": 15,
  "unknown_currentness_artifact_count": 79,
  "non_utf8_text_artifact_count": 0,
  "missing_schema_count": 17,
  "missing_artifact_envelope_count": 79,
  "schema_invalid_artifact_count": 0,
  "schema_unavailable_artifact_count": 0,
  "safe_to_backfill_artifact_count": 84,
  "stable_contract_debt_artifact_count": 79,
  "stable_contract_debt_issue_count": 175,
  "mtime_sensitive_attention_artifact_count": 65,
  "mtime_sensitive_attention_issue_count": 65
}
```

여기서 중요한 해석도 두 신규 리뷰가 대체로 정확하다.

- stable debt 중심 축은 `missing_artifact_envelope`, `unknown_currentness`, `missing_schema`
- `schema_invalid_artifact_count = 0` 유지
- `stale_artifact_count`, `mtime_sensitive_artifact_count`, `safe_to_backfill_artifact_count`는 **mtime-sensitive**라서 release gate 핵심 KPI로 직접 쓰면 위험

이 점은 실제 저장 산출물 구조와도 맞는다.

### 4.3 Learning readiness 관련 판단

`ops/reports/auto-improve-readiness.json`의 현재 저장 상태는 아래와 같다.

- `execution_readiness.status = pass`
- `execution_readiness.can_run = true`
- `runnable_proposal_count = 1`
- `learning_readiness.status = learning_uncertain`
- `likely_to_learn = false`
- `attempts_considered = 7`
- `session_reports_considered = 1`
- `session_calibration_status = no_session_context`
- `rework_count = 5`
- `hold_moving_average = 0.2857`
- `defect_escape_pair_count = 3`

즉, 두 신규 리뷰가 정리한 대로 **execution queue는 열려 있지만 learning confidence는 아직 통과 상태가 아니다.** 이 해석은 그대로 유지하는 것이 맞다.

### 4.4 Release-smoke 저장본 존재

실제 ZIP 내부 `ops/reports/release-smoke-report.json`은 다음 사실을 포함한다.

- `generated_at = 2026-04-28T00:28:56Z`
- `profile = full`
- `status = pass`
- `packed_file_count = 1322`
- archive budget: pass
- manifest comparison: pass
- smoke command 5개 모두 return code 0 저장

command별 저장 결과:

| command | returncode | duration_ms |
|---|---:|---:|
| `raw_registry_preflight` | 0 | 18975 |
| `wiki_lint` | 0 | 42242 |
| `wiki_eval` | 0 | 19613 |
| `wiki_stage2_eval` | 0 | 5854 |
| `planning_gate_validate` | 0 | 1526 |


이 역시 두 신규 리뷰가 공통으로 정리한 내용과 일치한다.

---

## 5. 실제 파일 대조 후 보정이 필요한 부분

### 5.1 가장 큰 보정: raw_registry_preflight live failure는 현재 ZIP에서 재현되지 않았다

두 신규 리뷰는 모두 v50 상세 재검토의 발견을 사실상 확정 사실처럼 계승한다. 요지는 다음과 같다.

- 라이브 `raw_registry_preflight` 실행 시 46건 `raw_path_mismatch`
- 그 결과 `make check` 실패
- 나아가 release-smoke live rerun도 partial failure
- 따라서 raw registry sync가 즉시 복구해야 할 P0

하지만 이번에 **현재 업로드된 ZIP을 추출한 뒤** 동일 진입점으로 직접 실행한 결과는 아래와 같았다.

```json
{
  "status": "pass",
  "error_count": 0,
  "warning_count": 0,
  "entry_count": 446
}
```

즉, **현재 실제 ZIP 추출본에는 적어도 raw registry 경로 불일치가 보이지 않는다.**

이 보정이 중요한 이유는 다음과 같다.

1. 두 신규 리뷰가 가장 높은 우선순위로 묶은 P0 blocker의 핵심 근거가 약해진다.
2. “현재 ZIP이 곧바로 `make check` 단계에서 깨진다”는 결론은 실제 파일만으로는 더 이상 확정할 수 없다.
3. v50 리뷰의 관찰은 **특정 개발 환경, 당시 라이브 워킹트리, 혹은 체크인 전 상태**를 반영했을 가능성이 있다.
4. 따라서 다음 스냅샷의 액션은 “registry sync를 이미 깨진 현재 상태로 전제하고 일괄 migration”이 아니라, **실패 조건을 재현 가능한 절차로 먼저 고정**하는 쪽이 더 안전하다.

이 항목의 통합 판정은 다음처럼 수정하는 것이 적절하다.

| 항목 | 두 신규 리뷰의 표현 | 실제 파일 대조 후 보정 |
|---|---|---|
| raw registry sync | 현재 ZIP의 확정 P0 blocker | **현재 추출본에서는 미재현**. 과거/특정 환경 관찰로 범위 축소 필요 |
| `make check` 실패 | 현재 상태의 확정 사실 | raw registry 실패를 직접 재현하지 못했으므로 **현재 ZIP 일반 사실로 단정 불가** |
| release-smoke live rerun fail | 현재 체크포인트의 확정 사실 | 이번 실행에서는 full rerun을 완주하지 못해 **미검증**으로 남겨야 함 |

### 5.2 현재 ZIP에 self-include되지 않은 두 신규 리뷰

현재 ZIP의 `external-reports/`는 35개 파일을 포함하고 있으며, 기존 통합 리뷰 파일 `llm_wiki_vnext_integrated_unified_report_20260427.md`는 실제로 self-include되어 있다. 그러나 이번에 새로 업로드된 아래 두 파일은 **현재 ZIP 내부에는 존재하지 않는다.**

- `llm_wiki_vnext_integrated_audit_report_20260428.md`
- `llm_wiki_vnext_integrated_tri_review_report_20260428.md`

즉, 두 신규 리뷰는 **현재 체크포인트를 분석한 외부 산출물**이지, **현재 체크포인트 자체에 포장된 내부 산출물**은 아니다.

### 5.3 “release-smoke 재현성 실패”는 현재로서는 강한 추정이지 확정 사실은 아니다

두 신규 리뷰는 저장본 pass와 라이브 rerun fail의 불일치를 중요한 문제로 꼽는다. 하지만 이번 검토에서는 full rerun 전체를 완주하지 못했다. 그 대신 다음 두 사실만 분명하다.

- 저장본 `release-smoke-report.json`은 실제 ZIP 안에 존재하며 내용도 유효하다.
- 저장본이 가리키는 첫 단계 중 하나인 `raw_registry_preflight`는 현재 추출본에서 pass한다.

따라서 현 시점의 가장 정직한 표현은 다음과 같다.

> **저장본 full release-smoke pass는 확인되지만, 현재 업로드 ZIP 기준 live full rerun의 성공/실패는 이번 실행에서 확정하지 못했다.**

즉, 두 신규 리뷰가 강하게 주장한 “live rerun failed”는 **보류/재확인 필요**로 내리는 편이 정확하다.

---

## 6. 현재 실제 파일 기준으로 확정되는 미완료 작업

### 6.1 Artifact contract stable debt 79/79/17

두 신규 리뷰가 강조한 가장 단단한 미완료 항목이다. 실제 저장본에서도 그대로 확인된다.

- `missing_artifact_envelope_count = 79`
- `unknown_currentness_artifact_count = 79`
- `missing_schema_count = 17`
- `schema_invalid_artifact_count = 0`

owner surface 기준으로 보면 envelope/currentness debt는 `ops_reports=11`, `runs=68`에 분포한다. 이 분포도 두 신규 리뷰의 설명과 일치한다.

### 6.2 Missing schema 17건

실제 저장본에서 missing schema 17건은 그대로 남아 있으며, 다음처럼 분류된다.

| path | owner_surface | safe_to_backfill | mtime_sensitive |
|---|---|---:|---:|
| `ops/reports/eval-initial-2026-04-12.json` | `ops_reports` | `true` | `false` |
| `ops/reports/lint-initial-2026-04-12.json` | `ops_reports` | `true` | `false` |
| `ops/reports/manifest-2026-04-12.json` | `ops_reports` | `true` | `false` |
| `ops/reports/review-archive-report.json` | `ops_reports` | `false` | `true` |
| `runs/run-20260415-raw-markdown-normalization/raw-markdown-normalization-report.json` | `runs` | `false` | `true` |
| `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/concept-continuity-integration-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-profiles-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-render-after-concept-integration-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-validate-after-concept-integration-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-reregistration-2026-04-22.json` | `runs` | `false` | `true` |
| `runs/run-20260422-raw-intake-registration-and-promotion/registration/source-english-summary-slug-manifest-2026-04-22.json` | `runs` | `false` | `true` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/raw-intake-promotion-validate-final-tree-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/raw-registry-preflight-final-tree-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/source-english-summary-slug-validate-final-tree-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/wiki-lint-final-tree-2026-04-22.json` | `runs` | `true` | `false` |
| `runs/run-20260422-raw-intake-registration-and-promotion/validation/wiki-stage2-final-tree-2026-04-22.json` | `runs` | `true` | `false` |

실무적으로는 여기서 **13건(`safe_to_backfill=true`, `mtime_sensitive=false`)을 먼저 정리**하고, **나머지 4건은 regenerate 또는 legacy classification**으로 처리하는 순서가 맞다. 이 전략은 두 신규 리뷰의 공통 권고와도 부합한다.

### 6.3 Learning readiness 미완결

이 항목은 실제 저장본 기준으로도 가장 분명한 blocker 중 하나다.

- `learning_readiness.status = learning_uncertain`
- `attempts_considered = 7` (기준 10 미달)
- `session_calibration_status = no_session_context`
- `telemetry_coverage_ratio = 0.0` (loop-health available이지만 텔레메트리 자체는 비어 있음)
- `rework_count = 5`
- `hold_moving_average = 0.2857`
- `defect_escape_pair_count = 3`

즉, execution queue가 열려 있다는 이유만으로 release confidence를 높게 볼 수는 없다.

### 6.4 Pytest 진입점 계약 문제는 현재도 실제로 존재한다

이번에 실제 추출본 기준으로 plain pytest 수집을 다시 확인한 결과, 아래 문제가 재현됐다.

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest --collect-only -q`
- 결과: **104 errors during collection**
- 대표 오류: `ModuleNotFoundError: No module named 'ops'`

반면 설정 파일과 Makefile은 다음 상태다.

- `pytest.ini`에는 `pythonpath = .`가 없다.
- `Makefile`은 `python -m pytest` 계열을 사용한다.
- `requirements-dev.txt`는 `pytest>=8.3,<9`, `pytest-xdist>=3.6,<4`를 요구한다.

따라서 이 항목은 두 신규 리뷰의 정리보다 오히려 더 강하게 말할 수 있다.

> **plain pytest는 현재 실제 추출본에서 여전히 깨지며, 공식 진입점 계약을 더 이상 미뤄둘 수 없다.**

### 6.5 Release-smoke report hygiene

`ops/reports/release-smoke-report.json` 저장본의 `command` 필드는 다음과 같이 host-local 절대 경로를 포함한다.

- `'/mnt/c/Users/Administrator/Desktop/작업/LLM Wiki vNext/.venv/bin/python' ...`
- `'/mnt/c/Users/ADMINI~1/AppData/Local/Temp/.../unpacked/LLM Wiki vNext' ...`

기능상 오류는 아니지만, 공용 산출물 hygiene 관점에서는 개선하는 편이 좋다. 이 부분도 신규 리뷰들의 문제 제기가 타당하다.

---

## 7. 이번 대조 과정에서 새로 정리된 개선 포인트

### 7.1 raw registry 이슈는 “복구”보다 “재현 프로토콜 고정”이 먼저다

두 신규 리뷰의 권장안은 바로 migration으로 들어가지만, 실제 ZIP 추출본에서 preflight가 pass한 이상 선후가 바뀌어야 한다.

권장 순서:
1. failure를 재현한 정확한 입력 상태와 실행 경로를 다시 고정
2. live tree / extracted archive / release archive 각각에서 분리 재현
3. 그 뒤에만 migration 또는 alias 정책 결정
4. 재현 스크립트와 샘플 case를 test fixture로 남김

### 7.2 test-execution summary artifact는 실제로 유용하다

두 신규 리뷰가 제안한 `ops/reports/test-execution-summary.json`은 이번 재검토 같은 상황에서 특히 유용하다. 같은 smoke 또는 pytest 계열이 **어느 환경에서, 어떤 진입점으로, 어떤 fingerprint에서, 몇 초 걸렸는지**를 남기지 않으면 “리뷰 간 상충”을 해소하기 어렵다.

---

## 8. 테스트 절차 병목 분석 및 개선안

### 8.1 병목의 본질

두 신규 리뷰의 진단과 실제 파일 구조를 함께 보면 병목의 핵심은 **테스트 개수 자체**보다 **whole-vault 검증의 중복 실행 구조**다.

현재 병목을 만드는 축은 다음과 같다.

1. `raw_registry_preflight`
2. `wiki_lint`
3. `wiki_eval`
4. `wiki_stage2_eval`
5. `planning_gate_validate`
6. archive build / extract / manifest comparison
7. pytest 본체와 release smoke가 서로 비슷한 surface를 다시 검증할 가능성

즉, “662개 테스트라서 느리다”보다 **같은 전체 트리 성격의 검증이 다른 gate에서 반복된다**가 더 정확하다.

### 8.2 실제 파일이 보여주는 병목 징후

- stored release-smoke command 합계만도 `88,210 ms`
- Makefile은 xdist parallel pytest를 전제한다
- `pytest.ini`는 plain pytest에 우호적이지 않다
- full profile만 존재하고 fast profile이 없다
- stable KPI와 mtime-sensitive KPI가 문서상 충분히 분리되지 않으면, 불필요한 재생성과 재검증이 반복된다

### 8.3 권장 구조

#### A. Gate profile 4단 분리

| profile | 목적 | 권장 위치 |
|---|---|---|
| `dev-fast` | ruff + 핵심 schema/report/unit smoke | 로컬 / PR 기본 |
| `contract-check` | artifact freshness stable only + generated report contract + schema tests | PR required |
| `release-smoke-fast` | tiny fixture archive/build/extract/manifest smoke | PR required |
| `release-smoke-full` | 실제 vault 전체 smoke | nightly / release branch |

#### B. Fingerprint 기반 결과 재사용

- 동일 `source_tree_fingerprint`
- 동일 policy/schema fingerprint
- 동일 profile

이 세 조건이 같으면 이미 실행한 validator 결과를 `release-smoke-full`에서 재사용하게 만들어야 한다. 같은 전체 트리를 매번 처음부터 다시 훑는 구조는 오래 못 버틴다.

#### C. 진입점 계약 정리

권장안은 다음 둘 중 하나를 확정하는 것이다.

1. `python -m pytest`와 `make test*`만 공식 지원으로 문서화
2. `pytest.ini`에 `pythonpath = .`를 추가해 plain `pytest`도 지원

현재 실제 상태는 1번에 가깝지만, 문서와 실패 메시지가 그 현실을 충분히 설명하지 못한다.

---

## 9. 권장 실행 순서

### PR-0. 재현 프로토콜 고정
- v50 리뷰가 주장한 raw registry mismatch 46건을 **현재 어떤 상태에서 재현할 수 있는지** 먼저 확정
- live tree / extracted zip / release archive를 구분
- 재현되면 fixture와 regression test 추가
- 재현되지 않으면 해당 이슈를 현재 blocker 목록에서 내림

### PR-1. Artifact contract stable debt 다음 tranche
- 목표: `79/79/17` 축소
- 우선순위: `safe_to_backfill=true`, `mtime_sensitive=false`인 13건부터
- 결과물: machine-readable classification 또는 schema/backfill 완료

### PR-2. Learning evidence hardening
- `attempts_considered >= 10`
- `session_calibration_status != no_session_context`
- `telemetry_coverage_ratio > 0`
- proposal → run → outcome → readiness 연결을 하나의 ledger로 닫기

### PR-3. Pytest 진입점 계약 확정
- 공식 진입점을 문서/Makefile/CI에서 동일하게 가리키도록 정리
- plain pytest 미지원이면 명시
- 지원할 거면 `pythonpath = .` 추가 및 bounded smoke로 보증

### PR-4. Release-smoke tiering
- `release-smoke-fast`
- `release-smoke-full`
- partial/interruption unit profile
- stored/live rerun status 분리 노출

### PR-5. Report hygiene 및 review provenance
- host-local absolute path redaction
- external review self-include 정책 결정
- `test-execution-summary.json` 도입

---

## 10. 현재 상태 라벨 (보정판)

```text
snapshot_status             = progressed_but_not_release_ready
zip_integrity_status        = pass
artifact_contract_status    = improved_but_open_79_79_17
schema_status               = schema_invalid_zero_missing_schema_17
execution_status            = pass
learning_status             = learning_uncertain
session_evidence_status     = partial_available
loop_health_status          = available_but_telemetry_missing
raw_registry_status         = not_reproduced_on_current_extracted_zip
release_smoke_status        = stored_full_pass_present_live_full_rerun_unverified
pytest_entrypoint_status    = plain_pytest_broken_python_m_pytest_effectively_required
report_hygiene_status       = host_local_command_paths_present
review_packaging_status     = current_two_reviews_not_self_included
release_confidence          = not_release_ready
recommended_phase           = reproduction_protocol_fix -> contract_completion -> learning_hardening
```

---

## 11. 한 줄 요약

두 신규 리뷰는 현재 ZIP이 **기존 기준선보다 확실히 나아졌다는 점**에서는 맞지만, 가장 강하게 주장한 **raw registry live failure / make check failure / release-smoke live 불일치**는 이번 실제 ZIP 대조에서 재현되지 않았다. 따라서 현재 실제 체크포인트의 확정 과제는 **stable debt 79/79/17 해소, learning readiness 보강, pytest 진입점 계약 정리, test gate tiering**이며, raw registry 이슈는 **현재 blocker로 단정하기보다 재현 프로토콜부터 먼저 고정**하는 것이 맞다.
