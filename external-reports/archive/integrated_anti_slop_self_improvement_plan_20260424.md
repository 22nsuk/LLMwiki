# LLM Wiki vNext — Integrated Anti-Slop & Self-Improvement Improvement Plan

- **파일명**: `integrated_anti_slop_self_improvement_plan_20260424.md`
- **작성일**: 2026-04-24
- **언어**: Korean
- **통합 범위**:
  - 기존 코드 정밀 검토 보고서
  - 기존 통합 개선안
  - `통합_최종_개선안.md`
  - `통합 개선방안.md`
- **핵심 관점**: Anti-Slop / Self-Improvement Closed Loop / Artifact Currentness / Typed Contract / Proposal-as-Experiment / IP·SBOM Compliance / Agent Workflow Governance

---

## 0. 최종 결론

LLM Wiki vNext는 단순한 자동화 스크립트 묶음이 아니라, **정책·스키마·리포트·실험 실행·테스트·자가 개선 루프가 결합된 운영형 메타-메인터넌스 런타임**이다. 현재 코드베이스의 핵심 강점은 이미 명확하다.

- 스키마 기반 리포트 생성
- 원자적 파일 쓰기와 rollback rehearsal
- public/private 경계 구획
- execution readiness와 learning readiness의 분리
- structural complexity budget
- direct-script fallback contract test
- 풍부한 테스트 surface

그러나 통합 검토 결과, 현재 위험은 “기능이 부족하다”가 아니라 **slop를 막기 위해 만들어진 장치들이 서로를 충분히 강하게 제약하지 못하는 상태**에 있다. 즉, 1차 slop는 상당 부분 방어하고 있으나, 이제는 **2차 slop**가 발생하고 있다.

> **2차 slop**란 리포트, 정책, 스키마, readiness, proposal, outcome metric 같은 방어 장치가 빠르게 늘어난 뒤, 그 장치들 사이의 currentness, provenance, type, gate semantics, metric vocabulary 계약이 느슨해지면서 방어 장치 자체가 판단 오염원이 되는 현상이다.

따라서 최종 개선 방향은 “더 많은 장치 추가”가 아니라 다음 6가지로 정렬되어야 한다.

1. **산출물 신뢰도 확보**: stale artifact를 제거하고 모든 generated artifact에 currentness envelope를 강제한다.
2. **학습 루프 폐쇄성 강화**: learning readiness를 shadow/advisory에서 active/review-required gate로 승격한다.
3. **proposal을 실험 계약으로 격상**: 모든 proposal은 hypothesis, evidence, expected signal, rollback trigger를 가져야 한다.
4. **상태와 payload 타입화**: `dict[str, Any]` 중심 로직을 DTO, TypedDict, Enum, Literal로 수렴시킨다.
5. **복잡도·규칙·메트릭을 선언화**: complexity budget, raw intake rule, metric registry를 정책화하고 자동 검증한다.
6. **AI 생성 코드의 법적·보안적 provenance를 확보**: IP/SBOM, snippet detection, AI-slop score gate를 CI와 promotion gate에 통합한다.

---

## 1. 통합 문서별 핵심 흡수 내용

### 1.1 기존 통합 개선안에서 유지해야 할 핵심

기존 통합 개선안은 다음 항목을 실무 실행 백로그 수준으로 구체화했다.

- 루트 `pytest_target.log`, `pytest_target.xml`, `pytest_requested_output.txt` 같은 stale artifact 제거
- generated artifact envelope 도입
- learning readiness를 운영 gate로 승격
- session envelope 도입
- `dict[str, Any]` payload를 DTO로 전환
- structural complexity budget의 unmonitored 후보를 단계적으로 monitored profile에 편입
- raw intake validation marker를 policy file로 외재화
- proposal ranking provenance와 canonical metric registry 도입
- `RuntimeContext` 강제 계약 테스트
- report archive 정리 루프

이 내용은 최종 통합안의 기본 골격으로 유지한다.

### 1.2 `통합_최종_개선안.md`에서 추가 흡수한 핵심

이 문서는 기존 개선안을 더 정리된 구조로 재배열하면서 특히 다음 개념을 강화했다.

- **2차 slop**: 방어 장치 자체의 계약 느슨화가 새로운 slop가 될 수 있다는 진단
- **Anti-Slop 성숙도 8축 모델**
  - 파일 쓰기 안전성
  - 출력 형식 계약
  - 실행 재현성
  - 증거 currentness
  - 상태 vocabulary
  - 타입 계약
  - 복잡도 제어
  - self-improvement 폐쇄성
- **Proposal evidence_refs + expected_metric_movement** 필수화
- **session envelope post_run_outcome** 명시화
- **metric vocabulary StrEnum 공통 모듈** 도입
- **Spec-First / proposal-as-spec** 철학 강화

이 문서의 핵심 기여는 기존 P0/P1/P2 항목을 단순 나열이 아니라 **자가 개선 시스템의 방어 성숙도 모델**로 재해석했다는 점이다.

### 1.3 `통합 개선방안.md`에서 추가 흡수한 핵심

이 문서는 산업·법무·보안·AI slop detector 관점을 추가했다. 기존 기술 개선안에 반드시 흡수해야 할 신규 축은 다음이다.

- **IP / 라이선스 / SBOM 컴플라이언스**
  - AI 생성 코드가 오픈소스 스니펫을 포함할 수 있음
  - AGPL 등 strong copyleft 코드 혼입 시 법적 감염 위험
  - 생성 코드 provenance 추적과 SBOM 무결성 필요
- **Snippet detection gate**
  - AI가 생성한 코드의 원천 불명 스니펫 탐지
  - attribution notice와 license policy enforcement 필요
- **AI-slop score gate**
  - unimplemented stub
  - disconnected pipeline
  - phantom import
  - placebo documentation
  - inflated wrapper
  - nonexistent API call
  - broken logic chain
- **score 기반 조치 체계**
  - `<30 CLEAN`
  - `>=30 SUSPICIOUS`
  - `>=50 INFLATED_SIGNAL`
  - `>=70 CRITICAL_DEFICIT`
- **token-level anti-slop 철학의 코드 운영 적용**
  - 전면 재작성보다 슬롭 발생 의사결정 지점에 외과적으로 gate 삽입
  - DPO식 전역 제약보다 FTPO식 token/decision-point 제약에 가까운 운영 설계
- **semantic review의 한계 인식**
  - LLM은 context window, cross-repository impact, 암묵적 business context에 취약
  - 따라서 proposal, session, artifact, metric에 명시적 provenance가 필요

이 문서의 핵심 기여는 최종 개선안에 **법적·보안적 provenance와 AI-slop scoring gate**를 추가해야 한다는 점이다.

---

## 2. 최종 우선순위 체계

| 우선순위 | 영역 | 핵심 목표 | 즉시성 |
|---|---|---|---|
| P0-A | Stale Artifact / Currentness | 현재 증거와 과거 흔적을 물리적으로 분리 | 즉시 |
| P0-B | Learning Gate | 실행 가능성과 학습 가능성을 운영상 분리 | 즉시 |
| P0-C | Proposal Contract | proposal을 검증 가능한 실험 단위로 격상 | 즉시 |
| P0-D | IP/SBOM / Snippet Gate | AI 생성 코드의 법적·보안적 provenance 확보 | 즉시~단기 |
| P1-A | Typed DTO / Vocabulary | 상태 전이와 payload shape를 타입으로 고정 | 단기 |
| P1-B | Complexity Budget | unmonitored complexity 후보를 active gate로 편입 | 단기 |
| P1-C | Rule Declarativization | marker/rule/threshold를 policy로 외재화 | 단기 |
| P1-D | Metric Registry | report field alias와 metric drift 방지 | 단기 |
| P1-E | Spec-First Workflow | agentic coding 전 spec artifact 강제 | 단기 |
| P2-A | CLI Boundary | exception taxonomy와 exit code 표준화 | 중기 |
| P2-B | Static Analysis | Ruff/mypy strict 범위 확대 | 중기 |
| P2-C | Wrapper Generation | direct-script fallback wrapper 생성화 | 중기 |
| P2-D | Report Archive Lifecycle | 외부 보고서와 finding lifecycle 정리 | 중기 |

---

# 3. P0 개선안 — 판단 신뢰도 오염 차단

## 3.1 P0-A: 루트 Stale Artifact 완전 격리 및 Currentness Envelope 도입

### 문제

루트에 남아 있는 과거 테스트 산출물은 자가 개선 루프에서 가장 위험한 오염원이다. 특히 과거 실패가 기록된 `pytest_target.xml`이 현재 코드의 실패처럼 해석되면, LLM agent는 존재하지 않는 defect를 수정하려고 멀쩡한 코드를 변형한다.

### 최종 조치

#### 3.1.1 루트 ephemeral artifact 금지

다음 파일 패턴은 root에 존재하면 CI 실패로 처리한다.

```text
pytest_*.log
pytest_*.xml
pytest_*_output.txt
pytest_*_requested*.txt
```

테스트 산출물은 다음 경로로만 생성한다.

```text
tmp/test-runs/<run-id>/pytest-target.log
tmp/test-runs/<run-id>/pytest-target.xml
tmp/test-runs/<run-id>/pytest-summary.json
```

#### 3.1.2 `.gitignore` 추가

```gitignore
# ephemeral test run artifacts — never commit
pytest_target.log
pytest_target.xml
pytest_requested_output.txt
pytest_*.log
pytest_*.xml
pytest_*_output.txt
tmp/test-runs/
```

#### 3.1.3 artifact hygiene test

```python
from pathlib import Path

ROOT_EPHEMERAL_PATTERNS = [
    "pytest_*.log",
    "pytest_*.xml",
    "pytest_*_output.txt",
    "pytest_*_requested*.txt",
]

def test_no_root_ephemeral_test_artifacts() -> None:
    offenders: list[str] = []
    for pattern in ROOT_EPHEMERAL_PATTERNS:
        offenders.extend(path.as_posix() for path in Path(".").glob(pattern))
    assert offenders == [], f"Root ephemeral artifacts found: {offenders}"
```

#### 3.1.4 Generated Artifact Envelope 표준

모든 generated JSON artifact는 다음 envelope를 가져야 한다.

```json
{
  "$schema": "ops/schemas/artifact-envelope.schema.json",
  "artifact_kind": "pytest_run_log",
  "generated_at": "2026-04-24T00:00:00Z",
  "producer": "pytest",
  "source_command": "make check-serial",
  "source_revision": "<git sha or unknown>",
  "source_tree_fingerprint": "<hash>",
  "input_fingerprints": {
    "policy": "<hash>",
    "schema": "<hash>"
  },
  "schema_version": 1,
  "artifact_status": "current",
  "retention_policy": "ephemeral",
  "encoding": "utf-8",
  "currentness": {
    "status": "current",
    "checked_at": "2026-04-24T00:00:00Z"
  }
}
```

허용 vocabulary:

```text
artifact_status: current | archived | stale | unknown
retention_policy: ephemeral | canonical_report | archive
currentness.status: current | stale | unknown | invalid
```

#### 3.1.5 Stale Artifact Detector 신규 도입

신규 모듈:

```text
ops/scripts/artifact_freshness_runtime.py
ops/schemas/artifact-freshness-report.schema.json
ops/reports/artifact-freshness-report.json
```

검사 항목:

- root ephemeral artifact 존재 여부
- `generated_at`이 source mtime보다 오래되었는지
- `$schema` 누락 여부
- artifact envelope 누락 여부
- UTF-8 decode 실패 여부
- currentness가 `unknown`인 artifact 수

report summary:

```json
{
  "stale_artifact_count": 0,
  "root_ephemeral_artifact_count": 0,
  "unknown_currentness_artifact_count": 0,
  "non_utf8_text_artifact_count": 0
}
```

### 완료 기준

- root에 pytest 계열 산출물이 없다.
- 모든 canonical report에 `$schema`, `generated_at`, `artifact_status`, `currentness`가 있다.
- artifact freshness report가 CI에서 생성되고 schema validation을 통과한다.
- UTF-8이 아닌 text artifact는 fail 또는 quarantine 처리된다.

---

## 3.2 P0-B: Learning Readiness를 운영 Gate로 승격

### 문제

현재 구조는 execution readiness와 learning readiness를 분리해 보는 좋은 설계를 갖고 있다. 그러나 learning readiness가 `shadow` 또는 advisory에 머물면 운영상 위험하다. `execution_readiness.pass`는 “실행할 수 있음”만 의미해야 하며, “지금 실행하면 학습 가치가 있음”을 뜻해서는 안 된다.

### 최종 조치

#### 3.2.1 readiness 최상위 상태 재정의

```json
{
  "execution_readiness": {
    "status": "pass",
    "gate_effect": "active",
    "can_run": true
  },
  "learning_readiness": {
    "status": "learning_uncertain",
    "gate_effect": "review_required",
    "likely_to_learn": false
  },
  "overall_recommendation": "run_only_as_bounded_trial",
  "operator_warning": "queue is runnable but learning evidence is insufficient"
}
```

#### 3.2.2 status vocabulary

```python
from enum import StrEnum

class GateEffect(StrEnum):
    ACTIVE = "active"
    SHADOW = "shadow"
    PREVIEW = "preview"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    NONE = "none"

class LearningReadinessStatus(StrEnum):
    LEARNING_READY = "learning_ready"
    LEARNING_UNCERTAIN = "learning_uncertain"
    RUNNABLE_BUT_UNINFORMATIVE = "runnable_but_uninformative"
    RUNNABLE_INSUFFICIENT_SESSION = "runnable_with_insufficient_session_context"
    RUNNABLE_HIGH_REWORK_RISK = "runnable_high_rework_risk"
    BLOCKED = "blocked"
```

#### 3.2.3 auto_improve_loop entry gate

```python
if learning_readiness.status != LearningReadinessStatus.LEARNING_READY:
    if not args.allow_learning_uncertain:
        print_error(
            "LEARNING GATE: queue may be executable, but learning evidence is insufficient. "
            "Use --allow-learning-uncertain only for bounded trial runs."
        )
        return 2
    print_warning(
        "Proceeding as BOUNDED TRIAL. This run must not be treated as confirmed learning."
    )
```

#### 3.2.4 Session Envelope 필수화

모든 auto-improve run은 다음 artifact를 생성한다.

```text
ops/reports/auto-improve-sessions/<session-id>/session-envelope.json
```

표준 schema:

```json
{
  "$schema": "ops/schemas/session-envelope.schema.json",
  "session_id": "session:...",
  "run_id": "run-...",
  "proposal_id": "proposal:...",
  "started_at": "...",
  "ended_at": "...",
  "operator_intent": "...",
  "execution_context": {
    "executor": "codex_exec",
    "max_minutes": 30
  },
  "learning_context": {
    "hypothesis": "...",
    "expected_metric_movement": {},
    "pre_run_readiness": "runnable_but_uninformative"
  },
  "role_dispatch": {
    "worker": [],
    "reviewer": [],
    "validator": [],
    "auditors": []
  },
  "post_run_outcome": {
    "decision": "hold",
    "observed_metric_movement": {},
    "learned": false,
    "why": "insufficient session evidence"
  },
  "learning_signals": {
    "new_failure_mode_discovered": false,
    "regression_prevented": false,
    "test_added": false,
    "complexity_reduced": false,
    "policy_contract_clarified": false
  }
}
```

### 완료 기준

- `learning_uncertain` 상태에서는 명시 flag 없이 live loop가 실행되지 않는다.
- session envelope가 없으면 outcome metrics가 해당 run을 confirmed learning으로 집계하지 않는다.
- `session_reports_considered=0`은 CLI와 report에서 강한 warning으로 노출된다.

---

## 3.3 P0-C: Proposal을 검증 가능한 실험 계약으로 격상

### 문제

현재 proposal은 개선 후보를 담는 큐 역할은 하지만, “왜 지금 이 실험을 해야 하는가”, “무엇이 바뀌면 성공인가”, “무엇이 바뀌지 않아야 하는가”, “어떤 경우 rollback해야 하는가”가 충분히 잠기지 않는다.

### 최종 조치

모든 proposal은 다음 필드를 가져야 한다.

```json
{
  "$schema": "ops/schemas/proposal-contract.schema.json",
  "proposal_id": "proposal:...",
  "target": "ops/scripts/...",
  "hypothesis": "learning readiness를 active gate로 승격하면 반복 rework를 줄인다",
  "single_mechanism_scope": {
    "primary_target": "ops/scripts/...",
    "allowed_supporting_targets": [],
    "forbidden_changes": []
  },
  "evidence_refs": [
    "ops/reports/auto-improve-readiness.json#/learning_readiness",
    "ops/reports/outcome-metrics.json#/metrics/rework_count"
  ],
  "expected_binary_signal": {
    "must_change": [],
    "must_not_change": []
  },
  "expected_metric_movement": {
    "rework_count": "down",
    "hold_moving_average": "down",
    "session_reports_considered": "up"
  },
  "rollback_trigger": [],
  "rollback_plan": "restore previous gate behavior",
  "minimum_validation_artifact": [],
  "baseline_failure_pattern": "...",
  "disqualifying_evidence": [],
  "learning_value": {
    "novelty": "medium",
    "evidence_confidence": "medium",
    "why_now": "current queue is runnable but low learning confidence"
  },
  "risk_class": "runtime_gate_change"
}
```

### Proposal pre-filters

proposal generation 전에 다음 필터를 통과해야 한다.

| 필터 | 목적 |
|---|---|
| `evidence_sufficiency_filter` | 근거 없는 proposal 제거 |
| `novelty_floor_filter` | 이전과 동일한 제안 반복 방지 |
| `rework_cycle_repetition_filter` | 동일 family의 rework 반복 감산 |
| `cross_report_consistency_filter` | report 간 모순 탐지 |
| `session_context_sufficiency_filter` | session evidence 부족 시 억제 |
| `family_hold_rate_filter` | 동일 family HOLD/DISCARD 과다 시 감산 |
| `proposal_size_asymmetry_filter` | 단일 mechanism 범위를 넘는 변경 거부 |
| `ip_snippet_risk_filter` | 출처 불명 스니펫 또는 고위험 라이선스 의심 시 억제 |
| `ai_slop_score_filter` | stub/phantom import/disconnected pipeline 위험 점수 반영 |

### 완료 기준

- proposal contract schema가 추가된다.
- proposal에 `hypothesis`, `evidence_refs`, `expected_metric_movement`, `rollback_plan`이 없으면 validation fail.
- promotion 결과가 proposal hypothesis의 성공/실패/불명확을 기록한다.

---

## 3.4 P0-D: IP/SBOM·Snippet Detection·AI-Slop Score Gate 도입

### 문제

AI 생성 코드는 기능적 품질뿐 아니라 법적·보안적 provenance 위험을 가진다. 원천 불명 오픈소스 스니펫, AGPL 등 strong copyleft 코드 조각, 알려진 취약점이 포함된 코드 fragment가 내부 코드베이스에 섞이면 SBOM 무결성과 라이선스 컴플라이언스를 훼손한다.

### 최종 조치

#### 3.4.1 Snippet provenance gate

신규 report:

```text
ops/reports/snippet-provenance-report.json
ops/schemas/snippet-provenance-report.schema.json
```

필수 필드:

```json
{
  "generated_at": "...",
  "source_revision": "...",
  "scanned_files": [],
  "matches": [
    {
      "path": "ops/scripts/...",
      "line_start": 10,
      "line_end": 22,
      "match_kind": "possible_open_source_snippet",
      "confidence": "medium",
      "license_risk": "unknown",
      "action": "manual_review_required"
    }
  ],
  "summary": {
    "high_risk_match_count": 0,
    "unknown_license_match_count": 0,
    "manual_review_required_count": 0
  }
}
```

#### 3.4.2 SBOM update gate

AI-generated or agent-modified dependency changes는 다음을 요구한다.

- dependency diff 생성
- license metadata 확인
- SBOM 업데이트 여부 확인
- high-risk license denylist 적용
- attribution notice 필요 여부 판단

#### 3.4.3 AI-slop score report

신규 report:

```text
ops/reports/ai-slop-score-report.json
ops/schemas/ai-slop-score-report.schema.json
```

탐지 feature:

| feature | 설명 |
|---|---|
| `unimplemented_stub` | pass/ellipsis/TODO만 있고 실제 연결 없음 |
| `phantom_import` | 존재하지 않거나 사용되지 않는 import |
| `disconnected_pipeline` | 호출 경로에 연결되지 않은 신규 pipeline |
| `placebo_documentation` | 코드 기능과 맞지 않는 장황한 문서화 |
| `inflated_wrapper` | 의미 없이 wrapper만 증가 |
| `nonexistent_api_call` | 실제 존재하지 않는 API 호출 |
| `broken_logic_chain` | 입력과 출력의 의미 연결이 끊김 |
| `unused_config_surface` | config만 추가하고 소비 경로 없음 |
| `orphan_schema` | schema 추가 후 producer/consumer 없음 |
| `orphan_report_field` | report field 추가 후 reader 없음 |

score action:

| score | 상태 | 조치 |
|---:|---|---|
| `<30` | CLEAN | 통상 리뷰 통과 가능 |
| `>=30` | SUSPICIOUS | reviewer attention |
| `>=50` | INFLATED_SIGNAL | promotion hold 기본값 |
| `>=70` | CRITICAL_DEFICIT | merge/promotion 차단 |

#### 3.4.4 Promotion gate 연결

promotion decision은 다음 조건을 만족해야 한다.

```text
snippet high-risk count == 0
unknown license manual-review count == 0 또는 승인 기록 존재
ai_slop_score < 50
critical slop feature count == 0
SBOM stale == false
```

### 완료 기준

- AI-generated/agent-modified code path에 snippet provenance report가 생성된다.
- dependency 변경 시 SBOM freshness가 검증된다.
- ai-slop score가 promotion gate의 active input으로 사용된다.

---

# 4. P1 개선안 — 구조적 품질 잠금

## 4.1 P1-A: `dict[str, Any]` Payload를 Typed DTO로 수렴

### 문제

`dict[str, Any]`는 LLM agent에게 가장 위험한 형태의 암묵적 계약이다. 필드 추가/삭제가 schema, report, test와 느슨하게 연결되고, 누락 필드가 빈 값으로 조용히 흐르며, 같은 개념이 `status`, `decision`, `outcome`, `verdict`, `failure_kind` 등으로 흩어진다.

### 우선순위 DTO

1. `RunTelemetry`
2. `ExecutionReadiness` / `LearningReadiness`
3. `SessionEnvelope`
4. `ProposalContract`
5. `AttemptRecord`
6. `LoadedSchema`
7. `AiSlopScoreReport`
8. `SnippetProvenanceReport`

### 예시

```python
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class RunTelemetry:
    session_id: str
    run_id: str
    generated_at: str
    proposal_id: str
    proposal_snapshot: str
    scope_freeze: str
    routing_reports: list[str]
    executor_reports: list[str]
    phase_durations: dict[str, float]
    decision: str
    finalized: bool

    def to_json(self) -> dict[str, object]:
        return asdict(self)

@dataclass(frozen=True)
class TelemetryMergeResult:
    payload: RunTelemetry
    preserved_fields: list[str]
    merged_fields: list[str]
    missing_expected_fields: list[str]
    diagnostics: list[str]
```

### drift detector

```python
def test_run_telemetry_dto_required_fields_match_schema() -> None:
    schema = load_schema(Path("ops/schemas/run-telemetry.schema.json"))
    assert set(RunTelemetry.required_fields()) == set(schema["required"])
```

### 완료 기준

- core report builder는 dict literal이 아니라 DTO builder를 거친다.
- schema required field와 DTO required field가 자동 비교된다.
- `Any` 출현 수를 단계적으로 감소시킨다.

---

## 4.2 P1-B: Status / Decision / Metric Vocabulary 공통화

신규 모듈:

```text
ops/scripts/vocabulary_runtime.py
```

예시:

```python
class Verdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    ATTENTION = "attention"

class PromotionDecision(StrEnum):
    PROMOTE = "promote"
    HOLD = "hold"
    DISCARD = "discard"
    ROLLBACK = "rollback"

class ArtifactStatus(StrEnum):
    CURRENT = "current"
    ARCHIVED = "archived"
    STALE = "stale"
    UNKNOWN = "unknown"

class SlopRiskStatus(StrEnum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    INFLATED_SIGNAL = "inflated_signal"
    CRITICAL_DEFICIT = "critical_deficit"
```

### 완료 기준

- `status == "pass"` 같은 raw string 비교가 핵심 런타임에서 사라진다.
- schema enum과 Python StrEnum 간 drift detector가 존재한다.

---

## 4.3 P1-C: Structural Complexity Budget 실효화

### 문제

현재 핵심 문제는 unmonitored 후보가 많고, touched check가 input manifest 부재 시 skip될 수 있다는 점이다.

### 조치

#### fallback discovery

```python
def discover_changed_targets_with_fallback() -> list[Path]:
    manifest = os.environ.get("CHANGED_FILES_MANIFEST")
    if manifest:
        return load_manifest(manifest)
    try:
        return get_git_changed_files()
    except GitUnavailableError:
        return get_recently_modified_scripts(max_age_minutes=60)
```

#### semantic complexity weights

```python
SEMANTIC_COMPLEXITY_WEIGHTS = {
    ast.If: 1,
    ast.For: 1,
    ast.While: 1,
    ast.Try: 1,
    ast.With: 1,
    ast.Match: 1,
    ast.BoolOp: 0.5,
    ast.ExceptHandler: 0.5,
    ast.ListComp: 0.5,
    ast.DictComp: 0.5,
    ast.IfExp: 0.3,
}
```

#### 5개 profile

| profile | 대상 | 기준 |
|---|---|---|
| `runtime_orchestrator_budget` | orchestration 핵심 | 엄격 |
| `runtime_helper_budget` | runtime helper | 중간 |
| `test_fixture_budget` | 테스트 fixture | 느슨 |
| `test_assertion_budget` | test assertion logic | 중간 |
| `generated_sample_budget` | generated samples | 최소 |

#### proposal seed 연결

```text
structural_complexity_budget_report.json
  → function_budget_top_n[status="unmonitored"]
  → mechanism_review_candidate
  → mutation_proposal
```

### 완료 기준

- unmonitored candidate count가 단계적으로 감소한다.
- touched check가 manifest 부재로 skip되지 않는다.
- complexity hotspot이 proposal seed로 자동 연결된다.

---

## 4.4 P1-D: Raw Intake Validation 규칙 선언화

### 문제

marker, heading, continuity 규칙이 코드 상수에 박혀 있으면 정책 변경이 코드 변경이 되고, 운영자/정책 담당자와 개발자의 책임 경계가 흐려진다.

### 조치

```text
ops/policies/raw-intake-validation/
  index.yaml
  synthesis-markers.yaml
  concept-markers.yaml
  continuity-headings.yaml

ops/schemas/raw-intake-validation-policy.schema.json
ops/scripts/raw_intake_validation_rules_runtime.py
```

`raw_intake_promotion_validation_runtime.py`는 rule evaluator만 담당한다.

### policy diff classifier

| 변경 종류 | 위험 | 조치 |
|---|---|---|
| threshold-only | 낮음 | info |
| new gate | 중간 | warn |
| gate severity change | 높음 | fail |
| schema contract change | 최고 | fail + manual review |
| routing model change | 높음 | fail |

---

## 4.5 P1-E: Canonical Metric Registry

### 문제

리포트가 많아질수록 같은 사실이 여러 이름으로 반복될 수 있다. 이는 self-improvement vocabulary slop다.

### registry 예시

```json
{
  "metric_id": "rework_count",
  "owner_report": "outcome_metrics",
  "source_fields": ["session.rework_events"],
  "update_frequency": "per_session",
  "promotion_gate_usage": true,
  "deprecated": false,
  "superseded_by": null
}
```

### 완료 기준

- 새 metric은 registry 등록 없이는 report에 추가할 수 없다.
- deprecated metric lifecycle이 존재한다.
- report field alias 금지 테스트가 존재한다.

---

## 4.6 P1-F: Spec-First Agent Workflow

### 문제

LLM agent에게 바로 코드 수정을 지시하면 context window 한계, 암묵적 business context 부재, semantic overconfidence로 인해 잘못된 구조 변경을 만들 수 있다.

### 조치

모든 non-trivial proposal은 코드 변경 전 spec artifact를 생성한다.

```text
runs/<run-id>/spec/
  requirements.md
  trade_offs.md
  data_model.md
  test_strategy.md
  rollback_plan.md
  risk_assessment.md
```

spec 검토 전에는 implementation phase로 넘어가지 않는다.

### 완료 기준

- `risk_class != trivial` proposal은 spec artifact 없이는 실행되지 않는다.
- spec의 `test_strategy.md`가 minimum validation artifact와 연결된다.
- spec의 `rollback_plan.md`가 proposal contract의 rollback trigger와 연결된다.

---

## 4.7 P1-G: RuntimeContext 계약 강제

### 조치

```python
def test_report_generators_do_not_call_datetime_now_directly() -> None:
    offenders = []
    for path in Path("ops/scripts").glob("*.py"):
        if path.name == "runtime_context.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "datetime.now(" in text or "dt.datetime.now(" in text:
            offenders.append(path.as_posix())
    assert offenders == [], f"Direct datetime.now() calls found: {offenders}"
```

`load_schema_with_vault_override()`는 provenance를 반환한다.

```python
@dataclass(frozen=True)
class LoadedSchema:
    payload: dict[str, object]
    source: Literal["vault", "package_resource"]
    path: str
```

---

# 5. P2 개선안 — 운영 표준화와 유지비 절감

## 5.1 CLI Boundary Exception Taxonomy

신규 enum:

```python
class RuntimeFailureKind(StrEnum):
    POLICY_LOAD_FAILED = "policy_load_failed"
    JSON_DECODE_FAILED = "json_decode_failed"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    ARTIFACT_STALE = "artifact_stale"
    LEARNING_GATE_BLOCKED = "learning_gate_blocked"
    IP_PROVENANCE_BLOCKED = "ip_provenance_blocked"
    AI_SLOP_SCORE_BLOCKED = "ai_slop_score_blocked"
    UNEXPECTED = "unexpected"
```

모든 CLI는 동일한 stderr shape와 exit code policy를 사용한다.

---

## 5.2 Ruff / mypy strict 확대

우선 대상:

1. `runtime_context.py`
2. `artifact_io_runtime.py`
3. `schema_runtime.py`
4. `auto_improve_readiness_runtime.py`
5. `auto_improve_session_runtime.py`
6. `auto_improve_iteration_persistence_runtime.py`
7. `structural_complexity_budget_runtime.py`
8. `artifact_freshness_runtime.py`
9. `ai_slop_score_runtime.py`
10. `snippet_provenance_runtime.py`

목표:

```text
mypy-strict-preview allowlist: 10 → 20 → 35
```

---

## 5.3 Direct-script wrapper 생성화

현재 direct-script fallback wrapper는 관리되고 있지만 장기적으로 hand-maintained 반복이다.

목표:

```text
pyproject.toml [project.scripts]
  → wrapper generator
  → ops/generated/direct_wrappers/*.py
  → contract test
```

---

## 5.4 Report Archive Lifecycle

외부 보고서와 finding이 계속 쌓이면 report 자체가 slop가 된다.

```json
{
  "report_id": "anti_slop_review_20260424",
  "artifact_class": "external_review",
  "supersedes": [],
  "artifact_status": "current",
  "reviewed_code_bundle": "LLM Wiki vNext(28).zip",
  "action_items": [
    {"id": "P0-stale-artifacts", "status": "open"}
  ]
}
```

finding lifecycle:

```text
external finding → improvement_observation → proposal → run → decision → closed/reopened
```

---

# 6. 핵심 모듈별 개선 지시

## 6.1 `auto_improve_readiness_runtime.py`

현재 책임:

- report loading
- queue parsing
- blocker summarization
- fallback history logic
- loop health summary
- learning uncertainty rules
- final report assembly

분리안:

```text
readiness_inputs_runtime.py
readiness_execution_runtime.py
readiness_learning_runtime.py
readiness_report_runtime.py
```

원칙:

```text
입력 정규화 → 판정 → 설명 → 출력
```

---

## 6.2 `auto_improve_session_runtime.py`

개선:

- `AttemptRecord`를 dataclass 또는 strict TypedDict로 강화
- `AttemptAssembler` 도입
- rework/rollback/defect_escape 공통 event vocabulary 도입
- session envelope writer 연결
- outcome metrics가 session envelope를 primary source로 사용

---

## 6.3 `auto_improve_iteration_persistence_runtime.py`

개선:

- `RunTelemetry` DTO 도입
- merge policy를 strategy object로 분리
- decision record extraction에 source provenance 추가
- behavior delta empty string diagnostic 추가
- write 후 schema validation 필수화

---

## 6.4 `structural_complexity_budget_runtime.py`

개선:

- `function_budget_top_n` runtime top 3 strict warning
- test fixture budget 분리
- schema fallback provenance diagnostics 기록
- input manifest 부재 시 fallback discovery
- complexity hotspot → proposal seed 연결

---

## 6.5 `raw_intake_promotion_validation_runtime.py`

개선:

- marker 상수를 policy file로 이동
- rule evaluator만 유지
- confidence-impact를 validation result에 추가
- family/concept/synthesis validator 분리

---

## 6.6 신규 `ai_slop_score_runtime.py`

역할:

- slop feature scan
- score 계산
- severity 산정
- proposal/promotion gate input 생성

---

## 6.7 신규 `snippet_provenance_runtime.py`

역할:

- modified/generated code path scan
- snippet match metadata 수집
- license risk classification
- SBOM freshness check와 연결

---

# 7. 테스트 전략

## 7.1 P0 테스트

| 테스트 | 목적 |
|---|---|
| `test_no_root_ephemeral_test_artifacts` | stale root artifact 차단 |
| `test_generated_artifacts_have_currentness_envelope` | artifact envelope 강제 |
| `test_learning_uncertain_blocks_live_loop_without_flag` | learning gate active화 |
| `test_session_envelope_written_after_auto_improve_run` | session evidence 확보 |
| `test_proposal_contract_requires_evidence_refs` | proposal-as-experiment 강제 |
| `test_ai_slop_score_blocks_critical_deficit` | slop score gate 활성화 |
| `test_snippet_high_risk_requires_manual_review` | IP provenance gate 활성화 |

## 7.2 P1 테스트

| 테스트 | 목적 |
|---|---|
| `test_dto_required_fields_match_schema` | DTO/schema drift 방지 |
| `test_schema_enum_matches_python_enum` | vocabulary drift 방지 |
| `test_complexity_touched_check_does_not_skip_without_manifest` | complexity gate 무력화 방지 |
| `test_raw_intake_rules_loaded_from_policy` | hardcoded marker 제거 |
| `test_metric_registry_has_no_alias_conflicts` | metric vocabulary slop 방지 |
| `test_spec_required_for_non_trivial_proposal` | spec-first 강제 |
| `test_report_generators_do_not_call_datetime_now_directly` | reproducibility 보장 |

## 7.3 P2 테스트

| 테스트 | 목적 |
|---|---|
| `test_cli_failures_use_runtime_failure_kind` | exception taxonomy 통일 |
| `test_direct_wrappers_are_generated` | hand-maintained wrapper 제거 |
| `test_external_report_findings_have_lifecycle_state` | report archive slop 방지 |

---

# 8. 실행 로드맵

## 8.1 1주차 — P0 Hygiene & Gate Lock

- root stale artifact 제거
- `.gitignore` 및 artifact hygiene test 추가
- artifact envelope schema 추가
- artifact freshness report 생성
- learning readiness gate flag 추가
- session envelope schema 초안 추가
- proposal contract schema 초안 추가

## 8.2 2주차 — Proposal / Session / Currentness 연결

- auto_improve_loop entry gate 구현
- session envelope writer 구현
- outcome metrics가 session envelope를 읽도록 연결
- proposal pre-filter 1차 구현
- expected metric movement 기록
- generated artifact index에 stale/currentness count 추가

## 8.3 3~4주차 — DTO / Complexity / Rule 선언화

- RunTelemetry DTO 도입
- ExecutionReadiness / LearningReadiness DTO 도입
- complexity touched fallback discovery 구현
- semantic complexity weights 추가
- raw intake validation policy 분리
- metric registry 초안 도입

## 8.4 1~2개월 — IP/SBOM / AI-Slop Gate / Strict Typing

- snippet provenance report 도입
- SBOM freshness check 연결
- AI-slop score runtime 도입
- promotion gate에 slop/IP 조건 연결
- mypy strict-preview 20+ 확대
- CLI failure taxonomy 통일

## 8.5 2~3개월 — 운영 성숙도 강화

- direct-script wrapper generation
- report archive lifecycle
- policy diff classifier
- complexity hotspot proposal 자동 생성
- spec-first workflow 전면 적용
- metric lifecycle/deprecation enforcement

---

# 9. 최종 운영 원칙

## 9.1 Evidence before mutation

증거가 없는 proposal은 생성하지 않는다. currentness가 불명확한 artifact는 evidence가 아니다.

## 9.2 Execution is not learning

실행 가능하다는 사실은 학습 가치가 있다는 뜻이 아니다. execution readiness와 learning readiness는 운영상 분리되어야 한다.

## 9.3 Proposal is an experiment

proposal은 작업 티켓이 아니라 실험 계약이다. hypothesis, evidence, expected metric movement, rollback trigger가 필수다.

## 9.4 Generated artifacts must declare freshness

모든 generated artifact는 생성 시점, producer, source revision, input fingerprint, currentness를 선언해야 한다.

## 9.5 Type the state, not just the function signature

함수 타입 힌트만으로는 부족하다. 상태 전이, decision vocabulary, report payload shape를 타입으로 잠가야 한다.

## 9.6 Anti-slop is surgical, not blanket suppression

모든 생성을 억제하는 것이 아니라 slop가 발생하는 특정 decision point에 gate를 삽입한다. 이는 FTPO/Antislop Sampler의 철학을 코드 운영에 적용한 것이다.

## 9.7 Legal provenance is part of code quality

AI 생성 코드에서 IP, license, SBOM provenance는 품질의 외부 문제가 아니라 promotion gate의 핵심 입력이다.

## 9.8 Humans remain the system governors

LLM agent는 강력한 pair programmer이지만 최종 governance 주체가 아니다. 정책, gate, schema, metric, promotion decision은 인간이 검토 가능한 형태로 남아야 한다.

---

# 10. 최종 Top 20 실행 항목

1. root stale pytest artifact 제거
2. root ephemeral artifact ban test 추가
3. generated artifact envelope schema 도입
4. artifact freshness runtime/report 추가
5. learning readiness를 review-required/active gate로 승격
6. `--allow-learning-uncertain` bounded trial flag 도입
7. session envelope schema/writer 도입
8. outcome metrics가 session envelope를 primary evidence로 사용
9. proposal contract schema 도입
10. proposal에 evidence_refs/expected_metric_movement/rollback_plan 필수화
11. proposal pre-filter 9종 도입
12. RunTelemetry DTO 도입
13. GateEffect/Verdict/PromotionDecision/ArtifactStatus/SlopRiskStatus StrEnum 공통화
14. complexity touched check skip 제거
15. semantic complexity weights 추가
16. raw intake validation marker policy 외재화
17. canonical metric registry 도입
18. snippet provenance/IP/SBOM gate 도입
19. AI-slop score report 및 promotion gate 연결
20. spec-first workflow를 non-trivial proposal에 강제

---

## 11. 최종 판단

LLM Wiki vNext는 이미 anti-slop를 의식하는 시스템이다. 문제는 slop 방어 장치가 부족한 것이 아니라, 그 장치들이 서로를 충분히 강하게 제약하지 못한다는 점이다. 현재의 다음 성숙 단계는 다음 문장으로 요약된다.

> **self-observing system에서 self-constraining system으로 전환해야 한다.**

그 전환의 핵심은 stale artifact 제거, learning gate 활성화, proposal 실험 계약화, DTO/type vocabulary 수렴, complexity/rule/metric 선언화, 그리고 IP/SBOM·AI-slop score gate의 운영 통합이다.

이 개선안이 실행되면 시스템은 단순히 “스스로를 관찰하는 런타임”이 아니라, **잘못된 증거를 학습하지 않고, 검증 불가능한 변이를 억제하며, 반복적으로 덜 sloppy해지는 운영형 자가 개선 시스템**으로 진화할 수 있다.
