# LLM\_Wiki\_vNext 코드 개선 방안 보고서

> 본 보고서는 `LLM_Wiki_vNext` 저장소의 소스 코드, 운영 스크립트, 스키마, 정책, 테스트, 자가 개선 루프를 **누락 없이** 검토하여 현재 성숙도를 진단하고, 우선순위별 보완 방안을 제시한다.

---

## 목차

1. [아키텍처 개요 및 구조 평가](#1-아키텍처-개요-및-구조-평가)
2. [강점: 잘 설계된 부분](#2-강점-잘-설계된-부분)
3. [문제점 분석 및 개선 방안](#3-문제점-분석-및-개선-방안)
4. [자가 개선 성숙도 평가](#4-자가-개선-성숙도-평가)
5. [개선 우선순위 로드맵](#5-개선-우선순위-로드맵)
6. [종합 결론](#6-종합-결론)

---

## 1. 아키텍처 개요 및 구조 평가

### 1.1 4-Layer 구조

| 레이어 | 위치 | 역할 | 변경 가능성 |
|--------|------|------|-------------|
| **Layer A** — Raw | `raw/` | 불변 원본 소스 | Immutable |
| **Layer B** — Knowledge Corpora | `wiki/`, `system/` | LLM 생성·유지 페이지 | Mutable |
| **Layer C** — Ops | `ops/` | policy / eval / lint / schema / scripts | Contract-oriented |
| **Layer D** — Operating Rules | `AGENTS.md` | 에이전트 행동 규칙 원본 | Semi-stable |

이 4-Layer 설계는 **소스의 불변성 보장**, **콘텐츠와 런타임의 분리**, **정책의 외부화**라는 세 가지 원칙을 구조적으로 실현하고 있다. 전체 설계 방향 자체는 매우 견고하다.

### 1.2 자가 개선 루프 구조

본 시스템은 3중 루프로 자가 개선을 구현한다.

```
Inner Loop (콘텐츠 유지)
  → source ingest → page 갱신 → lint/eval → keep/discard → log

Middle Loop (계획 및 게이트)
  → seed 동결 → plan 초안 → validation / signoff → bundle

Outer Loop (메커니즘 개선)
  → measure → localize → mutate (one mechanism) → evaluate → promote/discard → log
```

`Outer Loop`를 구현하는 스크립트 체인은 다음과 같이 완성되어 있다.

```
mechanism_review.py → mutation_proposal.py → run_mechanism_experiment.py
                      ↓
              promotion_gate.py → finalize_run.py
```

---

## 2. 강점: 잘 설계된 부분

### 2.1 Binary Eval 프레임워크

`wiki_eval.py`(Stage 1, 8개 eval)와 `wiki_stage2_eval.py`(Stage 2, 4개 eval)는 모두 **yes/no 이진 판단**을 유지하면서도 평가 범위를 점진적으로 확장하는 구조다. 특히 Stage 2는 `source_count` 정합성, 연구 앵커 레이어, 광범위 synthesis 경계, seed 흡수 힌트를 **기존 Stage 1 통과 후** 추가 검증하는 방식이다. 이 **단계적 eval** 설계는 gaming 위험을 최소화하는 우수한 패턴이다.

**Stage 1 Eval 목록 (wiki_eval.py)**

| # | Eval ID | 판단 기준 |
|---|---------|----------|
| 1 | `frontmatter_contract` | YAML frontmatter 필수 필드 존재 및 타입 일치 |
| 2 | `required_sections_present` | prefix/special page별 필수 섹션 존재 여부 |
| 3 | `source_trace_present` | Source trace 최소 항목 수 충족 여부 |
| 4 | `source_trace_targets_exist` | Source trace 내 로컬 경로의 실제 존재 여부 |
| 5 | `link_integration` | Related pages 최소 링크 수 충족 여부 |
| 6 | `broken_link_free` | 깨진 wikilink 부재 여부 |
| 7 | `source_page_substance` | Key points 4개↑ + Limitations 1개↑ 여부 |
| 8 | `decisionability` | synthesis/query 페이지의 Decision/takeaway 존재 여부 |

**Stage 2 Eval 목록 (wiki_stage2_eval.py)**

| # | Eval ID | 판단 기준 |
|---|---------|----------|
| 1 | `declared_source_count_matches_evidence` | synthesis의 source_count와 실제 링크 수 일치 |
| 2 | `central_research_source_has_anchor_layer` | 핵심 연구 논문 소스의 앵커 레이어 섹션 존재 |
| 3 | `broad_synthesis_has_boundary_sections` | 광범위 synthesis의 경계 및 미래 방향 섹션 존재 |
| 4 | `seed_source_has_absorption_hint` | source-only 시드의 흡수 힌트 섹션 존재 |

### 2.2 Thin CLI + Runtime 분리 패턴

대부분의 스크립트가 얇은 CLI 진입점(예: `promotion_gate.py`, 323줄)과 독립 런타임 모듈(예: `promotion_gate_mechanism_runtime.py`, 506줄)로 분리되어 있다. 이 패턴은 단위 테스트 작성을 크게 쉽게 만들고, CLI 변경이 로직에 파급되는 것을 막는다. **첫 번째 mechanism run**(`run-20260414-mechanism-planning-gate`)이 `planning_gate_validate.py`에 이 패턴을 적용한 것 자체가 자가 개선 루프가 실제로 작동한 증거다.

### 2.3 Schema-Driven 검증 체계

`ops/schemas/`에 12개의 JSON Schema 파일이 존재하며, 모든 artifact(promotion report, run-ledger, mechanism assessment, mutation proposals 등)가 스키마 검증을 거친다. 이는 LLM 에이전트가 만들어낸 JSON artifact의 형식 불일치를 방지하는 **핵심 안전망**이다.

### 2.4 Policy 외부화

`ops/policies/wiki-maintainer-policy.yaml`(policy version 3)이 런타임의 단일 진실 원천(Single Source of Truth)으로 기능하며, Python 코드 안에 미러링된 기본값이 없다. 이는 정책 변경이 코드 수정 없이 가능하고, 버전 관리가 명확한 장점을 제공한다.

### 2.5 테스트 규모

27개 테스트 파일, 총 약 6,945줄의 테스트 코드가 존재한다. 특히 `test_promotion_gate_equal_score.py`(589줄), `test_writer_output_paths.py`(797줄), `test_source_trace_checks.py`(529줄)는 핵심 경로를 충분히 커버하고 있다.

---

## 3. 문제점 분석 및 개선 방안

### 3.1 🔴 자가 개선 루프 — Bootstrap 미성숙 문제 (최우선)

**현황 진단**

`ops/reports/mechanism-review-candidates.json`은 현재 아래와 같이 보고하고 있다.

```json
"bootstrap": {
  "status": "bootstrap_history_insufficient",
  "summary": "comparable mechanism run history가 아직 부족해 trend-based candidate 평가 창이 열리지 않았다."
}
```

완료된 mechanism run은 단 **1건**(`run-20260414-mechanism-planning-gate`)뿐이다. `mechanism_branch_growth_without_test_growth_candidate`와 `mechanism_eval_stagnation_candidate` 모두 최소 **2건** 이상의 comparable run이 있어야 활성화된다. 그 결과 `mutation-proposals.json`의 `proposals` 배열도 **비어 있다**.

이는 **닭-달걀 순환 문제(cold-start problem)**다. 외부 루프가 구조적으로는 완성되어 있지만, 아직 이력 데이터가 충분하지 않아 스스로 다음 실험을 제안하지 못하는 상태다.

**개선 방안**

| 단계 | 내용 |
|------|------|
| **단기** | 동일 primary target(`ops/scripts/planning_gate_validate.py`) 또는 다른 적합한 target에 대해 2~3번의 추가 mechanism experiment를 실행하여 trend analysis 창을 활성화한다. |
| **단기** | `runs/README.md`에 "어떤 target을 선택해 다음 실험을 해야 하는가"를 가이드하는 bootstrap 지침을 추가한다. |
| **중기** | `mechanism_review_runtime.py`의 bootstrap 경고가 발생할 때 **bootstrap_suggestion** 필드를 추가하여 구체적인 다음 실험 대상 target을 자동으로 제안하게 한다. |

---

### 3.2 🔴 `run_mechanism_experiment_runtime.py` — 과도한 단일 파일 복잡도

**현황**

`run_mechanism_experiment_runtime.py`는 **1,066줄**로 전체 스크립트 중 가장 큰 파일이다. 이 파일 하나가 다음 역할을 모두 담당한다.

- scaffold 생성 (seed/plan/open-questions 초안)
- baseline/candidate measurement 호출
- repo health check (`make check`) 실행
- promotion gate 평가
- finalization 처리
- proposal snapshot 처리

이는 시스템이 다른 모듈에서 적용한 **thin CLI + runtime 분리 원칙을 스스로 위반**하고 있는 경우다. 특히 이 파일 자체가 향후 mechanism experiment의 primary target이 될 경우, 너무 큰 단위를 한꺼번에 변경하게 되어 `one mechanism per experiment` 원칙도 어려워진다.

**개선 방안**

아래와 같이 책임을 분리하는 리팩터링을 권장한다.

```
run_mechanism_experiment_runtime.py (현재 1,066줄)
    │
    ├── scaffold_runtime.py        (seed/plan/open-questions 생성 로직)
    ├── assessment_runtime.py      (baseline/candidate capture 호출)
    └── experiment_coordinator.py  (상위 흐름 조율)
```

이 분리는 그 자체로 mechanism experiment의 대상(`--primary-target`)이 될 수 있으며, 분리 후 테스트 커버리지 증가를 `candidate_eval`로 확인하는 정상적인 실험 절차를 따를 수 있다.

---

### 3.3 🟠 Schema 상수 중복 정의 — DRY 위반

**현황**

아래 4개 파일에 동일한 schema 경로 상수가 **각각 독립적으로 정의**되어 있다.

```python
# 동일한 상수가 4개 파일에 각각 존재
PROMOTION_REPORT_SCHEMA = "ops/schemas/promotion-report.schema.json"
```

| 파일 | 중복 상수 |
|------|----------|
| `finalize_run_runtime.py` | `PROMOTION_REPORT_SCHEMA`, `RUN_LEDGER_SCHEMA` |
| `mechanism_review_runtime.py` | `PROMOTION_REPORT_SCHEMA`, `EVAL_REPORT_SCHEMA` |
| `promotion_gate_common_runtime.py` | `PROMOTION_REPORT_SCHEMA`, `LINT_REPORT_SCHEMA`, `EVAL_REPORT_SCHEMA`, `RUN_LEDGER_SCHEMA` |
| `run_mechanism_experiment_runtime.py` | `PROMOTION_REPORT_SCHEMA`, `LINT_REPORT_SCHEMA`, `EVAL_REPORT_SCHEMA`, `RUN_LEDGER_SCHEMA` |

스키마 파일 경로가 변경될 경우 4곳을 모두 수정해야 하며, 하나라도 누락되면 런타임 에러로 이어진다.

**개선 방안**

`ops/scripts/schema_constants.py`(또는 `schema_runtime.py` 확장)에 모든 schema 경로 상수를 중앙화하고, 나머지 파일은 이를 `import`한다.

```python
# schema_constants.py (신규)
PROMOTION_REPORT_SCHEMA    = "ops/schemas/promotion-report.schema.json"
LINT_REPORT_SCHEMA         = "ops/schemas/lint-report.schema.json"
EVAL_REPORT_SCHEMA         = "ops/schemas/eval-report.schema.json"
RUN_LEDGER_SCHEMA          = "ops/schemas/run-ledger.schema.json"
MECHANISM_ASSESSMENT_SCHEMA = "ops/schemas/mechanism-assessment-report.schema.json"
```

---

### 3.4 🟠 핵심 Runtime 모듈의 직접 단위 테스트 부재

**현황**

현재 테스트 파일이 **완전히 누락된 핵심 모듈 7개**가 확인되었다.

| 누락된 테스트 파일 | 대상 모듈 | 위험도 |
|----------------|----------|--------|
| `test_wiki_eval.py` | `wiki_eval.py` (Stage 1 eval 핵심) | 🔴 높음 |
| `test_wiki_lint.py` | `wiki_lint.py` (lint 진입점) | 🔴 높음 |
| `test_frontmatter_runtime.py` | `frontmatter_runtime.py` | 🔴 높음 |
| `test_wiki_page_runtime.py` | `wiki_page_runtime.py` | 🟠 중간 |
| `test_source_trace_runtime.py` | `source_trace_runtime.py` | 🟠 중간 |
| `test_wiki_quality_runtime.py` | `wiki_quality_runtime.py` | 🟠 중간 |
| `test_output_runtime.py` | `output_runtime.py` | 🟡 낮음 |

`wiki_eval.py`와 `wiki_lint.py`는 `make check`의 핵심 gate임에도 직접적인 단위 테스트가 없다. 통합 경로를 통해 간접적으로 검증되고 있으나, 회귀 탐지 속도와 실패 지점 특정 능력이 제한된다.

**개선 방안**

우선순위 순으로 테스트를 추가한다. 특히 `test_wiki_eval.py`는 다음을 반드시 포함해야 한다.

- 각 8개 Stage 1 eval의 pass/fail 경계 조건 테스트
- `duplicate_stems` 조기 종료 경로 테스트
- frontmatter 파싱 실패 시 `frontmatter_ok = False` 처리 테스트

---

### 3.5 🟠 테스트 인프라 설정 파일 부재

**현황**

`pytest.ini`, `conftest.py`, `.coveragerc`, `tox.ini` 중 어느 것도 존재하지 않는다. `requirements.txt`에는 `PyYAML`과 `jsonschema` 두 개만 있어, `pytest` 자체도 선언되어 있지 않다.

**개선 방안**

```ini
# pytest.ini (신규)
[pytest]
testpaths = tests
python_files = test_*.py
addopts = --tb=short -q
```

```text
# requirements-dev.txt (신규)
pytest>=8.0,<9
pytest-cov>=5.0,<6
coverage[toml]>=7.0,<8
```

`conftest.py`에는 공통 임시 vault fixture를 중앙화한다. 현재 각 테스트 파일이 개별적으로 `tmp_path`를 사용해 임시 디렉터리를 만드는 패턴이 반복되는데, 이를 공유 fixture로 통일하면 테스트 유지 비용이 줄어든다.

---

### 3.6 🟠 CI/CD 파이프라인 부재

**현황**

`.github/workflows/` 디렉터리가 존재하지 않는다. `make check`는 로컬 실행 전용이며, 커밋이나 PR 시 자동 검증이 이루어지지 않는다.

**개선 방안**

```yaml
# .github/workflows/check.yml (예시)
name: check
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: make check
      - run: pytest tests/ --cov=ops/scripts --cov-report=xml
```

---

### 3.7 🟡 `finalize_run_runtime.py` — KST 시간대 하드코딩

**현황**

```python
# finalize_run_runtime.py:21
KST = dt.timezone(dt.timedelta(hours=9))
```

UTC 기반 `run-ledger.json` 이벤트 타임스탬프와 달리, `system-log.md`의 헤더 포맷(`[YYYY-MM-DD HH:MM]`)이 KST로 고정되어 있다. 이 저장소가 KST 이외 환경에서 운영되거나, 향후 다른 타임존 사용자가 참여할 경우 로그 타임스탬프 불일치가 발생한다.

**개선 방안**

로컬 표시 시간대를 `ops/policies/wiki-maintainer-policy.yaml`의 `display_timezone` 키로 외부화한다.

```yaml
# wiki-maintainer-policy.yaml 추가 항목
display:
  log_header_timezone: "Asia/Seoul"   # 현재 KST 하드코딩을 대체
```

---

### 3.8 🟡 Mechanism Review Family Catalog — v1의 제한된 다양성

**현황**

`mechanism_review_runtime.py`의 candidate family catalog은 현재 v1이며, 두 가지 family만 존재한다.

```
self_mod_stability
contract_regression_signals
```

분기 성장 없는 테스트 정체(`mechanism_eval_stagnation_candidate`)와 분기 성장을 감지하는 두 가지 candidate type만 생성 가능하다.

**개선 방안**

다음 family를 v2 로드맵으로 고려할 수 있다.

| 신규 Family | 감지 대상 |
|------------|---------|
| `schema_drift` | schema 변경이 test 없이 승격되는 패턴 |
| `policy_complexity_growth` | policy YAML이 지속적으로 커지는 신호 |
| `eval_coverage_gap` | eval이 특정 prefix type을 커버하지 못하는 구조적 공백 |
| `raw_registry_lag` | raw 등록 후 ingest까지의 평균 지연이 늘어나는 신호 |

---

### 3.9 🟡 `wiki_lint_registry_runtime.py` — 추가 분리 권장

**현황**

`wiki_lint_registry_runtime.py`는 677줄로, registry contract 검증, shard 파싱, source trace 해결, review candidate 생성 등 다수의 책임을 단일 파일에서 처리하고 있다. 이는 `run_mechanism_experiment_runtime.py`와 유사한 패턴이다.

**개선 방안**

```
wiki_lint_registry_runtime.py (현재 677줄)
    ├── registry_contract_runtime.py   (contract 검증)
    └── registry_shard_runtime.py      (shard 파싱 + review candidate)
```

---

## 4. 자가 개선 성숙도 평가

### 4.1 성숙도 요약 매트릭스

| 평가 차원 | 현재 상태 | 성숙도 점수 | 비고 |
|----------|---------|-----------|------|
| **Outer Loop 구조 완성도** | 전체 파이프라인 구현 완료 | ⭐⭐⭐⭐⭐ | mechanism\_review → mutation\_proposal → run\_experiment → gate → finalize |
| **Binary Eval 신뢰성** | Stage 1(8개) + Stage 2(4개) 안정적 작동 | ⭐⭐⭐⭐⭐ | 스키마 검증 포함 |
| **실험 이력 축적** | 1건 완료 (PROMOTE 결정) | ⭐⭐ | bootstrap\_history\_insufficient 상태 |
| **자동 후속 제안 능력** | proposals 배열 비어 있음 | ⭐ | cold-start 문제 |
| **테스트 안전망** | 핵심 7개 모듈 테스트 누락 | ⭐⭐⭐ | 통합 경로로 간접 커버 |
| **CI/CD 자동화** | 없음 | ⭐ | 로컬 make check만 존재 |
| **Policy 외부화** | policy v3, schema 12개 | ⭐⭐⭐⭐⭐ | 완성도 높음 |
| **스키마 상수 관리** | 4개 파일에 중복 정의 | ⭐⭐ | DRY 위반 |
| **코드 복잡도 관리** | run\_mechanism\_experiment\_runtime.py 1,066줄 | ⭐⭐ | 자가 개선 원칙 자기 위반 |

### 4.2 자가 개선 성숙도 단계 진단

이 시스템의 자가 개선 성숙도는 **"구조적 완성 단계, 실행 경험 부족 단계"** 에 해당한다.

**갖춰진 것 (Level 3 수준의 구조)**

measure → localize → mutate → evaluate → promote/discard → log의 완전한 루프가 스크립트로 구현되어 있다. 첫 번째 실험이 실제로 `PROMOTE` 결정을 낳고, `system-log.md`에 기록되었다. binary eval로 개선 여부를 판단하는 객관적 기준이 존재한다. same-eval 예외(equal-score promotion) 경로까지 설계되어 있다.

**부족한 것 (Level 1~2 행동 수준)**

시스템이 **스스로 다음 실험 후보를 제안하지 못하는 상태**다. 현재는 사람이 `--primary-target`을 직접 지정해야 한다. 단 1건의 run 이력으로는 trend-based candidate 탐지가 불가능하다. CI에 연결되지 않아 회귀가 자동으로 감지되지 않는다.

---

## 5. 개선 우선순위 로드맵

| 우선순위 | 작업 항목 | 예상 효과 |
|---------|---------|---------|
| **P0** | comparable mechanism run 2~3건 추가 실행 | bootstrap 문제 해소, trend candidate 활성화 |
| **P1** | `test_wiki_eval.py`, `test_wiki_lint.py` 작성 | 핵심 gate 회귀 탐지 |
| **P1** | `pytest.ini` + `requirements-dev.txt` 추가 | 테스트 인프라 표준화 |
| **P2** | `.github/workflows/check.yml` 추가 | 자동 CI 게이트 |
| **P2** | schema 상수를 `schema_constants.py`로 중앙화 | DRY 위반 해소 |
| **P3** | `run_mechanism_experiment_runtime.py` 분리 | 단일 파일 복잡도 해소 (그 자체가 다음 실험 대상) |
| **P3** | `finalize_run_runtime.py` KST 하드코딩 → policy 외부화 | 이식성 개선 |
| **P4** | mechanism review family v2 설계 | 자동 후보 다양성 확대 |
| **P4** | `wiki_lint_registry_runtime.py` 추가 분리 | 코드 유지보수성 향상 |

---

## 6. 종합 결론

`LLM_Wiki_vNext`는 **LLM 기반 persistent wiki와 자가 개선 메커니즘을 통합한 정교한 시스템**이다. 4-layer 아키텍처, binary eval, policy 외부화, schema-driven 검증, thin CLI + runtime 분리 패턴은 모두 현 상태에서도 높은 완성도를 보인다.

자가 개선 루프는 **파이프라인 구조는 완성**되어 있으나, **실행 이력의 절대적 부족**으로 인해 아직 스스로 다음 실험을 제안하거나 실행하지 못한다. 이는 설계 결함이 아니라 **부트스트랩 단계의 자연스러운 제약**이다. 추가 mechanism experiment를 2~3건 더 실행하면 trend-based 분석이 활성화되고, mutation proposal 파이프라인이 실질적으로 작동하기 시작할 것이다.

가장 시급한 개선 포인트는 CI 연결과 핵심 모듈 단위 테스트 추가이며, 이를 통해 외부 루프가 작동할 때 발생할 수 있는 회귀를 자동으로 감지하는 안전망을 갖추는 것이 다음 단계의 성숙도 달성을 위한 핵심 전제 조건이다.
