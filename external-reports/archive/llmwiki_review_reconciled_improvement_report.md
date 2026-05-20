# LLMwiki Review-Reconciled Improvement Report

- 작성일: 2026-05-15
- 출력 파일명: `llmwiki_review_reconciled_improvement_report.md`
- 작성 언어: 한국어
- 검토 대상:
  - `llmwiki_integrated_long_term_improvement_report.md`
  - `LLMwiki_통합_장기_개선_보고서.md`
  - `세-리뷰-통합-보고서-작성.md`
  - 기존 보고서 `llmwiki_long_term_improvement_report.md`
  - 실제 산출물 `LLMwiki-source(1).zip`
  - 실제 증빙 `release-closeout-sealed-rehearsal-check(1).json`
  - 실제 증빙 `release-post-seal-attestation(1).json`
  - 실제 증빙 `test-execution-summary-full(1).log`
  - 실제 증빙 `test-execution-summary-full.junit(1).xml`
- 작성 방식: 세 리뷰 전문 재검토 + 기존 리뷰 재평가 + 실제 파일/압축본 직접 대조 + 로컬 명령 재검증

---

## 1. 이번 보고서의 목적

이번 문서는 세 개의 신규 리뷰를 **동등하게 나열**하는 데서 멈추지 않고, 각 문서의 성격 차이를 분리해 본 뒤 **기존 리뷰와 실제 파일을 기준선으로 다시 정렬**한 개선 보고서다.

핵심 목표는 네 가지다.

1. 세 리뷰의 **공통 결론**과 **서로 다른 강조점**을 분리한다.
2. 기존 보고서가 이미 잘 짚은 내용과, 이번 세 리뷰가 실제로 더 전진시킨 내용을 구분한다.
3. 실제 ZIP/증빙 파일로 재검증했을 때 **그대로 유지되는 주장**과 **교정이 필요한 주장**을 명확히 한다.
4. 최종적으로 지금 시점에서 가장 실무적으로 유효한 **장기 최적 개선 로드맵**을 다시 제안한다.

이번 문서의 기본 원칙은 다음과 같다.

- **실제 파일이 최우선 근거**다.
- 세 리뷰는 모두 참고하되, **실제 독립 근거를 얼마나 새로 추가했는지에 따라 가중치를 다르게 둔다.**
- **gate를 약화하는 방향은 제안하지 않는다.** 대신 lane-aware, profile-aware, evidence-aware로 정교화한다.
- anti-slop는 **문구 통제**를 넘어서 **실행 품질 통제**까지 확장하는 방향으로 본다.

---

## 2. 입력 문서별 성격과 신뢰도 가중치

| 문서 | 역할 | 강점 | 한계 | 이번 보고서에서의 가중치 |
|---|---|---|---|---|
| `llmwiki_integrated_long_term_improvement_report.md` | 장기 개선 관점의 통합 보고서 | anti-slop 확장, self-improvement 설계, pass-but-noisy, ROI scoring, negative learning까지 잘 뻗어 있음 | 일부 수치가 추출 작업공간 기준이라 ZIP canonical 값과 분리 필요 | 상 |
| `LLMwiki_통합_장기_개선_보고서.md` | 가장 넓은 범위를 다루는 통합 보고서 | lane mismatch, complexity concentration, blocked→backlog, import alias, broad exception, 운영 로드맵이 가장 체계적 | 서술이 넓은 만큼 일부 항목은 실제 코드 확인보다 설계적 해석 비중이 큼 | 상 |
| `세-리뷰-통합-보고서-작성.md` | 요약형/작성용 압축 문서 | 우선순위 12개 액션이 간결하고 실행 순서가 분명함 | 독립 발견이 많지 않고 앞선 통합 리뷰를 압축한 성격이 강함 | 중 |
| `llmwiki_long_term_improvement_report.md` | 기존 단독 보고서 | anti-slop 축 확장, source-package 1급화, session synopsis, cross-eval ladder 등 선행 통찰이 좋음 | 세 리뷰 간 차이와 상충을 직접 정리한 문서는 아님 | 상 |
| 실제 ZIP/증빙 파일 | 최종 사실 기준선 | 해석이 아니라 현재 상태를 직접 보여 줌 | 설계적 제안은 제공하지 않음 | 최상 |

### 중요한 해석

세 신규 문서 중 **실질적으로 독립된 장문 리뷰는 앞의 두 문서**다. `세-리뷰-통합-보고서-작성.md`는 품질이 낮다는 뜻이 아니라, **새 증거를 추가한 문서라기보다 실행 순서를 압축한 보조 문서**에 가깝다. 따라서 이번 최종 보고서는 그 문서의 간결한 우선순위 감각은 살리되, 사실 판단은 앞의 두 통합 리뷰와 실제 파일에 더 많이 의존한다.

---

## 3. 실제 파일로 다시 확인한 기준선

### 3.1 릴리스/증빙 상태

실제 증빙 기준 현재 상태는 분명하다.

- `release-closeout-sealed-rehearsal-check`: `status=pass`, `preflight_status=sealed_clean_pass`, distribution ZIP SHA-256 일치
- `release-post-seal-attestation`: `status=pass`, `release_authority_status=clean_pass`, `sealed_release_status=sealed_clean_pass`, `machine_release_status=allowed`, `operator_release_status=allowed`, `accepted_risk_count=0`
- `test-execution-summary-full.log`: `1212 passed in 312.84s (0:05:12)`
- `test-execution-summary-full.junit.xml`: tests 1,212 / failures 0 / errors 0 / skips 0

즉, **현재 릴리스 authority는 깨끗하다.** 이번 개선 보고서는 “지금 릴리스가 실패 상태다”라는 문서가 아니라, **지금의 강한 운영 체계를 장기적으로 어떻게 덜 비대하고 더 설명 가능하게 만들 것인가**를 다루는 문서여야 한다.

### 3.2 학습 claim 상태

실제 attestation을 다시 보면 learning 쪽 해석은 더 정교해야 한다.

- `evidence_cohort_status=auto_confirmed`
- `confirmed_cohort_status=active`
- `valid_run_count=3`
- `min_required_run_count=3`
- `eligible_family_count=1`
- `full_suite_status=pass`
- `public_check_status=pass`
- 그러나 `claim_level=none`
- `improvement_claim_status=not_ready`
- `confirmed_learning_improvement_status=not_ready`
- `evidence_bundle_status=not_evaluated`
- `operator_confirmed_wording_allowed=false`

이 상태는 모순이 아니다. 오히려 현재 시스템이 **“근거 있는 실험 집합”과 “공개적으로 허용되는 개선 주장”을 의도적으로 분리**하고 있음을 뜻한다. 문제는 이 분리가 존재한다는 사실이 아니라, **왜 아직 `none`인지가 별도 activation artifact 없이 분산 필드에 흩어져 있다는 점**이다.

### 3.3 source ZIP 자체의 canonical 상태

ZIP를 직접 검사한 결과는 다음과 같다.

- 총 파일 수: **1,538**
- unique entry 수: **1,538**
- duplicate entry 수: **0**
- Python 파일: **403**
- Markdown: **893**
- JSON/YAML/TOML/XML: **159**
- `raw/`: **446**
- `wiki/`: **417**
- `system/`: **71**
- `ops/`: **378**
- `tests/`: **178**
- `raw/` 내 PDF: **61**

또한 ZIP에는 다음이 **포함되지 않는다.**

- `ops/reports/`
- `ops/operator/`
- `external-reports/`
- `runs/`
- `tmp/`
- `.venv/`
- `.mypy_cache/`
- `.ruff_cache/`
- `ops/raw-registry.json`
- `ops/script-output-surfaces.json`

이 exclusion은 우연이 아니라 `release-archive-self-description.json`에 **명시된 packaging policy**다.

### 3.4 코드 규모의 canonical 해석

세 리뷰에는 Python LOC와 broad exception 개수 등에 약간의 수치 차이가 있다. 이 차이는 대체로 **추출 작업공간에서 측정했는지, ZIP 자체를 기준으로 측정했는지**에서 온다.

ZIP 직접 스캔 기준으로 확인한 값은 다음과 같다.

- Python non-empty LOC: **126,776**
- `ops/` non-empty LOC: **72,845**
- `tests/` non-empty LOC: **52,845**
- 함수 수: **5,041**
- 클래스 수: **477**
- broad `Exception`/bare catch: **13**
- 80라인 초과 함수: **195**

따라서 기존 리뷰의 `125k 안팎`, `5k 함수`, `477 클래스`, `대형 오케스트레이터 집중`이라는 큰 판단은 유지되지만, **세부 수치가 상충할 때는 ZIP 직접 측정값을 canonical 값으로 쓰는 것이 맞다.**

---

## 4. 세 리뷰가 공통으로 맞게 본 것

세 리뷰와 기존 보고서가 거의 같은 결론에 수렴한 부분은 아래 다섯 가지다.

### 4.1 Source-package lane과 full-vault lane의 경계가 아직 거칠다

실제 재검증에서도 `make lint`는 `source_trace_target_missing` 40건으로 실패했다. 이 실패는 임의의 광범위한 파손이 아니라, 사실상 아래 세 ref에 집중되어 있다.

- `runs/run-20260422-raw-intake-registration-and-promotion/promotion/raw-intake-promotion-profiles-2026-04-22.json` (32회)
- `runs/run-20260422-raw-intake-registration-and-promotion/absorption/raw-intake-absorption-matrix-2026-04-22.json` (31회)
- `ops/raw-registry.json` (9회)

즉 문제의 본질은 “저장소 전체가 붕괴했다”가 아니라,

> **source package가 의도적으로 제외한 surface를 full-vault 기준 lint/eval이 그대로 missing으로 보고 있다는 점**

이다.

### 4.2 핵심 오케스트레이터가 너무 크다

실제 complexity budget 결과는 `status=attention`이며 warning target은 10개다.

- `ops/scripts/mechanism/auto_improve_readiness_runtime.py`
- `ops/scripts/mechanism/mutation_proposal_runtime.py`
- `ops/scripts/core/policy_validation_runtime.py`
- `ops/scripts/release/release_closeout_batch_manifest.py`
- `ops/scripts/release/release_evidence_dashboard.py`
- `ops/scripts/release/release_closeout_summary.py`
- `ops/scripts/test/test_execution_summary.py`
- `ops/scripts/learning/learning_delta_scoreboard.py`
- `ops/scripts/learning/learning_claim_evidence_bundle.py`
- `ops/scripts/learning/learning_claim_unlock_review.py`

세 리뷰가 모두 지적했듯 문제는 단순 LOC가 아니라 **decision kernel, normalization, report rendering, sealing/write가 한 모듈에 몰려 있는 구조**다.

### 4.3 strict preview는 작은 문제지만 방치하면 안 된다

실제 확인 결과:

- `ruff-strict-preview`: **6건**의 import 정렬 오류, 모두 자동 수정 가능
- `mypy-strict-preview`: allowlist 10개 경로가 모두 stale

더 중요한 점은 stale 10개가 완전히 사라진 파일이 아니라 대부분 **`ops/scripts/mechanism/` 또는 `ops/scripts/eval/`로 이동한 파일**이라는 것이다. 즉 지금 필요한 것은 기능 개발이 아니라 **경로 갱신과 조기 경보 체계 복구**다.

### 4.4 learning claim은 보수적으로 닫혀 있다

세 리뷰 모두 이 부분을 정확히 짚었다. 현재 시스템은 self-improvement evidence를 바로 claim으로 승격하지 않는다. 이 보수성은 유지해야 한다. 다만 `claim_level=none`의 이유를 사람이 JSON 여러 필드를 읽어 종합해야 하는 상태는 장기적으로 비효율적이다.

### 4.5 anti-slop는 더 넓어져야 한다

현재 anti-slop deduction 축은 주로 claim wording 방어에 강하다. 그러나 장기적으로는 다음까지 보아야 한다는 데 세 리뷰가 수렴한다.

- evidence density
- reproducibility
- scope discipline
- context efficiency / inflation
- operator override pressure
- blocked run에서의 negative learning harvest

이 방향은 기존 보고서의 문제의식과도 정확히 이어진다.

---

## 5. 세 리뷰가 서로 다르게 잘 본 것

### 5.1 `llmwiki_integrated_long_term_improvement_report.md`의 가장 큰 장점

이 문서는 **“지금의 문제를 어떻게 anti-slop/self-improvement 설계로 번역할 것인가”**를 가장 잘 다뤘다. 특히 다음은 그대로 채택할 가치가 높다.

- `missing_export_excluded_bound` 같은 **profile-aware source trace 분류**
- duplicate ZIP member를 `pass but noisy`가 아니라 **blocker 후보**로 보는 태도
- improvement proposal scoring을 ROI 기반으로 재정렬하는 관점
- `self-improvement-negative-lessons.json` 같은 **negative learning ledger**
- `session-synopsis.json`을 anti-slop 도구로 보는 해석

### 5.2 `LLMwiki_통합_장기_개선_보고서.md`의 가장 큰 장점

이 문서는 **운영 구조 전체를 재설계하는 지도**로 가장 강하다. 특히 아래는 이번 최종안에 반드시 남겨야 한다.

- blocked 상태를 backlog 생성기로 전환하는 설계
- broad exception boundary와 import compatibility alias를 **장기 유지보수 위험**으로 본 관점
- function-level refactor proposal이 module-level sprawl을 잘 못 잡는다는 지적
- attention을 영구 상태가 아니라 **SLA가 붙는 상태**로 관리해야 한다는 원칙
- anti-slop 핵심 운영 원칙을 명문화한 부분

### 5.3 `세-리뷰-통합-보고서-작성.md`의 가장 큰 장점

이 문서는 독립 분석량은 적지만 **실행 순서**를 가장 잘 요약했다. 실제로 바로 backlog를 자를 때 유용한 항목은 다음이다.

1. `auto_improve_readiness_runtime` 분해
2. `learning_delta_scoreboard` anti-slop 추출
3. `evidence_density_score` 추가
4. `reproducibility_score` 추가
5. `context_efficiency_score` 추가
6. source-package 자동 감지
7. `test_execution_summary` 분리
8. blocker 반복 → backlog 변환

즉 이 문서는 증거 문서라기보다 **실행 checklist**로 쓰는 것이 가장 적절하다.

### 5.4 기존 `llmwiki_long_term_improvement_report.md`가 여전히 유효한 부분

기존 보고서는 세 리뷰보다 먼저 다음을 강하게 제안했다.

- anti-slop를 축별 ledger로 바꾸기
- source-package mode를 1급 모드로 승격하기
- cross-eval ladder 명시화
- session synopsis artifact 도입
- “학습 주장”과 “운영 가치”를 직접 연결하기

이번 세 리뷰는 오히려 이 기존 보고서의 문제의식을 **실제 체크포인트에 더 정교하게 접지**한 것으로 보는 편이 맞다.

---

## 6. 실제 파일 대조로 교정해야 하는 지점

이번 통합에서 가장 중요한 부분이다. 세 리뷰의 큰 방향은 맞지만, 아래는 **표현을 더 정확히 고쳐야 한다.**

### 6.1 duplicate self-description 문제는 “현재 sealed ZIP 자체의 문제”가 아니다

실제 `LLMwiki-source(1).zip`는 duplicate entry가 **0개**다. 따라서 duplicate self-description은 **배포된 source ZIP의 현재 상태 결함**이라고 쓰면 과하다.

정확한 표현은 아래와 같다.

> `make release-smoke-fast`를 **이미 self-description이 들어 있는 source package extract**에서 다시 돌릴 때 duplicate self-description warning이 발생할 수 있으며, 이는 replay/repakaging 경로의 ambiguity다.

즉 이것은 **current artifact bug**라기보다 **rebuild/repackage path bug**로 다루는 것이 정확하다. 하지만 장기적으로는 충분히 중요한 문제이므로 hardening 우선순위는 유지해야 한다.

### 6.2 `drift_count=8`은 integrity failure가 아니라 post-seal sidecar 모델의 결과다

`release-post-seal-attestation`의 `pre_seal_post_seal_linkage`를 보면:

- `status=pass`
- `binding_mismatch_count=0`
- `current_missing_count=0`
- `drift_count=8`

이 의미는 “8개 artifact가 깨졌다”가 아니라, **pre-seal snapshot에서 본 digest와 post-seal current digest가 달라졌지만, authoritative binding은 현재 값과 맞는다**는 뜻이다. 실제로 linked artifact들은 source ZIP에 포함되지 않는 post-seal/current reports다.

따라서 장기 개선 보고서에는 다음처럼 써야 한다.

- drift 자체는 **설명 가능한 drift**와 **설명 불가능한 drift**로 다시 나눠라.
- 지금의 8 drift는 적어도 이 attestation에서는 **binding mismatch가 없는 post-seal drift**다.

### 6.3 source-package 실패는 “광범위한 decay”가 아니라 “소수 surface의 profile mismatch”다

`source_trace_target_missing` 40건은 페이지 수로는 많아 보이지만 실제 ref는 세 개로 압축된다. 이 점을 명확히 써야 개선 방향이 흐려지지 않는다.

즉 지금 필요한 것은 lint/eval을 약화하는 것이 아니라,

- missing target을 **profile-aware classification**으로 재평가하고
- digest-linked excluded surface를 **정상적인 externalized evidence**로 인식하게 만드는 것

이다.

### 6.4 stale mypy allowlist는 즉시 복구 가능한 관리 부채다

실제 파일 대조 결과 stale 10개는 다음과 같이 대부분 새 위치가 존재한다.

- `ops/scripts/auto_improve_execution_runtime.py` → `ops/scripts/mechanism/auto_improve_execution_runtime.py`
- `ops/scripts/auto_improve_execute_runtime.py` → `ops/scripts/mechanism/auto_improve_execute_runtime.py`
- `ops/scripts/auto_improve_iteration_persistence_runtime.py` → `ops/scripts/mechanism/auto_improve_iteration_persistence_runtime.py`
- `ops/scripts/mechanism_review_session_calibration_runtime.py` → `ops/scripts/mechanism/mechanism_review_session_calibration_runtime.py`
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py` → `ops/scripts/mechanism/mechanism_review_outcome_metrics_calibration_runtime.py`
- `ops/scripts/promotion_gate_mechanism_finalize_runtime.py` → `ops/scripts/mechanism/promotion_gate_mechanism_finalize_runtime.py`
- `ops/scripts/promotion_gate_mechanism_rule_registry_runtime.py` → `ops/scripts/mechanism/promotion_gate_mechanism_rule_registry_runtime.py`
- `ops/scripts/promotion_gate_mechanism_state_runtime.py` → `ops/scripts/mechanism/promotion_gate_mechanism_state_runtime.py`
- `ops/scripts/promotion_gate_mechanism_report_runtime.py` → `ops/scripts/mechanism/promotion_gate_mechanism_report_runtime.py`
- `ops/scripts/structural_complexity_budget_runtime.py` → `ops/scripts/eval/structural_complexity_budget_runtime.py`

이건 장기 과제가 아니라 **오늘 고쳐야 할 일**이다.

### 6.5 추출 작업공간 수치는 canonical 값과 분리해서 써야 한다

추출 디렉터리에는 로컬 `dev-install` 이후 `.venv`, `.ruff_cache`, `.mypy_cache`, `tmp/` 등이 생길 수 있다. 따라서 추출 작업공간 기준 파일 수/LOC를 곧바로 release package의 canonical 수치처럼 적으면 혼동이 생긴다.

앞으로는 항상 다음 원칙을 권장한다.

- **artifact canonical count**: ZIP 직접 스캔값
- **workspace operational count**: 추출 후 개발 환경 포함값

---

## 7. 최종 진단

모든 근거를 다시 맞춰 보면, 현재 LLMwiki의 장기 병목은 아래처럼 정리된다.

### 7.1 가장 먼저 고쳐야 할 병목

1. **source-package/profile-aware closure 부재**
2. **strict preview 조기 경보 체계 훼손**
3. **대형 오케스트레이터 집중**
4. **learning claim activation의 machine-readable 부재**
5. **anti-slop가 claim 중심에 머무는 구조**

### 7.2 그러나 당장 바꾸면 안 되는 것

1. release pass와 learning claim의 분리
2. one-mechanism discipline
3. source trace의 존재 자체
4. full-vault에서의 strict fail
5. operator/attestation 기반 digest linkage

즉 방향은 “느슨하게 만들기”가 아니라,

> **같은 엄격함을 더 정확한 프로파일과 더 작은 결정 커널로 재배치하는 것**

이다.

---

## 8. 최종 개선 방안

## 8.1 P0 — 0~3일

### A. strict preview 즉시 복구

- `mypy-strict-preview-allowlist.txt` 경로 10건을 실제 위치로 갱신
- `ruff-strict-preview` import order 6건 수정
- allowlist 존재 여부를 precheck하는 smoke 추가

**성공 기준**
- `make mypy-strict-preview` pass
- `make ruff-strict-preview` pass

### B. source-package wrong-lane 진단 강화

- `source_package_extract` sentinel이 있으면 잘못된 full-vault 명령에서 FileNotFoundError 대신 lane-aware guidance 출력
- README/AGENTS/Make help에 source-package canonical command를 명시

**성공 기준**
- 처음 들어온 사용자가 `make lint` 대신 어떤 명령을 써야 하는지 즉시 알 수 있음

### C. duplicate self-description replay 경로 차단

- `release_smoke.py`가 self-description을 중복 삽입하지 않도록 archive assembly 순서 보정
- duplicate member를 report에 수집하고 hard fail 처리

**성공 기준**
- 재포장/replay 시 duplicate member 0

---

## 8.2 P1 — 1~4주

### A. `source_trace_profile_runtime.py` 도입

권장 classification:

- `present`
- `missing_unclassified`
- `missing_export_excluded_bound`
- `missing_export_excluded_unbound`
- `missing_private_surface_expected`
- `missing_generated_rebuildable`

핵심 원칙은 “예외 허용”이 아니라 **예외의 권위자와 digest를 요구하는 것**이다.

### B. `learning_claim_activation_report.json` 도입

현재 흩어진 조건을 한 report로 수렴한다.

필수 필드 예시:

```json
{
  "claim_candidate": "none | bounded | confirmed",
  "blocked_predicates": [
    {
      "predicate": "evidence_bundle_active",
      "current": "not_evaluated",
      "required": "active",
      "repair_target": "make learning-claim-evidence-bundle"
    }
  ]
}
```

### C. 오케스트레이터 분해 시작

우선순위는 다음이 맞다.

1. `auto_improve_readiness_runtime.py`
2. `release_closeout_summary.py`
3. `test_execution_summary.py`
4. `mutation_proposal_runtime.py`
5. `learning_delta_scoreboard.py`

공통 분해 패턴:

- `load_inputs`
- `normalize`
- `classify`
- `decide`
- `render_report`
- `seal/write`

---

## 8.3 P2 — 1~3개월

### A. anti-slop 다축 ledger로 확장

최소 축:

- `claim_hygiene_score`
- `execution_hygiene_score`
- `reproducibility_score`
- `scope_discipline_score`
- `context_efficiency_score`
- `operator_override_pressure`

### B. negative learning ledger 도입

산출물 예시:

- `ops/reports/self-improvement-negative-lessons.json`

이 artifact는 “무엇을 시도했는가”보다 “무엇을 다시 시도하면 안 되는가”를 proposal scoring에 주입하는 역할을 해야 한다.

### C. blocked → backlog 자동 전환

반복 blocker family가 일정 횟수 이상 누적되면 remediation backlog를 기계적으로 만든다.

예:

- `learning_blocked_by_review_required` → review automation/evidence typing
- `execution_blocked_by_no_runnable_proposal` → seed run strategy / queue scoring
- `promotion_blocked_by_artifact_contract_failure` → report writer 분해 / schema helper 분리

### D. corpus entropy trend report

현재 broad synthesis watch candidate는 이미 잘 잡고 있다. 다음 단계는 같은 candidate가 **얼마나 오래 사라지지 않는지**를 보는 것이다.

추천 지표:

- `candidate_persistence_half_life`
- `broad_synthesis_persistence_count`
- `source_overlap_density`
- `router_fanout_growth`
- `raw_registry_shard_pressure`

---

## 8.4 P3 — 3~6개월

### A. source package replay kit

- source ZIP
- minimal evidence sidecar
- profile-aware replay command

이 세 가지를 묶어 **외부 소비자가 “왜 이 ZIP이 pass인지”를 추정이 아니라 절차로 재현**할 수 있게 한다.

### B. cross-eval ladder 명시화

현재 same-eval 중심 구조는 안전하지만, 장기적으로는 아래 ladder가 필요하다.

1. same-eval
2. cross-eval
3. non-regression
4. operator burden reduction
5. bounded claim

### C. canonical session synopsis artifact

장기 self-improvement harness에서 필요한 것은 긴 대화 기록이 아니라 **짧고 기계적인 다음 세션 진입점**이다.

권장 내용:

- 최근 blocker 3~5개
- 마지막 성공 패턴
- 금지된 반복 패턴
- 추천 seed run 후보
- 현재 evidence gap

---

## 9. 파일/모듈 단위 구체 제안

| 대상 | 왜 우선인가 | 권장 분해 | 주의점 |
|---|---|---|---|
| `auto_improve_readiness_runtime.py` | learning/release/execution readiness가 한곳에 몰림 | `readiness_inputs`, `readiness_queue`, `readiness_learning`, `readiness_authority` | decision kernel과 wording을 섞지 말 것 |
| `release_closeout_summary.py` | closeout 판정의 중심 허브 | `closeout_inputs`, `closeout_status_v2`, `closeout_risk`, `closeout_render` | status decision을 pure function으로 분리 |
| `test_execution_summary.py` | runner, parser, reuse, deselection lifecycle 혼재 | `pytest_invocation`, `junit_parser`, `suite_identity`, `summary_render` | full-suite identity contract 유지 |
| `mutation_proposal_runtime.py` | discovery/scoring/policy/render 결합 | `proposal_discovery`, `proposal_scoring`, `proposal_policy`, `proposal_render` | scoring 변경이 policy 완화로 이어지지 않게 할 것 |
| `learning_delta_scoreboard.py` | anti-slop/claim coverage/wording 통합 | `claim_predicates`, `anti_slop_runtime`, `scoreboard_decision`, `scoreboard_render` | claim gate를 느슨하게 만들지 말 것 |

---

## 10. 이번 통합에서 남겨야 할 운영 원칙

1. **Trace를 지우지 말고 계층화하라.**
2. **full-vault strictness는 유지하라.**
3. **source-package는 별도 profile로 명시하라.**
4. **release pass와 learning claim은 계속 분리하라.**
5. **one-mechanism discipline을 더 강하게 하라.**
6. **preview gate를 방치하지 말라.**
7. **더 많은 자동화보다 더 작은 decision kernel을 우선하라.**
8. **blocked run도 학습 자산으로 회수하라.**

---

## 11. 최종 권고

세 리뷰와 기존 보고서를 실제 파일에 다시 맞춰 보면, 가장 정확한 한 줄 평은 다음과 같다.

> **LLMwiki는 이미 강한 release/evidence discipline을 가진 저장소다. 지금 필요한 것은 기능 추가가 아니라, source-package와 full-vault의 경계를 기계적으로 분리하고, 대형 오케스트레이터를 더 작은 판정 커널로 쪼개며, anti-slop를 claim 방어에서 execution 방어까지 확장하는 일이다.**

우선순위는 분명하다.

1. **strict preview 복구**
2. **source trace profile-aware closure 도입**
3. **duplicate self-description replay 경로 차단**
4. **learning claim activation artifact 도입**
5. **핵심 오케스트레이터 분해**
6. **anti-slop 다축 ledger + negative learning ledger 도입**

가장 중요한 점은 이것이다.

- gate를 줄이지 말 것
- 예외를 숨기지 말 것
- 문구를 덜 쓰기보다 **판정 근거를 더 좁고 더 기계적으로 만들 것**

결론적으로, 이번 세 리뷰는 방향이 거의 맞았다. 다만 최종 실행안은 다음처럼 정리하는 것이 가장 정확하다.

> **“느슨한 자동화”가 아니라 “작고 설명 가능한 자동화”로 이동하라. “개선했다”를 더 빨리 말하려 하지 말고, “왜 아직 claim을 열 수 없는지”를 더 빠르고 기계적으로 설명하라.**

---

## 12. 부록 — 즉시 실행 Backlog 12

1. `mypy-strict-preview-allowlist.txt` stale path 10건 수정
2. `ruff-strict-preview` import order 6건 수정
3. wrong-lane diagnostic 출력 개선
4. README/AGENTS에 source-package canonical command 명시
5. `release_smoke.py` duplicate member guard 추가
6. `source_trace_profile_runtime.py` 신설
7. `learning_claim_activation_report.json` 신설
8. `auto_improve_readiness_runtime.py` 분해 착수
9. `release_closeout_summary.py` decision kernel 분리
10. `test_execution_summary.py` runner/parser 분리
11. anti-slop 다축 ledger 정의
12. `self-improvement-negative-lessons.json` 정의
