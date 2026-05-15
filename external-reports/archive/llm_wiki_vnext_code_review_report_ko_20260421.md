# LLM Wiki vNext 코드 정밀 리뷰 보고서

- 작성일: 2026-04-21
- 결과물: 현재 업로드된 `LLM Wiki vNext(14).zip`의 **주요 코드 표면**에 대한 정밀 리뷰
- 작성 언어: 한국어
- 파일명 요구사항 반영: 영문 파일명 사용

## 1. 검토 범위와 전제

이번 리뷰는 저장소 전체를 무차별적으로 훑는 방식이 아니라, **실제로 유지보수와 자가 개선 루프를 구성하는 코드 표면**을 중심으로 진행했다.

### 1-1. 주 검토 대상
- `ops/scripts/*.py`
- `tools/*.py`
- `tests/*.py`
- 루트 설정 및 운영 문서 (`README.md`, `ARCHITECTURE.md`, `Makefile`, `pyproject.toml`, `pytest.ini`, GitHub Actions 워크플로)
- 생성된 운영 artifact 일부 (`ops/reports/*.json`, `ops/reports/task-improvement-observations/*`)

### 1-2. 주 검토 제외 대상
- `.venv/`, cache 디렉터리, egg-info, 생성 산출물 자체의 내부 구현 상세
- `raw/`, `wiki/`, `system/`의 실제 콘텐츠 본문
  - 이유: 이번 요청은 **현재 코드 품질 및 개선 방안**이 핵심이며, 콘텐츠 코퍼스보다 런타임/운영 메커니즘 품질이 더 중요함

### 1-3. 검토 방법
- 정적 구조 분석: 파일 수, LOC, 대형 함수, 모듈 결합도, 순환 import 여부
- 실행 검증: `compileall` 및 핵심 테스트 일부 직접 실행
- 운영 artifact 검토: self-improve / supply-chain / calibration 관련 현재 상태 확인
- 메타 검토: 저장소 내부의 기존 improvement observation과 runtime decomposition 계획까지 교차 확인

---

## 2. 한눈에 보는 총평

이 저장소는 일반적인 “스크립트 모음” 수준을 이미 넘어섰다. **정책(policy)·스키마(schema)·아티팩트(artifact)·게이트(gate)·실험 루프(loop)**가 서로 물려 있는 구조이며, 특히 “자가 개선을 안전하게 제한하면서 운영 증거를 남기는 설계”가 인상적이다.

다만 동시에, 이 저장소의 핵심 리스크도 분명하다. **오케스트레이션 계층이 점점 거대해지고 있고, 그 복잡도가 스키마와 테스트로는 어느 정도 제어되지만 구조적으로 완전히 상쇄되지는 않고 있다.** 즉, 지금은 충분히 잘 돌아가지만, 시간이 더 지나면 “정책 기반 자동개선 시스템을 운영하기 위한 정책 기반 자동개선 시스템”처럼 복잡도가 자기 자신을 증폭시킬 가능성이 있다.

### 최종 판단
- **코드베이스 전반 품질**: 높음
- **운영 안전성**: 높음
- **테스트/계약 기반 성숙도**: 높음
- **구조적 단순성 / 유지보수성**: 중상
- **자가 개선(Self-Improve) 실운영 성숙도**: 중상
- **총평**: **강한 통제력을 가진 실험형 자가개선 플랫폼**이며, 이미 수준은 높다. 다만 다음 단계로 가려면 “더 많은 기능”보다 **복잡도 예산 관리와 오케스트레이터 분해**가 우선이다.

---

## 3. 정량 지표 요약

### 3-1. 코드/테스트 규모
- 주요 소스 파일 수(`ops/scripts` + `tools`): **115개**
- 주요 소스 LOC(공백 제외): **25,491**
- 테스트 파일 수: **95개**
- 테스트 LOC(공백 제외): **20,537**
- 테스트 LOC / 소스 LOC 비율: **0.81**

이 비율은 상당히 공격적으로 테스트를 유지하고 있다는 뜻이다. 단순 smoke 수준이 아니라, **운영 계약(contract)을 테스트 표면으로 끌어온 저장소**에 가깝다.

### 3-2. 가장 큰 핵심 파일 (상위 10개)
- `ops/scripts/filesystem_runtime.py`: 771 LOC, 함수 39개, 최장 함수 82 LOC
- `ops/scripts/auto_improve_runtime.py`: 724 LOC, 함수 21개, 최장 함수 145 LOC
- `ops/scripts/observability_artifacts_runtime.py`: 720 LOC, 함수 33개, 최장 함수 101 LOC
- `ops/scripts/mechanism_run_workspace_runtime.py`: 678 LOC, 함수 15개, 최장 함수 123 LOC
- `ops/scripts/policy_runtime.py`: 619 LOC, 함수 20개, 최장 함수 145 LOC
- `ops/scripts/mechanism_run_validation_runtime.py`: 616 LOC, 함수 26개, 최장 함수 61 LOC
- `ops/scripts/promotion_gate_mechanism_runtime.py`: 560 LOC, 함수 35개, 최장 함수 58 LOC
- `ops/scripts/mechanism_assess.py`: 544 LOC, 함수 28개, 최장 함수 56 LOC
- `ops/scripts/raw_markdown_runtime.py`: 541 LOC, 함수 31개, 최장 함수 98 LOC
- `ops/scripts/mechanism_candidate_registry_runtime.py`: 540 LOC, 함수 19개, 최장 함수 106 LOC

### 3-3. 가장 긴 핵심 함수 (120 LOC 이상, 상위 12개)
- `ops/scripts/wiki_stage2_eval.py:40` `evaluate()` — 약 184 LOC
- `ops/scripts/finalize_run_runtime.py:327` `finalize_run()` — 약 183 LOC
- `ops/scripts/wiki_eval.py:55` `evaluate()` — 약 179 LOC
- `ops/scripts/registry_review_candidate_passes_runtime.py:218` `_backlog_refactor_threshold_pass()` — 약 178 LOC
- `ops/scripts/behavior_delta_runtime.py:271` `build_behavior_delta_report()` — 약 166 LOC
- `ops/scripts/mechanism_review_candidate_runtime.py:126` `non_trigger_detail()` — 약 148 LOC
- `ops/scripts/policy_runtime.py:502` `validate_policy_registry_references()` — 약 145 LOC
- `ops/scripts/auto_improve_runtime.py:351` `_route_scaffold_phase()` — 약 145 LOC
- `ops/scripts/promotion_gate_mechanism_state_runtime.py:198` `build_mechanism_promotion_state()` — 약 138 LOC
- `ops/scripts/mechanism_review_history_runtime.py:69` `load_mechanism_run_snapshots()` — 약 127 LOC
- `ops/scripts/mechanism_review_session_calibration_runtime.py:63` `session_calibration_summary()` — 약 126 LOC
- `ops/scripts/wiki_doc_audit_runtime.py:171` `external_report_reference_issues()` — 약 125 LOC


### 3-4. 구조적 관찰
- `ops/scripts` 내부 import 그래프 기준 **명시적 순환 import는 발견되지 않음**
- 대형 함수와 오케스트레이터는 많지만, **순환 참조로 무너지는 구조는 아님**
- 즉, 문제는 “엉켜 있음”보다 **“너무 많은 상태 전이를 한 파일/한 함수가 안고 있음”** 쪽에 가깝다

---

## 4. 직접 확인한 실행 검증

### 4-1. 문법/컴파일 수준 검증
- `python3 -m compileall -q ops tests tools` 실행: **성공**

### 4-2. 직접 실행해 확인한 핵심 테스트
- `tests/test_finalize_run.py`: 11 passed in 9.48s
- `tests/test_auto_improve_runtime.py`: 11 passed in 18.03s
- `tests/test_mechanism_review.py + tests/test_planning_gate_validate_runtime.py`: 19 passed in 14.92s
- `tests/test_supply_chain_provenance.py + tests/test_sbom_readiness_gate_runtime.py + tests/test_subagent_routing.py`: 13 passed in 9.37s
- `tests/test_policy_runtime.py`: 10 passed


### 4-3. 실행 검증 해석
직접 확인한 테스트만 봐도, 이 저장소는 “테스트 파일이 많다” 수준이 아니라 **운영 흐름별로 계약이 쪼개져 있는 구조**다. 특히 다음 표면이 의미 있게 검증되어 있다.

- auto-improve session / queue / runtime
- mechanism review / planning validation
- finalize run
- policy runtime
- supply-chain provenance / SBOM readiness
- subagent routing

이는 자가 개선 루프를 갖는 저장소에서 매우 큰 강점이다. 단순 unit test보다 **정책·아티팩트·상태 전이 계약을 회귀 방지 대상으로 삼고 있기 때문**이다.

---

## 5. 강점 분석

### 5-1. 정책과 스키마가 “문서”가 아니라 실제 제어면이다
이 저장소의 가장 큰 장점은 정책과 스키마가 선언만 되어 있는 것이 아니라, 런타임이 실제로 이를 읽고 fail-closed로 작동한다는 점이다.

특히 다음 특성이 좋다.
- policy를 single source of truth로 두려는 방향이 강함
- JSON schema 기반 report/artifact가 광범위하게 깔려 있음
- promotion, validation, outcome tracking이 **문서 규칙**이 아니라 **실행 규칙**으로 연결됨

이 구조는 향후 기능이 늘어도 “무엇이 계약인지”를 명확히 유지하는 데 유리하다.

### 5-2. 자가 개선 루프가 매우 조심스럽게 설계되어 있다
이 저장소는 self-improve를 구현하면서도 “자동 수정” 자체보다 **안전한 경계 설정**을 먼저 만든 흔적이 많다.

대표적으로 좋았던 점:
- `allowed_executors`, `allowed_apply_roots` 같은 allowlist 중심 접근
- `canary_only` 기본값
- explicit live apply 전에 rollback rehearsal 요구
- `behavior-delta`, `run-ledger`, `routing provenance`, `artifact fingerprint` 같은 추적성 강화
- shell operator를 제한하는 command execution 계약

즉, 이 저장소는 “스스로 고친다”보다 **“고친 흔적과 고칠 권한을 통제한다”**에 더 무게를 두고 있다. 이 방향은 매우 건강하다.

### 5-3. 테스트 표면이 넓고, 이름이 역할 중심으로 정리되어 있다
테스트 네이밍과 분리가 비교적 잘 되어 있다.
예를 들어:
- `test_auto_improve_runtime.py`
- `test_mechanism_review.py`
- `test_planning_gate_validate_runtime.py`
- `test_supply_chain_provenance.py`
- `test_sbom_readiness_gate_runtime.py`

이런 식의 표면은 “기능 테스트”라기보다 **운영 계약 테스트**에 가깝고, 자가개선 시스템에서는 이 구성이 매우 중요하다.

### 5-4. 공급망/릴리즈 보안 성숙도가 높다
생성 artifact와 워크플로를 보면, 단순 패키지 빌드 수준을 넘어 다음 요소들이 이미 연결되어 있다.
- supply-chain provenance
- SBOM mapping / readiness gate
- CycloneDX, SPDX, OpenVEX, in-toto, Sigstore verification metadata
- GitHub release workflow에서 provenance attestation 및 PyPI publish

그리고 실제 생성된 report도 현재 시점에서 다음 상태를 보인다.
- `ops/reports/supply-chain-provenance.json`: **status = pass**
- `ops/reports/supply-chain-gate-report.json`: **status = pass**
- `ops/reports/sbom-readiness-gate-report.json`: **status = pass**

이 정도면 “보안 artifact를 추가했다”가 아니라, **릴리즈 신뢰성에 대한 체계적 관심이 코드 구조에 반영된 상태**라고 볼 수 있다.

### 5-5. 스스로의 한계를 이미 문서화하고 있다
`ops/runtime-decomposition-plan.md`와 improvement observation artifact를 보면, 저장소가 이미 자기 문제를 어느 정도 정확히 알고 있다.

특히 내부 observation에는 다음과 같은 문제가 이미 명시돼 있다.
- promotion gate의 추가 분해 필요
- structural complexity budget artifact 부재
- outcome/provenance evidence가 아직 audit-only에 머무는 문제

즉, 이 저장소는 “문제를 모르는 상태”가 아니라 **문제를 알고 있으나 아직 모두 기계화하지 못한 상태**다. 이는 분명한 강점이다.

---

## 6. 핵심 문제점 및 개선 필요 지점

### 6-1. 가장 큰 리스크는 기능 누락이 아니라 구조적 복잡도 누적이다
이 저장소는 기능적 빈틈보다 **복잡도 누적**이 더 위험하다.

대표 근거:
- `auto_improve_runtime.py`: 724 LOC
- `filesystem_runtime.py`: 771 LOC
- `observability_artifacts_runtime.py`: 720 LOC
- `mechanism_run_workspace_runtime.py`: 678 LOC
- `policy_runtime.py`: 619 LOC
- `finalize_run_runtime.py::finalize_run()` 약 183 LOC
- `planning_gate_validate_runtime.py::validate_run_dir()` 약 124 LOC
- `behavior_delta_runtime.py::build_behavior_delta_report()` 약 166 LOC
- `auto_improve_runtime.py::_route_scaffold_phase()` 약 145 LOC

이 문제의 본질은 “코드가 지저분하다”가 아니다. 오히려 코드 스타일은 비교적 일관적이다. 문제는 **상태 전이(state transition), 보고서 조립(report assembly), 정책 해석(policy interpretation), 파일 시스템 적용(apply/discard) 같은 서로 다른 책임이 오케스트레이션 함수에 과밀하게 몰리는 경향**이다.

#### 영향
- 신규 기능 추가 시, 기존 안정성 계약을 보존하기가 점점 어려워짐
- 테스트가 많아도 변경 비용이 커짐
- 자가개선 대상이 되는 모듈이 거대해져, self-improve의 적용 단위가 점점 덜 정밀해짐
- 결국 “자가개선 시스템이 자기 자신의 복잡도 때문에 개선 속도가 느려지는 상태”가 올 수 있음

### 6-2. 자가 개선의 “통제 구조”는 강하지만, “학습/보정 구조”는 아직 audit-only가 많다
운영 artifact를 보면, self-improve는 상당히 잘 instrumented 되어 있다. 하지만 **실제 보정(calibration)과 gate 반영은 아직 보수적**이다.

현재 확인된 상태:
- `outcome-metrics.json`
  - attempts_considered: **2**
  - rework_count: **1**
  - rollback_signal_count: **0**
  - defect_escape_proxy.count: **0**
- `mechanism-review-candidates.json`
  - candidates_emitted: **0**
- `mutation-proposals.json`
  - proposals_emitted: **0**

#### 해석
현재 저장소는 **자가개선 루프를 운영할 준비는 충분히 되어 있으나, 충분한 역사 데이터와 강한 자동 보정 규칙이 아직 쌓이지 않은 상태**다.

즉:
- 구조적 성숙도는 높음
- 실증 데이터 기반의 자동 보정 성숙도는 아직 더 올라갈 여지가 큼

이 저장소 내부 observation도 같은 점을 인정하고 있다. 특히 `task-20260419-detailed-review-current-code-reconciliation`에는 outcome/provenance evidence가 아직 strict calibration, promotion gate, release gate의 핵심 입력으로 완전히 승격되지 않았다는 취지의 open 항목이 남아 있다.

### 6-3. 정책 검증 로직이 강력한 대신, 너무 중앙 집중적이다
`policy_runtime.py`는 매우 중요한 모듈이지만, 동시에 리스크가 모이는 지점이다.

특히 다음 함수는 길이와 책임 범위가 크다.
- `validate_policy_registry_references()` 약 145 LOC
- `validate_policy_safety_invariants()` 약 119 LOC

이런 류의 함수는 처음에는 중앙 집중형이 편하지만, 시간이 지나면 다음 문제가 생긴다.
- 새 규칙 추가 시 함수가 계속 비대해짐
- rule metadata / registry / invariant 간 변경이 서로 영향을 줌
- 테스트는 통과해도 정책 해석의 설명 가능성이 떨어질 수 있음

#### 개선 방향
- validator를 “기능 묶음” 기준이 아니라 **규칙 family / invariant family** 기준으로 더 쪼개는 편이 좋다
- 예: `subagent rules`, `promotion rules`, `timeout/sandbox invariants`, `path/write-boundary invariants`, `display/timezone normalization invariants`
- 최종 aggregator는 유지하되, 세부 검증은 registry-dispatched validator 형태가 더 낫다

### 6-4. 관측성은 좋지만, 업계 표준 telemetry 모델과의 연결은 아직 약하다
현재는 report/artifact 중심 관측성이 매우 좋다. 하지만 traces/metrics/logs 관점의 **범용 observability 표준 모델**과 바로 연결되도록 설계된 흔적은 상대적으로 약하다.

지금 상태는 “내부 감사에는 강한데, 외부 관측 플랫폼과 자연스럽게 붙는 구조는 아님”에 가깝다.

#### 왜 중요한가
자가개선 루프가 커질수록 다음 질문이 중요해진다.
- 어느 phase가 가장 자주 막히는가?
- 어떤 제안 family가 가장 높은 rework를 유발하는가?
- role별 timeout, validator block, reviewer reject가 어느 조건에서 증가하는가?

현재도 일부는 artifact로 남지만, **metrics/traces/log correlation**이 더 잘 되면 운영 데이터 활용성이 크게 좋아진다.

### 6-5. 저장소 외부 거버넌스 증거는 코드 트리에서 완전히 확인되지 않는다
CI와 release workflow는 잘 갖춰져 있지만, 다음은 코드 트리만으로는 강하게 보장되지 않는다.
- 실제 GitHub branch protection 설정
- required review enforcement
- CODEOWNERS 기반 책임 할당

저장소 안에는 CI 워크플로가 존재하지만, **저장소 호스팅 계층의 보호 규칙**은 별도 설정이므로 코드 tree만으로는 확인할 수 없다.

또한 현재 tree에서 `CODEOWNERS` 파일은 보이지 않았다.

#### 의미
이 저장소는 내부 런타임 거버넌스는 강하지만, 저장소 호스팅 계층의 거버넌스 증거는 상대적으로 약하게 드러난다. self-improve 시스템일수록 이 부분은 중요하다.

---

## 7. 자가 개선(Self-Improve) 성숙도 평가

### 7-1. 평가 기준
이번 리뷰에서는 자가 개선 성숙도를 다음 5단계로 봤다.

1. **수동 개선 단계**
   - 사람이 문제를 찾고 직접 수정
2. **반복 가능한 자동화 단계**
   - 스크립트와 테스트로 재현 가능
3. **통제된 자가 개선 단계**
   - 제안/실행/평가/승격 루프가 존재하고, 안전 경계가 있음
4. **데이터 보정 기반 자가 개선 단계**
   - outcome/provenance/history가 정책과 우선순위에 실질 반영됨
5. **고도 자율 최적화 단계**
   - 다중 목표 최적화, 지속적 캘리브레이션, 운영 관측성이 강하게 자동 연결됨

### 7-2. 현재 평가
**현재 성숙도는 5단계 중 3.5 수준, 즉 “Level 3 상단 ~ Level 4 진입 직전”**으로 판단한다.

### 7-3. 이렇게 판단한 이유
#### 이미 잘 되어 있는 것
- proposal queue / selection / run scaffold / execution / evaluation / persistence 구조가 존재함
- policy, schema, artifact, ledger, fingerprint, routing provenance가 잘 깔려 있음
- `canary_only`, rollback rehearsal, allowed apply roots 등 **안전 장치가 강함**
- promotion gate와 review/mutation proposal 체계가 있음
- supply-chain provenance 및 attestation까지 엮여 있음

#### 아직 덜 성숙한 것
- outcome metrics가 아직 history가 얕음
- mechanism review candidate / mutation proposal의 실제 산출이 0건인 상태
- outcome/provenance signals가 다수 audit-only 또는 optional strict preview에 머무름
- 실시간 운영 데이터(phase bottleneck, failure clustering, proposal family별 위험도)를 폭넓게 자동 반영하는 구조는 아직 제한적

### 7-4. 실무적으로 해석하면
이 시스템은 **“자동으로 막 고치는 위험한 시스템”이 아니라, ‘조심스럽게 제한된 실험 루프’를 가진 시스템**이다.
이 점은 매우 좋다.

다만 다음 단계로 가려면,
- 제안을 더 많이 생성하는 것보다
- 이미 생성되는 evidence를 **실제 우선순위/승격/차단 판단에 점진적으로 반영**하는 방향이 중요하다.

즉, 지금은 “자가 개선을 할 수 있는 시스템”이고,
다음 단계는 “자가 개선 결과를 더 똑똑하게 학습하는 시스템”이 되어야 한다.

---

## 8. 우선순위별 개선 권고안

## 8-1. P0 — 가장 먼저 해야 할 것

### P0-1. structural complexity budget를 1급 artifact로 승격
이건 거의 최우선이다.

현재 저장소 내부 observation에도 이미 같은 취지의 항목이 있다. 실제로 이 저장소의 핵심 리스크는 기능 결함보다 **오케스트레이션 복잡도 누적**이다.

#### 권장안
- `ops/reports/structural-complexity-budget.json` 같은 deterministic artifact 추가
- touched file/function 기준으로 다음 지표 기록
  - file LOC
  - function LOC
  - branch/decision count
  - public API count
  - import fan-in / fan-out
- `make check-strict` 또는 별도 opt-in gate에서 예산 비교
- self-improve 대상 파일은 예산 위반 시 candidate priority를 낮추거나 HOLD 가중치 부여

#### 기대 효과
- “길어졌지만 테스트는 통과하는” 변화에 제동을 걸 수 있음
- 거대 오케스트레이터 분해가 정량 목표를 가짐

### P0-2. 초대형 오케스트레이터 추가 분해
우선순위 후보:
1. `auto_improve_runtime.py`
2. `mechanism_run_workspace_runtime.py`
3. `finalize_run_runtime.py`
4. `planning_gate_validate_runtime.py`
5. `policy_runtime.py`
6. `behavior_delta_runtime.py`

#### 분해 원칙
- 기능 기준보다 **상태 전이 경계 기준**으로 나눌 것
- report assembly / policy evaluation / filesystem mutation / decision reduction / telemetry emission을 분리할 것
- orchestration 함수는 “순서 조정자”로만 남길 것

### P0-3. audit-only outcome/provenance 신호를 strict preview gate로 승격
지금은 evidence가 쌓이고 있지만 실제 판정 영향이 제한적이다.

#### 권장안
- `policy`에 feature flag를 두고 opt-in strict mode 제공
- 초기에는 fail보다 **priority delta / warning 강화**로 연결
- history가 충분히 쌓이면 promotion/release gate 일부 입력으로 승격

예:
- 최근 동일 target family의 rework가 높으면 proposal priority 감점
- rollback rehearsal 미커버리지 반복 시 live apply 차단 강화
- provenance drift가 누적되면 strict release path에서 fail

### P0-4. 저장소 호스팅 계층 거버넌스 보강
#### 권장안
- `CODEOWNERS` 도입
- protected branch + required reviews + required status checks를 명시적으로 운영
- release/publish 관련 파일은 최소 2인 review 또는 code owner review 요구
- 저장소 문서에 repo-hosting governance contract를 짧게 명시

---

## 8-2. P1 — 다음 단계에서 꼭 할 것

### P1-1. observability schema를 범용 telemetry 모델과 더 쉽게 연결
현재 artifact 중심 관측성을 유지하되, 최소한 다음 공통 필드를 더 엄격히 정리하는 것이 좋다.
- `trace_id` 또는 equivalent correlation id
- phase start/end timestamps
- decision reason codes
- failure class taxonomy
- proposal family / risk flags / executor role / timeout cause

이렇게 해두면 이후 metrics backend나 tracing system으로 내보내기 쉬워진다.

### P1-2. policy validator의 family-based dispatch화
`policy_runtime.py`의 비대화를 막기 위해 다음 형태를 권장한다.
- registry reference validator group
- safety invariant validator group
- promotion rule validator group
- subagent ladder validator group
- write boundary / path normalization validator group

이렇게 되면 policy가 커져도 “하나의 큰 validator 함수”가 커지는 것을 막을 수 있다.

### P1-3. reviewer/validator block 패턴의 역사적 캘리브레이션 강화
현재는 세션 및 outcome rollup이 있지만, 다음 수준으로 가면 더 좋다.
- target family별 reject/hold 패턴 집계
- role별 false-positive/false-negative 회고
- candidate family별 defect escape proxy 비교

이 데이터가 쌓이면 proposal selection이 더 똑똑해질 수 있다.

### P1-4. local developer UX 보강
현재 CI/Make는 좋지만, 로컬 습관 강제는 상대적으로 약하다.

권장:
- `pre-commit` 도입
- 빠른 국소 검증 target 제공
  - 예: touched-files lint/test
- contributor 문서에 “변경 유형별 최소 실행 세트” 추가

---

## 8-3. P2 — 중기 과제

### P2-1. property-based / mutation-style testing 확대
특히 아래 영역은 예제 기반 테스트만으로는 한계가 있다.
- promotion rule reducer
- policy registry validator
- behavior delta classifier
- path/write boundary validator

이런 부분은 경계 조건이 많아서 property-based testing이 잘 맞는다.

### P2-2. self-improve 성능/비용 관점 계측
현재는 correctness와 traceability가 강점이지만, 다음도 중요해진다.
- proposal당 평균 소요 시간
- role dispatch 비용
- blocking phase 분포
- timeout 원인별 비율
- “가치 대비 비용”이 낮은 proposal family 식별

### P2-3. 사람이 이해하기 쉬운 아키텍처 맵 자동 생성
지금 문서는 좋지만, 코드가 커질수록 다음 자동 생성물이 있으면 더 좋다.
- module dependency map
- phase transition map
- artifact lineage map
- strict/normal gate matrix

---

## 9. 구체적인 파일별 코멘트

### 9-1. `ops/scripts/auto_improve_runtime.py`
**평가:** 핵심 조정자이며 설계 의도는 좋다. 하지만 여전히 orchestration 비중이 크다.

좋은 점:
- phase가 개념적으로 구분되어 있음
- session/report 쓰기와 rollup이 체계적임
- executor, proposal queue, routing, experiment runtime이 분리되어 있음

문제:
- `_route_scaffold_phase()`가 여전히 크다
- 세션 시작/반복/종료 로직이 한 파일에 집결되어 있다
- self-improve의 핵심 제어면이라 변경 파급력이 큼

권고:
- session lifecycle, proposal refresh/select, route/scaffold, execution/evaluation, persistence/finalize를 더 얇게 분리
- “phase DTO + phase executor” 패턴으로 정리하면 테스트가 더 쉬워짐

### 9-2. `ops/scripts/mechanism_run_workspace_runtime.py`
**평가:** 실제 mutation/apply/discard, repo health, changed files, behavior delta 등 위험한 작업이 몰려 있는 핵심 위험 표면이다.

좋은 점:
- 적용/폐기 경계가 명확함
- 명시적 artifact와 report를 남김
- write boundary에 대한 의식이 강함

문제:
- `_execute_mutation_step()`, `_repo_health_step()`, `_apply_or_discard_workspace_changes()` 모두 큼
- filesystem mutation / policy check / telemetry / report write가 같은 모듈에 과밀

권고:
- workspace mutation executor
- repo health assessor
- apply planner
- rollback/canary writer
- behavior-delta writer
로 더 분해할 것

### 9-3. `ops/scripts/policy_runtime.py`
**평가:** 중앙 통제점으로서 중요하지만, 장기적으로는 “너무 중요한 파일”이 될 위험이 있다.

좋은 점:
- safety invariant를 fail-closed로 보려는 방향이 좋음
- 정책 기반 통제가 실제 작동하도록 설계됨

문제:
- registry / invariant / ladder / sandbox / timezone / write boundary 검증이 중앙 집중화됨

권고:
- validator family 모듈화
- validator registry 기반 dispatch
- policy 변경 diff에 대해 더 직접적인 regression 설명 report 생성

### 9-4. `ops/scripts/finalize_run_runtime.py`
**평가:** 운영 closeout의 핵심인데 함수가 크다.

좋은 점:
- finalize 전에 필요한 artifact 정합성을 보려는 의도가 분명함
- atomic update 성격을 신경 쓴 흔적이 있다

문제:
- `finalize_run()` 자체 길이가 큼
- artifact 수집/검증/로그 기록/원자적 갱신이 응집되어 있음

권고:
- finalize precondition builder
- artifact ledger collector
- log entry renderer
- atomic plan executor
로 분리 추천

### 9-5. `ops/scripts/planning_gate_validate_runtime.py`
**평가:** planning validation contract가 강하지만, 파일이 다소 무거움

좋은 점:
- artifact completeness와 phase checks를 신중하게 다룸
- planning gate를 report 기반으로 강제하는 구조가 좋음

문제:
- `validate_run_dir()`가 핵심 책임을 과도하게 흡수

권고:
- phase-state resolution
- artifact loading/validation
- phase-specific check builders
- final report rendering
분리 필요

---

## 10. 이 저장소가 이미 잘하고 있는 “자가 개선 관련 성숙 포인트”

사용자 요청에 맞춰, 자가 개선과 관련한 성숙도를 조금 더 구체적으로 정리하면 다음과 같다.

### 이미 성숙한 점
1. **자기 통제(self-governance) 구조가 있음**
   - 정책, 스키마, 게이트, allowlist가 실질 제어면으로 작동
2. **실험 흔적을 남김**
   - ledger, telemetry, fingerprint, provenance aggregate, outcome metrics 등
3. **자동 수정에 앞서 안전 경계를 둠**
   - canary_only, rollback rehearsal, apply root 제한
4. **승격(promotion)과 실행(execution)을 분리해서 다룸**
   - 곧바로 live mutate하지 않음
5. **문제 재인식 능력이 있음**
   - improvement observation으로 follow-up을 구조화함

### 아직 보완이 필요한 점
1. **학습 신호가 실제 의사결정에 덜 반영됨**
2. **복잡도 누적을 막는 정량 예산이 없음**
3. **history가 얕아 calibration이 약함**
4. **repo-hosting 계층의 보호 규칙이 코드상 명시되지 않음**
5. **범용 observability 생태계와의 연결 여지가 남아 있음**

---

## 11. 최종 결론

이 저장소는 분명히 잘 만든 편이다. 특히 다음이 좋다.
- 테스트가 많다
- 정책/스키마/아티팩트가 실제 런타임 통제면이다
- 자가 개선을 무리하게 자동화하지 않고, 증거와 경계를 먼저 만든다
- 공급망/릴리즈 보안까지 시야에 넣고 있다

하지만 다음 단계에서 가장 중요한 것은 **기능 추가가 아니라 복잡도 관리**다.

### 한 줄 결론
**현재 상태는 “높은 통제력과 좋은 계약 기반을 가진 자가개선 런타임”이며, 가장 시급한 과제는 구조 분해와 복잡도 예산화다.**

### 실행 우선순위 요약
1. structural complexity budget 도입
2. 초대형 오케스트레이터 추가 분해
3. outcome/provenance audit 신호의 strict preview gate 승격
4. CODEOWNERS + protected branch + required checks 등 저장소 호스팅 계층 거버넌스 강화
5. observability 상호운용성 강화

---

## 12. 참고한 외부 프레임워크 관점

이번 성숙도 평가는 저장소 내부 코드와 artifact를 기준으로 했고, 아래 프레임워크/문서의 관점을 참고해 해석했다.

- NIST AI RMF
  - https://www.nist.gov/itl/ai-risk-management-framework
- NIST SSDF (SP 800-218)
  - https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SSDF for Generative AI / Dual-Use Foundation Models (SP 800-218A)
  - https://csrc.nist.gov/news/2024/nist-publishes-sp-800-218a
- SLSA
  - https://slsa.dev/
- OWASP SAMM
  - https://owaspsamm.org/model/
- OpenSSF Scorecard
  - https://securityscorecards.dev/
- GitHub Protected Branches / Required Status Checks
  - https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- OpenTelemetry
  - https://opentelemetry.io/docs/
- Argo Rollouts Canary Strategy
  - https://argo-rollouts.readthedocs.io/en/stable/features/canary/
- in-toto
  - https://in-toto.io/
- Sigstore
  - https://docs.sigstore.dev/about/overview/

이 참고 자료들은 이번 저장소에 외부 규격 준수 여부를 판정하려는 용도가 아니라, **자가개선 시스템의 운영 통제·보안 공급망·관측성·점진적 배포·증명 가능성**을 해석하는 보조 렌즈로만 사용했다.
