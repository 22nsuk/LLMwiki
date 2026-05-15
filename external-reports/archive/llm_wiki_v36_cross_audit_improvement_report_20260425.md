# LLM Wiki vNext v36 교차 검토 및 개선 보고서

- 파일명: `llm_wiki_v36_cross_audit_improvement_report_20260425.md`
- 작성일: 2026-04-25
- 작성 언어: 한국어
- 검토 대상: `LLM Wiki vNext.zip`
- 새로 검토한 리뷰: `llm_wiki_v36_integrated_review_report_20260425.md`
- 대조한 기존 리뷰/보고서:
  - `llm_wiki_vnext_audit_improvement_report_20260425.md`
  - `llm_wiki_vnext_review_improvement_plan_revised_20260425.md`
- 대조 방식: 실제 ZIP 해시·CRC·해제 결과 확인, 저장소 계약 문서 확인, Python/JSON 정적 검증, 주요 runtime 소스 직접 확인, 기존 generated report 내용 재계산, 새 통합 리뷰의 모든 항목을 수용/수정/미재현으로 재분류
- 중요한 한계: 현재 대화형 실행 환경에서는 외부 Python subprocess가 시작 단계에서 반복 지연되어 `make`, 외부 `pytest`, `ruff`, `mypy`, CLI `--help` 전체 벤치마크 완주를 새로 주장하지 않는다. 대신 현재 프로세스 내부 정적 검증, `jsonschema` 검증, 시스템 `unzip`, 기존 report artifact, 일부 pytest 직접 호출 결과를 근거로 분리 기재한다.

---

## 1. 최종 결론

새 통합 리뷰의 핵심 판단은 대체로 타당하다. 실제 업로드 ZIP은 새 통합 리뷰가 지칭한 v36 식별자와 정확히 일치하며, generated artifact 정합성 부채, self-improvement bootstrap 차단, strict preview import 정렬 오류, fast feedback 계층의 무게, optional JSON diagnostic 전파 미완, runtime surface 비대화, output path policy 불명확성, policy exact enumeration drift, root 0-byte placeholder 문제는 실제 파일에서도 확인된다.

다만 **ZIP 패키징 호환성** 항목은 이번 환경에서 새 통합 리뷰처럼 실패로 재현되지 않았다. `unzip -tqq`와 실제 `unzip -q -d` 해제 모두 성공했고, path component의 최대 UTF-8 byte 길이도 173 bytes로 확인되어 200~220 byte 예산을 넘는 파일은 없었다. 따라서 이 항목은 “현재 ZIP의 보편 실패”가 아니라 **다른 unzip 구현 또는 환경에서 재발 가능한 배포 호환성 회귀 리스크**로 재분류하는 것이 더 정확하다.

현재 v36에서 가장 먼저 고쳐야 할 항목은 다음 다섯 가지다.

1. **Generated artifact evidence chain 복구**: `artifact-freshness-report.json` 기준 142개 JSON artifact 중 135개가 envelope 부재 및 unknown currentness 상태다.
2. **Self-improvement bootstrap 차단 해소**: `mechanism-review-candidates.json`에서 7개 run을 발견했지만 7개 모두 `$schema` 누락 등 run artifact invalid로 skip되어 `runs_considered=0`이다.
3. **Strict preview I001 수정**: `ops/scripts/structural_complexity_budget_runtime.py` 3~4행 import 순서가 명백히 위반 상태다.
4. **산출물 진실성 gate의 전면 적용**: helper와 canonical envelope는 존재하지만 모든 report-producing surface에 일관 적용되지 않는다.
5. **Run/report schema validation debt 정리**: 직접 `jsonschema` 검증 결과, local schema를 가진 비-schema JSON 중 19개가 현재 schema validation error를 냈다.

대규모 리라이트보다 작은 PR을 순차 적용해야 한다. 권장 순서는 `Strict preview fix → run artifact schema/envelope backfill → artifact freshness top debt 및 canonical envelope hard fail → comparable finalized run 1건 확보 → fast-smoke/ZIP portability/cold-start 관찰성 보강`이다.

---

## 2. Evidence Manifest

### 2.1 직접 확인한 입력 파일

| 파일 | 크기 | SHA-256 | 판정 |
|---|---:|---|---|
| `LLM Wiki vNext.zip` | 190,999,399 bytes | `f18f7ac4eb32c2952ce8e668cd70ad9150572b3dc24320d6362d2b2cb86ea33c` | 새 통합 리뷰의 v36 식별자와 일치 |
| `llm_wiki_v36_integrated_review_report_20260425.md` | 45,184 bytes | `ae9a21b2167036e9fe084b9053a33c729711801b7d97a7435a79460a2022417d` | 이번 추가 리뷰 |
| `llm_wiki_vnext_audit_improvement_report_20260425.md` | 29,945 bytes | `ada45d29dcc4f6f37bd1dceeee14c5fce42db4fb047629a77fd67b31e6edb64a` | 기존 실제 파일 대조 보고서 |
| `llm_wiki_vnext_review_improvement_plan_revised_20260425.md` | 30,034 bytes | `933c3c8aa5ded3793a9d9487702af7ee3b9d0feb7a21880d839a32b2ea6e3e5a` | 기존 추가 리뷰 반영판 |

### 2.2 실제 ZIP/저장소 재검증

| 검증 항목 | 이번 재검증 결과 | 판정 |
|---|---:|---|
| ZIP 크기 | 190,999,399 bytes | 새 통합 리뷰와 일치 |
| ZIP SHA-256 | `f18f7ac4...86ea33c` | 새 통합 리뷰와 일치 |
| ZIP 엔트리 수 | 1,626 | 새 통합 리뷰와 일치 |
| ZIP CRC 검사 | 오류 없음 | 통과 |
| Python `zipfile` 전체 해제 | 파일 1,555개, 디렉터리 71개 | 통과 |
| 시스템 `unzip -tqq` | exit 0 | 통과 |
| 시스템 `unzip -q -d` 실제 해제 | 파일 1,555개, 디렉터리 71개 | 통과 |
| Python 파일 수 | 276개 | 새 통합 리뷰와 일치 |
| Python LOC | 72,510 lines | 리뷰별 측정 방식 차이는 있으나 규모 일치 |
| Python `py_compile` | 오류 0개 | 통과 |
| JSON 파일 수 | 213개 | 새 통합 리뷰와 일치 |
| JSON parse | 오류 0개 | 통과 |
| `ops.scripts` 모듈 import | 153개 import, 실패 0개 | 통과 |
| `artifact_freshness_runtime` cold import | 16.10초 | cold-start debt 재확인 |
| `tests/test_artifact_io_runtime.py` | 6 passed, 약 41.5초 | 선택 테스트 통과이나 실행 오버헤드 큼 |

### 2.3 주요 surface 분포

| surface | 파일 수 | 총 크기 |
|---|---:|---:|
| `raw/` | 446 | 222,014,694 bytes |
| `wiki/` | 417 | 2,092,204 bytes |
| `ops/` | 274 | 3,272,758 bytes |
| `runs/` | 156 | 8,437,703 bytes |
| `tests/` | 121 | 1,362,043 bytes |
| `system/` | 71 | 891,473 bytes |
| `external-reports/` | 28 | 1,031,734 bytes |

### 2.4 파일 확장자 분포

| 확장자 | 파일 수 | 총 크기 |
|---|---:|---:|
| `.md` | 937 | 9,819,006 bytes |
| `.py` | 276 | 2,758,261 bytes |
| `.json` | 213 | 9,673,929 bytes |
| `.pdf` | 62 | 216,311,785 bytes |
| `.txt` | 28 | 502,635 bytes |
| `.yaml` | 13 | 75,937 bytes |
| `.toml` | 10 | 24,482 bytes |

---

## 3. 새 통합 리뷰의 항목별 대조 판정

아래 표는 새 통합 리뷰의 모든 핵심 발견을 기존 보고서와 실제 파일에 대조한 결과다.

| 새 통합 리뷰 항목 | 실제 파일 대조 | 기존 보고서 대조 | 이번 보고서 판정 |
|---|---|---|---|
| 검토 대상 동일성(v36 SHA/size/entry count) | 실제 ZIP과 일치 | 기존 보고서도 현재 ZIP을 v36으로 재확인 | **수용** |
| 저장소는 운영형 self-improving system | AGENTS/README/ops/runs/wiki 구조로 확인 | 기존 보고서와 동일 | **수용** |
| 이전 P0 일부 해결: `release_smoke.py` timeout | `run_with_timeout()` 호출 3회, `subprocess.run()` 0회 | 기존 보고서와 동일 | **수용** |
| 이전 P0 일부 해결: direct datetime 제거 | `source_slug_curation.py`에 `datetime.now`/`utcnow` 직접 호출 없음, `RuntimeContext` 주입 경로 있음 | 기존 보고서와 동일 | **수용** |
| Optional JSON diagnostic 함수 존재 | `load_optional_json_object_with_diagnostics()` 존재, wrapper는 `_diagnostics` 버림 | 기존 보고서와 동일 | **부분 수용: 구현은 있음, 전파 미완** |
| Generated artifact envelope/currentness 부채 | freshness summary에서 142개 중 135개 envelope missing/unknown currentness | 기존 보고서와 동일 | **수용, P0 유지** |
| Self-improvement bootstrap 차단 | `can_run=false`, `runs_considered=0`, `runs_skipped=7`, runnable proposal 0 | 기존 보고서와 동일 | **수용, P0 유지** |
| Strict preview I001 import 정렬 오류 | `structural_complexity_budget_runtime.py` 3행 `json`, 4행 `collections` | 기존 보고서와 동일 | **수용, P0 유지** |
| ZIP 패키징 호환성 실패 | 이번 환경에서 시스템 `unzip` 테스트/실제 해제 모두 통과 | 기존 보고서는 외부 Python subprocess 한계로 주장 보류 | **수정: 현재 실패가 아니라 portability regression risk** |
| Fast feedback tier 무거움 | full make/pytest 완주 불가, 선택 pytest도 6개 테스트에 41.5초 | 기존 보고서와 동일 | **수용, P1 유지** |
| CLI cold-start 예산 | `ops.scripts` import 중 `artifact_freshness_runtime` 16.10초 | 기존 보고서와 동일 | **수용, P1 유지** |
| Self-improvement ledger/ROI 필요 | report 구조에 closed-loop `improvement_id` 연결 부족 | 기존 보고서와 동일 | **수용, P1 유지** |
| Long-running gate progress/timeout telemetry | 실행 한계와 선택 테스트 오버헤드로 운영성 이슈 확인 | 기존 보고서와 방향 동일 | **수용, P1 유지** |
| Runtime surface 비대 | `auto_improve_readiness_runtime.py` 1,257 nonempty LOC, branch 151 등 확인 | 기존 보고서와 동일 | **수용, P2 유지** |
| Output path policy 명시화 | `resolve_repo_output_path` 사용 파일 33개, `resolve_output_path` 사용 파일 6개 | 기존 보고서와 동일 | **수용, P2 유지** |
| Policy exact enumeration drift | 정책 YAML 1,667행, path candidate 35개 확인 | 기존 보고서와 동일 | **수용, P2 유지** |
| Root 0-byte placeholder | root source placeholder 2개 확인 | 새 통합 리뷰의 단독 발견, 실제 확인 | **수용, P2/P3 유지** |
| Public/private boundary risk | full vault surface가 ZIP에 포함됨 | 기존 보고서와 동일 | **수용, public export post-check 강화 필요** |
| `review/` 빈 디렉터리 목적 불명확 | ZIP entry로 디렉터리는 있으나 파일 0개 | 기존 보고서에서 낮은 우선순위 | **수용, P3 hygiene** |

---

## 4. 실제 파일 기준 추가 발견

새 통합 리뷰에는 없거나 약하게 언급된 항목 중, 이번 직접 검증에서 운영상 의미가 있는 항목은 다음과 같다.

### 4.1 Local schema validation error 19개

전체 JSON 213개는 parse 오류 없이 읽힌다. 그러나 local `$schema`를 가진 비-schema JSON을 `jsonschema`로 검증하면 86개는 통과하고 19개는 실패한다. 핵심 실패 유형은 다음과 같다.

| 실패 유형 | 대표 경로 | 의미 |
|---|---|---|
| `artifact_context` required 누락 | `ops/reports/openvex-draft.json` | supply-chain report schema와 artifact 사이 drift |
| `risk_flag_evidence` required 누락 | 여러 `baseline-mechanism-assessment.json`, `candidate-mechanism-assessment.json` | mechanism assessment schema evolution backfill 미완 |
| `launch_succeeded` required 누락 | 여러 `run-telemetry.json` | run telemetry schema evolution backfill 미완 |
| `$schema` 자체 누락 | 여러 `baseline-eval.json`, `candidate-eval.json`, lint JSON | mechanism review skip의 직접 원인 |

이 항목은 generated artifact debt와 self-improvement bootstrap 차단을 연결하는 구체 증거다. 단순히 “envelope가 없다”가 아니라, 현재 schema가 요구하는 필드를 충족하지 못하는 legacy run artifact가 self-improvement loop를 막고 있다.

### 4.2 ZIP 호환성 항목의 재분류 근거

이번 환경에서 확인된 사실은 다음과 같다.

| 검사 | 결과 |
|---|---|
| `unzip -tqq LLM Wiki vNext.zip` | exit 0 |
| `unzip -q LLM Wiki vNext.zip -d <dir>` | exit 0, 파일 1,555개 복원 |
| path component 최대 UTF-8 byte | 173 bytes |
| 200 bytes 초과 component | 0개 |
| 240 bytes 초과 component | 0개 |
| 255 bytes 초과 component | 0개 |

따라서 새 통합 리뷰의 “Info-ZIP 실패” 주장은 현재 환경에서는 재현되지 않는다. 다만 release archive는 사용자의 OS, unzip 구현, locale, normalization 방식에 따라 다르게 동작할 수 있으므로 **portable extract smoke**는 여전히 필요하다. 우선순위는 P0 current defect가 아니라 P1 release portability regression gate가 적절하다.

### 4.3 선택 pytest의 오버헤드

`pytest.main(['-q', 'tests/test_artifact_io_runtime.py'])`는 6개 테스트 모두 통과했지만 약 41.5초가 걸렸다. 테스트 자체가 무겁다기보다 현재 실행 환경의 pytest startup/import 오버헤드가 큰 것으로 보인다. 이는 새 통합 리뷰의 fast feedback 계층 문제와 같은 방향의 증거다.

---

## 5. 세부 진단

### 5.1 P0 — Generated artifact evidence chain 부채

`ops/reports/artifact-freshness-report.json`의 summary는 다음 상태를 보고한다.

| 항목 | 값 |
|---|---:|
| artifact_count | 142 |
| json_artifact_count | 142 |
| scanned_text_artifact_count | 165 |
| stale_artifact_count | 50 |
| unknown_currentness_artifact_count | 135 |
| missing_schema_count | 47 |
| missing_artifact_envelope_count | 135 |

surface별 부채는 아래와 같다.

| surface | artifact record | missing envelope | missing schema | missing generated_at |
|---|---:|---:|---:|---:|
| `runs/` | 103 | 103 | 43 | 35 |
| `ops/` | 39 | 32 | 4 | 22 |

issue 유형별 카운트는 다음과 같다.

| issue | count |
|---|---:|
| `missing_artifact_envelope` | 135 |
| `unknown_currentness` | 135 |
| `missing_generated_at` | 57 |
| `generated_at_older_than_file_mtime` | 50 |
| `missing_schema` | 47 |

**판단:** 이 문제는 여전히 P0다. self-improvement runtime이 generated artifact를 다시 입력으로 읽는 구조이므로, stale/unknown artifact가 proposal priority와 bootstrap 판단을 오염시킬 수 있다.

**권장 수정:**

1. 신규 canonical report의 envelope missing을 hard fail로 유지/강화한다.
2. legacy artifact는 즉시 실패시키지 말고 `legacy_report` role로 분류한다.
3. `runs/` 산하 core run JSON부터 `$schema`, `artifact_kind`, `generated_at`, `currentness`, `input_fingerprints`를 backfill한다.
4. artifact freshness report에 top debt list가 없으므로 `top_debt`, `owner_surface`, `recommended_next_action`을 추가한다.
5. freshness report가 “부채 총량”뿐 아니라 “다음 10개 파일”을 안정적으로 출력하게 한다.

---

### 5.2 P0 — Self-improvement bootstrap 차단

확인된 현재 상태는 다음과 같다.

| report | 핵심 신호 |
|---|---|
| `auto-improve-readiness.json` | `execution_readiness.can_run=false`, runnable proposal 0, blocked proposal 1 |
| `mechanism-review-candidates.json` | `runs_discovered=7`, `runs_considered=0`, `runs_skipped=7`, `candidates_emitted=0` |
| `mutation-proposals.json` | `proposals_emitted=1`, `blocked_proposals=1`, source candidates 0 |
| `outcome-metrics.json` | attempts 7, rework 5, defect escape proxy 3, session reports 0 |

`mechanism-review-candidates.json`의 skipped run detail은 모두 `baseline-eval.json`의 `$schema` required property 누락을 가리킨다. 즉, self-improvement loop는 알고리즘 문제보다 **schema-valid comparable history가 없어서 닫히지 않는 문제**다.

**권장 수정:**

1. 7개 run 전체를 한 번에 migration하지 말고, 가장 최근 또는 가장 단순한 finalized run 1건을 선택한다.
2. 해당 run의 `baseline-eval.json`, `candidate-eval.json`, `baseline-lint.json`, `candidate-lint.json`, `baseline-mechanism-assessment.json`, `candidate-mechanism-assessment.json`, `run-telemetry.json`을 현재 schema에 맞춘다.
3. `mechanism_review.summary.runs_considered > 0`을 첫 acceptance criteria로 둔다.
4. 그 다음 `candidates_emitted > 0`, `mutation_proposal.runnable_available_count > 0` 순서로 확장한다.
5. backfill 과정은 모든 값을 임의 생성하지 말고, 확인 가능한 값과 `unknown/not_available`을 구분하는 migration policy를 둔다.

---

### 5.3 P0 — Strict preview I001 import 정렬 오류

실제 파일 상단은 다음 순서다.

```python
from __future__ import annotations

from json import JSONDecodeError
from collections import defaultdict
from dataclasses import dataclass
```

`collections`가 `json`보다 앞서야 하므로 strict import sorting에서 I001이 발생한다. 동작 변경 없이 고칠 수 있는 가장 작은 P0다.

**권장 수정:**

```python
from __future__ import annotations

from collections import defaultdict
from json import JSONDecodeError
from dataclasses import dataclass
```

가능하면 `ruff check --select I --fix ops/scripts/structural_complexity_budget_runtime.py`로 처리하고, strict preview allowlist를 늘리지 않는다.

---

### 5.4 P0 — 산출물 진실성 gate의 전면 적용

현재 코드에는 이미 다음 요소가 있다.

| 요소 | 현재 상태 |
|---|---|
| canonical report envelope helper | 존재 |
| `describe_output_file()` | 존재 |
| `write_schema_validated_json()` | 존재 |
| report 생성 후 검증 | 일부 surface에만 적용 |
| Evidence Manifest 자동 삽입 | 전면 적용은 아님 |
| 다운로드 링크 전 physical artifact verification | 정책으로 완전히 강제되지는 않음 |

**권장 수정:**

1. report-producing CLI 공통 writer를 만들고 `exists`, `byte_size`, `sha256`, `generated_at`, `producer`, `source_command`를 반드시 기록한다.
2. report 파일을 사용자에게 제공하기 전 동일 정보를 별도 manifest로 검증한다.
3. “확인됨 / 상호확인 / 추론 / 미검증” 상태를 보고서 상단에 자동 표시한다.
4. canonical report가 Evidence Manifest 없이 생성되면 CI에서 실패하게 한다.
5. 외부 export용 report와 repo-local report의 output resolver를 명시적으로 분리한다.

---

### 5.5 P1 — ZIP portability gate

새 통합 리뷰는 ZIP 패키징 호환성을 P0/P1 후보로 제시했다. 이번 환경에서는 실패하지 않았으므로 우선순위를 다음처럼 조정한다.

| 조건 | 우선순위 |
|---|---|
| 현재 release ZIP이 일반 `unzip`에서 실제 실패 | P0 |
| 일부 환경에서만 실패 가능성이 있고 현재 재현 안 됨 | P1 |
| release archive가 내부 전용이고 Python `zipfile`만 지원 | P2 문서화 |

이번 재검증은 두 번째 조건에 해당한다.

**권장 수정:**

- release archive 생성 시 `portable_extract_smoke`를 추가한다.
- Python `zipfile` 해제와 시스템 `unzip` 해제를 모두 검사한다.
- path component byte budget을 200~220 bytes로 유지한다.
- raw web snapshot 파일명은 장기적으로 `slug + short-hash` 형태로 줄이고 원제목은 manifest/frontmatter에 보존한다.
- 이번 v36에서는 200 bytes 초과 component가 없었으므로, 즉시 파일명 일괄 변경보다 release gate 추가를 먼저 한다.

---

### 5.6 P1 — Fast feedback 계층 경량화

현재 `Makefile`에는 `test`, `test-serial`, `test-parallel`, `test-all`, `release-smoke` 등이 있으나, `fast-smoke`라는 명확한 최소 계약 tier는 없다. 선택 pytest 하나도 환경 오버헤드가 커서 빠른 피드백으로 보기 어렵다.

**권장 fast-smoke 범위:**

| 영역 | 포함 테스트 |
|---|---|
| artifact IO | optional JSON diagnostic, schema-valid write |
| output policy | repo-local output vs external output resolver |
| runtime context | frozen clock, timezone formatting |
| generated artifact | envelope/currentness sample |
| self-improvement bootstrap | schema-valid minimal run fixture |
| public/private boundary | public export leak smoke |
| command runtime | timeout metadata minimal test |

**완료 기준:** `make fast-smoke`가 일반 개발 머신에서 30~120초 내 안정적으로 완료되고, 실패 시 어느 phase에서 멈췄는지 즉시 보인다.

---

### 5.7 P1 — CLI cold-start 예산

직접 import 순회 결과 `ops.scripts.artifact_freshness_runtime`이 약 16.10초로 두드러졌다. 전체 153개 모듈 import는 18.19초였으므로, 거의 대부분의 cold import 비용이 한 모듈에 집중되어 있다.

**권장 수정:**

1. CLI `--help` path와 runtime heavy import를 분리한다.
2. `artifact_freshness_runtime`이 import 시점에 큰 schema graph, policy, filesystem scan을 가져오지 않도록 lazy import한다.
3. 주요 CLI `--help` p95 2초 이하를 soft budget으로 둔다.
4. cold-start benchmark report를 generated artifact로 남긴다.
5. 최초에는 hard fail보다 warning budget으로 연결한다.

---

### 5.8 P1 — Optional JSON diagnostic 전파

`artifact_io_runtime.py`에는 diagnostic API가 존재한다.

```python
def load_optional_json_object_with_diagnostics(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    ...
def load_optional_json_object(path: Path) -> dict[str, Any]:
    payload, _diagnostics = load_optional_json_object_with_diagnostics(path)
    return payload
```

즉, compatibility wrapper가 `_diagnostics`를 버린다. 존재만으로는 충분하지 않다. self-improvement loop의 입력 신뢰도를 높이려면 provenance-heavy caller가 diagnostic variant를 사용해야 한다.

**권장 수정:**

- readiness, mutation, mechanism review, artifact freshness caller부터 diagnostic variant로 전환한다.
- `missing`, `decode_error`, `type_error`를 같은 `{}`로 처리하지 않는다.
- diagnostic 결과를 report의 `diagnostics.input_files` 또는 warning budget에 노출한다.
- wrapper 사용 지점 inventory를 생성하고 단계적으로 감소시킨다.

---

### 5.9 P1 — Long-running gate telemetry

새 통합 리뷰의 지적처럼, 긴 gate가 멈추면 “코드 결함인지, 단순 장시간 실행인지, 특정 파일에서 hang인지” 판단하기 어렵다. 이번 환경에서도 외부 Python subprocess 및 pytest 실행 한계가 반복되어, 이 관찰성 문제가 실제 검토 비용을 키웠다.

**권장 수정:**

- 60초 이상 예상되는 gate는 10초마다 current phase와 last item을 stderr에 출력한다.
- timeout report에는 `current_phase`, `last_item`, `duration`, `stdout_tail`, `stderr_tail`, `timed_out`을 포함한다.
- `--max-items`, `--changed-only`, `--profile minimal` 옵션을 제공한다.
- release smoke는 짧은 smoke와 긴 release gate로 분리한다.

---

### 5.10 P2 — Runtime surface 분해

실제 AST/line 측정 기준으로 큰 파일은 다음과 같다.

| 파일 | nonempty LOC | 함수 수 | branch node |
|---|---:|---:|---:|
| `tests/test_mechanism_review.py` | 1,837 | 24 | 45 |
| `tests/test_mutation_proposal.py` | 1,375 | 24 | 29 |
| `ops/scripts/auto_improve_readiness_runtime.py` | 1,257 | 45 | 151 |
| `tests/test_run_mechanism_experiment.py` | 1,180 | 25 | 24 |
| `ops/scripts/mutation_proposal_runtime.py` | 1,154 | 50 | 137 |
| `ops/scripts/mechanism_assess.py` | 795 | 41 | 117 |
| `ops/scripts/filesystem_runtime.py` | 771 | 39 | 117 |
| `ops/scripts/auto_improve_session_runtime.py` | 737 | 46 | 136 |

**권장 분해 순서:**

1. `auto_improve_readiness_runtime.py`: evidence collector / blocker evaluator / recommendation renderer / report writer
2. `mutation_proposal_runtime.py`: evidence loading / scoring / blocker diagnostics / dedupe / report assembly
3. `filesystem_runtime.py`: path guard / atomic write / copy tree / cleanup / diagnostics
4. `auto_improve_session_runtime.py`: session state / run history validation / retry policy / output artifact write
5. `codex_exec_executor.py`: command construction / process execution / result parsing / artifact write

분해는 기능 변경 PR과 섞지 말고, 각 PR에서 관련 테스트만 같이 이동한다.

---

### 5.11 P2 — Output path policy 명시화

실제 grep 결과:

| resolver | 사용 파일 수 | 의미 |
|---|---:|---|
| `resolve_output_path` | 6 | 외부 출력 허용 가능성이 있는 일반 output |
| `resolve_repo_output_path` | 33 | repo-local report output 기본값 |

보안 기본값은 좋은 편이다. 그러나 CLI help와 report에 output class가 드러나지 않으면 사용자가 왜 외부 경로가 거부되는지 이해하기 어렵다.

**권장 output class:**

- `repo_report`: vault/repo 내부만 허용
- `external_export`: 명시 flag로 외부 경로 허용
- `ephemeral_temp`: report에는 sanitized temp path만 기록
- `public_export`: public/private leak post-check 필수

---

### 5.12 P2 — Policy exact enumeration drift

`ops/policies/wiki-maintainer-policy.yaml`은 1,667행이며, path candidate가 최소 35개 확인된다. `system/system-raw-registry/wiki/*.md` 같은 반복 영역은 exact enumeration보다 pattern + override 구조가 안정적이다.

**권장 수정:**

1. 공통 section contract를 pattern rule로 이동한다.
2. 예외 shard만 exact override로 남긴다.
3. policy 변경 시 affected path inventory를 자동 생성한다.
4. policy schema에 `pattern_rule`, `override_rule`, `deprecation_plan` 필드를 명확히 둔다.

---

### 5.13 P2/P3 — Root 0-byte placeholder와 review hygiene

루트 0-byte source placeholder 2개가 실제 확인됐다.

- `source--global-markets-misc-intake-w-230-2026-04-21.md`
- `source--global-markets-misc-intake-w-249-2026-04-21.md`

또한 전체 0-byte 파일은 17개이며, 대부분은 run stdout/stderr placeholder다. run stdout/stderr 0-byte는 정상일 수 있지만, root source placeholder는 provenance 관점에서 의도가 불명확하다.

**권장 수정:**

- 의도된 placeholder이면 생성 정책과 closeout 조건을 문서화한다.
- 잔존 산출물이면 ingest 후 cleanup routine을 추가한다.
- `review/` 빈 디렉터리도 patch workspace 용도라면 README/ARCHITECTURE에 역할을 명시한다.

---

## 6. 수정된 우선순위 매트릭스

| 우선순위 | ID | 항목 | 새 통합 리뷰 대비 조정 | 근거 |
|---|---|---|---|---|
| P0 | P0-1 | Generated artifact envelope/currentness backfill | 유지 | 142개 중 135개 debt |
| P0 | P0-2 | Self-improvement bootstrap 복구 | 유지 | `runs_considered=0`, runnable proposal 0 |
| P0 | P0-3 | Strict preview I001 수정 | 유지 | 실제 import 순서 위반 확인 |
| P0 | P0-4 | 산출물 진실성 gate 전면 적용 | 유지 | helper는 있으나 전면 강제 아님 |
| P0 | P0-5 | Run artifact schema validation backfill | 강화 | local schema validation 19개 실패 |
| P1 | P1-1 | ZIP portability gate | **P0/P1에서 P1로 조정** | 이번 환경에서는 `unzip` 성공, 다만 cross-platform risk |
| P1 | P1-2 | Fast-smoke tier 신설 | 유지 | `fast-smoke` target 없음, 선택 pytest도 무거움 |
| P1 | P1-3 | CLI cold-start budget | 유지 | `artifact_freshness_runtime` cold import 16.10초 |
| P1 | P1-4 | Optional JSON diagnostic caller 전환 | 유지 | wrapper가 diagnostic 폐기 |
| P1 | P1-5 | Long-running gate telemetry | 유지 | 검토/실행 비용 증가 |
| P1 | P1-6 | Self-improvement ledger/ROI | 유지 | closed-loop id/ROI 구조 부족 |
| P2 | P2-1 | Runtime surface 분해 | 유지 | readiness/mutation/filesystem/session 대형화 |
| P2 | P2-2 | Output path policy 명시화 | 유지 | resolver 차이가 CLI help에 약함 |
| P2 | P2-3 | Policy pattern rule 전환 | 유지 | YAML 1,667행, exact path candidate 35개 |
| P2/P3 | P2-4 | root placeholder/review hygiene | 유지 | root 0-byte source 2개 |
| P3 | P3-* | anti-slop scoreboard, semantic classifier, domain package 전환 | 유지 | 장기 운영성 |

---

## 7. 권장 PR/Experiment 실행 순서

### PR-1: Strict preview import order fix

- 대상: `ops/scripts/structural_complexity_budget_runtime.py`
- 작업: `collections` import를 `json` import 위로 이동
- 검증:
  - `ruff check --select I ops/scripts/structural_complexity_budget_runtime.py`
  - strict preview wrapper
- 예상 리스크: 매우 낮음
- 완료 기준: strict preview I001 0개

### PR-2: Minimal run artifact schema backfill

- 대상: `runs/` 중 finalized/comparable run 1건
- 작업:
  - eval/lint JSON에 `$schema`와 envelope 추가
  - mechanism assessment에 `risk_flag_evidence` 추가
  - telemetry에 `launch_succeeded` 추가
- 검증:
  - local schema validation 통과
  - `mechanism_review.summary.runs_considered > 0`
- 예상 리스크: 중간
- 완료 기준: self-improvement bootstrap이 `no_history`에서 벗어나는 첫 신호 확보

### PR-3: Artifact freshness top debt report

- 대상: `ops/scripts/artifact_freshness_runtime.py`, schema
- 작업:
  - `top_debt`
  - `owner_surface`
  - `recommended_next_action`
  - `legacy_report` role
- 검증:
  - artifact freshness report가 다음 10개 수정 대상을 안정적으로 출력
- 완료 기준: 신규 canonical report envelope missing 0, legacy debt는 role로 분리

### PR-4: Report output truthfulness helper 강제

- 대상: report writer 공통층
- 작업:
  - `exists`, `byte_size`, `sha256` 검증
  - Evidence Manifest 자동 삽입
  - 확인됨/추론/미검증 상태 표시
- 검증:
  - output file 없는 경우 실패
  - schema-valid report만 제공
- 완료 기준: canonical report-producing CLI 100% 적용

### PR-5: Fast-smoke target

- 대상: Makefile, pytest marker 또는 test selection helper
- 작업:
  - `make fast-smoke` 추가
  - 핵심 contract 테스트만 포함
  - duration artifact 생성
- 검증:
  - 일반 환경 30~120초 budget
  - 실패 위치 phase 출력
- 완료 기준: 개발자/CI가 full fast 전에 최소 계약을 빠르게 확인

### PR-6: ZIP portable extract smoke

- 대상: release archive 생성/검증
- 작업:
  - Python `zipfile` 해제 검증
  - system `unzip` 해제 검증
  - filename byte budget 검사
- 검증:
  - 현재 v36 ZIP 통과
  - 인위적 long filename fixture 실패 감지
- 완료 기준: cross-platform extract regression 방지

### PR-7: Optional JSON diagnostic propagation

- 대상: mechanism, mutation, readiness, freshness caller
- 작업:
  - diagnostic variant 사용
  - missing/decode/type error report 노출
- 검증:
  - malformed JSON fixture에서 silent `{}` 금지
- 완료 기준: provenance-heavy caller에서 diagnostic 폐기 지점 제거

### PR-8: Self-improvement ledger/ROI

- 대상: mutation proposal, outcome metrics, auto-improve session/readiness
- 작업:
  - `improvement_id`
  - `artifact_debt_reduced`
  - `tests_added`
  - `files_touched`
  - `latency_saved`
  - `defect_prevented`
  - `complexity_delta`
  - rejected reason / dedupe key
- 검증:
  - proposal → execution → outcome → regression check 연결
- 완료 기준: 같은 제안 반복 생성 감소, rejected proposal negative memory 보존

### PR-9: Runtime surface first split

- 대상: `auto_improve_readiness_runtime.py` 또는 `mutation_proposal_runtime.py` 중 하나
- 작업:
  - collector/evaluator/renderer/writer 중 가장 독립적인 경계 하나만 분리
- 검증:
  - 관련 테스트 통과
  - public API compatibility 유지
- 완료 기준: 동작 변경 없이 파일 책임 경계가 선명해짐

---

## 8. Acceptance Criteria

향후 개선 PR은 다음 기준을 만족해야 한다.

| # | 기준 |
|---:|---|
| 1 | 하나의 primary mechanism axis만 변경한다. behavior change와 cleanup을 섞지 않는다. |
| 2 | touched canonical report는 `$schema`, `artifact_kind`, `generated_at`, `producer`, `source_command`, `input_fingerprints`, `currentness`를 가진다. |
| 3 | report/download artifact는 링크 제공 전 `exists`, `byte_size`, `sha256`이 검증된다. |
| 4 | run artifact migration은 임의 추측값과 실제 확인값을 구분한다. |
| 5 | `mechanism_review.summary.runs_considered > 0`을 bootstrap 복구의 첫 기준으로 둔다. |
| 6 | `mutation_proposal`에 runnable proposal이 최소 1건 생길 때까지 auto-improve execution은 hold한다. |
| 7 | strict preview I001은 allowlist 추가 없이 제거한다. |
| 8 | optional JSON fallback은 `missing`, `decode_error`, `type_error`를 구분한다. |
| 9 | subprocess/gate 실행은 timeout, returncode, timed_out, termination reason, stdout/stderr tail을 남긴다. |
| 10 | 60초 이상 gate는 progress와 last item을 출력한다. |
| 11 | fast-smoke는 30~120초 budget을 목표로 하고 full fast와 역할을 분리한다. |
| 12 | ZIP release archive는 Python `zipfile`과 system `unzip` 양쪽에서 해제 검증을 통과한다. |
| 13 | path component byte budget을 검사하고 초과 시 release gate에서 실패한다. |
| 14 | output class(`repo_report`, `external_export`, `ephemeral_temp`, `public_export`)를 CLI help/report에 드러낸다. |
| 15 | public export 후 private path leak, raw/wiki/system/runs leak, generated report leak 검사를 수행한다. |
| 16 | runtime 분해 PR은 side-effect boundary를 기준으로 하고, compatibility facade를 유지한다. |
| 17 | policy exact enumeration을 줄일 때 affected path inventory를 같이 생성한다. |
| 18 | root placeholder는 의도/closeout 규칙을 문서화하거나 제거한다. |
| 19 | 미검증 주장은 핵심 결론에 섞지 않고 별도 상태로 표시한다. |
| 20 | artifact freshness debt가 신규로 증가하지 않는다. |

---

## 9. 검증 한계

1. `make test`, `make release-smoke`, `ruff`, `mypy` 전체 완주는 이번 환경에서 새로 주장하지 않는다.
2. `pip install -e .[dev]`는 실행 환경의 단일 작업 제한에 걸려 완료 확인하지 못했다. 다만 현재 프로세스에는 `PyYAML`, `jsonschema`, `pytest`가 이미 있었고, `ruff`, `mypy`는 import 가능한 상태가 아니었다.
3. 외부 Python subprocess는 `python -c` 수준에서도 반복 지연되어 CLI `--help` 벤치마크를 신뢰 가능한 방식으로 완주하지 못했다. 내부 import 측정으로 cold-start debt를 판단했다.
4. 선택 pytest는 `tests/test_artifact_io_runtime.py`만 완료 주장한다. `tests/test_command_runtime.py`와 `tests/test_release_smoke.py` 묶음 실행은 완료 코드를 얻기 전에 중단되어 근거로 쓰지 않았다.
5. 시스템 `unzip` 성공은 이번 Linux 환경의 결과다. 다른 unzip 구현, OS, locale, normalization 환경의 실패 가능성을 부정하지 않는다.
6. private corpus 본문은 보고서에 복사하지 않았고, 파일 구조·코드·schema·generated artifact 상태 중심으로만 기술했다.

---

## 10. 최종 실행 권고

새 통합 리뷰는 “세 리뷰를 빠짐없이 통합한 지도”로서 유용하지만, 실제 파일 재검증을 반영하면 우선순위는 조금 더 날카롭게 정리된다.

가장 먼저 할 일은 ZIP 파일명 일괄 변경이나 대형 runtime 분해가 아니다. 현재 운영 루프를 막는 직접 원인은 generated/run artifact evidence chain이다. 따라서 다음 세 묶음이 최소 완성 경로다.

1. **즉시 수정:** strict preview I001 import order fix.
2. **증거 체인 복구:** run artifact schema/envelope backfill 1건 → mechanism review가 run을 고려하도록 만들기.
3. **운영 루프 안정화:** artifact freshness top debt, report truthfulness gate, fast-smoke, ZIP portable extract smoke, optional diagnostic propagation.

그 뒤에 runtime surface 분해와 domain package 전환을 진행해야 한다. 이 순서를 지키면 대규모 리팩터링 없이도 현재 v36의 가장 큰 운영 리스크인 “증거를 믿고 개선할 수 없는 상태”를 빠르게 줄일 수 있다.
