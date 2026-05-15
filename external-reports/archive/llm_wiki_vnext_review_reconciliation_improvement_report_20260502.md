# LLM Wiki vNext 리뷰 대조 기반 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일 | 2026-05-02 (Asia/Seoul) |
| 작성 언어 | 한국어 |
| 산출 파일 | `llm_wiki_vnext_review_reconciliation_improvement_report_20260502.md` |
| 신규 검토 리뷰 1 | `llm_wiki_vnext_통합사후보고서_20260502.md` |
| 신규 검토 리뷰 2 | `integrated_post_review_report_20260502.md` |
| 기존 대조 리뷰 | `llm_wiki_vnext_v76_post_review_status_report_20260502.md` |
| 실제 대조 ZIP | `/mnt/data/LLM Wiki vNext(76).zip` |
| 실제 대조 트리 | `/mnt/data/llm_wiki_vnext_pristine` |
| ZIP SHA-256 | `4a354fd31bd970e8c21e14dfc2bc7935e0892eb109f86666891152e8fc2a1116` |
| 최종 판정 | **조건부 통과(`conditional_pass`) 유지, clean release 불가, machine release 불가** |

---

## 1. Executive Summary

두 신규 리뷰는 기존 사후 리뷰와 핵심 결론이 대체로 일치한다. 현재 스냅샷은 기준 개선 보고서 이후 상당한 개선이 반영되었지만, **clean release candidate가 아니라 operator accepted-risk review를 전제로 한 conditional snapshot**이다. 실제 파일과 재실행 결과를 대조해도 `release_closeout_summary`의 `release_readiness_state=conditional_pass`, `machine_release_allowed=false`, `clean_release_ready=false`, `operator_release_allowed=true` 판단은 그대로 유지된다.

다만 이번 재검토에서 두 가지 중요한 보정이 추가로 확인되었다.

1. **`mtime_ns` fingerprint 해석은 수정되어야 한다.** 신규 리뷰 2건은 `source_tree_fingerprint`가 `mtime_ns`를 포함하기 때문에 ZIP 재검증 false positive가 발생할 수 있다고 설명한다. 그러나 실제 `ops/scripts/source_tree_fingerprint_runtime.py`를 확인하면 `mtime_ns`는 `_SOURCE_TREE_CACHE` 비교용 signature에 사용되고, 최종 fingerprint payload에는 `path`, `sha256`, `size_bytes`만 들어간다. 따라서 현재 `41b1839a...` → `962fe24a...` 불일치는 단순 mtime 문제로 단정하기보다 **실제 release-source content divergence 또는 생성 순서 문제**로 보는 편이 더 정확하다.
2. **`command_runtime` 실패는 이번 환경에서 재현되지 않았다.** 신규 리뷰 중 하나는 `returncode=-15` 실패를 P0 후보로 제시했지만, 본 재검토에서 `tests/test_command_runtime.py` 전체 13개 테스트는 통과했다. 따라서 이 항목은 즉시 clean-release blocker로 고정하기보다 **Python/OS matrix 재현성 확인이 필요한 P1 위험**으로 조정하는 것이 타당하다.

반대로 다음 항목들은 실제 재실행으로도 실패 또는 미완료가 확인되었다.

- Ruff: `ops/scripts/release_closeout_batch_manifest.py`의 unused import `report_path`로 실패.
- Import fallback contract: `ops/scripts/release_closeout_batch_manifest.py`가 direct fallback file이지만 `ops/direct-script-entrypoints.txt`에 없어 실패.
- Writer output surface registry: 실제 AST inventory와 checked-in registry는 **`source_tree_fingerprint`만 다르고 나머지 registry payload는 동일**했다. 즉 writer surface 구조 drift라기보다 fingerprint 재봉인 누락이다.
- Release evidence cohort clean gate: `strict_same_fingerprint=false`, `accepted_risk_count=2`, `clean_lane_contract.status=fail`로 실패.
- Batch manifest: 존재하지만 finalization recipe에 충분히 결합되지 않았고, 최신 evidence batch를 마지막에 봉인하는 authority로 작동하지 않는다.

---

## 2. 검토 범위 및 방법

### 2.1 검토한 문서

| 구분 | 파일 | 역할 |
| --- | --- | --- |
| 신규 리뷰 A | `llm_wiki_vnext_통합사후보고서_20260502.md` | 세 독립 사후 리뷰의 결론을 한 번 더 요약하고, 기존 기준 보고서와 현재 산출물을 대조한 통합본 |
| 신규 리뷰 B | `integrated_post_review_report_20260502.md` | 리뷰 A보다 더 상세한 교차검증 보고서. 리뷰 A/B/C의 관점 차이, P0/P1/P2 실행계획, Definition of Done이 더 구체적 |
| 기존 리뷰 | `llm_wiki_vnext_v76_post_review_status_report_20260502.md` | 이전에 생성된 v76 사후 상태 보고서. Ruff 실패, batch manifest drift, closeout lineage 문제를 선행 지적 |
| 기준 보고서 | `external-reports/integrated_improvement_report_v3.md` | 최초 개선 요구사항과 P0/P1/P2 개선 축 제공 |
| 기준 보고서 | `external-reports/llm_wiki_vnext_unified_improvement_report_20260502.md` | v75 계열 개선 상태 및 clean/conditional lane 분리 요구 제공 |

### 2.2 실제 파일 범위

| 항목 | 값 |
| --- | ---: |
| ZIP 전체 엔트리 | 1805 |
| 일반 파일 | 1712 |
| 디렉터리 | 93 |
| 비압축 총량 | 244,003,741 bytes |
| 압축 총량 | 191,289,920 bytes |

상위 경로별 파일 수:

| 경로 | 파일 수 |
| --- | ---: |
| `raw` | 446 |
| `wiki` | 417 |
| `ops` | 364 |
| `runs` | 166 |
| `tests` | 137 |
| `system` | 71 |
| `external-reports` | 47 |
| `tmp` | 24 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |

확장자별 파일 수:

| 확장자 | 파일 수 |
| --- | ---: |
| `.md` | 956 |
| `.py` | 310 |
| `.json` | 309 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.yaml` | 14 |
| `.jsonl` | 12 |
| `.toml` | 10 |
| `<none>` | 5 |
| `.yml` | 2 |

### 2.3 본 재검토에서 추가 실행한 명령

| 명령 | 결과 | 해석 |
| --- | --- | --- |
| `python -m ruff check ops/scripts tests tools` | **fail** | `release_closeout_batch_manifest.py` unused import `report_path` |
| `python -m pytest tests/test_import_fallback_contract.py -q` | **fail** | batch manifest script가 fallback file이지만 direct allowlist에 없음 |
| `python -m pytest tests/test_writer_output_paths.py::WriterOutputPathsTest::test_script_output_surface_registry_matches_current_ast_inventory -q` | **fail** | actual/expected 차이는 `source_tree_fingerprint` 단일 필드 |
| `make release-evidence-cohort-check` | **fail** | strict cohort 및 clean lane contract 실패 |
| `python -m mypy @ops/mypy-allowlist.txt` | **pass** | 172개 source file 타입 검사 통과 |
| `python -m pytest tests/test_script_module_surface_contract.py -q` | **pass** | module/console surface 기존 정합성은 유지 |
| `python -m pytest tests/test_command_runtime.py -q` | **pass** | 신규 리뷰의 `command_runtime` SIGTERM 실패는 본 환경에서 재현되지 않음 |
| `python -m pytest tests/test_writer_output_paths.py -q` | **timeout** | 전체 writer suite는 본 컨테이너 제한 내 완료하지 못함. 핵심 drift는 targeted test로 재현 |
| `python -m pytest tests/test_generated_report_contracts.py -q` | **timeout** | 전체 generated-report suite는 본 컨테이너 제한 내 완료하지 못함 |

---

## 3. 신규 리뷰 2건의 핵심 주장 대조

### 3.1 공통 합의점

| 영역 | 통합 판정 |
| --- | --- |
| Release readiness | `conditional_pass` 유지 |
| Clean release | 불가 (`clean_release_ready=false`) |
| Machine release | 불가 (`machine_release_allowed=false`) |
| Operator release | 가능하나 accepted-risk review 전제 |
| Archive backlog | 해소 (`archive_candidate_count=0`) |
| Artifact freshness | top-level pass, stale/debt 0 |
| Release workflow clean gate | 구현됨 |
| Batch manifest | 도입됨. 단, final authority로는 미완성 |
| Learning readiness | `learning_uncertain`, promotion 불가 |
| Cohort/dashboard | attention/fail surface 유지 |
| Closeout lineage | 비원자적이며 fingerprint batch가 혼재 |
| 신규 drift | `release_closeout_batch_manifest.py`에서 재발 |

### 3.2 신규 리뷰 A의 특징

`llm_wiki_vnext_통합사후보고서_20260502.md`는 기존 세 사후 리뷰의 결과를 요약하고, 기준 개선 보고서 2건과 현재 ZIP을 다시 대조하는 방식이다. 주요 강점은 release readiness 상태를 짧고 명확하게 정리한 점, 기준 보고서 항목별 반영/미반영 상태를 표로 추적한 점, closeout lineage의 generated_at/fingerprint mismatch를 한눈에 볼 수 있게 정리한 점이다.

### 3.3 신규 리뷰 B의 특징

`integrated_post_review_report_20260502.md`는 신규 리뷰 A보다 더 상세하며, 리뷰 A/B/C의 관점 차이를 명확히 분리한다. 특히 Release workflow clean gate가 구현되었지만 job 간 workspace가 공유되지 않는다는 구조적 한계, `command_runtime` SIGTERM 실패, Definition of Done 확장을 더 선명하게 제시한다.

### 3.4 두 신규 리뷰 모두 보정이 필요한 부분

두 신규 리뷰 모두 `mtime_ns` 기반 fingerprint false positive 가능성을 강하게 받아들였지만, 실제 코드와 대조하면 이 해석은 수정이 필요하다.

```python
signature = [(entry.rel_path, entry.size, entry.mtime_ns) for entry in entries]
...
files.append({
    "path": entry.rel_path,
    "sha256": _sha256_file(entry.path),
    "size_bytes": entry.size,
})
fingerprint = _sha256_json(manifest)
```

즉 `mtime_ns`는 cache hit 여부를 판단하는 signature에는 들어가지만, 최종 fingerprint를 만드는 `manifest`에는 들어가지 않는다. 따라서 외부 ZIP 재검증에서 mtime이 달라졌다는 이유만으로 **cold computation의 최종 fingerprint가 바뀌지는 않는다**. 신규 리뷰 B의 가장 중요한 해석 보정점은 “mtime false positive”가 아니라 “fingerprint 계층과 batch finalization 계층을 분리해야 한다”로 재정의하는 편이 정확하다.

---

## 4. 실제 산출물 상태 재확인

### 4.1 Release Closeout Summary

| 필드 | 실제 값 |
| --- | --- |
| `generated_at` | 2026-05-02T05:43:08Z |
| `status` | pass |
| `release_readiness_state` | conditional_pass |
| `machine_release_allowed` | False |
| `operator_release_allowed` | True |
| `clean_release_ready` | False |
| `conditional_release_ready` | True |
| `requires_accepted_risk_review` | True |
| `accepted_risk_count` | 2 |
| `accepted_risk_family_count` | 2 |
| `source_tree_fingerprint` | `41b1839ac149b5f321b5037bbd5caf4b174d61ce791ec1182e0daa57534d5c06` |

판정: closeout 자체는 `pass`이나 release decision은 clean이 아니다. 두 신규 리뷰 및 기존 리뷰와 일치한다.

### 4.2 Release Evidence Cohort

| 필드 | 실제 값 |
| --- | --- |
| `generated_at` | 2026-05-02T04:01:30Z |
| `status` | attention |
| `strict_same_fingerprint` | False |
| `component_fingerprint_count` | 3 |
| `accepted_risk_count` | 2 |
| `source_tree_fingerprint` | `e3750a42bcc3d819a687ea9f2fe755302dcc3386b0d33f576cdd3126c6bdd6c3` |

판정: checked-in cohort는 `attention`이며 strict fingerprint 조건을 만족하지 못한다.

`make release-evidence-cohort-check` 재실행 결과도 `status=fail`, `strict_same_fingerprint=false`, `component_fingerprint_count=2`, `accepted_risk_count=2`, `clean_lane_contract.status=fail`을 반환했다. 실패 조건은 `zero_accepted_risk_family`, `strict_cohort_pass`, `release_closeout_clean`이다.

### 4.3 Release Evidence Dashboard

| 필드 | 실제 값 |
| --- | --- |
| `generated_at` | 2026-05-02T04:01:30Z |
| `status` | attention |
| `gate_count` | 11 |
| `authoritative_gate_count` | 2 |
| `live_rerun_not_run_count` | 7 |
| `accepted_risk_count` | 2 |
| `source_tree_fingerprint` | `e3750a42bcc3d819a687ea9f2fe755302dcc3386b0d33f576cdd3126c6bdd6c3` |

판정: dashboard는 checked-in 상태에서 `attention`이며, closeout/cohort/batch manifest와 동일한 최종 batch를 나타내지 않는다.

### 4.4 Auto-Improve / Learning Readiness

| 필드 | 실제 값 |
| --- | --- |
| `auto-improve.generated_at` | 2026-05-02T05:37:53Z |
| `can_execute_trial` | True |
| `can_promote_result` | False |
| `learning_readiness.status` | learning_uncertain |
| `learning_readiness.likely_to_learn` | False |
| `signoff_revalidation.status` | attention |
| `revalidation.status` | due |
| `window_ends_at` | 2026-05-09T05:38:04Z |

판정: 실행 trial은 가능하지만 promotion은 불가하다. clean release의 blocker라는 신규 리뷰들의 진단은 유지된다.

### 4.5 Artifact Freshness / Archive

| 필드 | 실제 값 |
| --- | --- |
| `artifact-freshness.status` | pass |
| `artifact_count` | 189 |
| `stale_artifact_count` | 0 |
| `missing_schema_count` | 0 |
| `stable_contract_debt_issue_count` | 0 |
| `operational_attention_issue_count` | 0 |
| `archive_candidate_count` | 0 |
| `archive planned_move_count` | 0 |

판정: 이 영역은 기준 보고서 이후 명확히 개선되어 완료로 볼 수 있다.

### 4.6 Test Execution Summary

| 필드 | 실제 값 |
| --- | --- |
| `generated_at` | 2026-05-02T05:50:00Z |
| `status` | pass |
| `counts.passed` | 116 |
| `counts.failed` | 0 |
| `pytest_marker_deselected_count` | 4 |
| `policy_deselected_count` | 0 |
| `source_tree_fingerprint` | `962fe24a44a61d9b89b52ea950929d38322990f23ff427c90e59e0b774e46937` |

판정: summary 자체는 pass이나 release-critical 실패를 대표하지 못한다. “대표 범위 부족” 지적은 타당하다.

### 4.7 Release Closeout Batch Manifest

| 필드 | 실제 값 |
| --- | --- |
| `generated_at` | 2026-05-02T04:04:49Z |
| `artifact_kind` | release_closeout_batch_manifest |
| `source_tree_fingerprint` | `2f4e9b0f7c71b696178115ab3360dd3a7191bdb848d3dd73716b2d6d79b0d5e8` |
| `batch_id` | batch-2026-05-02T04-04-49 |
| `artifacts` count | 8 |
| `dependency_order` count | 8 |

판정: manifest는 존재하지만 최종 batch authority가 아니다. manifest가 기록한 `release-smoke-report.json`은 `2026-05-02T04:00:16Z`인 반면 현재 checked-in smoke report는 `2026-05-02T05:49:35Z`다.

---

## 5. 기존 리뷰 대비 교정된 판단

### 5.1 변하지 않은 판단

| 기존 판단 | 이번 검토 판정 |
| --- | --- |
| clean release 상태가 아니다 | 유지 |
| machine release 불가 | 유지 |
| accepted-risk operator review 필요 | 유지 |
| release workflow clean gate는 구현되었다 | 유지 |
| archive/freshness debt는 해소되었다 | 유지 |
| batch manifest는 도입되었으나 미완성이다 | 유지 |
| closeout lineage는 원자적으로 재봉인되지 않았다 | 유지 |
| direct fallback drift가 재발했다 | 유지 |

### 5.2 강화된 판단

| 항목 | 강화 사유 |
| --- | --- |
| `release_closeout_batch_manifest.py`는 최우선 P0 | Ruff 실패와 import fallback 실패를 동시에 유발한다. |
| writer output surface 문제는 “surface 구조 drift”보다 “fingerprint 재봉인 누락”에 가깝다 | actual/expected registry를 비교한 결과 `source_tree_fingerprint`를 제외하면 완전히 동일했다. |
| batch manifest는 Makefile target 존재만으로 충분하지 않다 | `release-evidence-closeout` recipe의 마지막 authority로 강제되어야 한다. |
| test summary는 release contract 대표성이 부족하다 | summary pass와 실제 P0 테스트 실패가 동시에 존재한다. |

### 5.3 약화 또는 재분류된 판단

| 항목 | 기존/신규 리뷰 주장 | 이번 재분류 |
| --- | --- | --- |
| `mtime_ns` 때문에 ZIP fingerprint false positive 가능 | 신규 리뷰 B의 핵심 보정 | 실제 코드상 `mtime_ns`는 최종 fingerprint payload가 아니라 cache signature에 사용된다. 현재 mismatch의 주된 설명으로 쓰면 부정확하다. |
| `command_runtime` SIGTERM 실패 | 신규 리뷰 B/C에서 P0 후보 | 본 재검토에서 전체 `tests/test_command_runtime.py` 13개가 통과했다. P0 blocker가 아니라 Python/OS matrix 재현성 확인이 필요한 P1 위험으로 둔다. |
| `test_generated_report_contracts.py` 일부 실패 | 신규 리뷰에서 언급 | 본 환경에서는 전체 suite가 timeout되어 직접 확정하지 못했다. 다만 generated report finalization의 위험은 closeout/cohort/batch evidence로 이미 충분히 확인된다. |

---

## 6. 현재 남아 있는 작업분

### 6.1 P0 — Clean release를 막는 즉시 조치 항목

#### P0-1. Batch manifest direct fallback 계약 정리 및 Ruff 실패 제거

release_closeout_batch_manifest.py
  = 사람이 직접 돌리는 편의 스크립트가 아님
  = release-evidence-closeout의 마지막 canonical writer
  = evidence set의 digest, generated_at, fingerprint, release decision을 봉인
  = 이후 read-only check로만 검증
  = direct fallback 없음
  = candidate/promote 사용
  = schema가 status/summary/finality/downstream invalidation을 표현

Step 0: 즉시 수정
report_path unused import 제거.
direct fallback 분기 제거.
ops/direct-script-entrypoints.txt와 pyproject.toml에는 추가하지 않음.
test_import_fallback_contract.py, Ruff 재실행.
ops/script-output-surfaces.json 재생성.
Step 1: finalizer로 편입
candidate/promote 패턴 적용.
release-evidence-closeout 마지막 canonical write로 편입.
release-closeout-batch-manifest-check 추가.
tests/test_makefile_static_gates.py에 순서 검증 추가.
manifest 이후 canonical write 금지 검증 추가.
Step 2: schema와 runtime 강화
status, summary, finality, coherence, release_decision_snapshot 추가.
artifacts 항목에 producer, source_tree_fingerprint, currentness_status, role, required 추가.
missing/digest mismatch/newer dependency를 operator-readable failure로 표현.
path_group_inputs["sealed_artifacts"] 또는 digest map을 input_fingerprints에 반영.
Step 3: 구조 정리
runtime과 CLI wrapper 분리.
batch artifact list를 ops/policies/release-closeout-batch.json으로 이동.
direct fallback allowlist를 장기적으로 생성형 registry 또는 완전 제거 방향으로 정리.
publish job이 batch manifest를 최종 authority로 사용하도록 변경.

#### P0-2. `ops/script-output-surfaces.json` 재봉인

checked-in registry fingerprint는 `41b1839a...`, live AST inventory fingerprint는 `962fe24a...`다. 다만 `source_tree_fingerprint` 필드를 제거하면 actual/expected registry가 동일하므로, writer surface 구조 drift가 아니라 fingerprint 재봉인 실패로 판단한다.

#### P0-3. Closeout lineage 원자적 재봉인

| artifact | generated_at | fingerprint |
| --- | --- | --- |
| `release-evidence-cohort.json` | 2026-05-02T04:01:30Z | `e3750a42...` |
| `release-evidence-dashboard.json` | 2026-05-02T04:01:30Z | `e3750a42...` |
| `release-closeout-batch-manifest.json` | 2026-05-02T04:04:49Z | `2f4e9b0f...` |
| `release-closeout-summary.json` | 2026-05-02T05:43:08Z | `41b1839a...` |
| `release-smoke-report.json` | 2026-05-02T05:49:35Z | `962fe24a...` |
| `generated-artifact-index.json` | 2026-05-02T05:49:36Z | `962fe24a...` |
| `test-execution-summary.json` | 2026-05-02T05:50:00Z | `962fe24a...` |
| `artifact-freshness-report.json` | 2026-05-02T05:50:14Z | `962fe24a...` |

권장 순서: `script-output-surfaces` → bootstrap → auto-improve → release smoke → test summary → generated index → artifact freshness → learning signoff → closeout summary → cohort → dashboard → **batch manifest 마지막** → final attestation.

#### P0-4. `release-evidence-closeout` recipe에 batch manifest 편입

`Makefile`에는 `release-closeout-batch-manifest` target이 있으나, final closeout recipe의 마지막 authority로 충분히 강제되지 않는다. batch manifest 이후 canonical report 재생성을 금지하는 gate와 self-reference를 피하는 final attestation을 추가해야 한다.

#### P0-5. Clean lane accepted-risk 조건 명확화

현재 clean lane은 `zero_accepted_risk_family`, `strict_cohort_pass`, `release_closeout_clean` 세 조건 때문에 실패한다. clean release로 가려면 accepted risk family를 0으로 만들거나, accepted risk가 남는 경우 release state를 clean이 아니라 conditional로 고정해야 한다.

#### P0-6. Release-relevant test summary 확장

`test-execution-summary.json`에 최소한 Ruff, mypy, import fallback, script module surface, writer output paths, generated report contracts, release-evidence-cohort-check를 포함하거나, 포함하지 않는다는 경고를 machine-readable하게 기록해야 한다.

---

## 7. 새로 식별 또는 보정된 개선 방안

### 7.1 Fingerprint 체계 보정: mtime 해석이 아니라 payload 계층 분리

| fingerprint | 목적 | payload |
| --- | --- | --- |
| `content_fingerprint` | ZIP/외부 리뷰 재현성 | path + sha256 + size |
| `workspace_signature` | 캐시 무효화 및 local fast check | path + size + mtime_ns |
| `artifact_batch_fingerprint` | release evidence batch 원자성 | closeout/cohort/dashboard/batch 대상 artifact digest |
| `policy_fingerprint` | release policy 변경 추적 | policy files + schema files |

### 7.2 Registry equality 테스트 분리

현재 `test_script_output_surface_registry_matches_current_ast_inventory`는 surface payload와 source tree freshness를 한 assert에 묶는다. 실제로 surface는 동일하고 fingerprint만 다르므로, `surfaces` payload equality와 `source_tree_fingerprint` equality를 별도 실패로 분리해야 한다.

### 7.3 Batch manifest의 authority 모델 명확화

현재 batch manifest는 inventory에 가깝다. release authority로 쓰려면 `status`, `summary.final_authority`, `newer_dependency_detected`, `downstream_invalidated`, `canonical_write_after_batch_count`, `self_reference_strategy`를 schema에 포함해야 한다.

### 7.4 Direct fallback allowlist를 사람이 편집하지 않도록 전환

새 script가 추가될 때마다 `direct-script-entrypoints.txt`, `pyproject.toml`, output surface registry가 독립적으로 움직이며 drift가 재발한다. AST scan 기반 generated registry를 도입하여 direct fallback marker, argparse main, producer/output surface를 단일 파이프라인으로 관리해야 한다.

### 7.5 Release workflow artifact handoff 강화

`verify-clean-release` job이 만든 evidence와 `publish` job이 읽는 checked-in report가 다를 수 있다. evidence bundle upload/download, publish job 재검증, 또는 `git diff --exit-code ops/reports ops/script-output-surfaces.json ops/raw-registry.json ops/manifest.json`를 추가해야 한다.

### 7.6 `command_runtime`은 P1 matrix risk로 재분류

본 재검토에서 통과했으므로 즉시 P0로 두지 않는다. Python 3.12/3.13/3.14 및 가능한 OS matrix에서 단일 실행과 전체 suite 실행을 재확인하고, 재현되면 P0로 승격한다.

### 7.7 Generated report contract timeout 대응

본 환경에서 전체 `test_generated_report_contracts.py`가 timeout되었다. test marker를 `fast_contract`, `slow_regeneration`, `release_finalization`으로 분리하고, timeout 시 마지막 실행 test name과 per-test duration을 남기도록 개선한다.

---

## 8. 우선순위별 실행 계획

### 8.1 P0 — 1차 clean gate 회복

| 순서 | 작업 | 완료 기준 |
| ---: | --- | --- |
| 1 | batch manifest direct fallback 정책 결정 및 Ruff pass | fallback contract pass | unused import 제거
| 2 | console script/direct allowlist/module surface 정합화 | import fallback + script module surface pass |
| 3 | `ops/script-output-surfaces.json` 재생성 | targeted writer registry test pass |
| 4 | release-critical tests를 `test-execution-summary` 범위에 포함 | summary가 release contract 실패를 숨기지 않음 |
| 5 | closeout lineage를 정해진 순서로 재생성 | closeout/cohort/dashboard/batch 동일 batch |
| 6 | batch manifest를 마지막 authority로 봉인 | batch 이후 canonical write 0 |
| 7 | `make release-evidence-cohort-check` 통과 | clean lane contract pass |

### 8.2 P1 — 구조적 재발 방지

| 순서 | 작업 | 완료 기준 |
| ---: | --- | --- |
| 1 | fingerprint 계층 분리 | content/workspace/batch/policy fingerprint schema 반영 |
| 2 | registry equality 테스트 분리 | surface drift와 freshness drift를 별도 실패로 표시 |
| 3 | direct fallback/console/output registry 생성형 통합 | 새 script 추가 시 수동 allowlist drift 제거 |
| 4 | accepted risk authority vocabulary 통합 | closeout/dashboard/revalidation count 불일치 제거 |
| 5 | release workflow evidence handoff 강화 | verify와 publish 간 divergence 차단 |
| 6 | command_runtime Python matrix 확인 | 재현 시 P0, 비재현 시 문서화 |
| 7 | generated report contract timeout 진단 | test duration/last-test logging 추가 |

### 8.3 P2 — 유지보수성 개선

| 순서 | 작업 | 완료 기준 |
| ---: | --- | --- |
| 1 | 대형 runtime script 분리 | collector/normalizer/report-builder/writer 구조화 |
| 2 | dev artifact quarantine | canonical/working/scratch/archive 경계 명확화 |
| 3 | release operator bundle target 추가 | operator review package 단일 생성 |
| 4 | README/ops README 최신화 | clean vs conditional lane 설명 최신 상태 유지 |
| 5 | learning readiness telemetry 개선 | attempts ≥ 10, telemetry coverage > 0, rework/defect signal 개선 |

---

## 9. Clean Release Definition of Done

| 영역 | 완료 조건 |
| --- | --- |
| Ruff | `python -m ruff check ops/scripts tests tools` pass |
| Mypy | `python -m mypy @ops/mypy-allowlist.txt` pass 유지 |
| Import fallback | `tests/test_import_fallback_contract.py` pass |
| Script module surface | `tests/test_script_module_surface_contract.py` pass 유지 |
| Writer surface | `tests/test_writer_output_paths.py` 핵심 registry test pass |
| Generated report contracts | closeout/freshness/index 관련 generated report tests pass 또는 timeout 원인 문서화 |
| Command runtime | 지원 Python matrix에서 timeout test pass 또는 비지원 버전 명시 |
| Artifact freshness | stale/debt/schema/root-ephemeral 0 유지 |
| Archive | candidate/planned/applied unexpected move 0 유지 |
| Closeout decision | `clean_release_ready=true`, `machine_release_allowed=true` |
| Cohort | `strict_same_fingerprint=true` |
| Clean lane | `clean_lane_contract.status=pass` |
| Accepted risk | clean lane에서는 accepted risk family 0, 남는 경우 conditional release로 명확히 분리 |
| Batch manifest | latest evidence batch를 마지막에 봉인하고 이후 canonical write 0 |
| Dashboard | checked-in과 regenerated accepted risk count 일치 |
| Test summary | release-critical 실패를 숨기지 않음 |
| Workflow | verify-clean-release와 publish 간 evidence divergence 차단 |
| Learning readiness | `pass` 또는 operator accepted-risk signoff와 expiry/owner 명시 |

---

## 10. 재실행 로그 요약

### 10.1 Ruff 실패

```text
F401 [*] `.policy_runtime.report_path` imported but unused
  --> ops/scripts/release_closeout_batch_manifest.py:23:46
   |
21 |     from .artifact_io_runtime import write_schema_validated_json
22 |     from .output_runtime import display_path, resolve_repo_output_path
23 |     from .policy_runtime import load_policy, report_path
   |                                              ^^^^^^^^^^^
24 |     from .runtime_context import RuntimeContext
25 |     from .schema_runtime import load_schema_with_vault_override
   |
help: Remove unused import: `.policy_runtime.report_path`

Found 1 error.
[*] 1 fixable with the `--fix` option.
```

### 10.2 Import fallback 실패

```text
.F....                                                                   [100%]
=================================== FAILURES ===================================
_ ImportFallbackContractTests.test_direct_script_entrypoint_allowlist_matches_fallback_files _

self = <test_import_fallback_contract.ImportFallbackContractTests testMethod=test_direct_script_entrypoint_allowlist_matches_fallback_files>

    def test_direct_script_entrypoint_allowlist_matches_fallback_files(self) -> None:
        allowlist = _entrypoint_allowlist()
        fallback_files = {
            path.as_posix()
            for path in sorted(SCRIPTS_DIR.glob("*.py"))
            if "direct script fallback" in path.read_text(encoding="utf-8")
        }
    
        self.assertTrue(allowlist)
>       self.assertEqual(fallback_files, allowlist)
E       AssertionError: Items in the first set but not the second:
E       'ops/scripts/release_closeout_batch_manifest.py'

tests/test_import_fallback_contract.py:62: AssertionError
=========================== short test summary info ============================
FAILED tests/test_import_fallback_contract.py::ImportFallbackContractTests::test_direct_script_entrypoint_allowlist_matches_fallback_files - AssertionError: Items in the first set but not the second:
'ops/scripts/release_closeout_batch_manifest.py'
```

### 10.3 Writer registry targeted 실패

```text
핵심 차이:
- actual source_tree_fingerprint: 41b1839ac149...
- expected source_tree_fingerprint: 962fe24a44a6...
- `source_tree_fingerprint` 필드를 제거하면 actual == expected: True
```

### 10.4 Cohort clean gate 실패

```text
python3 -m ops.scripts.release_evidence_cohort --vault "." --out "tmp/release-evidence-cohort-check.json" --profile "base" --cohort-policy strict_same_fingerprint --provenance-mode "embedded_currentness"  --fail-on-attention --require-clean-lane
tmp/release-evidence-cohort-check.json
make: *** [Makefile:306: release-evidence-cohort-check] Error 1
```

### 10.5 통과한 검사

```text
mypy: Success: no issues found in 172 source files

script module surface: ........                                                                 [100%]

command runtime: .............                                                            [100%]
```

---

## 11. 최종 결론

두 신규 리뷰는 기존 리뷰보다 통합성과 실행 계획 면에서 개선되어 있으며, 특히 batch manifest, release workflow clean gate, accepted risk, learning readiness, closeout lineage를 하나의 운영 release model로 묶었다는 점에서 유용하다. 그러나 실제 파일 대조 결과 다음 보정이 필요하다.

1. `mtime_ns`는 최종 source tree fingerprint payload가 아니라 cache signature에 쓰이므로, fingerprint mismatch의 주요 원인을 mtime false positive로 단정하지 않는다.
2. `command_runtime` 실패는 이번 재실행에서 재현되지 않았으므로 P0 확정 blocker가 아니라 matrix 검증 대상이다.
3. `script-output-surfaces` 실패는 writer surface payload drift가 아니라 source_tree_fingerprint 재봉인 실패로 좁혀졌다.

따라서 현 시점의 실무 결론은 다음과 같다.

> **현재 스냅샷은 상당히 개선되었으나 clean release가 아니다. 우선 Ruff/import fallback/registry fingerprint/batch finalization/cohort clean gate를 순서대로 복구하고, 그 다음 learning readiness와 accepted-risk authority를 정리해야 한다.**
