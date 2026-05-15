# LLM Wiki vNext 통합 사후 리뷰 보고서

- **작성일**: 2026-04-26
- **작성 언어**: 한국어
- **검토 대상 아카이브 SHA-256**: `6f2c8f491b759bdc413455a020d770979deb0566bfc6d8444f72129ba709f0f6`
- **통합 기준 리뷰 파일**:
  - `llm_wiki_vnext_41_post_review_audit_report.md` (이하 **리뷰-A**)
  - `llm_wiki_vnext_post_review_work_report_20260426.md` (이하 **리뷰-B**)
  - `llm_wiki_vnext_post_review_reassessment_report.md` (이하 **리뷰-C**)
- **통합 목적**: 동일한 아카이브 체크포인트에 대해 독립적으로 수행된 세 편의 사후 리뷰를 교차 검증하고, 합의된 사실·진단·권고사항을 계층적으로 정리하여 누락 없는 단일 기준 문서를 제공한다.

> **중요한 전제**: 세 리뷰는 모두 동일한 ZIP 아카이브(SHA-256 일치)를 대상으로 작성되었으며, 리뷰 번호(41, 42, 날짜 기반)는 작성자/세션 식별자에 불과하고 상호 우열 관계가 없다. 이 보고서는 세 리뷰의 판정이 서로 충돌하는 경우 충돌 자체를 명시하고, 일치하는 경우 합의된 사실로 기술한다.

---

## 1. 최종 종합 결론

세 리뷰가 공통적으로 도달한 결론은 하나의 문장으로 집약된다.

> **현재 아카이브는 기존 리뷰(v39 계열 기준 `unified_current_audit_improvement_report.md`)가 지적한 운영 진단 표면을 실질적으로 개선하였으나, self-improving loop의 핵심 실행 경로(candidate 생성 → proposal 생성 → auto-improve 실행)는 여전히 모두 차단된 상태다.**

세 리뷰가 합의한 핵심 현황은 다음과 같다.

| 운영 지표 | 현재 값 | 합의된 판정 |
|---|---:|---|
| `mechanism-review / candidates_emitted` | 0 | 차단됨 |
| `mechanism-review / runs_skipped` | 5 | 차단 원인, 해소 필요 |
| `mutation-proposals / proposals_emitted` | 0 | 차단됨 |
| `mutation-proposals / blocked_proposals` | 0 | semantics 개선 필요 |
| `auto-improve-readiness / can_run` | false | 실행 불가 |
| `auto-improve-readiness / runnable_proposal_count` | 0 | 실행 불가 |
| `artifact-freshness / missing_artifact_envelope_count` | 130 | 잔존 부채 |
| `artifact-freshness / unknown_currentness_artifact_count` | 130 | 잔존 부채 |
| `artifact-freshness / missing_schema_count` | 39 | 잔존 부채 |
| `artifact-freshness / schema_invalid_artifact_count` | 12 | 잔존 부채 |

---

## 2. 검토 대상 아카이브 프로필

### 2.1 아카이브 식별

| 항목 | 값 |
|---|---:|
| 파일명 (리뷰별 표기 상이, 내용 동일) | `LLM Wiki vNext(41/42).zip` / `LLM Wiki vNext.zip` |
| 아카이브 SHA-256 | `6f2c8f491b759bdc413455a020d770979deb0566bfc6d8444f72129ba709f0f6` |
| 압축 전 전체 바이트 | 462,964,198 bytes |
| 압축 후 크기 | 273,066,366 bytes |
| ZIP entry 수 | 11,552 |
| 파일 수 | 10,595 |
| 디렉터리 수 | 957 |
| Python `zipfile.testzip()` | CRC 오류 없음 (리뷰-B 직접 확인) |

### 2.2 최상위 디렉터리 구성

| 최상위 디렉터리 | 파일 수 | 해석 |
|---|---:|---|
| `.venv` | 4,907–5,397 | Windows 가상환경 산출물, Linux 환경에서 실행 불가 |
| `.venv-py312` | 4,130–4,525 | Python 3.12 Windows 가상환경 산출물 |
| `raw` | 446–448 | PDF·web snapshot 원천 자료 |
| `wiki` | 417–418 | 공개 wiki corpus markdown |
| `ops` | 275–307 | 스크립트·스키마·정책·보고서 계약층 |
| `runs` | 156–174 | 과거 실행 산출물 |
| `tests` | 121–125 | 테스트 suite |
| `system` | 71–74 | 시스템 corpus |
| `external-reports` | 30–32 | 기존 리뷰·감사 보고서 |

> 리뷰-A와 리뷰-B/C 사이에 소수의 파일 수 차이가 나타나는 것은 집계 방식(ZIP 중앙 디렉터리 기반 vs 실제 해제 후 집계)의 차이로 보이며, SHA-256 동일성 기준으로 같은 아카이브로 판정한다.

### 2.3 확장자 분포 요약

| 확장자 | 파일 수 | 비고 |
|---|---:|---|
| `.py` | 3,373 | 대부분 가상환경 포함 Python source |
| `.pyc` | 3,040 | bytecode cache, 세 리뷰 모두 release 부적합 지적 |
| `.pyi` | 1,572 | type stub, 가상환경 내 포함 |
| `.md` | 943 | wiki·raw·system·report 문서 |
| `.pyd` | 464 | Windows binary extension |
| `.json` | 230 | 보고서·스키마·config |
| `.exe` | 133 | Windows executable |
| `.pdf` | 62 | raw source PDF |

---

## 3. 세 리뷰의 검증 범위 및 방법 비교

세 리뷰는 동일 아카이브를 서로 다른 깊이와 방법으로 검증했다. 각 리뷰의 검증 기여를 종합하면 다음과 같다.

| 검증 항목 | 리뷰-A | 리뷰-B | 리뷰-C |
|---|:---:|:---:|:---:|
| ZIP CRC 무결성 | ○ (중앙 디렉터리 기반) | ○ (Python `zipfile.testzip()`) | ○ (Python `zipfile` 해제) |
| UTF-8 환경 `unzip -q` 전체 해제 | △ | ○ | ○ |
| POSIX `LC_ALL=C LANG=C` `unzip -q` 해제 | 미완료 | ○ (실패 재현) | 미완료 (실패 간접 확인) |
| repo-owned JSON parse 검증 | ○ (중앙 디렉터리 기반) | ○ (214개 직접 parse) | ○ (214개) |
| repo-owned `py_compile` | ○ (직접 단일 파일) | ○ (276개) | ○ (276개) |
| `ruff check` 실행 | △ | 실패 (미설치) | ○ (직접 실행) |
| strict-preview `ruff` | ○ (test 통과 확인) | ○ (test 통과 확인) | ○ (직접 실행 통과) |
| `mypy` 실행 | △ | 실패 (미설치) | ○ (154 source files 통과) |
| strict-preview `mypy` | △ | 미확인 | ○ (10 source files 통과) |
| targeted pytest (개별) | △ | ○ (주요 test 통과) | ○ |
| `make release-smoke` 전체 완주 | 미완료 | 미완료 | 미완료 |
| `make check` / `make fast-smoke` 완주 | 미완료 | 미완료 | 미완료 |
| ops/reports JSON 직접 파싱 | ○ | ○ | ○ |
| public export 실제 실행 | △ | ○ (384개, leak 0) | △ |
| 비-ASCII 파일명 ZIP flag 분석 | △ | △ | ○ (340개, bit11 2개) |

> ○ = 완료·확인, △ = 부분·간접 확인, 미완료 = 세션 제약으로 미수행

---

## 4. 기존 리뷰 이후 완료 또는 진전된 작업 — 세 리뷰 합의 사항

### 4.1 P0-1: strict preview import order 수정 → **세 리뷰 모두 완료 판정**

기존 리뷰가 즉시 처리(P0) 항목으로 지적했던 `ops/scripts/structural_complexity_budget_runtime.py`의 import order I001(ruff strict preview)이 해소되었다. 현재 해당 파일의 import 순서는 다음과 같으며, 세 리뷰 모두 동일하게 확인했다.

```python
from collections import defaultdict
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any
```

- `dataclass`가 `JSONDecodeError`보다 앞에 배치되어 alphabetical import order를 만족한다.
- 리뷰-B·C는 `tests/test_ruff_strict_preview.py` 직접 실행 통과를 확인했고, 리뷰-C는 `python3 -m ruff check` 직접 실행도 통과했다.

**잔여 조치**: 전체 `ruff check --select I` 재확인을 통해 타 파일의 동류 문제가 없음을 지속 검증해야 한다.

---

### 4.2 mechanism review에 machine-readable candidate blocker 도입 → **세 리뷰 모두 진전 확인**

기존 리뷰가 요구한 "`candidates_emitted=0`일 때 machine-readable blocker 출력"이 구현되었다. 현재 `ops/reports/mechanism-review-candidates.json`에는 `diagnostics.candidate_blockers`가 존재하며, 리뷰-C는 14개의 blocker를 직접 집계했다.

현재 blocker 유형 분류:

| Blocker 유형 | 설명 |
|---|---|
| `threshold_not_triggered` | branch growth·high complexity·schema drift·policy complexity·eval stagnation 조건이 임계값 미충족 |
| `run_artifact_invalid` | legacy run artifact의 `$schema` 누락 또는 schema mismatch로 run이 skip됨 |
| `session_calibration` | session calibration 결과 no candidates |
| `outcome_metrics_evidence_gap` | outcome metrics evidence gap 또는 no candidates |

이 변화는 세 리뷰 모두 "기존에는 `candidates_emitted=0`으로 사람이 추론해야 했던 원인이 이제 machine-readable 형태로 제공된다"는 점에서 의미 있는 진전으로 평가했다. 다만 blocker가 생겼을 뿐 candidate는 아직 생성되지 않는다는 점에서 **"구조적 진전이지 운영 루프 복구는 아님"** 이라는 판정도 세 리뷰가 공통으로 내렸다.

---

### 4.3 artifact freshness report의 작업 큐 형태 진화 → **세 리뷰 모두 진전 확인, 리뷰-B·C는 완료 판정**

기존 리뷰의 P1 개선안이었던 작업 지향 필드들이 `ops/reports/artifact-freshness-report.json`에 추가되었다.

| 추가된 필드 | 내용 |
|---|---|
| `top_debt` | 우선 해소 대상 debt 항목 목록 |
| `owner_surface` | debt 소유 surface |
| `recommended_next_action` | 권장 다음 조치 (`regenerate_schema_invalid_artifacts`) |
| `safe_to_backfill` | 안전한 backfill 가능 여부 |
| `mtime_sensitive` | 파일시스템 mtime에 민감한 항목 여부 |
| `artifact_records` | 개별 artifact 레코드 |

- 리뷰-B는 `top_debt` 최상위 항목으로 `missing_artifact_envelope=130`, `unknown_currentness=130`, `missing_generated_at=60`을 직접 읽어 확인했다.
- 리뷰-A는 `top_debt` 필드의 full local 확인이 완전하지 않아 "부분 완료"로 보수적으로 판정했다.
- 이 보고서는 필드 존재 자체는 완료로, 해당 report가 보여주는 **debt 총량이 여전히 큰 상태**는 잔존 작업으로 분리한다.

---

### 4.4 mutation proposal empty-state 진단 보강 → **세 리뷰 모두 부분 완료 판정**

기존 리뷰의 "proposal queue가 조용히 빈 채로 끝나지 않게 하라"는 요구에 대응하여, 현재 `ops/reports/mutation-proposals.json`에 다음 진단 필드가 추가되었다.

| 추가된 진단 필드 |
|---|
| `queue_pressure_summary` |
| `evidence_gaps` |
| `empty_queue_blockers` |
| `family_session_calibration` |
| `queue_selection` |
| `recent_log_overlap` |

- 리뷰-B가 직접 확인한 `queue_pressure_summary` 값은: `"no proposals emitted | mechanism review emitted zero candidates | outcome_metrics_calibration.status=no_candidates | outcome_metrics: attempts_considered=7 is below min_attempts_considered=10"` 이다.
- 세 리뷰 모두, `proposals_emitted=0`과 `blocked_proposals=0`이 동시에 남아 있어 "empty/empty 종료 금지"라는 기존 수용 기준을 완전히 만족하지 못한다는 점을 공통으로 지적했다.

---

### 4.5 auto-improve readiness의 fallback seed 도입 → **세 리뷰 부분 완료 또는 진전 판정**

`ops/reports/auto-improve-readiness.json`에 fallback section이 추가되었다.

| Fallback 필드 | 현재 값 |
|---|---|
| `fallback.status` | `history_seeded` |
| `primary_targets` | `ops/scripts/auto_improve_iteration_persistence_runtime.py` |
| `seed_run_count` | 1 |
| `history_requirement` | 0 |

fallback family seed 자체는 잡혔지만, 최종 proposal queue가 비어 있어 `can_run=false`는 유지된다. 세 리뷰 모두 "fallback seed는 있으나 proposal queue는 여전히 비어 있음"이라는 결론을 공유한다.

---

### 4.6 OpenVEX schema debt 일부 해소 → **리뷰-B·C 확인, 리뷰-A 간접 확인**

기존 리뷰 기준 local schema validation 13개 실패 중 `ops/reports/openvex-draft.json` 1건이 해소되었다. 현재 `openvex-draft.json`에는 `artifact_context.artifact_set_id`, `artifact_context.security_advisories_ref`, `artifact_context.spdx_ref`, `metadata.advisory_count`, `metadata.artifact_set_id` 등 필수 필드가 추가되어 schema validation을 통과한다. 이로 인해 schema validation 실패 건수가 13건에서 12건으로 감소했다.

---

### 4.7 release smoke ZIP path budget 계약 추가 → **세 리뷰 부분 완료 판정**

`ops/scripts/release_smoke.py`에 다음 path budget 상수가 추가되었다.

| 상수 | 값 |
|---|---:|
| `ZIP_PATH_BYTE_LIMIT` | 65,535 |
| `ZIP_COMPONENT_BYTE_LIMIT` | 255 |
| `POSIX_ESCAPE_EXPANDED_FILENAME_BYTE_LIMIT` | 255 |

`tests/test_release_smoke.py`는 통과했다. 단, 이는 계약(contract)이 코드에 추가되었다는 의미이며, 실제 현재 아카이브가 해당 계약을 만족하는 상태는 아니다. POSIX C locale 해제 실패는 아직 미해결이다.

---

### 4.8 public export symlink safety 및 traversal hardening → **리뷰-B·C 완료 확인**

`ops/scripts/export_public_repo.py`의 `_is_safe_export_file()`이 symlink·non-file·vault 밖 resolved path를 제외하도록 강화되었다. 리뷰-B는 실제 `export_public_repo` 실행 결과를 직접 확인했으며, 384개 파일을 생성하고 `raw/`, `wiki/`, `system/`, `runs/`, `external-reports/` 계열의 leak가 0이었음을 확인했다.

---

### 4.9 정적 위생 전반 (ruff·mypy) → **리뷰-C에서 가장 완전한 확인**

리뷰-C는 다음 정적 검사를 모두 직접 실행하여 통과를 확인했다.

| 검사 | 결과 |
|---|---|
| `python3 -m ruff check ops/scripts tests tools` | 통과 |
| `python3 tools/ruff_strict_preview.py ...` | 통과 |
| `python3 -m mypy @ops/mypy-allowlist.txt` | 통과 (154 source files) |
| `python3 -m mypy --check-untyped-defs --disallow-untyped-defs --disallow-incomplete-defs @ops/mypy-strict-preview-allowlist.txt` | 통과 (10 source files) |

리뷰-B는 `ruff`·`mypy`가 미설치 환경에서 수행되어 이 검사를 완료하지 못했다. 리뷰-C의 결과가 가장 완전한 근거이므로, 현재 repo-owned 정적 위생은 통과 상태로 본다.

---

### 4.10 task-improvement-observations 기록 → **리뷰-B·C 확인**

`ops/reports/task-improvement-observations/task-20260426-unified-current-audit-reconciliation/improvement-observations.json`가 추가되어 있으며, supply-chain·public export·release manifest·artifact freshness scanning에서 로컬 virtualenv/cache path 문제로 release evidence path가 막히지 않도록 traversal exclusion helper를 공유해야 한다는 관찰이 `status=automated`로 기록되어 있다.

---

## 5. 아직 남아 있는 작업 — 세 리뷰 합의 잔여 항목

### 5.1 [P0] auto-improve queue를 실제 proposal 생성까지 복구

세 리뷰가 현재 가장 중요한 미완료 항목으로 동일하게 지적한 부분이다. 현재 병목 흐름을 세 리뷰가 공통으로 확인한 수치로 표현하면 다음과 같다.

```
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

세 리뷰 모두 "왜 비어 있는지 설명하는 능력은 개선되었지만, 실행 가능한 proposal을 생성하는 능력은 아직 없다"는 결론을 공유한다. 리뷰-C는 이를 "왜 안 되는지는 알지만 그 blocker를 아직 제거하지 못했다"고 표현했다.

**완료 기준 (세 리뷰 합산)**:

1. `candidates_emitted > 0`
2. `source_candidates_read > 0`
3. `proposals_emitted > 0` 또는 `blocked_proposals > 0`
4. `runnable_proposal_count > 0`
5. `execution_readiness.can_run == true` 또는 명시적 정책 사유로만 false

---

### 5.2 [P0] 과거 run artifact `$schema` backfill

세 리뷰 모두 동일한 5개 run이 `baseline-eval.json`의 `$schema` 누락으로 mechanism review에서 skip되고 있음을 확인했다.

| Skip된 Run | 원인 |
|---|---|
| `run-20260422-auto-improve-decision-record-fallback-retry3-linux-tmp` | `baseline-eval.json` `$schema` 누락 |
| `run-20260422-auto-improve-decision-record-fallback-retry2` | 동일 |
| `run-20260422-auto-improve-decision-record-fallback` | 동일 |
| `run-20260415-mechanism-planning-gate-second-clean` | 동일 |
| `run-20260414-mechanism-planning-gate` | 동일 |

또한 리뷰-B가 직접 확인한 결과, repo-owned JSON 214개 중 `$schema`가 없는 JSON이 49개이며, 그 중 상당수가 legacy run eval·lint·promotion artifact다.

**backfill 대상 파일 유형**:
- `runs/*/baseline-eval.json`
- `runs/*/candidate-eval.json`
- `runs/*/baseline-lint.json`
- `runs/*/candidate-lint.json`
- `runs/*/baseline-mechanism-assessment.json`
- `runs/*/candidate-mechanism-assessment.json`
- `runs/*/run-telemetry.json`

**완료 기준**: `runs_skipped=0` 목표, 최소한 `runs_considered`가 현재 2에서 7에 근접, schema invalid로 인한 skip 사유가 사라져야 함.

---

### 5.3 [P0] schema validation 실패 12건 정리

세 리뷰 모두 12건의 local schema validation 실패가 남아 있음을 확인했다. 리뷰-B가 직접 파싱하여 유형별로 정리한 내용은 다음과 같다.

| 유형 | 대상 파일 | 누락 필드 |
|---|---|---|
| mechanism assessment | 11개 `baseline/candidate-mechanism-assessment.json` | `complexity_profile.risk_flag_evidence`, `target_profiles`, `dimension_evidence` |
| run telemetry | 1개 `run-telemetry.json` | `command_timeouts.*` 하위 `launch_succeeded`, `signal_sent`, `final_state_observed`, `stdout_received`, `stderr_received` |

**완료 기준**: local `$schema` validation failure 0건.

---

### 5.4 [P0] generated artifact debt 대량 잔존

세 리뷰가 공통으로 확인한 `artifact-freshness-report.json`의 현재 주요 부채 수치는 다음과 같다.

| 부채 지표 | 현재 값 | 의미 |
|---|---:|---|
| `missing_artifact_envelope_count` | 130 | envelope 없는 artifact 다수 |
| `unknown_currentness_artifact_count` | 130 | 최신성 판단 불가 artifact |
| `missing_schema_count` | 39 | schema 미표기 artifact |
| `schema_invalid_artifact_count` | 12 | schema가 있어도 validation 실패 |
| `stale_artifact_count` | 55 | mtime 기준 오래된 artifact |
| `safe_to_backfill_artifact_count` | 85 | 안전하게 backfill 가능한 artifact |

리뷰-B는 추가로 mtime 민감도 문제를 실제 재현했다. 동일 runtime을 해제 후 다시 실행하면 `stale_artifact_count`가 55에서 85로 증가했다. 이는 archive 재해제 시 mtime이 변하면서 freshness 판단이 흔들리는 구조적 취약점이다. freshness 판단 로직을 `generated_at`/`input_fingerprints` 중심으로 재설계하거나, "archive rehydration mtime drift"를 별도 상태로 분리해야 한다.

리뷰-C는 추가로 `generated-artifact-index.json`의 상태가 `attention`임을 확인했으며, `archive_candidate_count=20`의 dated root-level artifact가 active namespace에 남아 있어 canonical/current와 archive/historical의 경계 정리가 필요함을 지적했다.

---

### 5.5 [P0] POSIX C locale ZIP 해제 실패 — 리뷰-B 직접 재현

리뷰-B가 실제로 `LC_ALL=C LANG=C unzip -q -d` 명령을 실행하여 `File name too long` 실패를 재현했다. 원인은 한글 파일명이 POSIX C locale에서 `#Uxxxx` 형태로 escape-expanded되면서 component byte 길이가 255를 초과하기 때문이다.

| 측정 항목 | 값 |
|---|---:|
| 최대 원본 component UTF-8 bytes | 173 |
| 최대 POSIX escape-expanded component bytes | 317 |
| escape-expanded component > 255인 파일명 수 | 6 |
| 최대 archive path UTF-8 bytes | 191 |
| 최대 escape-expanded archive path bytes | 335 |

상위 오류 파일은 모두 `raw/web-snapshots/` 아래 긴 한글 제목 파일이다.

리뷰-A가 지적한 ZIP 전체 규모 리스크와도 연결된다. 리뷰-A 기준으로 최대 path 길이는 335 UTF-8 bytes, 최대 component 길이는 317 UTF-8 bytes로, release gate의 path budget 계약(255 bytes)을 초과한다.

**완료 기준**: `LC_ALL=C LANG=C unzip -q -d <zip>` 성공, escape-expanded component 255 bytes 이하.

---

### 5.6 [P0] mutation proposal summary semantics 개선 필요

세 리뷰 모두 `proposals_emitted=0`과 `blocked_proposals=0`이 동시에 남아 있는 상태가 운영자에게 혼란을 준다는 점을 지적했다. 리뷰-A는 이를 가장 체계적으로 분석했다.

현재 문제: `empty_queue_blockers`는 존재하지만 `blocked_proposals=0`이라 "막힌 proposal이 없는 것인지, proposal 전 단계에서 막힌 것인지"가 summary만으로 불명확하다.

리뷰-A가 제안한 용어 분리:

| 제안 필드 | 의미 |
|---|---|
| `candidate_blocker_count` | candidate 생성 전 단계 문제 수 |
| `proposal_seed_blockers` | candidate를 proposal seed로 변환하는 단계 문제 |
| `proposal_blockers` | proposal object 생성 후 실행 불가가 된 문제 |
| `queue_blockers` | 최종 queue가 비는 모든 상위 원인 집계 |
| `fallback_seed_attempted` | fallback family seed 시도 여부 |
| `fallback_seed_result` | `seeded` / `no_candidate` / `policy_blocked` / `evidence_gap` |

---

### 5.7 [P1] release-smoke 전체 완주성 및 partial report 보장

세 리뷰 모두 `make release-smoke`의 전체 완주를 확인하지 못했다. 리뷰-B는 55초 제한 전에 종료되었고 report도 생성되지 않았음을 직접 확인했다. 리뷰-A와 리뷰-C도 동일한 한계를 인정했다.

핵심 문제: 장기 실행 중 timeout이나 인터럽트가 발생하면 부분 report조차 남지 않는다. 운영 관점에서 failure 사후 분석이 불가능하다.

**권장 대응** (세 리뷰 합산):
- `release-smoke --profile fast|full` 분리
- 각 phase 완료 후 partial report atomic write
- phase/last processed item/elapsed time/stdout tail/stderr tail을 중간 기록

---

### 5.8 [P1] session/outcome evidence 부족

세 리뷰 모두 `session_reports_considered=0`과 `attempts_considered=7`(< `min_attempts_considered=10`)이 auto-improve 차단의 또 다른 근본 원인임을 확인했다.

리뷰-C는 이를 "history가 적어서 못 돌리는 것"과 "history는 있는데 calibration 근거 형식이 약해서 못 돌리는 것"이 동시에 존재한다고 분석했다.

**권장 대응**:
- narrow mechanism run 3건 이상 추가
- session-level rollup artifact 생성 및 schema 표준화
- outcome metrics가 읽는 evidence path를 명확히 고정
- readiness gate에서 "history 부족"과 "artifact contract 부족"을 분리 표기

---

### 5.9 [P1] proposal lifecycle ledger 미완료 — 세 리뷰 공통 미완료

기존 리뷰가 요구한 `improvement_id` 기반 proposal lifecycle ledger는 세 리뷰 모두 미완료로 판정했다. 현재 `mutation-proposals.schema.json`에 `improvement_id`, `negative_memory_key`, `source_run_id`, `evidence_artifact_ids` 등 장기 lifecycle 필드가 아직 보이지 않는다(리뷰-C 직접 확인). proposal queue가 비어 있어 ledger 연결 자체를 테스트할 수 없는 상황이기도 하다.

---

## 6. 새로 식별된 개선 방안 — 리뷰 간 교차 분석으로 추가된 항목

### 6.1 비-ASCII 파일명 처리 전략 명시화 및 테스트 — 리뷰-C 신규 발견

리뷰-C만이 ZIP entry의 Unicode flag 구조를 직접 집계했다.

| 항목 | 수치 |
|---|---:|
| 비-ASCII 파일명 entry | 340개 |
| ZIP general purpose bit 11(UTF-8 flag) 사용 | 2개 |
| Unicode Path extra field (`0x7075`) 사용 | 340개 |

현재 아카이브는 대부분의 비-ASCII 파일명에서 **header bit 11보다 Info-ZIP Unicode Path extra field에 더 크게 의존**하고 있다. 이는 사양상 허용되지만, 도구별 해석 차이(Python `zipfile`, `Info-ZIP unzip`, `bsdtar`, `7z`)를 테스트하지 않으면 배포 후 환경에서 파일명 렌더링이 달라질 수 있다.

**권장 조치**:
- release gate에 `python zipfile`, `Info-ZIP unzip`, `bsdtar/7z` 매트릭스 추가
- 비-ASCII 파일명을 slug + short-hash로 패키징하고 원제목은 manifest/frontmatter에 보존
- ZIP 작성 시 "bit 11 only / upath only / dual compatibility" 중 정책화

---

### 6.2 raw/web-snapshots 파일명 정규화 — 세 리뷰 공통 권고

세 리뷰 모두 POSIX 해제 실패의 직접 원인이 `raw/web-snapshots/` 아래 긴 한글 제목 파일임을 확인했고, 파일명 정규화 정책을 권고했다. 세 리뷰의 권고를 종합하면:

**권장 파일명 패턴**:
```
raw/web-snapshots/<date>--<source-slug>--<title-slug-short>--<sha8>.md
```

**권장 frontmatter (메타데이터 보존)**:
```yaml
title_original: "..."
capture_url: "..."
captured_at: "..."
filename_policy: "slug-short-hash"
filename_slug: "..."
filename_hash: "..."
```

---

### 6.3 candidate-to-proposal bridge report 추가 — 리뷰-A 신규 제안

현재 mechanism review와 mutation proposal 사이에 중간 상태를 추적하는 독립 report가 없다. 리뷰-A가 제안한 구조:

**권장 파일명**: `ops/reports/candidate-proposal-bridge.json`

| 필드 | 설명 |
|---|---|
| `candidate_count` | mechanism review candidate 수 |
| `eligible_candidate_count` | proposal 전환 가능 candidate 수 |
| `ineligible_candidate_count` | 전환 불가 candidate 수 |
| `ineligibility_reasons` | 사유별 count |
| `proposal_seed_count` | proposal seed 생성 수 |
| `fallback_seed_count` | fallback seed 수 |
| `dedupe_drop_count` | 중복 제거 수 |
| `policy_block_count` | 정책상 block 수 |
| `bridge_status` | `ready` / `blocked` / `empty` / `evidence_gap` |

---

### 6.4 low-history candidate mode 도입 — 리뷰-B 신규 제안

현재 `attempts_considered=7`이 `min_attempts_considered=10`보다 낮아 outcome metrics calibration이 `no_candidates`로 이어지는 구조는 초기 bootstrap 구간에서 불필요하게 loop를 막는다. 리뷰-B가 제안한 low-history bootstrap mode:

```
history_mode: bootstrap
confidence: low
gate_effect: advisory | shadow
candidate_type: evidence_chain_backfill_bootstrap
runnable: false
next_evidence_needed: 3 comparable runs or 1 successful backfill run
```

이렇게 하면 실행은 막더라도 queue가 완전히 비지는 않는다.

---

### 6.5 legacy run artifact migrator 추가 — 리뷰-B 신규 제안

수동 backfill 대신 deterministic migrator를 만드는 방안이다. migrator의 필수 동작:

1. legacy eval·lint·mechanism·run-telemetry artifact 자동 발견
2. 원본 SHA-256과 migration time을 별도 `migration_context`에 기록
3. `$schema`, artifact envelope, `generated_at`, `currentness`, `input_fingerprints` 자동 채움
4. 확인 불가능한 값은 `legacy_unknown`과 `not_available`로 명확히 구분
5. migration 후 schema validation 수행
6. `runs_skipped`와 `schema_invalid_artifact_count` 감소를 acceptance metric으로 삼음

---

### 6.6 session rollup ingestion 우선순위 격상 — 리뷰-B 신규 제안

`session_reports_considered=0`은 outcome metrics 품질을 약화시킨다. 리뷰-B가 제안한 schema-backed session report 필드:

| 필드 | 설명 |
|---|---|
| `session_id` | 세션 식별자 |
| `run_id` | 연결된 run ID |
| `operator_decision` | 운영자 결정 |
| `verification_commands` | 검증 명령 목록 |
| `repair_loops` | 수리 루프 수 |
| `accepted_changes` | 승인된 변경 |
| `rejected_changes` | 거부된 변경 |
| `elapsed_seconds` | 소요 시간 |
| `failure_tail` | 실패 tail |
| `followup_observations` | 후속 관찰 |

---

### 6.7 `task-improvement-observations` 공통 artifact contract 편입 — 리뷰-C 신규 발견

리뷰-C가 확인한 결과, envelope 없는 ops report 35개 중 **23개가 `task-improvement-observations` 계열**이다. 이 계열이 공통 artifact contract(envelope/currentness)에 편입되지 않으면 freshness 일관성 저하, generated artifact debt 누적, machine-readable 재활용 약화로 이어진다.

**권장 조치**:
- `improvement-observations.json`도 canonical report envelope로 승격
- observation index/report 추가
- observation ↔ proposal ↔ run result 연결 ID 부여

---

### 6.8 supply-chain family 공통 envelope rollout — 리뷰-C 신규 발견

현재 envelope 없는 ops report 중 다음 supply-chain 계열이 포함된다.

- `cyclonedx-bom.json`
- `openvex-draft.json`
- `sbom-export-mapping.json`
- `sbom-readiness-gate-report.json`
- `supply-chain-gate-report.json`
- `supply-chain-provenance.json`

schema 강화가 일부 진행됐지만 공통 artifact contract 관점의 rollout은 완성되지 않았다.

---

### 6.9 vNext Review Delta Report 자동화 — 리뷰-A 신규 제안

리뷰-A가 제안한 `ops/reports/review-delta-report.json` 자동 생성 기능. 매 release마다 "기존 리뷰 이후 무엇이 완료되고 무엇이 남았는가"를 자동으로 산출한다.

| 필드 | 설명 |
|---|---|
| `baseline_review_id` | 기준 리뷰 artifact id |
| `current_archive_id` | 현재 ZIP/archive id |
| `accepted_recommendations` | 완료된 권고 |
| `partially_completed_recommendations` | 부분 완료 권고 |
| `open_recommendations` | 남은 권고 |
| `new_findings` | 새로 식별된 문제 |
| `regressions` | 악화된 항목 |
| `next_pr_queue` | 권장 PR 순서 |

---

### 6.10 Makefile `PYTHON` quoting 개선 — 리뷰-B 신규 발견

`make fast-smoke PYTHON="python3 -S"` 호출 시 Makefile에서 `"$(PYTHON)"`으로 실행되어 `/bin/sh: 1: python3 -S: Permission denied`가 발생했다. 권장 해결 방안:

- `PYTHON_BIN`과 `PYTHON_FLAGS` 분리
- `PYTHON_CMD`를 shell word로 다루되 quotes 제거
- CI에서 공식 wrapper script 문서화

---

### 6.11 release-smoke heartbeat 표준화 — 리뷰-A 제안

리뷰-A가 제안한 장기 실행 gate heartbeat 표준 필드:

| 필드 | 설명 |
|---|---|
| `phase` | 현재 단계 |
| `current_item` | 현재 처리 중인 파일 또는 test group |
| `items_done` | 완료 수 |
| `items_total` | 전체 수 |
| `elapsed_seconds` | 경과 시간 |
| `last_output_at` | 마지막 출력 시각 |
| `bytes_processed` | 처리된 byte 수 |
| `estimated_remaining_items` | 남은 item 수 |

---

## 7. 기존 리뷰 권고별 통합 최종 판정표

아래 표는 기존 리뷰(`unified_current_audit_improvement_report.md`)의 각 권고에 대해 세 리뷰의 판정을 교차 검증하여 최종 합의 판정을 도출한 것이다.

| 기존 권고 | 리뷰-A | 리뷰-B | 리뷰-C | **합의 판정** | 다음 조치 |
|---|:---:|:---:|:---:|:---:|---|
| strict preview I001 수정 | 완료 | 완료 | 완료 | **완료** | 전체 `ruff check --select I` 정기 재확인 |
| local schema validation error 13개 제거 | 부분 완료 | 부분 완료 | 부분 완료 | **부분 완료** | 잔여 12건 제거, 0건 목표 |
| 핵심 run artifact `$schema`/envelope backfill | 미완료 | 부분 완료 | 부분 완료 | **부분 완료** | 5개 skipped run backfill, 전체 `missing_schema` 39건 해소 |
| no-candidate blocker 기록 | 부분 완료 | 완료 | 완료 | **완료 (단, 운영 루프 미복구)** | blocker를 proposal seed로 연결하는 bridge 추가 |
| mutation proposal empty-state 제거 | 부분 완료 | 부분 완료 | 부분 완료 | **부분 완료** | `proposals_emitted=0`일 때 `blocked_proposals>0` 보장 |
| artifact freshness top debt/work queue | 부분 완료 | 완료 | 완료 | **완료 (debt 자체는 잔존)** | `top_debt[]` 활용하여 단계적 debt 해소 |
| canonical report truthfulness writer | 부분 완료 | 부분 완료 | 부분 완료 | **부분 완료** | `exists`, `size_bytes`, `sha256`, `schema_validation_status` 표준화 전체 확산 |
| ZIP portability gate | 미완료 | 부분 완료 | 부분 완료 | **부분 완료 (계약 추가, 실제 ZIP 미해결)** | filename canonicalization 및 POSIX escape budget gate |
| fast-smoke target | 부분 완료 | 부분 완료 (timeout) | 진전 확인 | **진전 확인, 완주 미검증** | fast/full 프로파일 분리, wall-clock 안정화 |
| long-running gate telemetry | 미완료 | 미완료 | 진전 확인 | **부분 완료** | heartbeat 표준 schema 도입, partial report 원자적 write |
| optional JSON diagnostics 전파 | 부분 완료 | 부분 완료 | 부분 확인 | **부분 완료** | missing/decode/type/read error 전파 표준화 |
| proposal lifecycle ledger | 미완료 | 미완료 (초기) | 미완료 | **미완료** | proposal 생성 후 `improvement_id` ledger 연결 |

---

## 8. 권장 PR 순서 — 세 리뷰 권고 통합

세 리뷰의 PR 순서 권고를 교차 분석하여 합의된 순서로 정리한다.

### PR-1: Run Artifact Schema Backfill (P0)

**목표**: mechanism review에서 skip되는 run을 0개로 줄이고 `runs_considered`를 7에 근접시킨다.

**작업 범위**:
- 5개 skipped run의 `baseline-eval.json`에 `$schema` 추가 및 artifact envelope backfill
- `runs/*/candidate-eval.json`, `baseline-lint.json`, `candidate-lint.json`, `run-telemetry.json`, `mechanism-assessment.json` 계열 backfill
- legacy migrator 스크립트 도입 (원본 SHA 기록, `legacy_unknown` 분리)
- mechanism review 재실행 후 `runs_skipped` 감소 확인

**완료 기준**:
- `$schema` 누락으로 skip되는 run 0개
- `schema_invalid_artifact_count` 감소
- `runs_considered >= 5`

---

### PR-2: Schema Validation 12건 정리 + Artifact Freshness `top_debt` 활용 (P0)

**목표**: local `$schema` validation failure 0건 달성 및 artifact debt 큐 활성화.

**작업 범위**:
- 11개 `baseline/candidate-mechanism-assessment.json` 누락 필드 추가
- 1개 `run-telemetry.json` `command_timeouts` 하위 필드 추가
- `top_debt[]`의 `path`·`owner_surface`·`debt_type`·`safe_to_backfill`·`recommended_action`·`expected_debt_reduction`을 활용한 debt 우선 해소
- `missing_artifact_envelope_count` 130건 단계적 감소 시작

**완료 기준**:
- local `$schema` validation failure 0건
- `missing_schema_count`와 `missing_artifact_envelope_count` 감소 추세 확인

---

### PR-3: Mutation Proposal Blocked Ledger + Candidate-to-Proposal Bridge (P0)

**목표**: proposal queue가 비어도 machine-readable 원인 계층을 제공하고, candidate→proposal 전환 경로를 추적 가능하게 한다.

**작업 범위**:
- `ops/reports/candidate-proposal-bridge.json` 신규 추가
- `mutation-proposals.json`에 `candidate_blocker_count`, `proposal_seed_blockers`, `empty_queue_blocker_count`, `fallback_seed_result` 필드 추가
- `proposals_emitted=0`일 때 `blocked_proposals>0` 또는 `proposal_blockers[]` 보장
- `mutation-proposals.schema.json` 및 `tests/test_mutation_proposal.py` 갱신

**완료 기준**:
- `proposals_emitted=0`이면 항상 `queue_blockers`가 summary에 노출
- candidate-to-proposal bridge report가 bridge_status를 제공

---

### PR-4: POSIX ZIP Portability Fix + Filename Canonicalization (P0)

**목표**: `LC_ALL=C LANG=C unzip -q -d` 성공, escape-expanded component 255 bytes 이하.

**작업 범위**:
- `raw/web-snapshots/` 아래 긴 한글 파일명 6건 이상을 `<date>--<source-slug>--<title-slug-short>--<sha8>.md` 패턴으로 정규화
- 원제목을 frontmatter/manifest에 보존
- release gate에 POSIX escape-expanded component budget 검사 추가
- ZIP 작성 시 Unicode flag 정책(bit 11 / upath / dual) 결정 및 문서화
- release gate에 `python zipfile`, `Info-ZIP unzip`, `bsdtar/7z` 매트릭스 추가

**완료 기준**:
- `LC_ALL=C LANG=C unzip -q -d <zip>` 성공
- escape-expanded component > 255 bytes인 파일명 0개

---

### PR-5: Release-Smoke Partial Report + Heartbeat (P1)

**목표**: timeout/인터럽트 시에도 partial report가 생성되고, 장기 실행 중 heartbeat가 출력된다.

**작업 범위**:
- `ops/scripts/release_smoke.py`에 partial report atomic write 추가
- `release-smoke --profile fast|full` 프로파일 분리
- 각 phase 완료 후 `phase`, `current_item`, `elapsed_seconds`, `timed_out`, `stdout_tail`, `stderr_tail` 기록
- heartbeat 필드 스키마 표준화

**완료 기준**:
- 강제 timeout fixture에서 partial report JSON 생성 확인
- `timed_out=true`, command tail, phase 기록 확인
- `make fast-smoke`가 목표 시간 내 완주

---

### PR-6: Auto-improve Readiness Acceptance 상향 + Session Evidence 보강 (P1)

**목표**: readiness 판단 기준을 proposal queue 중심으로 재정의하고, session/outcome evidence를 보강한다.

**작업 범위**:
- narrow mechanism run 3건 이상 추가로 `attempts_considered >= 10` 달성
- session-level rollup artifact 생성 및 `session_reports_considered > 0` 달성
- low-history candidate mode(bootstrap mode) 도입
- `selected_proposal_id`, `improvement_id` lifecycle ledger 연결
- `can_run=false`일 때 policy reason, evidence gap, empty queue, blocked proposal 분리 표기

**완료 기준**:
- `attempts_considered >= 10`
- `session_reports_considered > 0`
- runnable proposal이 있으면 `can_run=true` 판단이 일관됨

---

### PR-7: Archive Class Policy + Hygiene (P1)

**목표**: full/public/release/review archive class를 명시적으로 분리하고 가상환경·캐시를 정리한다.

**작업 범위**:
- release archive에서 `.venv/`, `.venv-py312/`, `.pyc`, `.exe`, `.pyd` 제외 정책화
- 루트 0-byte placeholder 2개 제거
- 빈 디렉터리 정리
- `generated-artifact-index.json`의 `archive_candidate_count=20` 정리 (canonical/historical 분리)

**완료 기준**:
- public export leak 0건 유지
- release archive에 `.venv*`, `.pyc`, cache 포함 없음
- `archive_candidate_count` 정리 완료

---

### PR-8: `task-improvement-observations` + Supply-chain Artifact Envelope (P2)

**목표**: 공통 artifact contract에 편입되지 않은 23개 `task-improvement-observations`와 supply-chain 계열 artifact를 envelope/currentness 체계로 통합한다.

**작업 범위**:
- `improvement-observations.json` canonical report envelope 승격
- observation index/report 추가, observation↔proposal↔run result 연결 ID 부여
- supply-chain family 공통 writer 도입 (cyclonedx-bom, openvex-draft, sbom 계열)

---

## 9. 통합 Acceptance Criteria

아래 기준은 세 리뷰의 수용 기준(AC)을 교차 분석하여 중복 제거 후 우선순위 순으로 정렬한 것이다.

| ID | 수용 기준 | 출처 |
|---|---|---|
| **AC-01** | `LC_ALL=C LANG=C unzip -q -d <zip>` 해제가 성공한다. | 리뷰-A·B·C |
| **AC-02** | escape-expanded filename component가 255 bytes를 넘지 않는다. | 리뷰-A·B·C |
| **AC-03** | `structural_complexity_budget_runtime.py` import order는 ruff strict-preview allowlist 없이 통과한다. | 리뷰-A·B·C |
| **AC-04** | repo-owned JSON parse error가 0이다. | 리뷰-A·B·C |
| **AC-05** | local `$schema` validation failure가 0이다. | 리뷰-A·B·C |
| **AC-06** | `$schema` 누락으로 skipped되는 run artifact가 0개이다. | 리뷰-A·B·C |
| **AC-07** | `runs_considered`가 현재 2에서 증가하여 5 이상이 된다. | 리뷰-A·B·C |
| **AC-08** | candidate가 0이면 `candidate_blockers[]`가 항상 존재한다. | 리뷰-A·B (완료 판정) |
| **AC-09** | proposal이 0이면 `blocked_proposals>0` 또는 `proposal_blockers[]`가 항상 존재한다. | 리뷰-A·B·C |
| **AC-10** | `candidates_emitted > 0`이 auto-improve 복구의 1차 기준이다. | 리뷰-A·B·C |
| **AC-11** | `proposals_emitted > 0`이 mutation proposal 복구의 2차 기준이다. | 리뷰-A·B·C |
| **AC-12** | `runnable_proposal_count > 0`이 readiness 복구의 3차 기준이다. | 리뷰-A·B·C |
| **AC-13** | `can_run=false`일 때 policy reason, evidence gap, empty queue, blocked proposal이 분리되어 표시된다. | 리뷰-A·B·C |
| **AC-14** | `empty_queue_blockers`와 `blocked_proposals`는 서로 다른 개념으로 schema에 명확히 분리된다. | 리뷰-A·B·C |
| **AC-15** | `artifact-freshness-report`가 `top_debt[]`를 제공하며, 각 debt item은 `path`, `owner_surface`, `debt_type`, `safe_to_backfill`, `recommended_action`, `expected_debt_reduction`을 포함한다. | 리뷰-A |
| **AC-16** | `missing_artifact_envelope_count`, `missing_schema_count`, `schema_invalid_artifact_count`가 release마다 감소 추세를 보인다. | 리뷰-A·B·C |
| **AC-17** | mtime-sensitive freshness와 fingerprint-based currentness가 분리된다. | 리뷰-A·B |
| **AC-18** | canonical report writer는 `exists`, `size_bytes`, `sha256`, `schema_validation_status`를 기록한다. | 리뷰-A·B |
| **AC-19** | release-smoke가 timeout되어도 partial report를 남긴다. | 리뷰-A·B·C |
| **AC-20** | `make fast-smoke`가 일반 Linux 환경에서 30~120초 내 완주한다. | 리뷰-A·B |
| **AC-21** | static gate는 의존성 누락 시 actionable bootstrap 안내를 제공한다. | 리뷰-B |
| **AC-22** | report 생성물은 파일 존재·크기·SHA-256을 evidence manifest에 자동 기록한다. | 리뷰-B |
| **AC-23** | `session_reports_considered`가 0인 상태는 readiness blocker 또는 warning으로 유지된다. | 리뷰-B·C |
| **AC-24** | proposal lifecycle ledger는 `improvement_id`, `source_run_id`, `evidence_artifact_ids`, `decision`, `outcome`을 연결한다. | 리뷰-A·B |
| **AC-25** | 비-ASCII 파일명 처리 방식(bit 11 / upath / dual)이 정책화되고 release gate에 `python zipfile`, `unzip`, `bsdtar/7z` 매트릭스가 추가된다. | 리뷰-C |
| **AC-26** | `task-improvement-observations` 계열이 공통 artifact envelope/currentness 체계에 편입된다. | 리뷰-C |
| **AC-27** | 루트 0-byte placeholder 2개가 제거된다. | 리뷰-B |
| **AC-28** | 후속 review report는 "검증 완료", "기존 report 근거", "추론", "미검증"을 구분하는 섹션을 포함한다. | 리뷰-B |

---

## 10. 세 리뷰 간 판정 차이 기록

이하는 세 리뷰 간에 판정이 일치하지 않는 항목을 명시한다. 합의 판정에서 채택된 기준도 함께 기술한다.

### 10.1 artifact freshness `top_debt` 필드 확인 여부

| 리뷰 | 판정 |
|---|---|
| 리뷰-A | `top_debt` 필드 full local 확인 불가 → "부분 완료" |
| 리뷰-B·C | `top_debt` 최상위 항목까지 직접 확인 → "완료 (P1-1)" |

**합의**: 필드 자체의 존재와 활용 가능성은 완료로 보되, 해당 report가 보여주는 **debt 총량이 아직 큰 상태**는 별도 잔여 작업으로 분리한다. 이는 리뷰-A의 엄격한 판정과 리뷰-B·C의 완료 판정을 절충한 것이다.

### 10.2 no-candidate blocker 기록 완료 여부

| 리뷰 | 판정 |
|---|---|
| 리뷰-A | "구조적으로 완료에 가까운 부분 완료" |
| 리뷰-B·C | "완료" |

**합의**: `candidate_blockers` 필드의 도입 자체는 완료로 본다. 단, 이것이 운영 루프 복구(candidate 생성)와는 분리된 진단 표면 개선임을 명시한다.

### 10.3 ruff·mypy 직접 실행 결과

| 리뷰 | 판정 |
|---|---|
| 리뷰-A | 간접 확인 수준 |
| 리뷰-B | 도구 미설치로 실행 불가 |
| 리뷰-C | 직접 실행 통과 (가장 강한 근거) |

**합의**: 리뷰-C의 직접 실행 결과를 채택한다. 현재 repo-owned 정적 위생(ruff·mypy)은 통과 상태이다.

---

## 11. 검증 한계 공통 선언

세 리뷰가 공통으로 완료 주장을 보류한 항목은 다음과 같다. 이 보고서도 동일하게 미완료로 선언한다.

- `make release-smoke` 전체 성공 판정
- 전체 `pytest` suite 완주
- `make check` / `make check-all` / `make release-check` 완주
- 모든 schema-backed artifact의 full live regeneration
- POSIX locale 전체 unzip 매트릭스 완주

이 한계에도 불구하고, 세 리뷰의 핵심 결론은 충분히 신뢰 가능하다. 세 리뷰 모두 실제 ZIP을 해제하고 `ops/reports` JSON을 직접 파싱했으며, 기존 리뷰와의 대조는 byte-identical SHA-256 일치를 확인한 동일 파일 기준으로 수행했다.

---

## 12. 최종 종합 판단

세 편의 독립 리뷰가 동일한 체크포인트를 서로 다른 깊이와 도구로 검토한 결과, 판정의 방향성은 세 리뷰 간에 고도로 일치했다. 이는 현재 아카이브의 상태에 대한 신뢰도를 높이는 동시에, 잔여 작업의 우선순위가 일관되게 수렴됨을 보여준다.

현재 아카이브는 기존 리뷰(v39 계열)에서 지적한 운영 진단 표면을 실질적으로 개선했다. strict import order가 수정되었고, candidate blocker와 empty queue blocker를 machine-readable 형태로 기록할 수 있게 되었다. artifact freshness report는 단순 숫자 집계에서 작업 큐 형태로 진화했으며, public export는 실제 실행에서 corpus leak 없이 동작한다.

그러나 self-improving loop의 핵심 목표는 아직 달성되지 않았다. 현재 시스템은 "왜 proposal이 없는지"를 더 잘 설명하지만, 여전히 proposal 자체를 만들어내지는 못한다. 병목의 근본에는 과거 run artifact의 schema contract 미충족이 있으며, 이로 인해 mechanism review → candidate 생성 → proposal 생성 → auto-improve 실행으로 이어지는 전체 경로가 차단된 상태다.

다음 작업의 핵심은 대규모 신기능 개발이 아니다. **과거 run artifact schema/envelope backfill → schema validation 12건 해소 → candidate-to-proposal bridge → fallback seed의 실질 proposal 전환 → session/outcome evidence 보강**의 순서로 진행하는 것이 세 리뷰가 공통으로 권고하는 최단 복구 경로다. POSIX filename canonicalization과 archive hygiene 분리는 그 이후에 병행하거나 별도 PR로 진행한다.

한 줄로 요약하면 다음과 같다.

> **현재 아카이브는 진단 표면에서 분명히 성장했지만, auto-improve loop를 재가동하기 위해 필요한 근본 조건—historical run contract 정리, session/outcome evidence 보강, proposal 생성 경로 복구—은 아직 완료되지 않았다.**

---

*이 보고서는 `llm_wiki_vnext_41_post_review_audit_report.md`, `llm_wiki_vnext_post_review_work_report_20260426.md`, `llm_wiki_vnext_post_review_reassessment_report.md` 세 편의 독립 사후 리뷰를 누락 없이 교차 검증하여 작성되었다. 각 리뷰의 원본 판정이 합의 판정과 다른 경우 섹션 10에 명시하였다.*
