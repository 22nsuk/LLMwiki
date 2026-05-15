# LLM Wiki vNext 현재 코드 검토 보고서

## 문서 정보
- 프로젝트: `LLM Wiki vNext`
- 검토 기준: 현재 코드 기준 전수 스캔 + 고위험 표면 심층 검토
- 작성 관점: **anti-slop** + **자가 개선(self-improvement)**
- 작성 언어: 한국어
- 파일명: 영문

---

## 1. 검토 범위와 방법

이번 검토는 저장소 전체를 “모든 파일을 수동 정독”하는 방식이 아니라, **저장소 구조 전수 스캔 → Python 표면 계량 분석 → 현재 런타임 산출물/게이트 상태 점검 → 고복잡도/고결합 모듈 심층 검토**의 순서로 진행했다.

실제 확인한 범위는 다음과 같다.

1. 저장소 구조와 설정 파일
   - `README.md`, `ARCHITECTURE.md`, `pyproject.toml`, `pytest.ini`, `Makefile`
2. 핵심 코드 표면 전수 스캔
   - `ops/scripts/*.py` 전체를 대상으로 파일 수, 라인 수, 함수 수, 장대 함수 길이, 패턴 분포를 계량화
3. 핵심 고위험 모듈 심층 검토
   - `ops/scripts/auto_improve_readiness_runtime.py`
   - `ops/scripts/filesystem_runtime.py`
   - `ops/scripts/codex_exec_executor.py`
   - `ops/scripts/auto_improve_runtime.py`
   - `ops/scripts/mutation_proposal_runtime.py`
   - `ops/scripts/policy_validation_runtime.py`
   - `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py`
4. 현재 산출물/운영 상태 점검
   - `ops/reports/structural-complexity-budget.json`
   - `ops/reports/mutation-proposals.json`
   - `ops/reports/mechanism-review-candidates.json`
   - `ops/reports/outcome-metrics.json`
5. 실제 실행으로 확인한 게이트/리포트
   - `python -m ops.scripts.raw_registry_preflight --vault .`
   - `python -m ops.scripts.planning_gate_validate --vault .`
   - `build_readiness_report(Path('.'))`

이 보고서는 “문체 개선”이나 “취향 수준의 리팩터링”이 아니라, **슬롭이 다시 스며드는 구조적 이유**와 **자가개선 루프가 스스로 품질을 올리지 못하게 만드는 병목**을 중심으로 정리한다.

---

## 2. 핵심 결론

이 저장소는 이미 일반적인 취미 프로젝트 수준을 넘어서 있다. 정책, 스키마, 테스트, 산출물, 메커니즘 리뷰, 프로모션 게이트, 공급망 산출물까지 갖춘 점은 분명 강점이다. 다만 현재 구조는 다음의 역설을 안고 있다.

> **“품질을 관리하는 장치는 많지만, 그 장치들 자체가 점점 더 많은 문자열 규약·사전(dict)·대형 오케스트레이터에 의존하고 있다.”**

즉, 이 프로젝트의 가장 큰 위험은 기능 부족이 아니라 **운영 메커니즘 자체의 슬롭 축적**이다. 현재 코드는 anti-slop 철학을 이미 정책과 리포트에 많이 담고 있지만, 실제 구현 계층에서는 아래 문제가 남아 있다.

- 상태와 계약이 여전히 너무 많이 `dict[str, Any]`와 문자열 키에 묶여 있다.
- 자가개선 루프가 풍부한 리포트를 생성하지만, **리포트 freshness / readiness / runnable 상태**를 강하게 묶는 폐회로가 아직 약하다.
- 복잡도 예산 시스템이 존재하지만, **실제 핫스팟이 monitored surface로 충분히 승격되지 않아** “복잡도는 보이지만 강제되지는 않는” 구간이 남아 있다.
- CLI wrapper, direct-script fallback, broad exception boundary가 반복되어 **코드베이스의 운영 표면이 넓고 얕게 중복**되어 있다.
- 테스트는 많지만, 일부는 대형 fixture/대형 단일 테스트 함수에 의존해 **테스트 자체가 새로운 슬롭 저장소**가 될 위험이 있다.

결론적으로, 현재 코드베이스는 “망가지기 쉬운 상태”는 아니다. 그러나 **현재의 자기방어 장치들이 더 정교한 typed contract와 phase boundary로 재구성되지 않으면, 장기적으로는 품질 관리 코드가 가장 먼저 비대해질 가능성**이 높다.

---

## 3. 현재 상태 요약

### 3.1 규모와 표면

정적 스캔 기준으로 확인된 핵심 규모는 다음과 같다.

- `ops/scripts` Python 파일: **150개**
- `tests` Python 파일: **109개**
- 테스트 함수 수: **579개**
- `ops/scripts` 총 코드량: 대략 **3.5만 라인대**
- `tests` 총 코드량: 대략 **2.8만 라인대**

이는 “기능 코드보다 품질/운영 코드가 적지 않은” 구조다. 이런 구조에서는 anti-slop 품질 관리 코드가 오히려 새로운 슬롭 생산자가 되지 않도록 **구조적 강제력**이 특히 중요하다.

### 3.2 대표 복잡도 핫스팟

길이와 함수 밀도가 높은 대표 모듈은 다음과 같다.

- `ops/scripts/filesystem_runtime.py` — 877 lines / 39 funcs
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py` — 742 lines / 26 funcs
- `ops/scripts/policy_validation_runtime.py` — 718 lines / 24 funcs
- `ops/scripts/mechanism_run_workspace_runtime.py` — 709 lines / 21 funcs
- `ops/scripts/codex_exec_executor.py` — 688 lines / 23 funcs
- `ops/scripts/mechanism_run_validation_runtime.py` — 685 lines / 26 funcs
- `ops/scripts/mechanism_review_candidate_runtime.py` — 680 lines / 22 funcs
- `ops/scripts/mutation_proposal_runtime.py` — 670 lines / 26 funcs

대표 장대 함수도 분명하다.

- `build_readiness_report()` — `ops/scripts/auto_improve_readiness_runtime.py:386` / **149 lines**
- `build_outcome_metrics_calibration_diagnostics()` — `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py:610` / **132 lines**
- `load_mechanism_run_snapshots()` — `ops/scripts/mechanism_review_history_runtime.py:82` / **127 lines**
- `session_calibration_summary()` — `ops/scripts/mechanism_review_session_calibration_runtime.py:76` / **126 lines**
- `build_report()` — `ops/scripts/mutation_proposal_runtime.py:549` / **121 lines**
- `execute_codex_exec_role()` — `ops/scripts/codex_exec_executor.py:572` / **109 lines**
- `_policy_complexity_growth_candidate()` — `ops/scripts/mechanism_candidate_registry_runtime.py:322` / **106 lines**
- `validate_frontmatter()` — `ops/scripts/frontmatter_runtime.py:81` / **104 lines**
- `_run_workspace_experiment_phase()` — `ops/scripts/run_mechanism_experiment_runtime.py:244` / **104 lines**
- `_run_registry_and_review_passes()` — `ops/scripts/wiki_lint.py:304` / **101 lines**

이 수치는 단순히 “큰 파일이 있다”는 뜻이 아니다. **운영·검증·자가개선의 핵심 제어 로직이 소수의 큰 함수와 큰 모듈에 농축되어 있다**는 의미다.

---

## 4. 현재 실행 상태에서 확인된 운영 신호

### 4.1 raw registry preflight는 현재 실패 상태

실행 확인 결과 `python -m ops.scripts.raw_registry_preflight --vault .`는 **fail** 상태를 반환했다. 오류 유형은 대표적으로 `raw_path_mismatch`였고, `system/system-raw-registry/wiki.md` 및 shard 페이지들에서 다수 관찰됐다.

이 점은 매우 중요하다. 이유는 다음과 같다.

- 프로젝트는 provenance와 inventory 일관성을 핵심 계약으로 내세우고 있다.
- 그런데 실제 현재 상태에서 registry preflight가 실패한다는 것은,
  **“코드가 품질을 관리한다”와 “운영 산출물이 최신 상태다”가 아직 자동으로 결합되어 있지 않다**는 뜻이다.
- 자가개선 루프 입장에서는 stale artifact 위에서 의사결정을 내릴 여지가 생긴다.

### 4.2 planning gate는 pass

`python -m ops.scripts.planning_gate_validate --vault .`는 `ops/templates` 기준으로 **pass**였다.

이 신호는 긍정적이다. 최소한 템플릿/스키마/기본 planning artifact 계약은 비교적 잘 정리돼 있다는 뜻이다. 즉, 문제는 “기초 계약이 없다”가 아니라 **운영 산출물의 지속 동기화와 readiness 폐루프가 약하다**는 데 있다.

### 4.3 auto-improve readiness는 warn

`build_readiness_report(Path('.'))` 기준 핵심 상태는 다음과 같았다.

- `status`: **warn**
- `proposals_emitted`: **1**
- `runnable_proposal_count`: **0**
- `blocked_proposal_count`: **1**
- blocker: **`recent_log_overlap`**
- `attempts_considered`: **7**
- `session_reports_considered`: **0**

즉, 자가개선 루프는 “아이디어를 생성하는 데”는 성공했지만, **지금 당장 실행 가능한 proposal queue**를 만들지는 못하고 있다. 현재 self-improvement 계층은 “생산”보다 “차단 이유 설명”에 더 강하다.

이건 나쁜 것만은 아니다. 무작정 돌지 않는다는 점은 anti-slop적이다. 다만 여기서 멈추면 시스템은 **잘 설명하는 보류 시스템**으로 남는다. 지금 필요한 것은 blocker를 설명하는 리포트가 아니라, blocker를 **줄이는 구조적 설계**다.

### 4.4 mutation proposal과 readiness의 메시지는 일관적이지만, 실행성은 낮다

`ops/reports/mutation-proposals.json` 요약은 다음과 같았다.

- `proposals_emitted`: **1**
- `blocked_proposals`: **1**
- queue selection 상 `runnable_available_count`: **0**
- blocked reason: **`recent_log_overlap`**

첫 proposal은 `ops/scripts/auto_improve_iteration_persistence_runtime.py`를 중심으로 한 좁은 변경을 제안하고 있으며, `must_not_increase_untyped_surface` 같은 anti-slop 제약도 담고 있다. 이 자체는 방향이 좋다. 문제는 이 anti-slop 제약이 **현재 전체 코드베이스 수준에서는 아직 충분히 시스템화되어 있지 않다**는 점이다.

---

## 5. anti-slop 관점 상세 평가

## 5.1 장점: 이미 anti-slop 철학이 코드베이스에 많이 스며 있다

이 프로젝트는 다음 점에서 분명히 성숙하다.

- README, architecture, policy, schema, tests, generated report의 계층이 분명하다.
- “한 번에 하나의 mechanism만 바꾼다”는 운영 철학이 문서와 리포트에 반영되어 있다.
- complexity budget, warning budget, promotion gate, planning gate 등 **품질을 구두가 아니라 artifact로 남기려는 습관**이 있다.
- self-improvement가 점수 향상만이 아니라 lint / complexity / tests / signoff 같은 다축 상태를 읽도록 설계되어 있다.

즉, anti-slop의 철학은 이미 있다. 지금 필요한 것은 철학의 추가가 아니라 **철학을 더 낮은 수준의 구현 계약으로 내리는 것**이다.

## 5.2 문제 1: 구현 경계가 아직도 “문자열 계약 + dict soup”에 많이 의존한다

프로젝트 전체에 `@dataclass`, `TypedDict`, `Protocol`이 이미 많이 사용되지만, 동시에 `dict[str, Any]`, `dict[str, object]`, `Mapping[str, Any]` 류 사용도 매우 많다. 스캔 기준 `ops/scripts` 안에서 이런 패턴이 **수백 회 수준**으로 등장한다.

대표적으로 다음 모듈이 그렇다.

- `ops/scripts/auto_improve_readiness_runtime.py`
- `ops/scripts/filesystem_runtime.py`
- `ops/scripts/behavior_delta_runtime.py`
- `ops/scripts/openvex_draft.py`
- `ops/scripts/raw_markdown_runtime.py`
- `ops/scripts/auto_improve_route_scaffold_runtime.py`

이 구조의 문제는 단지 타입이 약하다는 데 있지 않다.

1. **상태 모델이 파일 단위로 응집되지 않는다.**
   - 같은 report payload라도 각 함수가 키를 문자열로 다시 꺼내 쓰며 국소적으로 방어한다.
2. **오타/누락/shape drift가 늦게 드러난다.**
   - 스키마 검증 이전에는 문제를 알기 어렵고, 검증 이후에도 내부 계산에서 의미 drift가 날 수 있다.
3. **리팩터링 비용이 높다.**
   - 키 이름을 바꾸면 호출 체인 전체가 암묵적으로 깨질 수 있다.
4. **self-improvement loop가 실제로는 자기 자신을 안전하게 바꾸기 어렵다.**
   - 이유는 제안과 실행과 보고가 모두 문자열 contract에 걸쳐 있기 때문이다.

### 권고

- report payload를 단순 dict로 끝내지 말고, 최소한 핵심 흐름에는 **경계 전용 typed model**을 도입해야 한다.
- 추천 우선순위:
  1. `ReadinessReport*`
  2. `MutationProposal*`
  3. `MechanismReviewCandidate*`
  4. `ManifestApply*`
  5. `ExecutorReport*`
- “JSON으로 저장”은 마지막 단계여야 한다. 내부 계산에서는 class/typed structure를 쓰고, 직렬화 직전에만 dict로 내리는 편이 맞다.

이 작업은 anti-slop 관점에서 가장 투자 대비 효과가 크다.

## 5.3 문제 2: 복잡도 예산 시스템이 있는데, 실제 핫스팟을 충분히 강제하지 못한다

`ops/reports/structural-complexity-budget.json`은 top-level status가 `pass`지만, diagnostics의 `function_budget_top_n`을 보면 다음 특징이 있다.

- `total_candidate_count`: **28**
- `monitored_candidate_count`: **0**
- `unmonitored_candidate_count`: **28**

즉, 복잡도가 후보로는 보이지만 **감시(profile) 대상에는 충분히 편입되지 않았다**는 뜻이다.

특히 `ops/scripts/auto_improve_readiness_runtime.py`의 `build_readiness_report()`는 **149 lines**로 function budget candidate인데도 monitored가 아니다. 이건 현재 구조의 핵심 병목이 complexity tooling의 “관찰 대상”으로는 잡히지 않고 있다는 의미다.

### 권고

- complexity budget의 다음 승격 대상은 “가장 위험한 오케스트레이터”여야지, 가장 쉬운 함수가 아니어야 한다.
- 최소한 아래 함수는 **monitored hot path**로 승격하는 것이 맞다.
  - `build_readiness_report()`
  - `execute_codex_exec_role()`
  - `build_report()` in `mutation_proposal_runtime.py`
  - `build_outcome_metrics_calibration_diagnostics()`
  - `rehearse_manifest_apply_rollback()`
- 현재 preview artifact를 유지하되, touched-surface strict gate에서는 위 함수들에만 더 낮은 threshold를 거는 **핫패스 전용 프로파일**을 추가하는 것이 좋다.

이 조정 없이는 complexity budget이 “존재하는 문서”로 남고, anti-slop 강제력은 약해진다.

## 5.4 문제 3: CLI wrapper와 direct-script fallback이 얕게 넓게 중복된다

`ops/scripts` 전반에 direct script fallback 패턴이 반복된다. 확인된 수량도 적지 않다. `if __package__ in (None, ""):` 형태의 direct-script fallback이 **40개 이상** 존재하고, `broad-exception: cli_boundary`도 여러 entrypoint에서 반복된다.

대표 예시는 다음과 같다.

- `ops/scripts/mechanism_review.py`
- `ops/scripts/mutation_proposal.py`
- `ops/scripts/finalize_run.py`
- `ops/scripts/run_mechanism_experiment.py`

이 방식은 작은 저장소에서는 실용적이지만, 지금 규모에서는 다음 문제를 만든다.

- CLI boundary의 예외 코드/출력 형식/경계 처리가 미세하게 흩어진다.
- import fallback, stdout/stderr 처리, exit code 정책이 파일별로 drift할 수 있다.
- public surface contract 테스트 비용이 불필요하게 커진다.

### 권고

- `console_scripts` 기반 설치형 entrypoint를 늘리고, wrapper는 thin façade 하나로 수렴시키는 편이 좋다.
- 공통 helper 예시:
  - `run_cli_boundary(main_logic, *, known_errors, output_mode)`
  - `load_runtime_module_with_direct_fallback()`
  - `emit_json_and_written_to()`
- 목표는 “wrapper 삭제”가 아니라 **wrapper variability 제거**다.

anti-slop 관점에서 얕은 반복은 작아 보여도 장기 누수의 전형이다.

## 5.5 문제 4: readiness / freshness / artifact coherence가 아직 1급 시민이 아니다

현재 프로젝트는 generated artifact를 많이 사용한다. 그런데 실제 상태를 보면 다음이 동시에 성립한다.

- planning gate는 pass
- mutation proposal은 생성됨
- readiness는 warn
- raw registry preflight는 fail

이 조합은 **게이트 간 위계와 선행조건이 구현 수준에서 완전히 봉합되어 있지 않다**는 뜻이다. 지금 구조에서는 어떤 artifact는 최신이고 어떤 artifact는 stale일 수 있는데, 그 자체가 항상 상위 readiness를 막지는 않는다.

### 권고

- 모든 generated artifact에 대해 `freshness_class`, `source_inputs`, `depends_on_artifacts`, `invalidates_on`을 명시하는 **artifact dependency registry**를 도입하라.
- readiness는 다음 질문에 먼저 답해야 한다.
  1. 지금 proposal queue가 runnable한가?
  2. 그 proposal이 의존하는 artifact는 모두 current인가?
  3. registry / manifest / mechanism report / outcome metrics가 같은 causal snapshot을 가리키는가?
- 즉, readiness는 단순 경고 보고서가 아니라 **causal-coherence gate**가 되어야 한다.

이건 self-improvement를 진짜 운영 가능한 루프로 바꾸는 핵심이다.

## 5.6 문제 5: 테스트도 일부는 “슬롭의 저장소”가 될 조짐이 있다

테스트 수와 폭은 강점이다. 하지만 complexity diagnostics 상위 후보를 보면 테스트 쪽에도 장대 함수가 많다.

예:
- `tests/minimal_vault_runtime.py::seed_minimal_vault` — 387 lines
- `tests/test_policy_runtime.py::test_live_policy_loads_as_single_source_of_truth` — 376 lines
- `tests/test_planning_gate_validate.py::seed_mechanism_run_artifacts` — 280 lines
- `tests/test_auto_improve_runtime.py::...writes_successful_session_report` — 275 lines

이건 당장 버그는 아니지만, 다음 문제가 된다.

- fixture가 사실상 mini runtime이 되면, 테스트 실패 원인이 기능 코드인지 fixture인지 분리하기 어렵다.
- self-improvement loop가 테스트를 바꾸는 순간, 테스트가 “검증자”가 아니라 “또 다른 생산 코드”가 된다.

### 권고

- 거대 seed helper는 `scenario builders` + `artifact fixtures` + `assertion helpers`로 나누는 것이 좋다.
- 긴 테스트는 Arrange/Act/Assert를 실제 함수 수준으로 분리하라.
- test fixture도 complexity budget 대상에 포함하되, runtime과 다른 기준을 쓰라.

---

## 6. 자가 개선 관점 상세 평가

## 6.1 현재 루프는 “자기 설명”은 강하지만 “자기 수복”은 아직 약하다

현재 self-improvement 레이어는 다음을 잘한다.

- 최근 run history를 읽는다.
- candidate를 만든다.
- proposal을 만든다.
- blockers를 설명한다.
- readiness를 요약한다.

하지만 아래는 아직 약하다.

- blocker clearing 전략의 자동화
- stale artifact가 있을 때 상위 loop를 강제로 멈추는 강결합
- proposal execution 가능성을 높이는 preflight narrowing
- “왜 이번 proposal이 실행 불가였는가”의 재학습을 다음 queue priority에 충분히 환류하는 구조

즉, 현재 루프는 **판단 엔진**에 가깝고, 아직은 **수복 엔진**은 아니다.

## 6.2 `recent_log_overlap`는 단순 blocker가 아니라 설계 시그널이다

현재 blocked reason이 `recent_log_overlap`인 것은 우연한 운영 상태가 아니라, 설계 상 두 가지를 의미한다.

1. chronology 기반 dedupe/충돌 방지가 실제로 작동하고 있다.
2. 그러나 target rotation, cooldown, proposal diversification이 충분치 않아 **새로운 runnable work를 만들 정도로 search space를 넓히지 못한다.**

### 권고

- `recent_log_overlap`를 단순 blocked reason으로 두지 말고, 별도 family의 **queue shaping signal**로 승격해야 한다.
- 예:
  - overlap penalty를 주는 데서 끝내지 말고
  - 다음 cycle candidate 생성 시 non-overlapping family/target을 우선 공급하는 보정기를 둬야 한다.
- 즉, blocker를 기록하는 것에서 멈추지 말고 **blocker-aware proposal synthesis**로 넘어가야 한다.

## 6.3 self-improvement는 이제 “결과 점수”보다 “루프 효율”을 같이 최적화해야 한다

현재 리포트는 stage score, lint, complexity, promotion 상태를 잘 본다. 그러나 다음 운영 지표도 1급으로 올려야 한다.

### 추가 권장 KPI

- `proposal_to_runnable_rate`
  - emitted proposal 대비 runnable proposal 비율
- `blocker_recurrence_rate`
  - 최근 N회 중 같은 blocker 반복 비율
- `artifact_staleness_abort_rate`
  - stale artifact 때문에 루프가 멈춘 비율
- `same_target_repeat_rate`
  - 최근 M회 동안 같은 primary target family가 반복된 비율
- `queue_diversity_index`
  - family / target / failure mode 다양성 지표
- `time_to_clear_recent_log_overlap`
  - overlap blocker가 해소되기까지 걸린 cycle 수
- `self_improvement_false_start_rate`
  - proposal emitted 후 runnable 0으로 끝나는 비율

이 지표가 없으면 self-improvement는 “좋은 제안을 만드는지”는 보여도, “운영 가능한 제안을 꾸준히 만드는지”는 보여주지 못한다.

---

## 7. 파일별 보완 우선순위

## P0 — 즉시 손대야 하는 영역

### 1) `ops/scripts/auto_improve_readiness_runtime.py`

이 파일은 현재 자가개선 운영 판단의 허브인데, `build_readiness_report()`가 너무 많은 역할을 가진다.

현재 혼재된 책임:
- 입력 로드
- 요약 추출
- blocker 계산
- fallback seed 계산
- checks 생성
- remediation 생성
- next action 생성
- 최종 report assembly

### 권고 분해
- `load_readiness_inputs()`
- `derive_queue_state()`
- `derive_history_state()`
- `derive_readiness_checks()`
- `derive_readiness_remediations()`
- `derive_next_action()`
- `assemble_readiness_report()`

핵심은 함수 분해 그 자체보다도, **ReadinessState라는 typed aggregate를 먼저 만든 뒤 조합**하게 바꾸는 것이다.

### 2) `ops/scripts/filesystem_runtime.py`

이 파일은 안전 경계에 해당한다. anti-slop에서 가장 중요하게 봐야 하는 곳이다. 지금도 신중하게 짜여 있지만, 한 파일 안에 atomic write / manifest guard / rehearsal / rollback / shadow report가 너무 많이 모여 있다.

### 권고 분해
- `filesystem_atomic_runtime.py`
- `manifest_apply_guard_runtime.py`
- `manifest_apply_rehearsal_runtime.py`
- `manifest_apply_transaction_runtime.py`

이 파일은 “큰 파일”이어서 문제가 아니라, **실패했을 때 영향 반경이 넓은데 책임 분리가 아직 덜 됐다**는 점이 문제다.

### 3) `ops/scripts/codex_exec_executor.py`

실행기 쪽은 자가개선 루프의 실제 actuator다. 여기는 보고/프롬프트 생성/실행/출력 읽기/timeout 처리/ledger append가 응집돼 있다.

### 권고 분해
- prompt materialization
- process execution
- stream persistence
- output normalization
- executor report assembly
- timeout artifact assembly
- telemetry append

특히 executor는 실패 모드가 풍부하므로, anti-slop 관점에서 **“한 함수가 한 단계만 담당”**해야 한다.

## P1 — 다음 스프린트에서 해야 하는 영역

### 4) `ops/scripts/mutation_proposal_runtime.py`

proposal synthesis는 self-improvement의 핵심 두뇌다. 지금은 기능적으로는 충분하지만, calibration / queue pressure / family session diagnostics / priority breakdown이 한 보고서 assembly 안에 많이 엉겨 있다.

권고는 아래와 같다.
- proposal candidate normalization
- family diagnostics
- priority reducer chain
- blocker application
- report assembly

이 중 **priority reducer chain**은 별도 registry/strategy로 떼는 것이 특히 좋다.

### 5) `ops/scripts/policy_validation_runtime.py`

이 파일은 policy를 강하게 검증하는 장점이 있지만, 규칙이 길게 누적되면서 “정책 검증기의 구조적 예산”이 필요해진 상태다.

권고:
- registry별 validator 함수군 분리
- invariant catalog 정규화
- message builder 공통화
- string registry 검사와 semantic invariant 검사를 분리

### 6) `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py`

calibration 로직은 self-improvement의 품질을 좌우한다. 현재는 충분히 설명적이지만, 점점 “shadow scoring engine”이 되어 가고 있다.

권고:
- signal extraction
- family aggregation
- priority shadowing
- diagnostics rendering

으로 단계를 더 분리해야 한다.

## P2 — 중기 과제

### 7) CLI/public surface 정리

- 반복 wrapper 통합
- `console_scripts` 확대
- direct-script fallback 축소
- exit code / stderr contract 공통화

### 8) artifact dependency registry 도입

- readiness와 freshness를 causal graph로 연결
- stale artifact가 있으면 proposal runnable 판정을 보수적으로 하향

### 9) 테스트 fixture 구조 개선

- giant seed helper 분해
- scenario builder와 assertion helper 분리
- 테스트 자체의 complexity budget 도입

---

## 8. 권장 로드맵

## 1단계: 구조적 anti-slop 최소선 확보

목표는 “더 예쁜 코드”가 아니라 **슬롭 재유입 방지 장치**를 심는 것이다.

- `ReadinessState`, `MutationProposal`, `ExecutorReport`, `ManifestApplyItem` 같은 typed boundary 도입
- `build_readiness_report()` 분해
- `execute_codex_exec_role()` 분해
- complexity hot path monitored profile 추가

## 2단계: self-improvement를 설명형에서 실행형으로 이동

- `recent_log_overlap` blocker-aware proposal diversification 추가
- artifact freshness / coherence gate 추가
- runnable proposal 생성률 KPI 추가

## 3단계: 운영 표면 축소

- CLI wrapper 공통화
- direct-script fallback 감소
- public surface/entrypoint 구조 정리

---

## 9. 지금 당장 실행할 추천 작업 7개

1. `auto_improve_readiness_runtime.py`에 `ReadinessState` 도입 후 `build_readiness_report()` 분해
2. `structural-complexity-budget`에 hot path monitored profile 추가
3. `mutation-proposals.json`와 readiness를 묶는 freshness/coherence preflight 추가
4. `recent_log_overlap` 전용 diversification reducer 추가
5. `filesystem_runtime.py`를 transaction / rehearsal / guard 계층으로 분리
6. `codex_exec_executor.py`를 prompt / execute / persist / report 단계로 분리
7. giant test seed helper를 scenario builder 방식으로 축소

---

## 10. 최종 판단

현재 코드베이스는 이미 “대충 만든 자동화 코드” 단계는 지났다. 오히려 문제는 그 반대다. **운영 철학과 품질 장치가 많아졌는데, 그 장치들을 묶는 구현 경계가 아직 충분히 강하지 않다.**

anti-slop 관점에서 지금 가장 중요한 보완은 다음 한 줄로 요약된다.

> **문자열 규약과 거대 오케스트레이터를 typed state와 강한 phase boundary로 치환하라.**

자가개선 관점에서 지금 가장 중요한 보완은 다음 한 줄이다.

> **더 많은 proposal을 만드는 것이 아니라, 더 높은 runnable rate와 더 낮은 blocker recurrence를 만드는 쪽으로 루프를 재설계하라.**

이 두 축만 제대로 잡히면, 이 저장소는 “품질 관리 코드가 많은 프로젝트”를 넘어 **스스로 품질을 보수적으로 끌어올리는 운영 시스템**으로 한 단계 올라갈 수 있다.

---

## 부록 A. 이번 검토에서 직접 확인한 핵심 증거

- `ops/scripts/auto_improve_readiness_runtime.py:386` — `build_readiness_report()` 장대 함수
- `ops/scripts/filesystem_runtime.py:601` — `rehearse_manifest_apply_rollback()`
- `ops/scripts/filesystem_runtime.py:826` — `apply_manifest_transaction()`
- `ops/scripts/codex_exec_executor.py:197` — `_materialize_prompt()`
- `ops/scripts/codex_exec_executor.py:572` — `execute_codex_exec_role()`
- `ops/scripts/mutation_proposal_runtime.py:549` — `build_report()`
- `ops/scripts/policy_validation_runtime.py:221` — `_validate_promotion_rule_metadata_registry()`
- `ops/scripts/policy_validation_runtime.py:588` — `_validate_subagent_role_registry()`
- `ops/reports/structural-complexity-budget.json` — monitored 0 / unmonitored 28 후보 확인
- `ops/reports/mutation-proposals.json` — emitted 1 / blocked 1 / `recent_log_overlap`
- `ops/reports/outcome-metrics.json` — `attempts_considered=7`, `session_reports_considered=0`
- `python -m ops.scripts.raw_registry_preflight --vault .` — fail (`raw_path_mismatch` 다수)
- `python -m ops.scripts.planning_gate_validate --vault .` — pass
- `build_readiness_report(Path('.'))` — warn, runnable proposal 0

## 부록 B. 한계와 해석 주의

- 본 검토는 저장소 전수 스캔과 핵심 표면 심층 검토를 수행했지만, 모든 파일의 모든 라인을 동일 밀도로 수동 독해하지는 않았다.
- `ruff`, `mypy`는 현재 컨테이너 도구 가용성 제약 때문에 재실행하지 못했다. 대신 코드 패턴, 현재 산출물, 일부 실제 게이트 실행 결과를 근거로 판단했다.
- 따라서 본 보고서는 “정적 스타일 이슈 목록”이 아니라, **현재 아키텍처/운영 메커니즘의 구조적 개선안**으로 읽는 것이 맞다.
