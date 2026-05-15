# LLM Wiki vNext 통합 코드·보고서 정합성 검토 및 개선 보고서

- **파일명:** `llm_wiki_vnext_integrated_anti_slop_report_20260424.md`
- **작성일:** 2026-04-24
- **작성 언어:** 한국어
- **검토 대상:** 현재 코드 번들 `LLM Wiki vNext(30).zip`, 기존 anti-slop 코드 개선 보고서, 업로드된 code/plan gap report
- **핵심 관점:** Anti-Slop, Self-Improvement Closed Loop, Evidence Currentness, Typed Contract, Proposal-as-Experiment, Session Evidence, SBOM·IP Provenance, Agent Workflow Governance

---

## 0. 최종 결론

현재 LLM Wiki vNext는 단순한 문서 처리 프로젝트가 아니라, LLM 기반 위키 운영을 위해 **검증·프로모션·자가 개선·공급망 산출물·공개 표면 관리**를 포함한 운영 플랫폼에 가깝다. 기존 보고서가 지적한 “검증 장치는 있으나 강제력이 약하다”는 판단과, 업로드된 gap 보고서가 지적한 “anti-slop를 관찰하는 체계에서 anti-slop를 강제하는 체계로 승격해야 한다”는 판단은 현재 코드 상태와 일치한다.

가장 중요한 결론은 다음이다.

> 현재 코드는 anti-slop 감지 장치를 상당히 많이 갖췄지만, 그 장치들이 아직 stale evidence, low-learning execution, weak proposal, orphan artifact, AI/IP provenance risk를 실제 실행 차단 조건으로 충분히 강제하지 못한다.

현재 코드에서 확인되는 긍정적 기반은 명확하다.

1. `artifact_freshness_runtime.py`, `artifact-envelope.schema.json`, `artifact-freshness-report.schema.json` 등 산출물 currentness 감지 기반이 존재한다.
2. `auto-improve-readiness.json`은 execution readiness와 learning readiness를 분리한다.
3. `mutation-proposals.json`은 proposal queue와 hypothesis, expected binary signal을 이미 갖고 있다.
4. structural complexity budget, review archive report, generated artifact index, supply-chain gate, SBOM readiness gate가 존재한다.
5. release workflow는 provenance/attestation 방향을 포함한다.
6. `ops/scripts` 중심의 운영 runtime과 `ops/schemas` 중심의 계약 계층이 분리되어 있다.

그러나 현재 가장 큰 위험은 “장치의 존재”가 “개선의 증거”로 오인될 수 있다는 점이다. 실제 report 상태는 다음과 같은 경고를 계속 보여준다.

| 영역 | 현재 신호 | 판단 |
|---|---:|---|
| Artifact freshness | JSON artifact 142개 중 141개 envelope 누락, 141개 unknown currentness, stale 52개 | 감지는 구현, 신뢰 계약 확산 미완료 |
| Learning readiness | `learning_uncertain`, `gate_effect=shadow`, session report 0개 | 실행 가능성과 학습 가능성이 분리됐지만 active gate 아님 |
| Outcome metrics | attempts 7개, session reports 0개, rework 5, defect escape proxy 3 | 자가 개선 루프가 학습 증거로 충분히 닫히지 않음 |
| Mutation proposal | proposal 1개, binary signal 있음 | 실험 계약으로는 아직 부족 |
| Generated artifact lifecycle | archive candidate 19개 | 문서·리포트 slop 정리 필요 |
| Complexity budget | attention 3개, failure 0개 | 관찰은 가능하나 touched fallback·semantic weight 부족 |
| Supply chain | SBOM/OpenVEX/provenance 계열 존재 | dependency provenance는 진전, AI snippet/IP provenance는 공백 |

따라서 이번 통합 보고서의 핵심 권고는 “새로운 report를 더 많이 만드는 것”이 아니다. 우선순위는 다음 6단계다.

```text
1. canonical JSON report 전체에 artifact envelope와 currentness 계약을 확산한다.
2. learning readiness를 shadow signal에서 review_required/active gate로 승격한다.
3. proposal을 개선 후보가 아니라 실험 계약으로 격상한다.
4. session envelope를 outcome metrics의 primary evidence로 연결한다.
5. AI-slop score와 snippet/IP provenance를 promotion gate input으로 추가한다.
6. 상태값·metric·decision vocabulary를 StrEnum/registry/DTO로 수렴시킨다.
```

---

## 1. 통합 검토 기준

이번 보고서는 세 가지 입력을 맞춰 재작성했다.

1. **현재 코드 번들:** `LLM Wiki vNext(30).zip`
   - ZIP 총 파일 수: 1,618개
   - 압축 해제 기준 총 크기: 약 239MB
   - `ops/scripts/*.py`: 154개
   - `tests/*.py`: 116개
   - `ops/reports/*.json`: 19개
   - `ops/schemas`, `ops/policies`, `.github/workflows`, `Makefile`, `pyproject.toml` 포함

2. **기존 anti-slop 코드 개선 보고서**
   - 핵심 진단: schema/report/runtime 기반은 있으나 stale artifact, optional loader, broad fallback, session evidence, strict gate 확대가 필요함.
   - 주요 권고: artifact envelope, 자가 개선 학습 루프 폐쇄, strict static gate 확대, fallback 탈하드코딩, CI/공급망 강화.

3. **업로드된 code/plan gap report**
   - 핵심 진단: 신규 통합 계획서는 방향성이 성숙했지만, 현재 코드는 아직 anti-slop 강제 체계에 미도달.
   - 주요 권고: currentness envelope, learning active gate, proposal contract, session envelope, AI-slop score, snippet provenance, metric registry, spec-first workflow. fileciteturn0file0

---

## 2. 현재 코드 상태 스냅샷

### 2.1 규모와 구조

| 항목 | 현재 확인값 |
|---|---:|
| ZIP 파일 수 | 1,618 |
| 압축 해제 기준 크기 | 약 239MB |
| `ops/scripts/*.py` | 154 |
| `tests/*.py` | 116 |
| `ops/reports/*.json` | 19 |
| `ops/scripts + tests` 기준 Python 파일 | 270개 이상 |
| dataclass 사용 지점 | 약 119개 |
| `dict[str, Any]` 사용 | 약 35개 파일 / 382회 |
| `StrEnum` 사용 | 확인되지 않음 |

이 수치는 코드베이스가 이미 상당히 운영화되어 있음을 보여준다. 특히 `ops/scripts`가 154개라는 점은 자동 개선, 산출물 검증, 공급망, promotion decision, public extraction, archive hygiene 등을 별도 runtime으로 분리해왔다는 의미다. 다만 self-improvement payload와 report payload에는 여전히 `dict[str, Any]`가 넓게 남아 있어 typed contract 관점에서는 후속 정리가 필요하다.

### 2.2 핵심 report 상태

| report | 현재 상태 | 핵심 관찰 |
|---|---|---|
| `artifact-freshness-report.json` | `attention` | artifact 142개, stale 52개, unknown currentness 141개, missing envelope 141개 |
| `auto-improve-readiness.json` | execution pass / learning uncertain | 실행 가능하지만 학습 가능성은 shadow warning 상태 |
| `mutation-proposals.json` | `pass` | proposal 1개, blocked 0개, session unavailable |
| `outcome-metrics.json` | summary 중심 | attempts 7개, session reports 0개 |
| `generated-artifact-index.json` | `attention` | root reports 19개, archive candidate 19개 |
| `structural-complexity-budget.json` | `attention` | profile 3개, target 22개, attention 3개, failure 0개 |
| `supply-chain-gate-report.json` | `pass` | supply-chain gate 자체는 통과 |
| `sbom-readiness-gate-report.json` | `pass` 추정 | SBOM readiness 계층 존재 |

---

## 3. 기존 보고서와 gap 보고서의 정합성 판단

### 3.1 기존 보고서의 강점

기존 보고서는 현재 코드의 가장 실질적인 문제를 잘 잡았다.

- canonical report가 많아졌지만 신뢰 가능한 current artifact인지 불명확함.
- optional loader, broad fallback, malformed artifact 처리에서 침묵 실패 가능성이 있음.
- 자가 개선 루프가 session evidence와 rollback/rework signal로 충분히 닫히지 않음.
- strict static gate가 일부 allowlist/smoke 수준에 머물 가능성이 있음.
- raw intake validation, observability rollup, readiness runtime 등 고복잡도 runtime을 분해해야 함.
- CI/CD와 공급망 산출물은 존재하나 최소 권한·attestation·artifact retention 측면에서 더 엄격해져야 함.

### 3.2 업로드된 gap 보고서의 강점

업로드된 gap 보고서는 기존 보고서보다 운영 계약 관점이 더 강하다. 특히 다음 개념은 현재 코드에 직접 반영할 가치가 크다.

- **2차 slop:** 방어 장치 자체가 stale하거나 loose하면 품질 장치가 오히려 판단 오염원이 된다.
- **Currentness envelope:** report가 존재한다는 사실보다, 언제·누가·무엇을 입력으로·어떤 schema로 생성했는지가 중요하다.
- **Learning readiness gate:** “실행 가능”과 “학습 가능”은 다른 상태이며, learning uncertain은 자동 개선 결과를 confirmed learning으로 집계하면 안 된다.
- **Proposal-as-experiment:** proposal은 작업 지시가 아니라 hypothesis, evidence, expected metric movement, rollback trigger를 가진 실험 계약이어야 한다.
- **Session envelope:** outcome metrics가 신뢰되려면 session 단위의 operator intent, role dispatch, post-run outcome, learned signal이 있어야 한다.
- **AI/IP provenance:** SBOM은 dependency inventory에는 유효하지만, AI가 생성·수정한 코드 snippet provenance까지 자동으로 해결하지 않는다.

### 3.3 통합 판단

두 보고서의 결론은 충돌하지 않는다. 기존 보고서는 “현재 코드의 결함과 보완 지점”을 잘 잡았고, gap 보고서는 “그 보완을 어떤 governance model로 승격할지”를 잘 제시한다. 따라서 통합 방향은 다음과 같다.

```text
기존 보고서의 실무적 결함 목록
+ gap 보고서의 계약·증거·자가 개선 모델
= 현재 코드에 바로 적용 가능한 anti-slop enforcement roadmap
```

---

## 4. P0 개선 영역: Artifact Currentness를 hard evidence gate로 승격

### 4.1 현재 상태

`artifact_freshness_runtime.py`와 관련 schema/report는 이미 존재한다. 현재 report는 root ephemeral artifact가 0개라는 좋은 신호를 보이지만, canonical JSON artifact 대부분은 envelope/currentness 계약이 없다.

| 지표 | 값 |
|---|---:|
| artifact_count | 142 |
| json_artifact_count | 142 |
| scanned_text_artifact_count | 163 |
| stale_artifact_count | 52 |
| root_ephemeral_artifact_count | 0 |
| unknown_currentness_artifact_count | 141 |
| non_utf8_text_artifact_count | 0 |
| missing_schema_count | 47 |
| missing_artifact_envelope_count | 141 |

### 4.2 문제

현재 시스템은 stale artifact를 “볼 수는” 있지만, 대부분의 report가 아직 “신뢰 가능한 evidence”로 판정될 조건을 갖추지 못했다. 이 상태에서 auto-improve, promotion decision, readiness 판단이 report를 evidence로 사용하면, 판단의 입력 자체가 stale하거나 source가 불명확할 수 있다.

### 4.3 개선 방안

1. 핵심 report 5개에 우선 envelope를 적용한다.
   - `ops/reports/auto-improve-readiness.json`
   - `ops/reports/mutation-proposals.json`
   - `ops/reports/outcome-metrics.json`
   - `ops/reports/generated-artifact-index.json`
   - `ops/reports/structural-complexity-budget.json`

2. envelope 필수 필드는 최소 다음을 포함한다.

```json
{
  "$schema": "...",
  "artifact_kind": "canonical_report",
  "generated_at": "...",
  "producer": {
    "name": "...",
    "version": "..."
  },
  "source_command": "...",
  "source_revision": "...",
  "source_tree_fingerprint": "...",
  "input_fingerprints": [],
  "schema_version": "...",
  "artifact_status": "current|stale|unknown",
  "retention_policy": "canonical|ephemeral|archive_candidate",
  "encoding": "utf-8",
  "currentness": {
    "status": "current|stale|unknown",
    "checked_at": "...",
    "max_age_seconds": 0
  }
}
```

3. `missing_artifact_envelope_count`를 budget화한다.

```text
현재 baseline: 141
1차 목표: 핵심 5개 적용 후 <= 136
2차 목표: ops/reports canonical JSON 전체 적용 후 <= 20
최종 목표: canonical report envelope missing 0
```

4. promotion/readiness/outcome metrics는 `artifact_status=unknown` 또는 `currentness.status=unknown`인 report를 primary evidence로 쓰지 못하게 한다.

---

## 5. P0 개선 영역: Learning readiness를 shadow에서 active/review gate로 승격

### 5.1 현재 상태

현재 readiness report는 execution과 learning을 분리한다.

```json
{
  "execution_readiness": {
    "status": "pass",
    "gate_effect": "active",
    "can_run": true
  },
  "learning_readiness": {
    "status": "learning_uncertain",
    "gate_effect": "shadow",
    "can_run": true,
    "likely_to_learn": false
  }
}
```

learning readiness metrics는 다음과 같다.

| metric | 값 | 해석 |
|---|---:|---|
| attempts_considered | 7 | 최소 10 미만 |
| session_reports_considered | 0 | session evidence 없음 |
| session_calibration_status | `no_session_context` | session 기반 calibration 불가 |
| rework_count | 5 | 반복 수정 높음 |
| hold_moving_average | 0.2857 | hold 비율 높음 |
| discard_moving_average | 0.1429 | discard 신호 존재 |
| defect_escape_pair_count | 3 | defect escape proxy 존재 |

### 5.2 문제

현재 상태에서는 execution readiness가 pass이면 auto-improve loop를 실행할 수 있다. 그러나 learning readiness는 shadow이므로 실제 학습 불확실성이 실행 차단으로 연결되지 않는다. 즉, “실행은 가능하지만 배울 가능성이 낮은 작업”이 confirmed self-improvement로 취급될 위험이 있다.

### 5.3 개선 방안

1. `auto_improve_loop.py`에 다음 flag를 추가한다.

```text
--allow-learning-uncertain
```

2. 기본 동작은 다음이어야 한다.

```text
execution_readiness.status == pass 이고
learning_readiness.status != learning_ready 이면
--allow-learning-uncertain 없이는 실행 차단
```

3. `--allow-learning-uncertain`로 실행한 경우 session/report에 반드시 다음을 남긴다.

```json
{
  "bounded_trial": true,
  "learning_confirmation_eligible": false,
  "reason": "learning readiness was uncertain at session start"
}
```

4. `learning_readiness.can_run`은 의미가 모호하므로 분리한다.

```text
execution_readiness.can_execute
learning_readiness.can_count_as_learning
```

5. status vocabulary는 다음으로 정리한다.

| 기존 | 권장 |
|---|---|
| `learning_likely` | `learning_ready` |
| `learning_uncertain` | 유지 |
| `shadow` | `review_required` 또는 `active` |
| `can_run` | `can_execute`, `can_count_as_learning`로 분리 |

---

## 6. P0 개선 영역: Proposal을 실험 계약으로 격상

### 6.1 현재 상태

현재 `mutation-proposals.json`은 proposal queue와 hypothesis 성격의 필드를 갖고 있다.

현재 proposal에 이미 있는 좋은 필드:

- `proposal_id`
- `family`
- `priority`
- `primary_targets`
- `single_mechanism_scope`
- `change_hypothesis`
- `expected_binary_signal`
- `must_change_tests`
- `must_not_expand_apply_roots`
- `must_not_increase_untyped_surface`
- `required_artifacts`
- `why_now`

### 6.2 문제

현재 proposal은 “작업 후보”로서는 충분하지만, “실험 계약”으로는 부족하다. 특히 expected metric movement, rollback trigger, rollback plan, evidence_refs, disqualifying evidence가 proposal-level required로 보장되지 않는다.

### 6.3 개선 방안

1. 신규 schema 또는 nested object를 추가한다.

```text
ops/schemas/proposal-contract.schema.json
```

또는 기존 `mutation-proposals.schema.json` 안에 다음을 추가한다.

```json
{
  "proposal_contract": {
    "hypothesis": "...",
    "evidence_refs": [],
    "expected_binary_signal": "...",
    "expected_metric_movement": [],
    "minimum_validation_artifact": [],
    "rollback_trigger": [],
    "rollback_plan": "...",
    "disqualifying_evidence": [],
    "risk_class": "trivial|bounded|risky",
    "learning_value": "low|medium|high"
  }
}
```

2. 기존 필드와 신규 필드는 다음처럼 매핑한다.

| 기존 필드 | 신규 필드 |
|---|---|
| `change_hypothesis` | `proposal_contract.hypothesis` |
| `expected_binary_signal` | `proposal_contract.expected_binary_signal` |
| `required_artifacts` | `proposal_contract.minimum_validation_artifact` |
| `single_mechanism_scope` | `proposal_contract.scope` |
| `blocked_by` | `proposal_contract.disqualifying_evidence` |

3. proposal 생성 시 evidence currentness를 검사한다.

```text
proposal_contract.evidence_refs에 연결된 report가
- envelope 없음
- currentness unknown
- stale
이면 proposal은 runnable이 아니라 review_required가 되어야 한다.
```

4. proposal pre-filter는 다음 순서로 도입한다.

```text
1. evidence_sufficiency_filter
2. session_context_sufficiency_filter
3. rework_cycle_repetition_filter
4. proposal_size_asymmetry_filter
5. expected_metric_movement_validator
```

---

## 7. P0 개선 영역: Session envelope를 outcome metrics의 primary evidence로 연결

### 7.1 현재 상태

현재 session 관련 runtime과 schema는 존재한다.

- `auto_improve_runtime.py`
- `auto_improve_session_runtime.py`
- `auto_improve_session_completion_runtime.py`
- `auto-improve-session.schema.json`

그러나 현재 `outcome-metrics.json`은 `session_reports_considered=0`을 나타낸다. 즉, outcome metrics는 아직 실제 session evidence를 primary source로 쓰지 못하고 있다.

### 7.2 문제

session evidence가 없으면 다음 질문에 답할 수 없다.

- 운영자가 무엇을 의도했는가?
- 어떤 proposal이 어떤 조건에서 선택됐는가?
- 어떤 agent role이 어떤 작업을 수행했는가?
- 실행 전 learning readiness는 어떤 상태였는가?
- 실행 후 실제 metric movement는 예상과 일치했는가?
- rollback/rework/defect escape가 발생했는가?
- 이번 run을 confirmed learning으로 세도 되는가?

### 7.3 개선 방안

1. 신규 schema를 추가한다.

```text
ops/schemas/session-envelope.schema.json
```

2. session envelope 필수 필드는 다음과 같다.

```json
{
  "session_id": "...",
  "generated_at": "...",
  "operator_intent": "...",
  "execution_context": {
    "source_revision": "...",
    "tree_fingerprint": "...",
    "policy": "..."
  },
  "learning_context": {
    "pre_run_readiness": "...",
    "bounded_trial": false,
    "can_count_as_learning": true
  },
  "role_dispatch": [],
  "proposal_contract_refs": [],
  "post_run_outcome": {
    "status": "pass|hold|rollback|discard",
    "observed_metric_movement": [],
    "rework_signal": false,
    "defect_escape_signal": false
  },
  "learned": {
    "confirmed": false,
    "summary": "...",
    "evidence_refs": []
  }
}
```

3. session completion 시 다음을 함께 생성한다.

```text
ops/reports/auto-improve-sessions/<session-id>.json
ops/reports/auto-improve-sessions/<session-id>/session-envelope.json
```

4. `outcome_metrics.py`는 evidence 우선순위를 다음으로 변경한다.

```text
session-envelope.json > auto-improve-session.json > legacy run telemetry
```

5. `session_reports_considered=0`인 상태에서는 `learning_readiness.gate_effect`가 `shadow`가 아니라 최소 `review_required`여야 한다.

---

## 8. P0 개선 영역: AI-slop score와 snippet/IP provenance gate 추가

### 8.1 현재 상태

현재 공급망 계층은 dependency/SBOM/provenance 중심으로 상당히 진전되어 있다.

확인되는 구성:

- `supply_chain_provenance.py`
- `supply_chain_gate_runtime.py`
- `sbom_export_mapping.py`
- `sbom_readiness_gate_runtime.py`
- `cyclonedx_sbom.py`
- `openvex_draft.py`
- `in_toto_statement.py`
- `sigstore_bundle.py`
- `cyclonedx-bom.json`
- `openvex-draft.json`
- `sbom-readiness-gate-report.json`
- `supply-chain-gate-report.json`

### 8.2 문제

SBOM은 software component inventory에는 강하지만, AI agent가 생성하거나 수정한 코드 snippet의 출처·라이선스·복붙 위험을 자동으로 보장하지 않는다. 특히 self-improvement loop가 코드를 생성·수정한다면, dependency provenance와 별도로 snippet provenance가 필요하다.

### 8.3 개선 방안: `ai_slop_score_runtime.py`

신규 runtime을 추가한다.

```text
ops/scripts/ai_slop_score_runtime.py
ops/schemas/ai-slop-score-report.schema.json
ops/reports/ai-slop-score-report.json
```

1차 feature는 외부 서비스 없이 AST/repository graph 기반으로 시작한다.

| feature | score | 설명 |
|---|---:|---|
| production path의 unimplemented stub | +25 | `pass`, `...`, TODO-only 함수 |
| orphan schema | +20 | producer/consumer 없는 schema |
| orphan report field | +15 | schema에는 있으나 reader 없음 |
| disconnected pipeline | +20 | Make/CLI/test 연결 없는 runtime |
| nonexistent API call | +30 | 존재하지 않는 함수·module 참조 |
| unused config surface | +10 | policy key가 소비되지 않음 |
| no test for new runtime | +20 | 신규 runtime에 테스트 없음 |

판정 기준:

```text
< 30: CLEAN
>= 30: SUSPICIOUS
>= 50: INFLATED_SIGNAL
>= 70: CRITICAL_DEFICIT
```

### 8.4 개선 방안: `snippet_provenance_runtime.py`

신규 runtime을 추가한다.

```text
ops/scripts/snippet_provenance_runtime.py
ops/schemas/snippet-provenance-report.schema.json
ops/reports/snippet-provenance-report.json
```

초기 목적은 완전한 license 판정이 아니라 review queue 생성이다.

```json
{
  "status": "attention",
  "scanned_files": [],
  "matches": [],
  "summary": {
    "high_risk_match_count": 0,
    "unknown_license_match_count": 0,
    "manual_review_required_count": 0
  }
}
```

promotion gate 연결 기준:

```text
ai_slop_score >= 70: fail
ai_slop_score >= 50: hold by default
snippet high risk: fail
unknown license: manual review required
```

---

## 9. P1 개선 영역: Typed DTO와 vocabulary registry

### 9.1 현재 상태

현재 dataclass는 이미 광범위하게 사용된다. 그러나 `dict[str, Any]`가 약 35개 파일에서 382회 수준으로 남아 있고, `StrEnum` 기반 공통 vocabulary는 확인되지 않았다.

### 9.2 문제

self-improvement 시스템에서 raw string status는 drift의 주요 원천이다.

예:

```text
pass / passed / ok
attention / warn / warning
hold / held / review_required
learning_likely / likely_to_learn / learning_ready
```

이런 값이 builder, schema, report consumer 사이에서 조금씩 달라지면 schema 검증은 늦게 실패하거나, 더 나쁘게는 실패하지 않고 잘못된 판단을 만든다.

### 9.3 개선 방안

1. 신규 vocabulary runtime을 추가한다.

```text
ops/scripts/vocabulary_runtime.py
```

2. 1차 enum은 다음 5개만 둔다.

```python
class GateEffect(StrEnum):
    ACTIVE = "active"
    SHADOW = "shadow"
    REVIEW_REQUIRED = "review_required"
    BLOCKING = "blocking"

class Verdict(StrEnum):
    PASS = "pass"
    ATTENTION = "attention"
    FAIL = "fail"

class PromotionDecision(StrEnum):
    PROMOTE = "promote"
    HOLD = "hold"
    DISCARD = "discard"
    ROLLBACK = "rollback"

class ArtifactStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"

class SlopRiskStatus(StrEnum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    INFLATED_SIGNAL = "inflated_signal"
    CRITICAL_DEFICIT = "critical_deficit"
```

3. schema enum과 Python enum의 drift detector를 추가한다.

```text
tests/test_schema_enum_matches_vocabulary_runtime_enum.py
```

4. 우선 DTO화 대상은 다음 순서다.

| 우선순위 | DTO | 이유 |
|---:|---|---|
| 1 | `ExecutionReadiness` / `LearningReadiness` | active gate 전환 핵심 |
| 2 | `ProposalContract` | proposal-as-experiment 강제 |
| 3 | `SessionEnvelope` | outcome metrics primary evidence |
| 4 | `RunTelemetry` | rework hotspot 정리 |
| 5 | `ArtifactFreshnessRecord` | envelope 확산 기반 |

---

## 10. P1 개선 영역: Structural complexity budget 강화

### 10.1 현재 상태

현재 structural complexity budget report는 다음 상태다.

| 지표 | 값 |
|---|---:|
| status | `attention` |
| profile_count | 3 |
| target_count | 22 |
| targets_with_attention_count | 3 |
| targets_with_failure_count | 0 |
| function_budget_candidate_count | 2 |

현재 function budget candidate는 test fixture helper 성격이 강하다.

| 파일 | 함수 | lines | threshold |
|---|---|---:|---:|
| `tests/minimal_vault_seed_core.py` | `seed_minimal_vault` | 388 | 180 |
| `tests/minimal_vault_seed_smoke.py` | `seed_open_question_smoke_vault` | 287 | 180 |

### 10.2 문제

complexity budget 자체는 유효하지만, touched check가 입력 manifest 부재 시 skip되는 구조라면 PR/agent run에서 실제 변경 파일 감시가 빠질 수 있다. 또한 test fixture helper와 production runtime을 같은 profile로 보면 잘못된 우선순위가 나올 수 있다.

### 10.3 개선 방안

1. `complexity-budget-touched-check`가 manifest 부재 시 skip하지 말고 fallback discovery를 사용한다.

```text
CHANGED_FILES_MANIFEST 있음: manifest 사용
없음 + git 사용 가능: git diff --name-only 사용
없음 + git 불가: 최근 수정 파일 또는 strict preview allowlist 사용
그래도 없음: attention report 생성, silent skip 금지
```

2. profile을 5개로 분리한다.

```text
production_runtime_budget
test_fixture_budget
schema_builder_budget
report_renderer_budget
agent_orchestration_budget
```

3. semantic complexity weight를 추가한다.

| signal | 가중치 |
|---|---:|
| direct file mutation | +3 |
| subprocess execution | +3 |
| schema validation | +2 |
| broad fallback | +2 |
| external report parsing | +2 |
| decision/promotion mutation | +4 |
| pure data rendering | +1 |

---

## 11. P1 개선 영역: Raw intake validation rule 외재화

### 11.1 현재 상태

raw intake validation runtime은 marker 기반 검증을 수행한다. 다만 marker가 코드 상수로 들어가 있으면 정책 변경과 코드 변경이 결합된다.

### 11.2 문제

policy를 코드에 박아두면 다음 문제가 생긴다.

- rule 변경 이력이 code diff에 묻힌다.
- 운영자가 quality rule만 조정하기 어렵다.
- rule severity 변경과 runtime behavior 변경이 분리되지 않는다.
- self-improvement agent가 policy drift를 감지하기 어렵다.

### 11.3 개선 방안

다음 파일을 추가한다.

```text
ops/policies/raw-intake-validation/index.yaml
ops/policies/raw-intake-validation/synthesis-markers.yaml
ops/policies/raw-intake-validation/concept-markers.yaml
ops/policies/raw-intake-validation/continuity-headings.yaml
ops/schemas/raw-intake-validation-policy.schema.json
ops/scripts/raw_intake_validation_rules_runtime.py
```

policy diff classifier는 다음 severity로 시작한다.

| 변경 | severity |
|---|---|
| marker 추가 | info |
| marker 삭제 | warn |
| threshold 변경 | warn |
| gate severity 변경 | fail |
| schema required 변경 | fail |

---

## 12. P1 개선 영역: Canonical metric registry 추가

### 12.1 현재 상태

현재 readiness/outcome/promotion 계층에는 metric이 이미 많다.

- `attempts_considered`
- `session_reports_considered`
- `rework_count`
- `hold_moving_average`
- `discard_moving_average`
- `defect_escape_pair_count`
- `rollback_signal_count`
- `operator_effort_proxy`

### 12.2 문제

metric registry가 없으면 동일 개념이 report마다 다른 이름으로 증가한다. 이는 report가 많아지는 프로젝트에서 전형적인 vocabulary slop로 이어진다.

### 12.3 개선 방안

1. registry 파일을 추가한다.

```text
ops/policies/metric-registry.yaml
```

2. metric schema는 최소 다음을 required로 둔다.

```yaml
metric_id: outcome.rework_count
owner_report: ops/reports/outcome-metrics.json
source_fields: []
unit: count
update_frequency: per_auto_improve_session
promotion_gate_usage: hold_signal
deprecated: false
superseded_by: null
```

3. 새 report field가 readiness/outcome/promotion 판단에 쓰이면 registry 등록 없이는 schema validation이 실패해야 한다.

---

## 13. P1 개선 영역: CI/CD 및 공급망 hardening

### 13.1 현재 장점

현재 release workflow에는 provenance/attestation 방향이 포함되어 있고, supply-chain gate 및 SBOM readiness report도 존재한다. 이는 좋은 방향이다. SLSA provenance는 artifact가 어디서·언제·어떻게 만들어졌는지 설명하는 attestation model을 제공하며, GitHub artifact attestations도 build provenance를 확립하는 기능을 제공한다. citeturn594236search0turn149200search1

### 13.2 현재 gap

1. CI workflow에는 top-level/job-level 최소 권한 선언이 부족할 가능성이 있다.
2. release workflow 외 일반 CI job은 `permissions: contents: read` 같은 최소 권한을 명시해야 한다.
3. action pinning은 tag 기반이면 충분한 출발점이지만, 보안 수준을 높이려면 SHA pinning 또는 allowlist report가 필요하다.
4. OpenVEX draft의 statement count가 0인 경우, 취약점이 없어서 0인지, advisory input이 없어서 0인지, deferred 상태인지 구분해야 한다.

GitHub Actions는 `permissions` 키를 top-level 또는 job-level에서 지정해 `GITHUB_TOKEN` 권한을 최소화할 수 있으며, 지정하지 않은 권한은 `none`으로 처리된다. GitHub 문서도 action 참조를 버전/SHA 등으로 명시할 것을 권장한다. citeturn752601search0turn752601search1

### 13.3 개선 방안

1. CI workflow 상단에 추가한다.

```yaml
permissions:
  contents: read
```

2. write 권한이 필요한 job에만 job-level permission을 둔다.

3. 신규 report를 추가한다.

```text
ops/scripts/github_actions_security_runtime.py
ops/schemas/github-actions-security-report.schema.json
ops/reports/github-actions-security-report.json
```

검사 항목:

- top-level permissions 존재 여부
- job-level write permission 수
- unpinned action 수
- third-party action allowlist 위반 수
- secrets 사용 job 수
- OIDC permission 사용 job 수

4. OpenVEX draft metadata에 다음을 추가한다.

```json
{
  "vulnerability_source": "security-advisories.json|none|unavailable",
  "statement_count_reason": "no_known_vulnerabilities|advisory_report_missing|vex_deferred"
}
```

SBOM은 software component inventory와 dependency relationship을 기계 판독 가능한 방식으로 표현하는 데 유효하고, VEX는 알려진 취약점이 제품에 실제 영향을 주는지 전달하는 보완 문서다. CycloneDX와 CISA의 SBOM/VEX 자료는 이 구분을 명확히 한다. citeturn594236search4turn579798search1turn722457search2

---

## 14. P1 개선 영역: Spec-first agent workflow

### 14.1 현재 상태

현재 proposal queue, scope freeze, route scaffold, run ledger 성격의 구성은 존재한다. 그러나 non-trivial proposal을 implementation 전에 spec artifact로 강제하는 구조는 부족하다.

### 14.2 개선 방안

`risk_class != trivial`이면 다음 spec file을 먼저 생성해야 한다.

```text
runs/<run-id>/spec/requirements.md
runs/<run-id>/spec/trade_offs.md
runs/<run-id>/spec/data_model.md
runs/<run-id>/spec/test_strategy.md
runs/<run-id>/spec/rollback_plan.md
runs/<run-id>/spec/risk_assessment.md
```

필수 cross-check:

| spec file | 연결 대상 |
|---|---|
| `requirements.md` | `proposal_contract.hypothesis` |
| `test_strategy.md` | `minimum_validation_artifact` |
| `rollback_plan.md` | `rollback_trigger` |
| `risk_assessment.md` | `risk_class`, `disqualifying_evidence` |
| `data_model.md` | schema/DTO 변경 |

LLM 시스템은 비결정성을 갖기 때문에 전통적 unit test만으로 품질을 보장하기 어렵고, structured eval, metric, continuous evaluation을 통해 변경 효과를 비교해야 한다. OpenAI의 평가 가이드도 production data, metric 정의, run/compare, continuous evaluation을 강조한다. citeturn579798search7

---

## 15. 보안·LLM risk 관점 보완

LLM 기반 운영 시스템에서는 prompt injection, supply chain, improper output handling, excessive agency, misinformation, unbounded consumption 같은 위험을 code governance에 직접 연결해야 한다. OWASP LLM Top 10 2025는 prompt injection, supply chain, improper output handling 등을 핵심 위험으로 제시한다. citeturn695323search0turn695323search5

현재 코드의 anti-slop 체계는 이 위험군과 다음처럼 연결되어야 한다.

| LLM risk | 코드 차원의 대응 |
|---|---|
| Prompt injection | raw intake validation, role boundary, output sanitization |
| Supply chain | SBOM, OpenVEX, provenance, snippet provenance |
| Improper output handling | generated code gate, proposal contract, test-first validation |
| Excessive agency | learning readiness gate, bounded trial, policy-based executor |
| Misinformation | evidence currentness, source fingerprint, session envelope |
| Unbounded consumption | max proposals, max minutes, subprocess timeout, budget gate |

특히 LLM output이 shell, SQL, path, Markdown/HTML 등에 직접 전달되면 output handling risk가 커지므로, agent-generated output은 downstream system에 들어가기 전 schema validation과 context-specific escaping/sanitization을 거쳐야 한다. OWASP는 improper output handling을 LLM 출력이 후속 시스템으로 전달되기 전 검증·정제·처리가 부족한 상태로 설명한다. citeturn695323search6

---

## 16. 테스트 추가 계획

### 16.1 P0 테스트

| 테스트 | 목적 |
|---|---|
| `test_canonical_reports_add_artifact_envelope_incrementally` | envelope 확산 회귀 방지 |
| `test_artifact_unknown_currentness_not_primary_evidence` | unknown report의 evidence 오염 방지 |
| `test_learning_uncertain_blocks_auto_improve_without_flag` | learning gate active화 |
| `test_allow_learning_uncertain_marks_bounded_trial` | bounded trial 오염 방지 |
| `test_session_envelope_written_on_completion` | session evidence 확보 |
| `test_outcome_metrics_ignore_unconfirmed_bounded_trials` | false learning 방지 |
| `test_proposal_contract_requires_expected_metric_movement` | proposal-as-experiment 강제 |
| `test_proposal_contract_requires_rollback_plan` | rollback semantics 강제 |
| `test_ai_slop_score_blocks_critical_deficit` | AI slop gate 활성화 |
| `test_snippet_unknown_license_requires_review` | IP provenance gate 활성화 |

### 16.2 P1 테스트

| 테스트 | 목적 |
|---|---|
| `test_schema_enum_matches_vocabulary_runtime_enum` | status drift 방지 |
| `test_metric_registry_covers_readiness_and_outcome_metrics` | metric alias 방지 |
| `test_complexity_touched_check_uses_fallback_when_manifest_missing` | complexity gate skip 방지 |
| `test_raw_intake_rules_loaded_from_policy_files` | hardcoded marker 제거 |
| `test_spec_required_for_non_trivial_proposal` | spec-first 강제 |
| `test_run_telemetry_dto_required_fields_match_schema` | DTO/schema drift 방지 |
| `test_ci_workflow_declares_minimal_permissions` | GITHUB_TOKEN 최소 권한 |
| `test_workflow_actions_are_pinned_or_allowlisted` | action supply-chain risk 감소 |
| `test_no_pyc_or_pycache_in_review_archive` | archive hygiene |

pytest는 `tmp_path` fixture를 통해 테스트별 unique temporary directory를 제공하므로, artifact/report writer 테스트는 root 오염 없이 `tmp_path` 기반으로 작성하는 편이 적합하다. 대규모 테스트 실행 시간은 pytest-xdist의 `pytest -n auto`로 줄일 수 있다. citeturn210618search2turn118319search3

---

## 17. 실행 로드맵

### 17.1 0~3일: Evidence 신뢰도 고정

1. `artifact-freshness-report.json`의 현재 baseline을 CI artifact로 고정한다.
2. 핵심 5개 canonical report에 artifact envelope를 적용한다.
3. `missing_artifact_envelope_count` budget을 추가한다.
4. `artifact_status=unknown` report를 primary evidence로 금지한다.
5. CI workflow에 `permissions: contents: read`를 추가한다.
6. review archive에서 `.pyc`, `__pycache__` 제외 gate를 추가한다.

### 17.2 1주: Learning gate active화

1. `auto_improve_loop.py`에 `--allow-learning-uncertain` 추가.
2. learning uncertain 기본 실행 차단.
3. bounded trial run marker 추가.
4. bounded trial은 confirmed learning에서 제외.
5. readiness status vocabulary 정리.

### 17.3 2주: Proposal/session 계약화

1. `proposal-contract.schema.json` 추가 또는 `proposal_contract` nested object 추가.
2. `expected_metric_movement`, `rollback_trigger`, `rollback_plan`, `evidence_refs` required화.
3. `session-envelope.schema.json` 추가.
4. session completion에서 envelope 생성.
5. outcome metrics가 session envelope를 primary evidence로 사용.

### 17.4 3~4주: Typed contract·metric registry 정리

1. `vocabulary_runtime.py` 추가.
2. schema enum drift detector 추가.
3. `LearningReadiness`, `ProposalContract`, `SessionEnvelope`, `RunTelemetry` DTO 도입.
4. `metric-registry.yaml` 추가.
5. raw intake marker policy 외재화.
6. complexity touched fallback discovery 구현.

### 17.5 1~2개월: AI/IP provenance gate

1. `ai_slop_score_runtime.py` 추가.
2. `snippet_provenance_runtime.py` 추가.
3. promotion gate에 slop/IP 조건 연결.
4. OpenVEX에 `statement_count_reason` 추가.
5. GitHub Actions security report 추가.
6. strict preview allowlist를 touched-code 기준으로 확대.

### 17.6 2~3개월: 운영 성숙도

1. spec-first workflow 전면 적용.
2. direct-script wrapper generation.
3. report archive lifecycle state 도입.
4. policy diff classifier 도입.
5. complexity hotspot을 proposal seed로 자동 연결.
6. metric deprecation lifecycle 적용.

---

## 18. Top 30 작업 항목

| 우선순위 | 작업 |
|---:|---|
| 1 | 핵심 5개 canonical report에 artifact envelope 적용 |
| 2 | `missing_artifact_envelope_count` budget 추가 |
| 3 | unknown/stale report를 primary evidence에서 제외 |
| 4 | `--allow-learning-uncertain` 추가 |
| 5 | learning uncertain 기본 실행 차단 |
| 6 | bounded trial marker와 metrics 제외 처리 |
| 7 | `session-envelope.schema.json` 추가 |
| 8 | session completion에서 `session-envelope.json` 생성 |
| 9 | outcome metrics의 primary evidence를 session envelope로 전환 |
| 10 | `proposal-contract.schema.json` 추가 |
| 11 | proposal에 `evidence_refs` required화 |
| 12 | proposal에 `expected_metric_movement` required화 |
| 13 | proposal에 `rollback_trigger`, `rollback_plan` required화 |
| 14 | proposal evidence currentness check 추가 |
| 15 | `vocabulary_runtime.py`와 `StrEnum` 도입 |
| 16 | schema enum ↔ Python enum drift detector 추가 |
| 17 | `RunTelemetry` DTO 도입 |
| 18 | `LearningReadiness` / `ExecutionReadiness` DTO 도입 |
| 19 | complexity touched fallback discovery 구현 |
| 20 | test fixture budget profile 분리 |
| 21 | raw intake marker policy 외재화 |
| 22 | canonical metric registry 추가 |
| 23 | `ai_slop_score_runtime.py` 추가 |
| 24 | `snippet_provenance_runtime.py` 추가 |
| 25 | CI workflow에 최소 권한 선언 추가 |
| 26 | GitHub Actions security report 추가 |
| 27 | OpenVEX draft에 `statement_count_reason` 추가 |
| 28 | review archive에서 `.pyc`/`__pycache__` 제외 gate 추가 |
| 29 | spec-first workflow를 non-trivial proposal에 강제 |
| 30 | report archive lifecycle state 도입 |

---

## 19. 최종 판단

현재 LLM Wiki vNext의 품질 장치는 적지 않다. 오히려 많은 편이다. 문제는 “장치가 없다”가 아니라 “장치들이 서로의 output을 강하게 제약하지 못한다”는 데 있다.

가장 위험한 anti-slop 실패 모드는 다음이다.

1. report가 생성됐다는 이유만으로 current evidence라고 간주한다.
2. execution readiness가 pass라는 이유만으로 self-improvement가 학습 가능하다고 간주한다.
3. proposal에 hypothesis가 있다는 이유만으로 실험 계약이 성립했다고 간주한다.
4. session evidence가 없는데도 outcome metrics를 confirmed learning으로 사용한다.
5. SBOM이 있다는 이유만으로 AI-generated snippet/IP provenance까지 해결됐다고 간주한다.
6. schema가 있다는 이유만으로 Python DTO와 status vocabulary drift가 없다고 간주한다.

따라서 최종 권고는 다음 한 문장으로 요약된다.

> 지금 필요한 것은 anti-slop 장치를 더 많이 만드는 일이 아니라, 이미 존재하는 장치들이 stale evidence, low-learning execution, weak proposal, orphan artifact, AI/IP provenance risk를 실제로 막도록 강제하는 일이다.

---

## 20. 외부 기준 정렬

이번 통합 판단은 다음 외부 기준과 정렬했다.

- GitHub Actions는 workflow/job 단위 `permissions`로 `GITHUB_TOKEN` 권한을 최소화할 수 있고, third-party action 사용 시 명시적 ref/SHA pinning이 권장된다. citeturn752601search0turn752601search1
- SLSA provenance와 GitHub artifact attestations는 artifact가 어디서·어떻게 생성되었는지 검증 가능한 provenance를 제공하는 방향과 맞닿아 있다. citeturn594236search0turn149200search1
- CycloneDX SBOM과 CISA SBOM/VEX 자료는 dependency inventory와 vulnerability applicability evidence를 분리해 다룰 필요성을 뒷받침한다. citeturn594236search4turn579798search1
- OpenVEX는 SBOM을 보완해 취약점이 제품에 영향을 주는지 표현하는 최소 JSON-LD VEX 형식을 지향한다. citeturn722457search2
- Ruff preview mode는 opt-in unstable lint/fix/style 기능이므로 allowlist 기반 도입 후 touched-code gate로 확대하는 전략이 적합하다. citeturn193242search3
- mypy의 `disallow_untyped_defs`, `disallow_any_generics`, `warn_return_any` 등 optional strict checks는 typed contract 강화에 직접 연결된다. citeturn193242search0turn193242search1
- Python `jsonschema`는 instance를 schema로 검증하고 schema 자체의 유효성도 확인하므로 report contract 검증 계층에 적합하다. citeturn193242search6
- NIST SSDF는 보안 개발 활동을 공통 vocabulary와 practice로 정리한다는 점에서 metric/status registry와 CI gate 강화의 외부 기준으로 유용하다. citeturn579798search0
- OWASP LLM Top 10 2025는 prompt injection, supply chain, improper output handling, excessive agency 등을 LLM application risk로 제시하므로 agent workflow governance와 연결해야 한다. citeturn695323search0turn695323search5
- OpenAI evaluation best practices는 metric 정의, run/compare, continuous evaluation을 강조하므로 self-improvement loop는 session evidence와 expected/observed metric movement를 중심으로 닫혀야 한다. citeturn579798search7
