# LLM Wiki vNext 코드 검토 및 개선 보고서

## 1. 보고서 목적

이 보고서는 업로드된 현재 워크스페이스 전체를 기준으로, **코드/테스트/정책/생성 산출물 구조를 함께 검토**한 뒤 다음 두 축에 집중해 개선 방안을 제시한다.

1. **anti-slop 관점**
   - 코드가 “그럴듯해 보이지만 실제로는 유지보수성·검증 가능성·경계 명확성·실행 신뢰성”을 잃는 지점을 줄이는 것
   - 중복, 과도한 분산, 암묵적 계약, artifact drift, 실행 경계 누수, 테스트 취약성, 과한 설명성에 비해 약한 보증을 제거하는 것

2. **자가 개선(self-improvement) 관점**
   - 이 저장소가 이미 갖고 있는 `mechanism review -> mutation proposal -> auto improve -> promotion` 루프를
     “보고서 생산 시스템”에서 “실제 개선 효과를 누적하는 시스템”으로 끌어올리는 것
   - 개선 후보 선정, 실행, 검증, 차단, 회귀 방지, 근거 축적을 더 폐루프(closed loop)에 가깝게 만드는 것

---

## 2. 검토 범위와 접근 방식

이번 검토는 저장소 내부의 다음 표면을 중심으로 수행했다.

- `ops/scripts/` 중심의 Python runtime/CLI 코드
- `tests/`의 계약 테스트 및 회귀 테스트 자산
- `pyproject.toml`, `Makefile`, `README.md`, `ARCHITECTURE.md`
- `ops/reports/*.json`에 남아 있는 구조 복잡도·readiness·mechanism review·mutation proposal·outcome metrics 산출물
- 저장소 루트에 포함된 `pytest_target.xml`, `pytest_target.log` 등 테스트 관련 artifact

실제 분석에서 확인한 핵심 정황은 다음과 같다.

- Python 파일 수: **257개**
- `ops/scripts/` 표면: **142개 파일**
- 그중 `_runtime.py` 파일: **96개**
- 비-`_runtime.py` 엔트리/래퍼 파일: **46개**
- 구조 복잡도 경고 표면에 오른 핵심 파일:
  - `ops/scripts/raw_intake_promotion_runtime.py`
  - `ops/scripts/observability_artifacts_runtime.py`
  - `ops/scripts/policy_validation_runtime.py`
  - `ops/scripts/structural_complexity_budget_runtime.py`
- 저장소 내부 readiness 산출물 기준:
  - `ops/reports/auto-improve-readiness.json` 상태는 `warn`
  - 사유는 **proposal은 존재하지만 runnable 상태가 아니며 `recent_log_overlap`에 막혀 있음**
- 저장소 내부 구조 복잡도 산출물 기준:
  - `ops/reports/structural-complexity-budget.json` 상태는 `attention`
  - `targets_with_attention_count = 4`

이 보고서는 “예쁜 말로 재서술한 감상문”이 아니라, **현재 코드가 실제로 어떤 방식으로 복잡성을 키우고 있으며, 무엇을 먼저 고치면 개선 루프의 실효성이 올라가는지**를 중심으로 정리한다.

---

## 3. 총평

이 코드베이스는 단순한 위키 생성기가 아니라 다음이 한 워크스페이스에 공존하는 구조다.

- raw/source intake
- wiki/system corpus 유지
- eval/lint/planning/promotion gate
- supply-chain / SBOM / provenance artifact 생성
- self-improvement queue / proposal / execution / promotion loop

즉, 문제의 본질은 “기능이 부족한 저장소”가 아니라 **너무 많은 운영 개념이 이미 들어와 있고**, 그것이 다시 `_runtime.py` 단위 helper 분해와 report 기반 운영으로 확장되면서 **표면적 정교함에 비해 실질적 단순성이 부족해진 저장소**라는 점이다.

좋은 점도 분명하다.

- schema 검증, gate, audit artifact, rollback rehearsal, promotion/report 개념이 이미 있다.
- atomic write, apply guard, report schema 같은 “운영 안전장치”를 코드 수준에서 갖추려는 의도가 강하다.
- 테스트 자산도 꽤 많고, 최소한 “무엇을 계약으로 보아야 하는지”에 대한 팀의 의식이 있다.

하지만 anti-slop 관점에서 보면 지금의 가장 큰 문제는 다음 세 문장으로 요약된다.

1. **코드가 이미 충분히 많은데, 여전히 논리 경계보다 파일 경계가 먼저 늘고 있다.**
2. **보고서와 진단은 풍부한데, 개선 루프를 실제로 앞으로 밀어주는 실행 폐루프는 아직 약하다.**
3. **저장소 안에 코드·산출물·캐시·실행 이력·문서 코퍼스가 함께 있어, 신호 대 잡음비가 떨어진다.**

---

## 4. anti-slop 관점 핵심 진단

## 4.1 저장소 표면이 과도하게 넓고, 신호 대 잡음비가 낮다

현재 압축본에는 코드 외에도 다음 성격의 자산이 대량 포함되어 있다.

- `.mypy_cache`, `.ruff_cache`, `.pytest_cache`
- `dist/`, `llm_wiki_vnext.egg-info/`
- `runs/`

- 코드 리뷰 시 실제 변경 표면보다 **생성 산출물이 더 강하게 시야를 점유**한다.
- “무엇이 source of truth인지”가 코드 독자에게 즉시 명확하지 않다.
- self-improvement 루프가 만들어내는 artifact 자체가 다시 저장소 복잡도를 밀어 올린다.

### 개선 제안

- **저장소를 더 명확히 분리**할 것
  1. 실행 코드/테스트/package surface
  2. workspace surface
  3. generated report/run history surface

---

## 4.2 `_runtime.py` 분해는 진행됐지만, 인지 복잡도는 충분히 줄지 않았다

파일 수 기준으로 보면 `ops/scripts/` 안에서 `_runtime.py`가 **96개**다. 이것은 분해를 많이 했다는 뜻이지만, 동시에 다음 징후이기도 하다.

- 책임이 잘 나뉜 것이 아니라 **오케스트레이션과 helper가 다층으로 흩어진 상태**일 수 있다.
- 한 기능을 이해하려면 관련 runtime file 여러 개를 순회해야 한다.
- “작게 쪼갰다”와 “이해하기 쉬워졌다”가 동일하지 않은데, 현재는 그 둘이 혼동될 여지가 있다.

실제로 긴 함수는 여전히 여러 개 남아 있다.

- `auto_improve_readiness_runtime.build_readiness_report` (137 lines)
- `mechanism_review_outcome_metrics_calibration_runtime.build_outcome_metrics_calibration_diagnostics` (132 lines)
- `structural_complexity_budget_runtime.build_report` (128 lines)
- `mechanism_review_history_runtime.load_mechanism_run_snapshots` (127 lines)
- `mechanism_review_session_calibration_runtime.session_calibration_summary` (126 lines)
- `mutation_proposal_runtime.build_report` (120 lines)
- `policy_validation_runtime.validate_policy_safety_invariants` (120 lines)
- `raw_intake_promotion_runtime.scaffold_profile_bundle` (115 lines)

즉, 현재 상태는 **“큰 파일을 작은 파일로 쪼갰지만, 중요한 판단 로직은 여전히 긴 함수 안에 남아 있는 구조”**에 가깝다.

### 개선 제안

- 파일 분해보다 **의사결정 분해(decision decomposition)** 를 우선할 것
- 각 긴 함수는 다음 셋으로 나누는 것이 좋다.
  1. 입력 정규화
  2. 판정/정책 계산
  3. 출력 조립
- 특히 `build_report` 류 함수는 공통적으로 다음 anti-slop 규칙을 적용할 것
  - 한 함수가 **schema load + source load + normalize + evaluate + summarize + serialize** 를 동시에 하지 않도록 분해
  - 최종 assemble 함수는 “이미 계산된 값”만 합치는 얇은 레이어로 유지
- `_runtime.py` 증설보다 먼저 **도메인 패키지 재편**을 검토할 것
  - 예: `ops/scripts/mechanism_review_*` -> `ops/mechanism_review/...`
  - 예: `ops/scripts/auto_improve_*` -> `ops/auto_improve/...`
  - 예: `ops/scripts/supply_chain_*` -> `ops/supply_chain/...`

이 프로젝트는 이제 스크립트 모음이 아니라 **도메인 패키지**로 다뤄야 한다.

---

## 4.3 구조 복잡도 경고 표면이 실제로 큰 책임 덩어리를 가리키고 있다

저장소 내부 `ops/reports/structural-complexity-budget.json`은 `attention` 상태이며, 특히 아래 파일들이 경고 표면으로 잡혀 있다.

### 1) `ops/scripts/raw_intake_promotion_runtime.py`

- nonempty line count: 789
- function count: 27
- branch node count: 102
- budget 초과: line/function/branch 모두 초과

이 파일은 이름상 “raw intake promotion”이지만 실제로는 다음이 뒤섞여 있다.

- matrix payload 해석
- synthesis/concept scaffold 생성
- bridge source 제안
- refresh profile 생성
- validation
- 텍스트 section 파싱 성격의 helper

즉, 하나의 작업이 아니라 **데이터 해석 + 초안 생성 + 검증 + 기존 코퍼스 연결**이 한 표면에 붙어 있다.

#### 개선 방향

- `matrix ingestion`
- `new family scaffold`
- `refresh scaffold`
- `profile validation`
- `bridge source suggestion`

을 별도 모듈로 쪼개고, 지금 파일은 orchestration만 남겨야 한다.

특히 `scaffold_profile_bundle()`은 새 family와 refresh 흐름을 동시에 품고 있어, “입력 matrix를 어떤 도메인 액션으로 분류하고 어떤 payload를 만들지”가 한 함수 안에 농축되어 있다. 이 로직은 **규칙 엔진** 또는 **action resolver + builder registry**로 바꾸는 편이 낫다.

---

### 2) `ops/scripts/observability_artifacts_runtime.py`

- nonempty line count: 767
- function count: 33
- branch node count: 77
- budget 초과

이 파일은 이름이 “observability”지만 실제로는 observability만 하지 않는다.

- fingerprint
- trends
- routing provenance
- multiple artifact schema wiring
- validation / write
- attempt/outcome linkage

즉, “관측성 artifact의 공통 모델”이 아니라 **관측성 관련 산출물 전체의 편집실**처럼 작동하고 있다.

#### 개선 방향

- artifact family별 submodule 분리
  - `artifact_fingerprint.py`
  - `promotion_decision_trends.py`
  - `routing_provenance.py`
  - `shared_schema_write.py`
- 이 파일은 `registry + shared write contract` 정도만 남기고, 각 artifact 계산은 별도 모듈로 이동
- “observability”라는 이름 아래 무엇까지 들어오는지 **수용 범위(boundary)** 를 명시할 것

지금 상태는 “관측성”이라는 좋은 이름이 **아무 artifact나 들어갈 수 있는 포켓**으로 쓰일 위험이 있다.

---

### 3) `ops/scripts/policy_validation_runtime.py`

- nonempty line count: 658
- line count만 예산 초과
- `validate_policy_safety_invariants()` 단일 함수가 120 lines

이 파일은 특히 anti-slop 관점에서 중요하다. 정책 검증은 본질적으로 **확장될수록 커지는 영역**이므로, 초기에 구조를 잡지 못하면 계속 비대해진다.

지금처럼 invariants를 한 함수에 계속 누적하면 다음 문제가 생긴다.

- 정책 규칙 추가가 “조건문 추가”로 귀결된다.
- 어떤 규칙이 어떤 운영 위험을 막는지 파악하기 어렵다.
- 실패 메시지의 일관성/분류 체계가 약해지기 쉽다.
- rule-level 단위 테스트보다 **거대한 회귀 테스트**에 의존하게 된다.

#### 개선 방향

- invariant를 **명명된 rule 객체/함수 목록**으로 분해
- 예: `RULES: list[PolicyInvariantRule]`
- 각 rule은 최소 계약을 가질 것
  - `id`
  - `summary`
  - `severity`
  - `evaluate(policy) -> list[Violation]`
- violation은 구조화된 typed object로 통일
- 보고서/CLI/테스트는 rule id 기준으로 다룰 것

정책 검증은 “if 숲”이 아니라 **정책 규칙 registry**가 되어야 한다.

---

## 4.4 코드 엔트리포인트의 `sys.path` 삽입이 너무 많다

`ops/scripts/*.py` 엔트리포인트 중 **42개 파일**에서 다음 패턴이 반복된다.

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
```

이 패턴은 단기적으로는 실행 편의를 주지만, anti-slop 관점에서는 좋지 않다.

- 패키징 경계보다 실행 편의가 앞선다.
- 테스트/런타임/직접 실행 시 import semantics가 달라질 수 있다.
- 엔트리포인트가 많아질수록 같은 boilerplate가 증식한다.
- “왜 이 스크립트는 단독 실행이 되고, 저 스크립트는 안 되는가”가 구조상 명확하지 않다.

### 개선 제안

- 직접 실행용 스크립트를 줄이고, `python -m ops.scripts.<name>` 또는 console script entry point로 통일
- `sys.path.insert(...)`는 공통 bootstrap 한 곳으로 수렴하거나 제거
- 엔트리포인트 레이어를 `cli/` 또는 `__main__` 경로로 분리
- “라이브러리 함수”와 “CLI 프론트”를 더 강하게 분리

지금 구조는 runtime helper를 잘게 나눈 반면, **실행 진입 방식은 여전히 ad-hoc**한 면이 있다.

---

## 4.5 테스트가 숨은 저장소 의존성(hidden repo dependency)을 드러내고 있다

저장소 루트의 `pytest_target.xml`에는 2026-04-21 시점의 타깃 테스트 실패가 남아 있다. 핵심 실패는 `structural_complexity_budget_runtime.build_report()`가 **임시 vault 안에서 schema 파일을 찾지 못해 실패**한 케이스다.

즉, 함수가 개념상 “주어진 vault에 대해 report를 빌드”한다고 되어 있지만, 실제로는 다음 성격의 암묵적 가정을 가진다.

- 특정 schema 파일이 repo/vault에 존재해야 한다.
- 테스트 fixture가 정책만 seed해도 충분하지 않다.
- 코드 계약이 “self-contained build”가 아니라 “repo state dependent build”에 가깝다.

이건 anti-slop 관점에서 매우 중요한 신호다. 왜냐하면 이런 코드는 보통 아래 문제를 낳기 때문이다.

- 함수가 재사용 가능해 보이지만 사실상 **특정 저장소 형태에 잠겨 있다**.
- temp dir 기반 테스트가 쉽게 깨진다.
- 기능 경계가 “입력 인자”가 아니라 “주변 파일 시스템 분위기”에 의해 결정된다.

### 개선 제안

- schema 로딩 전략을 명확히 둘로 나눌 것
  1. **package-bundled schema** 로드
  2. **vault override schema** 로드
- 기본 동작은 package-bundled schema로 하고, vault 쪽은 override/extension만 허용
- 테스트 fixture는 `seed_policy()`뿐 아니라 `seed_repo_contract_surface()` 같은 상위 fixture를 제공
- build 함수는 “필수 외부 파일 목록”을 명시적으로 받거나, missing dependency를 구조화된 오류로 반환할 것

핵심은 **“실제로 필요한 dependency를 숨기지 않는 것”**이다.

---

## 4.6 type/lint 게이트가 존재하지만 기본 강도는 아직 보수적이다

`pyproject.toml` 기준으로 현재 상태는 다음 성격이다.

- `ruff`: 사실상 `E/F` 중심의 최소 게이트
- `mypy`:
  - `follow_imports = skip`
  - `ignore_missing_imports = true`
  - `warn_unused_ignores = true`
- 별도로 strict preview allowlist는 존재하지만, 기본 게이트는 아니다.

이는 “기존 코드베이스를 깨지 않게 점진 도입”한다는 관점에서는 이해되지만, anti-slop 관점에서는 다음 한계가 있다.

- 타입이 있는 척 보이지만 실제로는 **untyped 영역이 넓게 남을 수 있다**.
- `ignore_missing_imports`와 `follow_imports=skip` 조합은 안전성보다 조용함을 우선시한다.
- strict preview가 존재해도 default가 아니면, 실제 개선 루프는 계속 느슨한 지대에서 돈다.

### 개선 제안

- 한 번에 전체 strict로 가지 말고 **typed island 전략**을 명시화
- 우선순위 surface:
  - `filesystem_runtime.py`
  - `output_runtime.py`
  - `policy_validation_runtime.py`
  - `auto_improve_*`
  - `promotion_*`
- mypy는 다음 순서로 강화
  1. `--check-untyped-defs` 확대
  2. 핵심 모듈에 `--disallow-untyped-defs`
  3. 핵심 경계에 `--disallow-untyped-calls`
  4. error code 단위 ratchet
- ruff는 preview allowlist를 운영 artifact가 아니라 **실제 품질 상승 레버**로 쓰도록 범위를 주기적으로 확대

현재 상태는 “엄격성 도구는 있음”인데, **엄격성이 기본 작동 모드가 아니라 선택 기능**에 머물러 있다.

---

## 4.7 broad exception 경계는 일부 정당하지만, 의미 경계가 더 필요하다

`except Exception`은 대체로 CLI boundary에 위치해 있어 무분별하다고 보기는 어렵다. 예를 들면 다음 류다.

- `auto_improve_loop.py`
- `executor_runtime.py`
- `finalize_run.py`
- `run_mechanism_experiment.py`
- `promotion_gate.py`

이건 CLI boundary라는 맥락에서 수용 가능한 경우가 많다. 다만 아래 두 종류는 더 정교해질 필요가 있다.

1. **파서/정규화 경계에서 모든 예외를 삼키는 경우**
   - 예: `raw_markdown_runtime.split_frontmatter()`의 tolerant parse boundary
2. **내부 오류를 CLI 일반 오류와 같은 방식으로 납작하게 만드는 경우**
   - 디버깅/관측성에서는 손해가 될 수 있음

### 개선 제안

- CLI boundary 예외 처리와 도메인 boundary 예외 처리를 분리
- parser는 `ParseResult(ok, value, warnings, error_kind)` 구조로 반환
- broad catch는 유지하더라도, 내부적으로는 **오류 분류 코드(error kind)** 를 반드시 남길 것
- self-improvement loop에서는 “무엇이 실패했는지”가 다음 mutation proposal의 근거가 되어야 하므로, 사람이 읽기 쉬운 문장보다 **기계가 다시 소비하기 쉬운 실패 분류**가 더 중요하다.

---

## 4.8 print 기반 CLI 출력이 많아 구조화 출력 계약을 약화시킨다

패턴 스캔 기준 `print(` 사용이 많고, 여러 CLI 스크립트가 `print(json.dumps(...))` 또는 `print(str(exc), file=sys.stderr)`를 사용한다.

문제는 print 자체가 아니라, **출력 계약의 종류가 코드 관점에서 1급 개념이 아닌 점**이다.

- stdout JSON
- stderr human-readable
- written_to 라인
- exit code

이 조합이 파일마다 반복되면서 사실상 **암묵적 CLI 프로토콜**이 만들어진다.

### 개선 제안

- 공통 CLI response helper 도입
  - `emit_success(payload, written_to=...)`
  - `emit_cli_error(kind, message, exit_code, details=None)`
- 모든 엔트리포인트는 동일한 stdout/stderr/exit code 규약을 사용
- 가능하면 machine JSON mode와 human mode를 분리

self-improvement 시스템에서는 출력도 다시 입력이 된다. 따라서 출력 포맷은 미학이 아니라 **계약**이다.

---

## 5. 자가 개선 관점 핵심 진단

## 5.1 “개선 시스템”은 존재하지만 아직 충분히 앞으로 나아가지 못한다

저장소 안에는 이미 상당히 많은 자가 개선 표면이 있다.

- `mechanism_review`
- `mutation_proposal`
- `auto_improve_readiness`
- `auto_improve_* runtime`
- `promotion gate`
- `outcome metrics`
- `observability artifacts`

즉, 개념은 이미 충분하다. 문제는 **개념 수가 많다는 사실이 곧 개선력이 높다는 뜻은 아니라는 점**이다.

실제 readiness report는 proposal이 있어도 runnable이 아니고, `recent_log_overlap` 같은 차단 요인 때문에 루프가 멈춰 있다. 이는 안전장치 자체는 존재하지만, 동시에 다음을 시사한다.

- 시스템이 스스로 **멈출 이유를 잘 만들지만**, 다시 전진시키는 경로는 약하다.
- 개선 후보 생성은 되는데, **실행 가능한 단위로 좁히는 능력**이 더 필요하다.
- report가 많아질수록 “설명은 되지만 행동은 안 되는” 상태가 생길 수 있다.

### 개선 제안

- readiness의 목적을 “정지 판단”에서 “다음 실행 가능한 최소 단위 선택”으로 이동
- blocked proposal에 대해 단순 blocked_by만 남기지 말고 다음 필드를 추가
  - `unblock_action_type`
  - `unblock_minimum_evidence`
  - `suggested_manual_step`
  - `suggested_auto_retry_window`
- `recent_log_overlap` 같은 차단 규칙은 **hard block**과 **soft cooldown**을 구분
- 현재처럼 queue가 비어 보이거나 runnable이 0이면, 시스템이 자동으로 더 작은 scope proposal을 재생성하도록 설계

지금은 “안전하게 멈추는 시스템”에 가까우며, 목표는 “작게라도 계속 전진하는 시스템”이어야 한다.

---

## 5.2 개선 후보의 우선순위 산정은 더 직접적인 결과지표와 연결되어야 한다

현재도 historical/session calibration, queue pressure, blocked 상태, overlap penalty 같은 개념이 들어 있다. 하지만 여전히 개선 우선순위가 **보고서 내부 설명력** 쪽으로 많이 기울어 있고, 실제 결과와의 연결은 더 강화할 여지가 있다.

### 개선 제안

우선순위 계산을 다음 네 층으로 정리할 것을 권한다.

1. **위험도**
   - 회귀 파급 범위
   - apply root 폭
   - runtime criticality

2. **개선 기대값**
   - 최근 실패/재작업 빈도
   - 동일 family 반복 HOLD/DISCARD 횟수
   - 구조 복잡도 attention 여부

3. **실행 용이성**
   - touched files 수
   - 필요한 schema/fixture 수
   - supporting test 존재 여부

4. **검증 가능성**
   - 단위 테스트로 국소 검증 가능한가
   - deterministic gate를 붙일 수 있는가
   - rollback rehearsal이 명확한가

현재 시스템은 2번과 4번의 서술은 풍부하지만, 3번을 더 적극적으로 계산해 **“작게 이길 수 있는 개선”** 을 앞으로 당겨야 한다.

---

## 5.3 개선 루프가 자기 자신을 더 강하게 평가해야 한다

self-improvement 시스템이 진짜 성숙하려면, 단순히 대상 코드를 평가하는 것만이 아니라 **개선 루프 자체의 성능**을 정량적으로 평가해야 한다.

현재 outcome metrics와 readiness artifact가 있으므로, 다음 지표를 추가하면 좋다.

### 제안 지표

- proposal 생성 대비 runnable 비율
- runnable proposal 대비 실제 실행 비율
- 실행 대비 promote 비율
- promote 후 동일 family 재작업 발생률
- 동일 failure mode 재발 시간
- “blocked 상태로 남은 평균 시간”
- report 생성량 대비 실제 merged/promoted 개선 수

이 지표가 없으면 self-improvement 시스템이 **실제로 개선하고 있는지, 아니면 개선을 설명하는 문서를 늘리고 있는지** 분간하기 어렵다.

---

## 5.4 mutation 단위를 더 작고 더 비가역성이 낮게 만들어야 한다

현재 구조는 상당히 안전 지향적이지만, 그만큼 mutation이 조금만 커져도 queue가 막히거나 signoff 부담이 올라갈 수 있다.

### 개선 제안

- mutation proposal 생성 시 기본 단위를 더 작게 제한
  - 한 번에 primary target 1개
  - supporting target 1~2개
  - 테스트 파일 1~2개
- proposal에 **blast radius score** 추가
- auto-improve는 낮은 blast radius proposal만 자동 실행
- 큰 mutation은 auto path가 아니라 assisted/manual path로 자동 분기

이렇게 해야 self-improvement 루프가 “큰 개선을 드물게 시도하는 시스템”이 아니라 **작은 개선을 꾸준히 적립하는 시스템**이 된다.

---

## 5.5 self-improvement 증거가 문서보다 코드 경계에 더 가까워져야 한다

현재는 report/json artifact가 풍부하다. 하지만 장기적으로 가장 좋은 증거는 다음이다.

- failing test가 pass로 바뀜
- complexity budget attention이 해소됨
- type coverage가 올라감
- apply root가 축소됨
- hidden dependency가 제거됨

즉, 개선 근거는 report 안에만 있지 말고 **코드/테스트/게이트 변화로 직접 체현되어야 한다.**

### 개선 제안

각 mutation proposal에 다음 “반드시 변해야 하는 증거”를 붙일 것.

- `must_change_tests`
- `must_change_budget_signal`
- `must_change_report_fields`
- `must_not_expand_apply_roots`
- `must_not_increase_untyped_surface`

이렇게 해야 proposal이 “설명 가능한 개선 가설”을 넘어서 **검증 가능한 변경 계약**이 된다.

---

## 6. 파일별 구체 보완 방향

## 6.1 `ops/scripts/raw_intake_promotion_runtime.py`

### 현재 문제

- responsibility mix가 크다.
- scaffold 생성과 validation이 같은 표면에 과도하게 붙어 있다.
- family 생성/refresh 생성/bridge source suggestion/section parsing 성격이 섞인다.

### anti-slop 보완안

- `bundle_builder.py`, `profile_validator.py`, `bridge_source_selector.py`, `refresh_scaffold.py`로 분리
- `proposed_action`에 대한 분기문 대신 registry 기반 builder 매핑 도입
- 생성 payload를 `TypedDict` 또는 dataclass로 구조화
- `analysis_blocks`, `related_pages`, `source_trace` 같은 반복 구조는 전용 builder 함수 사용

### self-improvement 보완안

- 새 family scaffold 품질을 측정하는 미니 score 도입
  - empty placeholder 비율
  - source_stems/bridge_source_stems 연결성
  - required section 충족도
- refresh profile 실패 패턴을 outcome metrics에 직접 연결

---

## 6.2 `ops/scripts/observability_artifacts_runtime.py`

### 현재 문제

- 이름에 비해 너무 많은 artifact family를 직접 다룬다.
- schema wiring + payload assemble + file write가 한 파일에 많이 모여 있다.

### anti-slop 보완안

- artifact family 단위로 모듈 분리
- 공통 write/validate helper만 공유
- artifact마다 `build_*`, `validate_*`, `write_*` 3단 계약 유지
- top-level registry는 artifact 선언 메타데이터만 보유

### self-improvement 보완안

- routing provenance와 outcome trend를 연결하는 “loop health summary” 산출물 추가
- self-improvement 관련 artifact는 별도 하위 namespace로 분리해 읽기 부담 감소

---

## 6.3 `ops/scripts/policy_validation_runtime.py`

### 현재 문제

- policy invariant가 함수 본문에 누적되는 구조
- 추가 규칙이 쌓일수록 가독성과 테스트 포인트가 악화될 위험

### anti-slop 보완안

- rule registry로 분해
- violation object 표준화
- rule별 단위 테스트 추가
- 규칙 설명과 코드가 1:1로 매핑되도록 id 부여

### self-improvement 보완안

- 어떤 policy invariant가 자주 mutation을 막는지 추적
- 반복적으로 막히는 rule은 “정책을 고칠지, 코드를 고칠지” decision report에 연결

---

## 6.4 `ops/scripts/structural_complexity_budget_runtime.py`

### 현재 문제

- 보고서 생성 함수가 길다.
- schema 의존이 temp-vault 테스트에서 드러나듯 숨은 저장소 의존성을 가진다.
- complexity report가 있으나, 개선 action 연결은 아직 약하다.

### anti-slop 보완안

- schema source를 package-bundled 기본값으로 전환
- target scan / function budget / report assembly 분리
- “주의(attention)”의 의미를 더 직접적으로 action-oriented하게 바꿀 것
  - split candidate
  - extract registry candidate
  - add type boundary candidate

### self-improvement 보완안

- complexity report의 top candidates를 mutation proposal seed로 자동 연결
- 단, report 전체를 seed하지 말고 **scope 1개**만 제안하도록 제한

---

## 6.5 `ops/scripts/auto_improve_readiness_runtime.py`

### 현재 문제

- readiness가 설명은 잘 하지만, blocked 상태를 executable next step으로 충분히 환원하지 못한다.
- queue가 막히면 사람이 reasoning해야 할 부분이 여전히 많다.

### anti-slop 보완안

- readiness report를 “상태 보고서”보다 “다음 액션 결정서”로 재정의
- blocked 이유마다 machine-readable remediation code 추가
- next_action 문자열보다 structured remediation payload를 우선

### self-improvement 보완안

- blocked proposal이 일정 시간 이상 유지되면 자동으로 narrower proposal 생성
- cooldown과 permanent block 구분
- 실행 가능한 후보가 0이면 fallback family를 자동 재스코프

---

## 6.6 `ops/scripts/codex_exec_executor.py`

### 현재 문제

- `execute_codex_exec_role()`가 길고, prompt materialization/command execution/report assembly의 관심사가 붙어 있다.
- self-improvement 루프의 실제 실행기인 만큼, 실패 이유를 더 세밀하게 구조화해야 한다.

### anti-slop 보완안

- prompt 준비 / sandbox execution / result classification / artifact capture를 분리
- executor result를 enum + structured diagnostics로 표준화
- “실패”를 한 덩어리로 두지 말고 timeout/input/contract/tooling/classification 실패로 나눌 것

### self-improvement 보완안

- executor failure class를 mutation outcome metrics와 직접 연결
- 어떤 failure class가 proposal family별로 반복되는지 집계

---

## 7. 우선순위별 실행 계획

## P0 — 즉시 착수 (1주 내)

### 목표

복잡도와 숨은 계약을 줄이고, self-improvement 루프의 “막힘”을 완화한다.

### 작업

1. `structural_complexity_budget_runtime.py`
   - schema 로딩을 package-bundled 기본으로 전환
   - temp vault 테스트 취약성 제거
2. `policy_validation_runtime.py`
   - invariant를 rule registry로 1차 분해
3. `raw_intake_promotion_runtime.py`
   - scaffold 생성 / validation 분리
4. `auto_improve_readiness_runtime.py`
   - blocked reason -> remediation payload 구조화
5. 엔트리포인트 공통화
   - `sys.path.insert(...)` boilerplate 제거 계획 수립

### 기대 효과

- 테스트 취약성 감소
- 복잡도 경고의 실질 해소 시작
- readiness가 실제 실행 계획으로 더 가까워짐

---

## P1 — 단기 개선 (2~4주)

1. `observability_artifacts_runtime.py` artifact family 분해
2. typed island 확대
   - filesystem/output/policy/auto_improve 계열부터
3. ruff strict preview 범위 확대
4. mutation proposal에 blast radius / remediation / must-change evidence 추가
5. blocked proposal 자동 축소(scope shrinking) 시도

### 기대 효과

- 코드 탐색 비용 감소
- 개선 proposal의 실행 성공률 상승
- self-improvement 루프의 실효성 증가

---

## P2 — 중기 재구성 (1~2개월)

1. `ops/scripts`를 스크립트 모음에서 도메인 패키지로 재편
2. observability / mechanism review / auto improve / supply chain 모듈군 재구성
3. report 중심 self-improvement를 test/budget/type delta 중심으로 전환

### 기대 효과

- 장기 유지보수성 상승
- 신규 기여자 온보딩 비용 감소
- generated artifact에 눌리지 않는 코드 중심 개선 체계 정착

---

## 8. anti-slop 체크리스트 제안

앞으로 변경마다 아래 체크리스트를 통과시키면 좋다.

### A. 경계

- 이 변경은 새로운 파일을 늘리기 전에 기존 책임을 줄였는가?
- 입력/판정/출력 경계를 분리했는가?
- 숨은 파일 시스템 의존성이 추가되지 않았는가?

### B. 검증

- 테스트가 문자열 스냅샷이 아니라 계약을 검증하는가?
- 실패 시 error kind가 구조화되어 남는가?
- report가 아니라 테스트/게이트 변화로 개선이 증명되는가?

### C. self-improvement

- 이 변경은 proposal을 더 runnable하게 만드는가?
- blocked 상태를 줄이는가, 아니면 설명만 늘리는가?
- 같은 family에서 재작업 가능성을 줄였는가?

### D. 복잡도

- 긴 함수가 줄었는가?
- branching이 registry/strategy로 대체되었는가?
- `_runtime.py` 파일 수 증가가 아니라 인지 복잡도 감소로 이어졌는가?

---

## 9. 결론

이 저장소의 가장 큰 장점은 **운영 메커니즘을 코드로 고정하려는 의지**가 강하다는 점이다. schema, gate, report, rollback, promotion, readiness, calibration이 이미 존재한다는 사실 자체는 좋은 기반이다.

하지만 현재 단계에서 가장 필요한 것은 새로운 개념을 더 추가하는 일이 아니다. 필요한 것은 다음 세 가지다.

1. **복잡도를 실제로 줄이는 구조 재편**
2. **자가 개선 루프를 더 작고 더 자주 전진시키는 실행 설계**
3. **보고서 중심 개선에서 코드/테스트/게이트 중심 개선으로의 이동**

한 문장으로 요약하면:

> 지금 코드는 “잘 관리하려는 시스템”으로는 상당히 성숙했지만, “덜 복잡하게 계속 좋아지는 시스템”으로 가려면 아직 몇 군데 핵심 병목을 더 걷어내야 한다.

우선순위는 명확하다.

- 첫째, `raw_intake_promotion_runtime.py`, `observability_artifacts_runtime.py`, `policy_validation_runtime.py`의 책임 분해
- 둘째, hidden dependency와 엔트리포인트 boilerplate 제거
- 셋째, self-improvement queue를 설명형 보고서에서 실행형 remediation으로 전환

이 세 축만 제대로 정리해도, 이 저장소는 “기능이 많은 운영 저장소”에서 **“검증 가능하게 스스로 나아지는 운영 코드베이스”** 로 한 단계 올라갈 수 있다.

---

## 10. 부록: 즉시 손볼 파일 목록

### 최우선

- `ops/scripts/raw_intake_promotion_runtime.py`
- `ops/scripts/observability_artifacts_runtime.py`
- `ops/scripts/policy_validation_runtime.py`
- `ops/scripts/structural_complexity_budget_runtime.py`
- `ops/scripts/auto_improve_readiness_runtime.py`

### 다음 순번

- `ops/scripts/codex_exec_executor.py`
- `ops/scripts/run_mechanism_experiment_runtime.py`
- `ops/scripts/mutation_proposal_runtime.py`
- `ops/scripts/mechanism_review_outcome_metrics_calibration_runtime.py`
- `ops/scripts/mechanism_review_session_calibration_runtime.py`

### 구조 개편 후보

- `ops/scripts/*` 전반의 CLI 엔트리포인트 레이어
- schema 로딩/출력/write helper 공통 경계
- self-improvement artifact와 실제 code delta 사이의 추적 계약
