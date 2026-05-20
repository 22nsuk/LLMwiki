# LLMwiki 실제 코드 변경 구현 보고서

- 작성일: 2026-05-16
- 작성 언어: 한국어
- 파일명: `llmwiki_code_change_implementation_report_20260516.md`
- 목적: 앞선 3개 리뷰와 기존 대조 보고서를 실제 코드 변경 작업으로 바로 연결할 수 있도록, **수정 대상 파일·권장 변경 내용·예상 영향·검증 방법**을 파일 단위로 정리한다.

---

## 1. 이 문서의 성격

이 문서는 “무엇이 문제인가”를 반복하는 리뷰 문서가 아니라, **실제 PR을 어떻게 쪼개고 어떤 파일을 어떤 순서로 고칠지**를 정리한 구현 지시 문서다.

핵심 목표는 아래 네 가지다.

1. `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT`를 제거해 **불필요한 수동 갱신 게이트**를 없앤다.
2. source package lane에서 `ops/script-output-surfaces.json` 부재로 생기는 실패를 실제 코드 수준에서 줄인다.
3. `tests/test_makefile_static_gates.py`와 workflow static test를 **문자열 고정 테스트**에서 **구조 검증 테스트**로 바꾼다.
4. goal runtime은 이미 들어와 있으므로, 다음 단계는 “존재 여부 확인”이 아니라 **process-persistent backend / 모듈 분해 / 장기 실행 관측성 보강**이다.

---

## 2. 이번 보고서 작성 시 직접 다시 맞춰 본 사실

이번 보고서는 기존 리뷰를 재인용하는 데 그치지 않고, 업로드된 source package와 실제 파일을 다시 맞춰서 작성했다.

### 2.1 현재 source package에서 직접 확인한 사실

- `mk/test.mk`에 `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT ?= 1263`가 여전히 존재한다.
- `mk/test.mk`의 `test-execution-summary-full-refresh`는 full suite를 돌린 뒤 JSON에서 `pytest_collect_nodeid_digest.nodeid_count`를 읽어 **1263과 다르면 실패**한다.
- `README.md`, `ops/README.md`에도 이 고정 count 전제가 문서화되어 있다.
- `tests/test_makefile_static_gates.py`는 위 상수 문자열과 echo/error 문구를 그대로 assert한다.
- source package lane은 `mk/release.mk`의 `SOURCE_PACKAGE_TEST_DESELECTS`로 아래 다섯 파일을 직접 `--deselect` 한다.
  - `tests/test_generated_report_contracts.py`
  - `tests/test_external_report_lifecycle_static.py`
  - `tests/test_import_fallback_contract.py`
  - `tests/test_script_module_surface_contract.py`
  - `tests/test_writer_output_paths.py`
- `ops/policies/source-package-test-deselections.json`도 같은 5건을 budget 5로 허용한다.
- source package 안에는 `ops/script-output-surfaces.json`가 없다.
- 반면 `ops/script-module-surfaces.json`는 source package 안에 들어 있다.
- `ops/scripts/core/codex_goal_client.py`는 실제로 존재하지만, 현재 기본 backend는 `FakeGoalBackend`이며 `persistent_across_processes=False`다.
- `ops/scripts/mechanism/auto_improve_goal_runtime.py`는 1,063 lines 규모의 대형 모듈이며, `run_goal_bound_auto_improve`, `_run_auto_improve_with_optional_sustain`, `_maintenance_loop`에 책임이 많이 몰려 있다.
- `ops/scripts/core/command_runtime.py`는 heartbeat 필드를 갖고 있지만 여전히 `communicate()` 중심 구현이어서, “마지막 stdout 시각” 같은 세밀한 장기 런 관측성을 바로 추가하기 쉬운 구조는 아니다.

### 2.2 이번에 다시 돌려 본 최소 검증

- `PYTHONPATH=. python -m pytest --collect-only -q` 결과를 합산하면 **1263개**가 수집된다.
- `PYTHONPATH=. python -m pytest -q tests/test_codex_goal_client.py tests/test_codex_goal_contract.py`는 통과한다.
- 현재 source package 구조만 보면 `ops/script-output-surfaces.json`가 비어 있는 게 아니라 **아예 포함되어 있지 않기 때문에**, 관련 3개 테스트 모듈을 source-package lane에서 제외한 이유가 코드 수준에서 설명된다.

---

## 3. 실제 변경 원칙

### 3.1 없애야 하는 것
- **고정 숫자 gate**
- **긴 문자열 exact assert**
- **source package에서 의도적으로 없는 artifact를 전제로 한 무조건 실패**
- **production 경로에서의 silent fake backend fallback**

### 3.2 반드시 유지해야 하는 것
- `pytest_collect_nodeid_digest`
- `nodeid_outcome_consistency`
- `test_target_fingerprints`
- `failed-nodeids` artifact
- `deselection_lifecycle`
- release/readiness/goal runtime 핵심 safety test
- sealed release / post-seal / release-closeout summary 계열 보호막

### 3.3 지금 당장 하지 말아야 하는 것
- full suite evidence 제거
- release authority vocabulary 완화
- source package exclusion을 무작정 없애고 raw `pytest`를 억지로 green 처리
- goal runtime 핵심 테스트를 삭제해서 속도를 맞추기

---

## 4. 권장 PR 분해

가장 안전한 구현 순서는 아래와 같다.

| PR | 목적 | 위험도 | 권장 범위 |
|---|---|---:|---|
| PR-1 | expected node count 제거 + summary consistency 강화 | 낮음 | Make, docs, test 3~4개 파일 |
| PR-2 | source package lane 실질 보정 | 중간 | clean extract runtime, release mk, deselection policy, 관련 test |
| PR-3 | static contract test 구조화 | 중간 | `test_makefile_static_gates.py`, workflow static tests, 일부 generated report tests |
| PR-4 | goal runtime hardening | 중상 | `codex_goal_client.py`, goal runtime, status/runtime tests |
| PR-5 | 장기 런 관측성 개선 | 중상 | `command_runtime.py`, executor/goal status 쪽 연동 |

권장 방식은 **PR-1 → PR-2 → PR-3 → PR-4** 순서다. PR-5는 구조 변경 폭이 있어서 마지막으로 미루는 편이 안전하다.

---

## 5. PR-1: `EXPECTED_NODE_COUNT` 제거와 summary consistency 강화

### 5.1 수정 대상 파일

- `mk/test.mk`
- `README.md`
- `ops/README.md`
- `tests/test_makefile_static_gates.py`
- `tests/test_test_execution_summary.py`

### 5.2 현재 문제

현재 `test-execution-summary-full-refresh`는 아래 방식으로 동작한다.

1. full suite를 실행해 summary JSON 생성
2. JSON의 `pytest_collect_nodeid_digest.nodeid_count`를 읽음
3. 그 값이 `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT`와 다르면 실패

이 설계는 아래 이유로 유지 가치가 낮다.

- 테스트가 1개 늘거나 줄면 **정상적인 변경**도 실패가 된다.
- 실제 중요한 변화는 count가 아니라 **nodeid 집합과 fingerprint 변화**다.
- 이미 요약 artifact 안에 더 강한 증거가 있다.
  - `pytest_collect_nodeid_digest.sha256`
  - `nodeid_outcome_consistency`
  - `test_target_fingerprints`
  - `failed_nodeids`
  - `deselection_lifecycle`

### 5.3 구체 변경안

#### A. `mk/test.mk`
아래 두 가지를 한다.

1. `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT ?= 1263` 삭제
2. `test-execution-summary-full-refresh`의 shell count equality block 삭제

즉, 아래 구간을 제거한다.

```make
TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT ?= 1263

test-execution-summary-full-refresh: test-execution-summary-full
	@actual=$$($(PYTHON) -c 'import json; data=json.load(open("$(TEST_EXECUTION_SUMMARY_FULL_OUT)", encoding="utf-8")); print(data.get("pytest_collect_nodeid_digest", {}).get("nodeid_count", ""))'); \
	if [ "$$actual" != "$(TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT)" ]; then \
		echo "full-suite node count $$actual does not match expected $(TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT); update TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT only with refreshed full evidence"; \
		exit 1; \
	fi
	@echo "full-suite evidence refreshed against expected collect-only node count $(TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT)"
```

대신 아래 정도로 바꾸는 것이 좋다.

```make
test-execution-summary-full-refresh: test-execution-summary-full
	@echo "full-suite evidence refreshed; collect-only nodeid digest and count recorded in $(TEST_EXECUTION_SUMMARY_FULL_OUT)"
```

핵심은 **blocking removal**이지, 별도 새 gate를 급하게 끼워 넣는 것이 아니다.

#### B. `README.md`, `ops/README.md`
아래 문장을 삭제/치환한다.

- `TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT=1263`
- “테스트 추가/삭제 시 기준값을 갱신해야 한다”는 설명

대체 문구는 아래 방향이 맞다.

- full suite refresh는 **recorded nodeid digest / count / test_target_fingerprints**를 남긴다.
- 변화 판단은 operator가 **digest/fingerprint/evidence freshness**를 기준으로 본다.
- count는 기록값이지, 더 이상 release-blocking constant가 아니다.

#### C. `tests/test_makefile_static_gates.py`
다음 assertion은 제거 대상이다.

- 상수 literal assert
- expected count echo string assert
- mismatch error string assert

즉, 아래 성격의 검증을 없앤다.

- `"TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT ?= 1263"`
- `"full-suite evidence refreshed against expected collect-only node count ..."`
- `"full-suite node count $$actual does not match expected ..."`

대신 남겨야 하는 것은 아래뿐이다.

- `test-execution-summary-full-refresh` target 존재
- `test-execution-summary-full-refresh`가 `test-execution-summary-full`에 의존
- full summary target이 shard aggregate, junit, log, failed-nodeids out을 계속 남김

#### D. `tests/test_test_execution_summary.py`
이 파일은 삭제가 아니라 **강화** 대상이다.

추가 권장 테스트는 아래 3개다.

1. aggregate summary에 `pytest_collect_nodeid_digest.status == "collected"`일 때 `nodeid_outcome_consistency.status`가 함께 구조적으로 존재하는지 확인
2. `failed-nodeids` artifact가 있을 때, `failed + errors`와 artifact line count가 맞는지 확인
3. JUnit artifact가 있을 때 summary total과 JUnit testcase count가 어긋나는 경우를 fail/attention으로 분류하는 helper 테스트 추가

여기서 중요한 점은, **Makefile에서 숫자를 맞추는 대신 summary artifact 자체의 자기 일관성**을 테스트 레벨에서 강화하는 것이다.

### 5.4 완료 기준

- 테스트 추가/삭제만으로 `mk/test.mk`, `README.md`, `ops/README.md`, `tests/test_makefile_static_gates.py`를 동시에 수정하지 않아도 된다.
- `test-execution-summary-full-refresh`는 full evidence 생성 자체만 담당한다.
- summary artifact의 무결성은 `tests/test_test_execution_summary.py`가 맡는다.

---

## 6. PR-2: source package lane 실질 보정

### 6.1 수정 대상 파일

- `ops/scripts/core/source_package_clean_extract.py`
- `mk/release.mk`
- `ops/policies/source-package-test-deselections.json`
- `tests/test_source_package_clean_extract.py`
- `tests/test_makefile_static_gates.py`

### 6.2 현재 문제

source package 안에는 `ops/script-output-surfaces.json`가 없는데, 아래 세 파일은 그 artifact를 직접 읽는다.

- `tests/test_import_fallback_contract.py`
- `tests/test_script_module_surface_contract.py`
- `tests/test_writer_output_paths.py`

그래서 현재 source-package lane은 이 세 파일을 통째로 `--deselect` 한다.

이 방식의 문제는 다음과 같다.

- artifact 부재를 **실행 중 생성 가능**한 문제로 보지 않고, 테스트 모듈 자체를 영구 제외하고 있다.
- deselection budget 5개 중 3개를 단지 artifact 한 개 부재 때문에 쓰고 있다.
- source package clean extract report가 실제로 “extract 후 무엇을 생성해서 어떤 테스트를 돌렸는가”를 덜 설명하게 된다.

### 6.3 권장 구현 방향

여기서는 **artifact를 source package extract 안에서 생성**하는 쪽이 더 적합하다.

즉, `release-source-package-check` 전에 현재 vault에서 미리 만들 것이 아니라,
`ops/scripts/core/source_package_clean_extract.py`가 **extract root에서 직접** 아래 명령을 먼저 실행하도록 바꾼다.

```bash
python -m ops.scripts.script_output_surfaces --vault . --out ops/script-output-surfaces.json
```

이 방식의 장점은 다음과 같다.

- source ZIP의 본래 구조는 그대로 유지할 수 있다.
- extract 내부에서 필요한 canonical artifact를 명시적으로 재생성하므로 **재현성 설명력이 높다**.
- `tests/test_import_fallback_contract.py`, `tests/test_script_module_surface_contract.py`, `tests/test_writer_output_paths.py`를 deselect 목록에서 뺄 수 있다.

### 6.4 구체 변경안

#### A. `ops/scripts/core/source_package_clean_extract.py`

`_clean_extract_commands()`의 현재 명령 순서는 다음과 같다.

1. ruff
2. mypy
3. test-source-package

여기에 **0번 단계**를 추가한다.

```python
("script-output-surfaces", [
    request.source_python,
    "-m",
    "ops.scripts.script_output_surfaces",
    "--vault",
    ".",
    "--out",
    "ops/script-output-surfaces.json",
])
```

최종 순서는 아래가 된다.

1. `script-output-surfaces`
2. `ruff`
3. `mypy`
4. `test-source-package`

이때 보고서에도 아래 상태를 추가하는 것이 좋다.

- `script_output_surfaces_status`

지금도 `commands[]` 배열에는 들어가겠지만, top-level 요약 상태가 있으면 source package clean extract report를 읽는 쪽이 더 쉽다.

#### B. `mk/release.mk`

현재:

```make
SOURCE_PACKAGE_TEST_DESELECTS ?= --deselect=tests/test_generated_report_contracts.py --deselect=tests/test_external_report_lifecycle_static.py --deselect=tests/test_import_fallback_contract.py --deselect=tests/test_script_module_surface_contract.py --deselect=tests/test_writer_output_paths.py
```

PR-2에서는 아래처럼 줄이는 것이 좋다.

```make
SOURCE_PACKAGE_TEST_DESELECTS ?= --deselect=tests/test_generated_report_contracts.py --deselect=tests/test_external_report_lifecycle_static.py
```

즉, 5개 → 2개로 줄인다.

#### C. `ops/policies/source-package-test-deselections.json`

현재 budget:

```json
"max_count": 5
```

PR-2에서는 아래로 줄인다.

```json
"max_count": 2
```

그리고 실제 항목도 5개 → 2개로 줄인다.

남길 항목:
- `tests/test_generated_report_contracts.py`
- `tests/test_external_report_lifecycle_static.py`

제거할 항목:
- `tests/test_import_fallback_contract.py`
- `tests/test_script_module_surface_contract.py`
- `tests/test_writer_output_paths.py`

### 6.5 `tests/test_source_package_clean_extract.py` 변경점

현재 테스트는 command 수를 3개로 본다.

```python
self.assertEqual(len(report["commands"]), 3)
self.assertEqual(len(calls), 3)
```

PR-2 이후에는 4개로 바뀌어야 한다.

또한 아래 검증을 추가해야 한다.

- 첫 번째 command name이 `script-output-surfaces`
- extract root 아래 `ops/script-output-surfaces.json`가 생성되었는지
- test-source-package 실행 전에 artifact가 만들어졌는지

### 6.6 완료 기준

- source package clean extract가 extract 내부에서 `ops/script-output-surfaces.json`를 생성한다.
- source-package deselection budget이 5 → 2로 줄어든다.
- source-package lane에서 output-surface artifact 부재 때문에 3개 모듈을 통째로 빼지 않아도 된다.

---

## 7. PR-3: static contract test를 구조 검증으로 전환

### 7.1 수정 대상 파일

- `tests/test_makefile_static_gates.py`
- `tests/test_ci_workflow_static.py`
- `tests/test_release_workflow_static.py`
- `tests/test_generated_report_contracts.py`
- `tests/test_report_schema_sample_regeneration.py`
- `tests/test_writer_output_paths.py`

### 7.2 `tests/test_makefile_static_gates.py`

#### 현재 문제
- 2,653 lines
- 54 tests
- 대량의 `assertIn("literal", text)` 중심
- recipe 순서·echo 문구·변수 literal까지 고정

#### 권장 방향
이 파일은 삭제가 아니라 **semantic parser test**로 바꿔야 한다.

#### 구체 변경
1. `_target_block()`는 유지
2. 새 helper를 추가
   - `_assert_target_depends_on(target, dep)`
   - `_assert_recipe_contains_tokens(target, required_tokens)`
   - `_assert_assignment_exists(name)`
   - `_assert_assignment_not_exists(name)`
3. “한 줄 전체 exact match”를 줄이고, **필수 token 집합**만 검사

예:
- 기존: 전체 `python -m ops.scripts.test_execution_summary ...` 문자열 exact assert
- 변경: target이
  - `ops.scripts.test_execution_summary`
  - `--collect-nodeids`
  - `--junit-xml-path`
  - `--execution-log-out`
  - `--failed-nodeids-out`
  를 포함하는지만 검사

#### 기대 효과
- 작은 recipe 리팩터링에도 테스트가 덜 깨진다.
- 파일 길이를 30~50% 줄일 수 있다.
- 불필요한 string churn이 크게 줄어든다.

### 7.3 `tests/test_ci_workflow_static.py`, `tests/test_release_workflow_static.py`

#### 현재 문제
YAML을 파싱하면서도 핵심 검증은 여전히 string exact assert 비중이 높다.

#### 권장 방향
- job / step / matrix / artifact name 단위로 YAML 구조 검증
- exact shell line 전체 비교는 최소화
- lockfile install pattern 같은 반복 검증은 helper 함수로 빼기

#### 예시
- 유지할 것:
  - 특정 job 존재
  - 특정 step name 존재
  - matrix tier / python-version 일치
  - artifact upload step 존재
- 줄일 것:
  - 긴 multi-line shell literal 전체 존재 여부
  - 들여쓰기 수준까지 text로 검증하는 방식

### 7.4 `tests/test_generated_report_contracts.py`

#### 현재 문제
source package에서 빠지는 checked-in generated artifact를 많이 직접 읽는다.
이 파일 전체를 없애면 안 되지만, 지금은 너무 많은 항목을 개별 test로 쪼개 두었다.

#### 권장 방향
artifact tier를 도입한다.

- **Tier 1**
  - `artifact-freshness`
  - `generated-artifact-index`
  - `test-execution-summary`
  - `auto-improve-readiness`
  - release 핵심 report
- **Tier 2**
  - supply-chain / backfill / reference manifest 계열
- **Tier 3**
  - observation / archive / historical note 계열

그리고 같은 패턴은 `pytest.mark.parametrize`로 묶는다.

### 7.5 `tests/test_report_schema_sample_regeneration.py`

#### 현재 문제
fixture governance와 direct script smoke가 한 파일에 섞여 있고, 현재 6 tests 대비 wall-clock이 상대적으로 크다.

#### 권장 방향
- generator output vs fixture equality smoke 1~2개
- direct `--check` smoke 1개
- stale fixture failure path는 최소화

### 7.6 `tests/test_writer_output_paths.py`

#### 현재 문제
이 파일은 두 역할이 섞여 있다.

1. 실제 runtime output path contract
2. checked-in `ops/script-output-surfaces.json` inventory parity

#### 권장 방향
둘을 분리한다.

- `tests/test_output_runtime_contract.py`
  - relative path under vault
  - permissive vs repo artifact classification
  - resolver misuse 방지
- `tests/test_script_output_surface_inventory.py`
  - AST inventory == `ops/script-output-surfaces.json`
  - allowed output option drift 감시

이 분리를 하면 source package lane과 full vault artifact parity lane의 경계가 더 선명해진다.

---

## 8. PR-4: goal runtime hardening

### 8.1 수정 대상 파일

- `ops/scripts/core/codex_goal_client.py`
- `tests/test_codex_goal_client.py`
- `ops/scripts/mechanism/auto_improve_goal_runtime.py`
- `ops/scripts/mechanism/goal_run_status.py`
- 관련 goal runtime tests

### 8.2 `codex_goal_client.py`

#### 현재 문제
현재 기본 동작은 아래와 같다.

- injectable callable backend가 있으면 사용
- 없으면 `_DEFAULT_FAKE_BACKEND` 사용

이 구조는 테스트에는 편하지만, 실제 장기 실행 경로에서는 문제가 있다.

- 프로세스 경계를 넘으면 state가 사라진다.
- production에서 backend 부재를 명시적으로 드러내지 못하고 조용히 fake로 내려갈 수 있다.

#### 권장 변경

##### A. `FileGoalBackend` 추가
저장 위치는 기존 status/runtime과 맞추는 편이 좋다.

- 기본 권장 path: `ops/reports/codex-goal-contract.json`
- 구현 책임:
  - set: schema validate 후 파일 저장
  - get: 파일 읽기
  - update: 기존 payload merge 후 재검증

##### B. `update_goal()` merge 후 재검증
현재 `update_goal()`는 backend에 patch를 그대로 넘긴다.
실제 persistent backend에서는 **merge 결과 전체를 schema 검증**해야 한다.

##### C. production path에서 fake backend를 silent default로 쓰지 않기
권장 방식:

- test에서는 `FakeGoalBackend`를 명시 주입
- runtime/CLI에서는 `FileGoalBackend` 또는 외부 adapter를 명시 주입
- backend 미설정 시 long-run 경로는 실패시키기

#### 권장 인터페이스

```python
def detect_goal_backend(..., allow_fake: bool = False) -> GoalBackend:
    ...
```

또는

```python
def require_persistent_goal_backend(...) -> GoalBackend:
    ...
```

### 8.3 `tests/test_codex_goal_client.py`

추가할 테스트:

1. `FileGoalBackend` set/get/update persistence test
2. process-persistent capability가 `True`인지 확인
3. update patch 후 merged contract 전체가 schema valid인지 확인
4. backend 미설정 + `allow_fake=False`일 때 실패하는지 확인

### 8.4 `auto_improve_goal_runtime.py`

#### 현재 문제
이 파일은 기능은 이미 있지만, 장기 유지보수성 관점에서는 너무 크다.

직접 확인한 상위 함수:
- `run_goal_bound_auto_improve` (121 lines)
- `_run_auto_improve_with_optional_sustain` (108 lines)
- `_maintenance_loop` (100 lines)

#### 권장 분해안

| 새 파일 | 책임 |
|---|---|
| `ops/scripts/mechanism/goal_runtime_request.py` | request/dataclass/normalization |
| `ops/scripts/mechanism/goal_runtime_maintenance.py` | heartbeat, checkpoint, periodic refresh scheduling |
| `ops/scripts/mechanism/goal_runtime_backoff.py` | retry-after parse, backoff status write |
| `ops/scripts/mechanism/goal_runtime_resume.py` | resume metadata, checkpoint resumption |
| `ops/scripts/mechanism/goal_runtime_runner.py` | top-level orchestration |

중요한 점은 **외부 API를 바꾸지 않고 내부 분해만 먼저 하는 것**이다.
즉, public entrypoint인 `run_goal_bound_auto_improve()`는 유지하되 내부 import만 나누는 방식이 안전하다.

### 8.5 `goal_run_status.py`

이 파일은 이미 canonical artifact 경로를 잘 정의하고 있으므로, 이번 PR에서 크게 건드릴 필요는 없다.
다만 `FileGoalBackend`를 도입하면 아래 연동은 자연스럽게 맞춘다.

- `DEFAULT_CONTRACT_PATH`
- `DEFAULT_STATUS_PATH`
- `DEFAULT_AUDIT_LOG_PATH`
- `DEFAULT_RESUME_METADATA_PATH`

즉, goal 상태와 contract 저장 경로를 서로 다른 체계로 만들지 말고, 지금 정의된 canonical path 집합을 유지한다.

---

## 9. PR-5: 장기 런 관측성 보강 (지금 당장 큰 구조 변경은 금지)

### 9.1 수정 대상 파일

- `ops/scripts/core/command_runtime.py`
- `tests/test_command_runtime.py`
- `tests/test_command_runtime_heartbeat.py`
- goal/runtime status writer 쪽 연계 파일

### 9.2 중요한 현실 점검

기존 리뷰에서는 `last_stdout_at`, `quiet_seconds`, `last_artifact_touch_at` 같은 필드를 추가하자고 제안했지만, 현재 `command_runtime.py`는 `process.communicate(timeout=...)` 중심 구현이다.

즉, 지금 구조에서 “마지막 stdout 시각”을 정확히 넣으려면 단순 dataclass 필드 추가로 끝나지 않는다.

필요한 변화는 대체로 아래 둘 중 하나다.

1. nonblocking read loop 도입
2. 별도 output collector thread / selector 기반 스트리밍 도입

따라서 이 영역은 **소규모 cleanup PR에 끼워 넣으면 안 된다.**

### 9.3 현실적인 1차 목표

PR-5의 1차 목표는 아래 정도가 적당하다.

- `heartbeat_status`를 실제 goal status/report와 더 잘 연결
- executor backoff 시점 / last checkpoint 시점 / last heartbeat 시점을 status artifact 쪽에서 더 잘 보이게 하기
- command runtime 자체는 작은 필드 추가보다 **API boundary 정리**부터 하기

즉, “command runtime에 모든 걸 넣자”가 아니라,
**장기 실행 관측성은 goal status artifact와 command runtime을 분담해서 본다**가 맞다.

---

## 10. 추가 권장: source-package 전용 marker 구조화

이건 PR-2 이후 단계에서 권장한다.

### 10.1 수정 대상 파일
- `pytest.ini`
- `ops/test-lane-registry.json`
- `tests/test_generated_report_contracts.py`
- `tests/test_external_report_lifecycle_static.py`
- 필요 시 `tests/test_makefile_static_gates.py`

### 10.2 이유
PR-2를 해도 source package lane에는 여전히 2개 deselect가 남는다.

- `tests/test_generated_report_contracts.py`
- `tests/test_external_report_lifecycle_static.py`

이 둘은 공통적으로 source package에 **의도적으로 없는 checked-in artifact root**를 본다.

따라서 장기적으로는 `--deselect`보다 marker가 낫다.

### 10.3 권장 marker
새 marker 예시:

- `full_vault_generated_artifact`

등록 위치:
- `pytest.ini`
- `ops/test-lane-registry.json`

source package lane expression은 아래처럼 바뀐다.

```text
not artifact_finalization and not release_sealing and not full_vault_generated_artifact
```

이후 `ops/policies/source-package-test-deselections.json`는 **0건**까지 줄일 수 있다.

---

## 11. 실제 파일별 변경 목록

### 11.1 즉시 수정 대상

| 파일 | 변경 |
|---|---|
| `mk/test.mk` | expected node count 상수 및 fail block 삭제 |
| `README.md` | expected count 문구를 digest/fingerprint 기록 문구로 수정 |
| `ops/README.md` | same |
| `tests/test_makefile_static_gates.py` | expected count literal / echo / error string assert 삭제 |
| `tests/test_test_execution_summary.py` | summary consistency 검증 2~3건 추가 |
| `ops/scripts/core/source_package_clean_extract.py` | extract 내부 `script-output-surfaces` 생성 step 추가 |
| `mk/release.mk` | source package deselect list 5 → 2 축소 |
| `ops/policies/source-package-test-deselections.json` | budget 5 → 2 축소 |
| `tests/test_source_package_clean_extract.py` | command 수/생성 artifact expectations 갱신 |

### 11.2 다음 단계 수정 대상

| 파일 | 변경 |
|---|---|
| `tests/test_ci_workflow_static.py` | YAML AST 기반 검증으로 구조화 |
| `tests/test_release_workflow_static.py` | same |
| `tests/test_generated_report_contracts.py` | artifact tiering + parameterize |
| `tests/test_writer_output_paths.py` | runtime contract / inventory parity 분리 |
| `ops/scripts/core/codex_goal_client.py` | `FileGoalBackend` 도입 |
| `tests/test_codex_goal_client.py` | persistent backend tests 추가 |
| `ops/scripts/mechanism/auto_improve_goal_runtime.py` | 내부 모듈 분해 |

---

## 12. 추천 구현 순서 상세

### Step 1
`mk/test.mk`, `README.md`, `ops/README.md`, `tests/test_makefile_static_gates.py`, `tests/test_test_execution_summary.py`를 먼저 고친다.

이 단계는 기능 리스크가 거의 없다.
릴리즈 의미론도 건드리지 않는다.

### Step 2
`ops/scripts/core/source_package_clean_extract.py`에 `script-output-surfaces` 생성 step을 추가하고,
`mk/release.mk`, `ops/policies/source-package-test-deselections.json`, `tests/test_source_package_clean_extract.py`를 함께 갱신한다.

이 단계는 source-package lane의 실질 개선이다.
현재 5개 deselect 중 3개를 회수할 수 있다.

### Step 3
static gate test를 구조 검증으로 바꾼다.
이 단계는 churn 감소 효과가 크지만, PR-1/2보다 코드량이 많다.

### Step 4
goal runtime persistent backend를 도입한다.
이 단계부터는 장기 런 신뢰성에 직접 영향이 생긴다.

---

## 13. 권장 검증 명령

### PR-1 이후
```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_test_execution_summary.py \
  tests/test_makefile_static_gates.py
```

### PR-2 이후
```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_source_package_clean_extract.py \
  tests/test_import_fallback_contract.py \
  tests/test_script_module_surface_contract.py \
  tests/test_writer_output_paths.py
```

```bash
make test-source-package
make release-source-package-check
```

### PR-3 이후
```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_makefile_static_gates.py \
  tests/test_ci_workflow_static.py \
  tests/test_release_workflow_static.py \
  tests/test_generated_report_contracts.py
```

### PR-4 이후
```bash
PYTHONPATH=. python -m pytest -q \
  tests/test_codex_goal_client.py \
  tests/test_goal_run_status.py \
  tests/test_goal_auto_improve_runtime.py
```

### 최종 closeout
```bash
make test-execution-summary
make release-source-package-check
make report-contract-closeout
```

---

## 14. 하지 말아야 할 구현

1. source package lane을 green으로 만들기 위해 핵심 테스트를 삭제하지 말 것
2. expected node count를 advisory라는 이름만 바꿔 다시 hard gate로 남기지 말 것
3. `FakeGoalBackend`를 production 기본값으로 유지한 채 long-run runtime을 시작하지 말 것
4. `command_runtime.py`에 출력 timestamp 필드를 작은 patch처럼 억지로 넣지 말 것
5. `tests/test_makefile_static_gates.py`를 통째로 지우지 말 것
   - 없애는 게 아니라 **구조 검증으로 바꾸는 것**이 목적이다.

---

## 15. 최종 권고

가장 먼저 해야 할 실제 코드는 아래 두 줄기다.

### 1순위
**`TEST_EXECUTION_SUMMARY_FULL_EXPECTED_NODE_COUNT` 제거**

이건 지금 당장 치워도 안전하다.
효과는 즉각적이고, 유지보수 비용을 바로 줄인다.

### 2순위
**source package clean extract 안에서 `script-output-surfaces`를 생성하도록 변경**

이건 현재 source-package lane의 구조적 결함을 실제 코드로 고치는 일이다.
단순 문서 수정이 아니라, extract 환경에서 필요한 artifact를 명시적으로 재생성하는 설계라서 의미가 크다.

그 다음이 static gate 구조화이고, 마지막이 goal runtime hardening이다.

---

## 16. 한 줄 요약

이 저장소에서 지금 바로 손대야 할 것은 “테스트 수를 줄이는 일”이 아니라,
**고정 숫자 gate를 제거하고, extract 환경에서 재생성 가능한 artifact는 실제로 재생성하게 만들고, 문자열 고정 테스트를 구조 검증으로 바꾸는 일**이다.
