# LLM Wiki vNext — Code / Existing Report / Integrated Plan Gap Report

- **파일명**: `llm_wiki_vnext_code_plan_gap_report_20260424.md`
- **작성일**: 2026-04-24
- **언어**: Korean
- **비교 대상**:
  - 현재 코드 번들: `LLM Wiki vNext(29).zip`
  - 기존 보고서: `llm_wiki_vnext_anti_slop_self_improvement_report_20260424.md`
  - 신규 통합 계획서: `integrated_anti_slop_self_improvement_plan_20260424.md`
- **핵심 관점**: Anti-Slop / Self-Improvement Closed Loop / Evidence Currentness / Typed Contract / Proposal-as-Experiment / SBOM·IP Provenance / Agent Workflow Governance

---

## 0. 최종 결론

신규 통합 계획서는 기존 보고서의 문제의식을 잘 흡수했고, 특히 **2차 slop**, **currentness envelope**, **learning readiness gate**, **proposal-as-experiment**, **IP/SBOM·snippet provenance**, **AI-slop score**를 추가하여 방향성은 더 성숙해졌다. 그러나 현재 코드와 대조하면 결론은 명확하다.

> 현재 코드베이스는 “anti-slop를 관찰하는 체계”까지는 상당히 구현되어 있으나, 신규 통합 계획서가 요구하는 “anti-slop를 강제하는 체계”에는 아직 도달하지 않았다.

가장 중요한 차이는 다음이다.

1. **Stale artifact 감지는 구현되었지만, 대부분의 산출물은 아직 envelope 미적용 상태다.** `artifact_freshness_runtime.py`와 schema/report는 존재하지만 현재 report 기준 JSON artifact 142개 중 141개가 `missing_artifact_envelope`, 141개가 `unknown_currentness`, 52개가 stale로 잡힌다.
2. **Learning readiness는 분리되었지만 active gate가 아니다.** 현재 `auto-improve-readiness.json`은 `execution_readiness.status=pass`, `learning_readiness.status=learning_uncertain`, `learning_readiness.gate_effect=shadow` 상태다. 계획서가 요구하는 `review_required` 또는 active block semantics는 아직 없다.
3. **Proposal은 개선 후보 큐 수준이며 실험 계약 수준은 아니다.** `change_hypothesis`, `expected_binary_signal`은 있으나 `proposal-contract.schema.json`, `expected_metric_movement`, `rollback_trigger`, `rollback_plan`, proposal-level `evidence_refs`는 없다.
4. **Session report는 있으나 session envelope는 없다.** `auto-improve-session.schema.json`은 존재하지만 계획서가 요구하는 `operator_intent`, `learning_context`, `role_dispatch`, `post_run_outcome`, `learned` 중심의 session envelope는 없다. 현재 `ops/reports/auto-improve-sessions/`에도 실제 session report가 없다.
5. **SBOM/OpenVEX/provenance는 상당 부분 구현되었지만, AI 생성 코드의 IP/snippet provenance gate는 없다.** CycloneDX/OpenVEX/SLSA 방향의 supply-chain 산출물은 있으나 `snippet_provenance_runtime.py`, `ai_slop_score_runtime.py`, 관련 schema/report/gate는 없다.
6. **DTO 전환은 일부 진행되었으나 상태 vocabulary는 아직 raw string 중심이다.** dataclass는 118개 확인되지만 `dict[str, Any]`는 34개 파일에서 377회 등장하고, `StrEnum` 기반 공통 vocabulary는 없다.
7. **Structural complexity budget은 구현되어 있으나 touched check가 입력 manifest 부재 시 skip된다.** 신규 계획서의 fallback discovery와 semantic complexity weight는 아직 없다.
8. **raw intake validation marker는 여전히 코드 상수다.** 신규 계획서의 policy-file 외재화는 아직 구현되지 않았다.
9. **CI/release는 상당히 양호하지만 CI job-level permissions hardening은 미흡하다.** release workflow는 OIDC 및 attest 권한을 명시하지만 CI workflow에는 top-level/job-level `permissions: contents: read` 같은 최소 권한 선언이 없다.
10. **문서/보고서 lifecycle 문제는 여전히 남아 있다.** `generated-artifact-index.json`은 19개 archive candidate를 잡고 있으며, 외부 보고서 root 파일이 계속 판단 context에 남아 있다.

따라서 이번 재작성 보고서의 권고는 “기능을 더 붙이는 것”이 아니라, 이미 있는 anti-slop runtime을 다음 순서로 **강제형 계약 시스템**으로 승격시키는 것이다.

```text
1단계: artifact freshness를 hard evidence gate로 승격
2단계: learning readiness를 bounded trial gate로 승격
3단계: proposal schema를 실험 계약으로 분리
4단계: session envelope를 outcome metrics의 primary evidence로 연결
5단계: IP/snippet/AI-slop score를 promotion gate input으로 추가
6단계: DTO·Enum·metric registry로 상태 vocabulary 수렴
```

---

## 1. 검토 범위와 직접 확인 결과

### 1.1 코드 번들 스냅샷

ZIP listing 기준 현재 번들은 다음 규모다.

| 항목 | 확인값 |
|---|---:|
| ZIP entry 수 | 1,905 |
| Python 파일 | 276 |
| JSON 파일 | 211 |
| Markdown 파일 | 933 |
| PDF 파일 | 62 |
| `.pyc` 파일 | 283 |
| `__pycache__` 포함 파일 | 287 |
| 240자 초과 경로 | 0 |
| 최장 경로 길이 | 183 |
| root `pytest_*` 산출물 | 0 |

긍정적으로는 기존 보고서에서 강조한 긴 경로/루트 pytest artifact 문제는 현재 ZIP 기준 상당히 개선되어 있다. 반대로 `.pyc`와 `__pycache__`가 여전히 ZIP 안에 포함되어 있어 release/review archive hygiene은 아직 완결되지 않았다.

### 1.2 현재 코드 surface

| 항목 | 확인값 |
|---|---:|
| `ops/scripts/*.py` | 154 |
| 전체 `tests` top-level 파일 | 116 |
| dataclass class | 118 |
| `dict[str, Any]` 등장 | 34개 파일 / 377회 |
| `typing.Any` import | 44개 파일 |
| `StrEnum` 등장 | 0회 |
| broad `except Exception` | 10개 파일 / 12회 |
| direct wall-clock 호출 | 2개 파일 / 2회 |
| direct-script wrapper 목록 | 46개 |
| direct script fallback marker | 44회 |

이 수치는 현재 코드가 “무질서한 스크립트 묶음”은 아니며 dataclass, schema, wrapper, policy, runtime 분리가 상당히 진행되었음을 보여준다. 다만 self-improvement payload와 report payload에서는 여전히 `dict[str, Any]`와 raw string status가 주된 결합 방식이다.

---

## 2. 기존 보고서와 신규 통합 계획서의 차이

### 2.1 기존 보고서가 주로 잡은 문제

기존 보고서는 다음 항목을 핵심 결함으로 보았다.

- ZIP/review archive hygiene 부재
- 외부 보고서와 generated artifact 누적
- Ruff/Mypy 기본 gate 약함
- structural complexity budget이 hard gate가 아님
- command runtime cold-start 취약성
- RuntimeContext 미적용 경로
- 일부 subprocess timeout 부재
- warning budget 실패 상태
- broad `except Exception` 경계 명확화 필요
- direct-script fallback drift
- `Any`/dict payload로 인한 schema drift
- CI/CD, SBOM/OpenVEX/provenance 개선 필요

현재 코드에는 이 중 일부가 반영되어 있다. 특히 `.gitignore`의 root pytest artifact 차단, `artifact_freshness_runtime.py`, strict preview allowlist, Windows strict preview smoke, supply-chain workflow, release provenance attestation은 기존 보고서 이후 진전된 항목으로 판단된다.

### 2.2 신규 통합 계획서가 새로 강화한 문제

신규 통합 계획서는 기존 보고서보다 한 단계 더 운영적이다. 핵심 추가점은 다음이다.

- “2차 slop” 개념: 방어 장치 자체가 stale하거나 loose하면 판단 오염원이 된다는 진단
- currentness envelope를 모든 generated artifact에 강제
- learning readiness를 shadow에서 active/review-required gate로 승격
- proposal을 hypothesis/evidence/expected signal/rollback trigger가 있는 실험 계약으로 격상
- session envelope를 outcome metrics의 primary evidence로 사용
- snippet provenance, AI-slop score, IP/SBOM gate를 promotion gate에 연결
- Status/Decision/Metric vocabulary를 `StrEnum`과 registry로 통합
- spec-first workflow를 non-trivial proposal에 강제

이 신규 계획은 방향성이 타당하다. 다만 현재 코드 반영률은 항목별로 편차가 크다.

---

## 3. 신규 계획 대비 현재 코드 반영률 매트릭스

| 신규 계획 항목 | 현재 코드 상태 | 반영률 | 판단 |
|---|---|---:|---|
| Root stale artifact 제거 | root `pytest_*` 없음, `.gitignore` 반영 | 80% | 구현됨. ZIP 내부 `.pyc`는 별도 hygiene 이슈 |
| Artifact freshness runtime | runtime/schema/report/test 존재 | 65% | detector는 구현, envelope 확산 미완료 |
| Generated artifact envelope | schema와 detector 존재 | 15% | 142개 JSON 중 141개가 envelope 없음 |
| Learning readiness 분리 | execution/learning report 분리 | 60% | shadow gate로만 존재 |
| Learning active/review gate | 없음 | 10% | `--allow-learning-uncertain` 없음 |
| Session envelope | auto-improve session schema는 있음 | 25% | 계획서의 envelope semantics 없음 |
| Proposal contract schema | 없음 | 20% | mutation proposal은 있으나 contract schema 아님 |
| Proposal expected metric movement | 없음 | 15% | binary signal만 존재 |
| Proposal evidence refs | promotion 쪽에는 있음 | 20% | proposal-level 필수 아님 |
| Snippet provenance gate | 없음 | 0% | 신규 구현 필요 |
| AI-slop score gate | 없음 | 0% | 신규 구현 필요 |
| SBOM/OpenVEX/provenance | 상당수 runtime/report/workflow 존재 | 65% | security advisories/model artifacts는 현 reports에 없음 |
| DTO 전환 | dataclass 다수 존재 | 45% | 핵심 payload는 여전히 dict/Any 다수 |
| Status vocabulary StrEnum | 없음 | 0% | raw string 중심 |
| Complexity budget | runtime/report/Make target 존재 | 60% | fallback discovery/semantic weights 없음 |
| Raw intake rule declarativization | 없음 | 10% | marker가 코드 상수 |
| Canonical metric registry | 없음 | 0% | 신규 구현 필요 |
| Spec-first workflow | 없음 | 0% | 신규 구현 필요 |
| RuntimeContext 계약 | 많이 적용됨 | 70% | direct wall-clock 2개만 남음 |
| CI permissions hardening | release는 양호, CI는 미흡 | 55% | CI에 permissions 명시 필요 |
| Direct-script wrapper generation | wrapper inventory 존재 | 35% | 생성화는 미구현 |
| Report archive lifecycle | generated-artifact-index 존재 | 45% | archive candidate가 아직 19개 |

---

## 4. P0 Gap 상세 분석

## 4.1 P0-A: Artifact Currentness / Envelope

### 현재 구현

현재 코드에는 `ops/scripts/artifact_freshness_runtime.py`, `ops/schemas/artifact-freshness-report.schema.json`, `ops/schemas/artifact-envelope.schema.json`, `tests/test_artifact_freshness_runtime.py`가 존재한다. `artifact_freshness_runtime.py`는 root ephemeral pattern과 envelope required fields를 명시한다.

확인된 주요 코드:

```text
ops/scripts/artifact_freshness_runtime.py:22-27
ROOT_EPHEMERAL_PATTERNS = [
    "pytest_*.log",
    "pytest_*.xml",
    "pytest_*_output.txt",
    "pytest_*_requested*.txt",
]

ops/scripts/artifact_freshness_runtime.py:38-52
ENVELOPE_REQUIRED_FIELDS = [
    "$schema", "artifact_kind", "generated_at", "producer",
    "source_command", "source_revision", "source_tree_fingerprint",
    "input_fingerprints", "schema_version", "artifact_status",
    "retention_policy", "encoding", "currentness",
]
```

`.gitignore`에도 root pytest artifact 금지 패턴과 `tmp/test-runs/`가 반영되어 있다.

### 현재 report 결과

`ops/reports/artifact-freshness-report.json` 기준:

| 지표 | 값 |
|---|---:|
| status | `attention` |
| artifact_count | 142 |
| stale_artifact_count | 52 |
| root_ephemeral_artifact_count | 0 |
| unknown_currentness_artifact_count | 141 |
| non_utf8_text_artifact_count | 0 |
| missing_schema_count | 47 |
| missing_artifact_envelope_count | 141 |

### 판단

이 항목은 **detector는 구현되었지만 enforcement 대상이 자기 자신 외 거의 확산되지 않은 상태**다. 즉 현재 시스템은 slop 오염원을 “볼 수는 있지만”, 아직 대부분의 canonical report를 “신뢰 가능한 current artifact”로 만들지는 못한다.

### 개선 지시

1. `write_schema_validated_json()`에 optional envelope injection을 붙이지 말고, **canonical report builder가 명시적으로 envelope를 채우도록** 한다. 자동 주입은 producer identity를 흐릴 수 있다.
2. `ops/reports/artifact-freshness-report.json` 자신은 이미 envelope를 갖고 있으므로, 다음 1차 대상은 아래 5개다.
   - `ops/reports/auto-improve-readiness.json`
   - `ops/reports/mutation-proposals.json`
   - `ops/reports/outcome-metrics.json`
   - `ops/reports/generated-artifact-index.json`
   - `ops/reports/structural-complexity-budget.json`
3. `artifact-freshness-check --fail-on-fail`만으로는 부족하다. 현재 status가 `attention`이어도 `make check`를 통과할 수 있으므로, P0 기간에는 `missing_artifact_envelope_count` budget을 별도 threshold로 둔다.

권장 단계:

```text
Phase 1: missing_artifact_envelope_count <= 141 유지, 신규 증가 금지
Phase 2: 핵심 5개 report envelope 적용 후 <= 136
Phase 3: canonical report 전체 적용 후 <= 20
Phase 4: ops/reports canonical JSON은 envelope missing 0
```

---

## 4.2 P0-B: Learning Readiness Gate

### 현재 구현

현재 report는 execution과 learning을 분리한다.

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

`auto_improve_readiness_runtime.py`에서도 learning status는 계산되지만 gate effect는 고정적으로 `shadow`다.

```text
ops/scripts/auto_improve_readiness_runtime.py:580
status = "learning_likely" if likely_to_learn else "learning_uncertain"

ops/scripts/auto_improve_readiness_runtime.py:603
gate_effect="shadow"
```

반면 `auto_improve_loop.py`의 CLI 인자에는 `--allow-learning-uncertain`이 없다.

```text
ops/scripts/auto_improve_loop.py:18-26
--vault
--policy
--session-id
--resume-session
--max-proposals
--max-minutes
--max-consecutive-failures
--executor
--class
```

### 현재 위험

현재 `auto-improve-readiness.json`은 다음 warning급 learning signal을 이미 갖고 있다.

| metric | 값 | 의미 |
|---|---:|---|
| attempts_considered | 7 | 최소 10 미만 |
| session_reports_considered | 0 | session evidence 없음 |
| session_calibration_status | `no_session_context` | calibration 불가 |
| rework_count | 5 | 반복 수정 높음 |
| hold_moving_average | 0.2857 | hold 비율 높음 |
| defect_escape_pair_count | 3 | defect escape proxy 존재 |

그런데 auto-improve loop 자체는 learning gate를 읽지 않고 바로 실행 가능하다. 이 상태는 신규 계획서가 정의한 2차 slop의 핵심 사례다.

### 개선 지시

1. `auto_improve_loop.py`에 다음 flag를 추가한다.

```text
--allow-learning-uncertain
```

2. `run_auto_improve_session()` 시작 전에 readiness report를 재생성 또는 읽고, 다음 조건을 적용한다.

```python
if learning_readiness.status != "learning_likely":
    if not allow_learning_uncertain:
        raise AutoImproveUsageError("learning readiness is not ready; use --allow-learning-uncertain for bounded trial")
```

3. vocabulary는 신규 계획서 표현에 맞춰 `learning_likely`보다 `learning_ready`로 수렴하는 편이 낫다. 단, 기존 report와 tests 호환을 위해 deprecation period를 둔다.

권장 전환:

```text
learning_likely          -> learning_ready
learning_uncertain       -> learning_uncertain
not_runnable             -> blocked 또는 not_runnable 유지
shadow                   -> review_required 또는 active
```

4. `learning_uncertain + --allow-learning-uncertain`인 경우 session report에 `bounded_trial=true`를 남겨 outcome metrics가 confirmed learning으로 집계하지 않도록 한다.

---

## 4.3 P0-C: Proposal Contract

### 현재 구현

현재 `mutation-proposals.json`의 proposal은 다음 필드를 갖는다.

```json
{
  "proposal_id": "...",
  "family": "contract_regression_signals",
  "priority": 70,
  "primary_targets": ["ops/scripts/auto_improve_iteration_persistence_runtime.py"],
  "single_mechanism_scope": "...",
  "change_hypothesis": "...",
  "expected_binary_signal": "...",
  "must_change_tests": ["tests/test_auto_improve_iteration_runtime.py"],
  "must_not_expand_apply_roots": true,
  "must_not_increase_untyped_surface": true,
  "required_artifacts": [...],
  "why_now": "..."
}
```

이는 기존 보고서의 “narrow proposal” 방향과 잘 맞는다. 그러나 신규 통합 계획서가 요구하는 “proposal as experiment contract”에는 아직 부족하다.

### 현재 schema에 없는 필드

`ops/schemas/mutation-proposals.schema.json`의 proposal required field에는 아래가 없다.

| 계획서 요구 필드 | 현재 상태 |
|---|---|
| `proposal-contract.schema.json` | 없음 |
| `hypothesis` | `change_hypothesis`로 일부 존재 |
| `evidence_refs` | proposal-level 없음 |
| `expected_metric_movement` | 없음 |
| `rollback_trigger` | 없음 |
| `rollback_plan` | 없음 |
| `minimum_validation_artifact` | 없음 |
| `disqualifying_evidence` | 없음 |
| `risk_class` | 없음 |
| `learning_value` | 없음 |

### 개선 지시

1. 기존 `mutation-proposals.schema.json`을 즉시 깨지 말고 `proposal_contract` object를 optional로 추가한다.
2. 1주 내 `proposal_contract`를 required로 승격한다.
3. 기존 필드와 신규 필드의 매핑은 다음처럼 한다.

| 기존 필드 | 신규 contract 필드 |
|---|---|
| `change_hypothesis` | `hypothesis` |
| `expected_binary_signal` | `expected_binary_signal` |
| `must_change_budget_signal` | `expected_metric_movement` 일부 |
| `required_artifacts` | `minimum_validation_artifact` |
| `single_mechanism_scope` | `single_mechanism_scope.primary_target` + `allowed_supporting_targets` |
| `blocked_by` | `disqualifying_evidence` 일부 |

4. proposal pre-filter는 한 번에 9종을 넣지 말고 다음 순서로 넣는다.

```text
1차: evidence_sufficiency_filter
2차: session_context_sufficiency_filter
3차: rework_cycle_repetition_filter
4차: proposal_size_asymmetry_filter
5차: expected_metric_movement_validator
```

`ip_snippet_risk_filter`와 `ai_slop_score_filter`는 해당 runtime/report가 생긴 뒤 promotion gate로 연결한다.

---

## 4.4 P0-D: Session Envelope / Outcome Metrics

### 현재 구현

현재 session 관련 코드는 존재한다.

- `ops/scripts/auto_improve_runtime.py`
- `ops/scripts/auto_improve_session_runtime.py`
- `ops/scripts/auto_improve_session_completion_runtime.py`
- `ops/schemas/auto-improve-session.schema.json`

그러나 현재 schema는 session report이며, 신규 계획서의 session envelope와는 다르다. 현재 schema required fields는 다음 중심이다.

```text
session_id, generated_at, policy, status, budget, executor,
attempted_proposal_ids, quarantined_proposal_ids, run_ids,
iterations, learning_summary, loop_state, rollups, stop_reason
```

신규 계획서가 요구하는 다음 필드는 없다.

```text
operator_intent
execution_context
learning_context
role_dispatch
post_run_outcome
learning_signals.learned
expected_metric_movement
observed_metric_movement
```

또한 현재 `ops/reports/auto-improve-sessions/`에는 실제 session report 파일이 없다. outcome metrics report도 `session_reports_considered=0`이다.

### 판단

현재 self-improvement loop는 session을 기록할 수 있는 구조는 있으나, 현재 evidence graph에는 session evidence가 비어 있다. 이 상태에서는 proposal ranking과 outcome metrics가 confirmed learning을 주장하면 안 된다.

### 개선 지시

1. `auto-improve-session.schema.json`을 무리하게 바꾸지 말고 신규 `session-envelope.schema.json`을 추가한다.
2. auto-improve session completion 시 다음 두 파일을 함께 생성한다.

```text
ops/reports/auto-improve-sessions/<session-id>.json
ops/reports/auto-improve-sessions/<session-id>/session-envelope.json
```

3. `outcome_metrics.py`는 다음 우선순위로 evidence를 읽는다.

```text
session-envelope.json > auto-improve-session.json > legacy run telemetry
```

4. `session_reports_considered=0`인 경우 readiness report의 `learning_readiness.gate_effect`는 `review_required` 이상이어야 한다.

---

## 4.5 P0-E: IP/SBOM / Snippet Detection / AI-Slop Score

### 현재 구현

공급망 관련 구현은 상당히 많다.

- `ops/scripts/supply_chain_provenance.py`
- `ops/scripts/supply_chain_gate_runtime.py`
- `ops/scripts/sbom_export_mapping.py`
- `ops/scripts/sbom_readiness_gate_runtime.py`
- `ops/scripts/cyclonedx_sbom.py`
- `ops/scripts/openvex_draft.py`
- `ops/scripts/in_toto_statement.py`
- `ops/scripts/sigstore_bundle.py`
- `ops/reports/cyclonedx-bom.json`
- `ops/reports/openvex-draft.json`
- `ops/reports/sbom-readiness-gate-report.json`
- `ops/reports/supply-chain-gate-report.json`

현재 report 상태:

| report | 상태 |
|---|---|
| `supply-chain-provenance.json` | `pass` |
| `supply-chain-gate-report.json` | `pass` |
| `sbom-export-mapping.json` | `pass` |
| `sbom-readiness-gate-report.json` | `pass` |
| `cyclonedx-bom.json` | components 21개 |
| `openvex-draft.json` | statements 0개, draft |
| `security-advisories.json` | 현재 reports root에 없음 |
| `supply-chain-artifact-model.json` | 현재 reports root에 없음 |

release workflow도 `actions/attest-build-provenance@v2`를 사용하고, `id-token: write`, `attestations: write` 권한을 명시한다.

### Gap

신규 통합 계획서의 핵심인 다음 runtime은 없다.

```text
ops/scripts/snippet_provenance_runtime.py
ops/scripts/ai_slop_score_runtime.py
ops/schemas/snippet-provenance-report.schema.json
ops/schemas/ai-slop-score-report.schema.json
ops/reports/snippet-provenance-report.json
ops/reports/ai-slop-score-report.json
```

즉 현재 SBOM은 dependency provenance 중심이고, AI-generated or agent-modified code snippet provenance는 다루지 않는다.

### 개선 지시

1. 먼저 **외부 스캐너 의존 없는 lightweight local detector**로 시작한다.
2. `ai_slop_score_runtime.py`의 1차 feature는 AST와 repository graph만으로 잡을 수 있는 항목으로 한정한다.

1차 구현 가능 feature:

| feature | 구현 난이도 | 구현 방식 |
|---|---:|---|
| `unimplemented_stub` | 낮음 | `pass`, `...`, TODO-only 함수 탐지 |
| `phantom_import` | 낮음 | import 대상 파일/모듈 존재 여부 + unused import는 Ruff와 연계 |
| `orphan_schema` | 중간 | schema 파일명과 producer/consumer grep |
| `orphan_report_field` | 중간 | schema field와 reader path reverse index |
| `unused_config_surface` | 중간 | policy key 소비 경로 탐지 |
| `inflated_wrapper` | 중간 | wrapper가 단순 pass-through인데 별도 테스트 없는 경우 |
| `disconnected_pipeline` | 중간 | Makefile/entrypoint/tests 연결 여부 |

3. `snippet_provenance_runtime.py`는 초기에 “정확한 오픈소스 매칭”보다 “manual review required 후보 생성”으로 시작한다.

1차 report 필드:

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

4. promotion gate 연결은 처음부터 block으로 두지 말고 다음 budget을 둔다.

```text
ai_slop_score >= 70: fail
ai_slop_score >= 50: hold by default
snippet high risk: fail
unknown license: manual review required
```

---

## 5. P1 Gap 상세 분석

## 5.1 Typed DTO / Vocabulary

### 현재 구현

dataclass는 이미 상당히 쓰인다. 예:

- `ExecutionReadinessAssessment`
- `LearningReadinessAssessment`
- `AutoImproveIterationRequest`
- `PersistIterationPhaseResult`
- `ExecutionOutcome`
- `MechanismPromotionState`
- `CommandSpec`
- `RuntimeContext`

그러나 report payload 조립과 schema 경계에서는 `dict[str, Any]`가 많다. 확인 결과 `dict[str, Any]`는 34개 파일에서 377회 등장한다. `StrEnum`은 없다.

### 문제

자가 개선 시스템에서 `status`, `decision`, `outcome`, `verdict`, `gate_effect`, `risk_status`가 raw string이면 LLM agent가 필드명을 바꾸거나 비슷한 값을 새로 만들어도 정적 분석이 막지 못한다. schema가 막아도 Python builder와 schema 간 drift가 발생한다.

### 개선 지시

1. 신규 `ops/scripts/vocabulary_runtime.py`를 추가한다.
2. 1차 enum은 아래 5개만 둔다.

```python
class GateEffect(StrEnum): ...
class Verdict(StrEnum): ...
class PromotionDecision(StrEnum): ...
class ArtifactStatus(StrEnum): ...
class SlopRiskStatus(StrEnum): ...
```

3. schema enum과 Python enum의 drift detector를 만든다.
4. 다음 DTO부터 우선 전환한다.

| 우선순위 | DTO | 이유 |
|---:|---|---|
| 1 | `ExecutionReadiness` / `LearningReadiness` | active gate 전환의 핵심 |
| 2 | `ProposalContract` | proposal-as-experiment 강제 |
| 3 | `SessionEnvelope` | outcome metrics primary evidence |
| 4 | `RunTelemetry` | 현재 rework hotspot |
| 5 | `ArtifactFreshnessRecord` | envelope 확산의 기반 |

---

## 5.2 Structural Complexity Budget

### 현재 구현

현재 complexity budget은 구현되어 있다.

- `ops/scripts/structural_complexity_budget_runtime.py`
- `ops/scripts/structural_complexity_budget.py`
- `ops/reports/structural-complexity-budget.json`
- `Makefile` target: `complexity-budget`, `complexity-budget-check`, `complexity-budget-touched-check`

현재 report summary:

| 지표 | 값 |
|---|---:|
| status | `attention` |
| profile_count | 3 |
| target_count | 22 |
| targets_with_attention_count | 3 |
| targets_with_failure_count | 0 |
| function_budget_candidate_count | 2 |

현재 function candidates:

| 파일 | 함수 | lines | threshold |
|---|---|---:|---:|
| `tests/minimal_vault_seed_core.py` | `seed_minimal_vault` | 388 | 180 |
| `tests/minimal_vault_seed_smoke.py` | `seed_open_question_smoke_vault` | 287 | 180 |

### Gap

`Makefile`의 touched check는 명시 입력이 없으면 skip된다.

```text
Makefile:123-128
if CHANGED_FILES_MANIFEST 또는 STRUCTURAL_COMPLEXITY_BUDGET_TARGETS가 있으면 실행
else "complexity-budget-touched-check skipped" 출력
```

신규 계획서가 요구한 fallback discovery는 없다. 또한 현재 budget은 branch node count 중심이며 semantic complexity weights는 없다.

### 개선 지시

1. `complexity-budget-touched-check`는 skip 대신 fallback discovery를 사용한다.
2. git이 없거나 changed file을 알 수 없으면 최근 수정 파일 또는 strict preview allowlist를 fallback으로 삼는다.
3. function candidate 2개는 둘 다 test seed helper이므로 `test_fixture_budget` profile로 분리한다.
4. `function_budget_top_n`의 top 3가 unmonitored일 경우 `attention`을 유지하고, monitored target이면 `warn` 또는 proposal seed로 연결한다.

---

## 5.3 Raw Intake Validation Rule Declarativization

### 현재 구현

`ops/scripts/raw_intake_promotion_validation_runtime.py`의 marker는 코드 상수다.

```text
SYNTHESIS_ANALYSIS_TEMPLATE_MARKERS
SYNTHESIS_FOLLOW_UP_SPLIT_MARKERS
CONCEPT_CONTINUITY_MARKERS
CONCEPT_SPLIT_CONTINUITY_HEADINGS
```

### 문제

이는 policy 변경과 코드 변경을 결합한다. 운영자가 raw intake quality rule을 조정하려면 runtime code를 수정해야 하며, policy diff classifier를 만들기도 어렵다.

### 개선 지시

1. 다음 파일을 추가한다.

```text
ops/policies/raw-intake-validation/index.yaml
ops/policies/raw-intake-validation/synthesis-markers.yaml
ops/policies/raw-intake-validation/concept-markers.yaml
ops/policies/raw-intake-validation/continuity-headings.yaml
ops/schemas/raw-intake-validation-policy.schema.json
ops/scripts/raw_intake_validation_rules_runtime.py
```

2. 기존 runtime은 evaluator만 담당한다.
3. policy diff classifier는 다음부터 시작한다.

| 변경 | severity |
|---|---|
| marker 추가/삭제 | warn |
| threshold 변경 | info/warn |
| gate severity 변경 | fail |
| schema required 변경 | fail |

---

## 5.4 Canonical Metric Registry

### 현재 구현

`outcome-metrics.json`, `promotion-decision-trends.json`, readiness report 등에서 metric이 사용되지만 metric registry는 없다.

현재 주요 metric:

```text
attempts_considered
session_reports_considered
rework_count
hold_moving_average
discard_moving_average
defect_escape_pair_count
rollback_signal_count
operator_effort_proxy
```

### 문제

report가 늘어날수록 같은 의미가 다른 이름으로 반복될 위험이 있다. 이는 신규 통합 계획서가 지적한 vocabulary slop다.

### 개선 지시

1. `ops/metric-registry.json` 또는 `ops/policies/metric-registry.yaml`를 추가한다.
2. 새 report field가 promotion/readiness/outcome에 쓰이면 registry 등록을 필수화한다.
3. `metric_id`, `owner_report`, `source_fields`, `update_frequency`, `promotion_gate_usage`, `deprecated`, `superseded_by`를 필수화한다.
4. schema sample regeneration test에 registry validation을 포함한다.

---

## 5.5 Spec-First Agent Workflow

### 현재 구현

현재 proposal, scope freeze, route scaffold, run ledger 등은 존재하지만 신규 계획서가 말하는 non-trivial proposal용 spec artifact는 없다.

미구현 경로:

```text
runs/<run-id>/spec/requirements.md
runs/<run-id>/spec/trade_offs.md
runs/<run-id>/spec/data_model.md
runs/<run-id>/spec/test_strategy.md
runs/<run-id>/spec/rollback_plan.md
runs/<run-id>/spec/risk_assessment.md
```

### 개선 지시

1. `risk_class != trivial`이면 implementation 전에 spec generation phase를 추가한다.
2. spec file은 단순 문서가 아니라 `proposal_contract`와 cross-check되어야 한다.
3. `test_strategy.md`에는 `minimum_validation_artifact`를 반드시 인용한다.
4. `rollback_plan.md`는 `rollback_trigger`와 1:1로 매핑되어야 한다.

---

## 6. CI/CD 및 공급망 gap

## 6.1 GitHub Actions

### 현재 장점

- CI는 Python 3.12와 3.14 matrix를 사용한다.
- fast/slow/integration/integration-heavy/public tier로 분리되어 있다.
- Windows release smoke와 strict preview smoke가 있다.
- release workflow는 `id-token: write`, `attestations: write`, `actions/attest-build-provenance@v2`, PyPI trusted publishing 흐름을 갖는다.

### Gap

CI workflow에는 top-level 또는 job-level `permissions` 선언이 없다. GitHub Actions 보안 권장사항의 최소 권한 원칙을 기준으로 보면, read-only job은 다음이 명시되어야 한다.

```yaml
permissions:
  contents: read
```

또한 `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`는 tag pinning이다. 조직 보안 수준이 높아지면 SHA pinning 또는 trusted action allowlist가 필요하다.

### 개선 지시

1. CI top-level에 `permissions: contents: read`를 추가한다.
2. release workflow는 현재 권한이 목적에 맞지만, publish job 외에는 write permission이 없어야 한다.
3. action pinning policy를 report로 만든다.

```text
ops/reports/github-actions-security-report.json
ops/schemas/github-actions-security-report.schema.json
```

검사 항목:

- top-level/job-level permissions 존재 여부
- write permission 사용 job 수
- unpinned action 수
- third-party action allowlist 위반 여부
- secrets 사용 job 수

---

## 6.2 SBOM/OpenVEX/Provenance

현재 CycloneDX BOM과 OpenVEX draft는 존재한다. OpenVEX draft는 `statement_count=0`이다. 취약점 statement가 없는 것이 항상 문제는 아니지만, “vulnerability input이 없어서 0인지”, “scan 결과 취약점이 없어서 0인지”, “아직 VEX 판단이 deferred인지”를 구분해야 한다.

### 개선 지시

1. OpenVEX draft metadata에 다음을 추가한다.

```json
{
  "vulnerability_source": "security-advisories.json | none | unavailable",
  "statement_count_reason": "no_known_vulnerabilities | advisory_report_missing | vex_deferred"
}
```

2. release workflow가 upload하는 `security-advisories.json`, `supply-chain-artifact-model.json`, `spdx-sbom.json`, `in-toto-statement.json`, `sigstore-bundle-verification.json`는 현재 root reports listing에 없다. cached target이 생성할 수 있더라도 canonical reports currentness에는 빈틈이다.
3. artifact freshness가 위 supply-chain artifacts도 envelope 대상으로 잡아야 한다.

---

## 7. 모듈별 구체 개선 지시

## 7.1 `artifact_freshness_runtime.py`

### 현재 상태

- 구현 상태 양호.
- root ephemeral artifact와 envelope 누락 탐지 가능.
- self report는 envelope를 갖는다.

### 보완

1. `artifact_records`를 DTO화한다.
2. `artifact_status`, `retention_policy`, `currentness.status`를 StrEnum으로 전환한다.
3. canonical report 별 owner/producer registry를 둔다.
4. `missing_artifact_envelope_count` budget을 지원한다.
5. `artifact_status=unknown`인 경우 promotion/readiness evidence로 사용할 수 없도록 `evidence_usable=false`를 record에 추가한다.

---

## 7.2 `auto_improve_readiness_runtime.py`

### 현재 상태

- execution readiness와 learning readiness 분리 구현.
- learning signal 수집 구현.
- shadow mode로 운영.

### 보완

1. `LearningReadinessStatus`와 `GateEffect` enum 도입.
2. `session_reports_considered=0`이면 `gate_effect=review_required`.
3. `learning_uncertain` 상태의 recommended command에는 반드시 `--allow-learning-uncertain`가 들어가야 한다.
4. `readiness_exit_code()`가 learning gate mode를 선택적으로 반영하도록 한다.
5. `can_run`을 execution과 learning에서 같은 의미로 쓰지 말고 다음처럼 분리한다.

```text
execution_readiness.can_execute
learning_readiness.can_count_as_learning
```

---

## 7.3 `auto_improve_loop.py` / `auto_improve_runtime.py`

### 현재 상태

- loop orchestration은 구조화되어 있음.
- session report writer와 outcome metrics 연결 지점이 있음.
- learning gate를 entry에서 보지 않음.

### 보완

1. `--allow-learning-uncertain` 추가.
2. entry gate에서 readiness report 확인.
3. session start 시 `pre_run_readiness` snapshot을 저장.
4. session completion 시 `session-envelope.json` 생성.
5. bounded trial run은 promotion decision과 outcome metrics에서 confirmed learning으로 집계하지 않음.

---

## 7.4 `mutation_proposal_runtime.py` / `mutation-proposals.schema.json`

### 현재 상태

- proposal queue와 priority breakdown은 존재.
- hypothesis와 expected binary signal은 존재.
- contract schema는 없음.

### 보완

1. `proposal_contract` nested object 추가.
2. `expected_metric_movement`와 `rollback_plan` required.
3. `evidence_refs`는 report JSON pointer 형식으로 제한.
4. `risk_class` enum 추가.
5. proposal 생성 시 evidence currentness check를 수행.

---

## 7.5 `auto_improve_iteration_persistence_runtime.py`

### 현재 상태

이 파일은 현재 rework hotspot이다. outcome metrics의 rework key도 이 파일을 강하게 가리킨다.

```text
targets:ops/scripts/auto_improve_iteration_persistence_runtime.py
attempt_count=5
rework_count=4
```

### 보완

1. `RunTelemetry` DTO 도입.
2. `_preserve_existing_telemetry_fields(payload: dict[str, Any], existing_report: dict)`를 DTO merge policy로 교체.
3. schema required fields와 DTO required fields drift test 추가.
4. merge diagnostics를 report에 남긴다.

---

## 7.6 `structural_complexity_budget_runtime.py`

### 현재 상태

- preview complexity report 구현.
- 3개 profile.
- function top N diagnostics 존재.

### 보완

1. touched check fallback discovery.
2. 5개 profile로 재분류.
3. semantic complexity weights 도입.
4. unmonitored candidate를 proposal seed로 연결.
5. test fixture helper의 budget을 별도 profile로 분리.

---

## 7.7 `raw_intake_promotion_validation_runtime.py`

### 현재 상태

- marker 기반 validation 구현.
- marker가 코드 상수.

### 보완

1. policy file 외재화.
2. rule evaluator 분리.
3. confidence impact 필드 추가.
4. policy diff classifier 추가.

---

## 7.8 신규 `ai_slop_score_runtime.py`

### 1차 책임

- stub 탐지
- orphan schema/report field 탐지
- disconnected pipeline 탐지
- phantom import 탐지
- unused config surface 탐지

### 1차 score 산식 예시

| feature | score |
|---|---:|
| unimplemented stub in production path | +25 |
| orphan schema | +20 |
| orphan report field | +15 |
| disconnected Make/CLI pipeline | +20 |
| nonexistent API call | +30 |
| unused config surface | +10 |
| no test for new runtime | +20 |

판정:

```text
<30 CLEAN
>=30 SUSPICIOUS
>=50 INFLATED_SIGNAL
>=70 CRITICAL_DEFICIT
```

---

## 7.9 신규 `snippet_provenance_runtime.py`

### 1차 책임

- modified/generated code path만 scan
- large exact snippet 후보 추출
- license-risk unknown 후보 기록
- manual review required count 생성
- SBOM freshness와 연결

초기에는 완전한 license detection보다 “review queue 생성”이 목적이다.

---

## 8. 테스트 추가 계획

## 8.1 즉시 추가할 P0 테스트

| 테스트 | 목적 |
|---|---|
| `test_canonical_reports_add_artifact_envelope_incrementally` | envelope 확산 회귀 방지 |
| `test_learning_uncertain_blocks_auto_improve_without_flag` | learning gate active화 |
| `test_allow_learning_uncertain_marks_bounded_trial` | bounded trial 오염 방지 |
| `test_session_envelope_written_on_completion` | session evidence 확보 |
| `test_outcome_metrics_ignore_unconfirmed_bounded_trials` | false learning 방지 |
| `test_proposal_contract_requires_expected_metric_movement` | proposal-as-experiment 강제 |
| `test_proposal_contract_requires_rollback_plan` | rollback semantics 강제 |
| `test_ai_slop_score_blocks_critical_deficit` | AI slop gate 활성화 |
| `test_snippet_unknown_license_requires_review` | IP provenance gate 활성화 |

## 8.2 P1 테스트

| 테스트 | 목적 |
|---|---|
| `test_schema_enum_matches_vocabulary_runtime_enum` | status drift 방지 |
| `test_metric_registry_covers_readiness_and_outcome_metrics` | metric alias 방지 |
| `test_complexity_touched_check_uses_fallback_when_manifest_missing` | complexity gate skip 방지 |
| `test_raw_intake_rules_loaded_from_policy_files` | hardcoded marker 제거 |
| `test_spec_required_for_non_trivial_proposal` | spec-first 강제 |
| `test_run_telemetry_dto_required_fields_match_schema` | DTO/schema drift 방지 |

## 8.3 CI/static 테스트

| 테스트 | 목적 |
|---|---|
| `test_ci_workflow_declares_minimal_permissions` | GITHUB_TOKEN 최소 권한 |
| `test_workflow_actions_are_pinned_or_allowlisted` | action supply-chain risk 감소 |
| `test_release_uploaded_artifacts_are_generated_by_make_target` | release artifact 누락 방지 |
| `test_no_pyc_or_pycache_in_review_archive` | archive hygiene |

---

## 9. 실행 로드맵

## 9.1 0~3일: Evidence 신뢰도 고정

1. ZIP/review archive에서 `.pyc`, `__pycache__` 제외 테스트 추가.
2. `artifact-freshness-report.json`의 `missing_artifact_envelope_count` baseline을 고정한다.
3. 핵심 5개 canonical report에 envelope를 추가한다.
4. CI에 `permissions: contents: read`를 추가한다.
5. `auto_improve_loop.py`에 `--allow-learning-uncertain` flag를 추가한다.
6. `learning_uncertain`이면 기본 실행을 차단한다.

## 9.2 1~2주: Learning loop 폐쇄

1. `session-envelope.schema.json` 추가.
2. session completion에서 envelope 생성.
3. outcome metrics가 session envelope를 primary evidence로 사용.
4. proposal contract nested object 추가.
5. `expected_metric_movement`, `rollback_plan`, `evidence_refs`를 required로 승격.
6. bounded trial이 confirmed learning으로 집계되지 않도록 처리.

## 9.3 3~4주: Typed contract / policy externalization

1. `vocabulary_runtime.py` 추가.
2. schema enum drift detector 추가.
3. `RunTelemetry`, `LearningReadiness`, `ProposalContract`, `SessionEnvelope` DTO 도입.
4. raw intake marker policy file 외재화.
5. metric registry 초안 도입.
6. complexity touched fallback discovery 구현.

## 9.4 1~2개월: IP/SBOM / AI slop gate

1. `ai_slop_score_runtime.py` 추가.
2. `snippet_provenance_runtime.py` 추가.
3. promotion gate에 slop/IP 조건 연결.
4. OpenVEX statement count reason 추가.
5. security advisories / supply-chain artifact model 산출물 currentness 보장.
6. strict preview allowlist를 10개에서 20개 이상으로 확대.

## 9.5 2~3개월: 운영 성숙도

1. direct-script wrapper generation.
2. spec-first workflow 전면 적용.
3. report archive lifecycle state 도입.
4. policy diff classifier 도입.
5. complexity hotspot -> proposal seed 자동 연결.
6. metric deprecation lifecycle 적용.

---

## 10. 최종 Top 25 작업 항목

1. ZIP/review archive에서 `.pyc`/`__pycache__` 제거 gate 추가.
2. `artifact-freshness-report.json`의 current baseline을 CI artifact로 보존.
3. 핵심 5개 report에 artifact envelope 추가.
4. `missing_artifact_envelope_count` budget 도입.
5. `auto_improve_loop.py`에 `--allow-learning-uncertain` 추가.
6. `learning_uncertain` 기본 실행 차단.
7. bounded trial run 표시 및 metrics 오염 방지.
8. `session-envelope.schema.json` 추가.
9. session completion에서 `session-envelope.json` 생성.
10. outcome metrics가 session envelope를 primary evidence로 사용.
11. `proposal-contract.schema.json` 또는 `proposal_contract` nested object 추가.
12. proposal에 `evidence_refs`, `expected_metric_movement`, `rollback_plan` 필수화.
13. proposal-level currentness check 추가.
14. `vocabulary_runtime.py`와 `StrEnum` 도입.
15. schema enum ↔ Python enum drift detector 추가.
16. `RunTelemetry` DTO 도입.
17. `LearningReadiness` / `ExecutionReadiness` DTO 도입.
18. complexity touched check fallback discovery 구현.
19. test fixture budget profile 분리.
20. raw intake marker policy 외재화.
21. canonical metric registry 추가.
22. `ai_slop_score_runtime.py` 추가.
23. `snippet_provenance_runtime.py` 추가.
24. CI workflow에 최소 권한 선언 추가.
25. OpenVEX draft에 `statement_count_reason` 추가.

---

## 11. Anti-slop 관점 최종 판단

현재 LLM Wiki vNext는 이미 다음을 갖고 있다.

- schema 기반 report
- atomic/write guard 계열 runtime
- artifact freshness detector
- execution/learning readiness 분리
- structural complexity budget
- supply-chain provenance/SBOM/OpenVEX 방향성
- strict preview allowlist
- session/report/rollup 구조
- public/private boundary

따라서 단순히 “품질 장치가 없다”고 보는 것은 부정확하다. 더 정확한 진단은 다음이다.

> 품질 장치는 많아졌지만, 아직 그 장치들이 서로의 output을 강하게 제약하지 못한다.

신규 통합 계획서의 “self-observing system에서 self-constraining system으로 전환”이라는 결론은 현재 코드와 비교해도 타당하다. 다만 구현 순서는 반드시 다음 원칙을 따라야 한다.

1. **관찰 runtime을 먼저 hard gate로 승격한다.** 새 기능보다 artifact/currentness/learning gate가 먼저다.
2. **계약 없이 agent를 돌리지 않는다.** proposal은 작업 지시가 아니라 실험 계약이어야 한다.
3. **session evidence 없는 학습은 학습으로 세지 않는다.** `session_reports_considered=0`인 상태에서 confirmed learning을 주장하면 안 된다.
4. **report가 많아지는 것은 개선이 아니다.** currentness envelope, archive lifecycle, metric registry가 함께 있어야 한다.
5. **AI-generated code 품질에는 법적 provenance가 포함된다.** SBOM만으로는 AI snippet/IP risk를 다루지 못한다.
6. **status vocabulary를 타입화해야 한다.** raw string 상태값은 self-improvement drift의 주요 원천이다.

최종 우선순위는 아래 한 문장으로 요약된다.

> 지금 필요한 것은 anti-slop 장치를 더 많이 만드는 일이 아니라, 이미 존재하는 장치들이 stale evidence, low-learning execution, weak proposal, orphan artifact를 실제로 막도록 강제하는 일이다.

---

## 12. 참고한 외부 기준

아래 기준은 이번 gap 판단의 외부 정렬점으로 사용했다.

- Ruff configuration: `pyproject.toml`, `ruff.toml`, `.ruff.toml` 기반 구성과 lint rule selection/ignore semantics.
- mypy command line / strict mode: `--disallow-untyped-defs`, `--disallow-incomplete-defs`, `--check-untyped-defs` 등 strict adoption 기준.
- JSON Schema / python-jsonschema: JSON payload를 계약으로 검증하는 구조.
- GitHub Actions secure use: workflow 권한 최소화와 third-party action 위험 관리.
- SLSA Provenance: artifact가 어디서, 언제, 어떻게 생성되었는지 검증 가능한 provenance 모델.
- OpenVEX specification: SBOM과 함께 vulnerability applicability를 표현하는 최소 JSON-LD 문서 모델.
- CycloneDX specification: software bill of materials와 vulnerability/VEX use case.
- OpenTelemetry observability model: logs, metrics, traces를 통한 runtime 관찰성.
- OpenAI evaluation best practices: objective, dataset, metric, compare/iterate cycle.
- OWASP Top 10 for LLM Applications 2025: prompt injection, supply-chain vulnerabilities, insecure output handling 등 LLM agent 운영 위험.

