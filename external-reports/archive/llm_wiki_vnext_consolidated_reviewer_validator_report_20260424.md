# LLM Wiki vNext Consolidated Anti-Slop & Self-Improvement Review

- **파일명:** `llm_wiki_vnext_consolidated_reviewer_validator_report_20260424.md`
- **작성일:** 2026-04-24
- **작성 언어:** 한국어
- **대조 대상:** 업로드한 기존 통합 보고서 `llm_wiki_vnext_integrated_anti_slop_report_20260424(1).md`, 현재 코드 번들 `LLM Wiki vNext(31).zip`, 직전 생성 보고서 `llm_wiki_vnext_full_anti_slop_self_improvement_review_report.md`
- **검토 프레임:** anti-slop, self-improvement closed loop, evidence currentness, typed contract, proposal-as-experiment, session evidence, supply-chain/IP provenance, reviewer-validator 상호 보완
- **중요 전제:** 이번 문서는 실제 코드와 report artifact를 다시 대조하여, 기존 보고서에서 이미 해결된 항목과 아직 남은 항목을 분리한다.
- **추가 갱신 메모(2026-04-24 late update):** 이번 재검토에는 후속 runtime 변경도 포함한다. 현재 코드 기준으로 `mechanism-review-candidates`와 `mutation-proposals`는 empty/non-ready 계열 상태를 `attention`으로 분리하고, `auto_improve_readiness_runtime.py`는 upstream attention을 `execution_readiness.reasons`와 `queue.evidence_gaps`에 요약한다. 또한 VS Code Python interpreter는 `${workspaceFolder}\\.venv\\Scripts\\python.exe`로 고정됐고, 관련 targeted pytest slice가 통과했다.

---

## 0. 최종 결론

현재 `LLM Wiki vNext(31).zip`은 업로드된 기존 통합 보고서가 기준으로 삼은 `LLM Wiki vNext(30).zip`보다 한 단계 진행된 상태다. 따라서 기존 보고서의 일부 P0 권고는 더 이상 “신규 구현 필요”가 아니라 “구현된 계약을 더 넓게 확산하고, gate semantics를 더 엄격히 검증할 단계”로 재분류해야 한다.

| 항목 | 업로드 기존 통합 보고서 기준 | 현재 코드/이번 재검토 기준 | 통합 판단 |
|---|---:|---:|---|
| ZIP 파일 수 | 1,618 | 1826 | 코드 표면이 증가했으므로 기존 수치 폐기 |
| 디렉터리 수 | 명시적 수치 없음 | 69 | 현재 zip manifest 기준으로 갱신 |
| `tests/*.py` | 116 | 121 | 검증 표면 증가 |
| `ops/scripts/*.py` | 154 | 154 | 운영 runtime 규모는 유지 |
| artifact stale 수 | 52 | 50 | 일부 개선 또는 재생성됨 |
| unknown currentness | 141 | 135 | 개선됐지만 여전히 높음 |
| missing artifact envelope | 141 | 135 | 핵심 canonical 일부는 해결, 전체 확산은 미완료 |
| core canonical envelope | 적용 권고 | 일부 핵심 report에 이미 적용 | 권고를 “확산·gate화”로 수정 |
| `--allow-learning-uncertain` | 추가 권고 | 코드와 테스트에 존재 | 신규 구현 대신 semantic validation 필요 |
| mechanism review status semantics | empty/no-history 위험을 별도 승격해야 함 | 저장된 snapshot은 `candidates_emitted=0`, `status=pass`; 현재 runtime contract는 disabled/bootstrap/no-candidate에서 `status=attention` | no-history/no-candidate가 더 이상 success처럼 설계되지 않음 |
| mutation proposal status semantics | proposal 1개로 서술 | 저장된 snapshot은 `proposals_emitted=0`, `status=pass`; 현재 runtime contract는 empty/blocked-only에서 `status=attention` | status separation은 구현됐고 남은 병목은 queue unblock |
| execution readiness | pass 중심 서술 | 저장된 snapshot은 `warn`, `can_run=False`; 현재 runtime contract는 upstream attention을 `reasons`/`queue.evidence_gaps`에도 요약 | readiness가 빈 queue를 상류 attention과 함께 드러냄 |
| learning readiness | `learning_uncertain` 중심 | `not_runnable`, `likely_to_learn=False` | 현재는 proposal 부재로 not_runnable |
| 개발 환경/검증 | interpreter 경로와 pytest 진입 경로가 불명확 | VS Code interpreter는 `${workspaceFolder}\\.venv\\Scripts\\python.exe`; targeted pytest slice 통과 | 환경 드리프트를 줄였고 관련 회귀 검증 경로가 재현 가능 |

> 현재 필요한 작업은 “기존 보고서의 권고를 그대로 반복”하는 것이 아니라, 이미 반영된 P0 조치와 아직 남은 P0 조치를 분리하고, self-improvement가 빈 queue·stale evidence·미확정 학습을 성공처럼 보이게 만드는 2차 slop을 제거하는 것이다.

가장 중요한 최종 우선순위는 다음 7개다.

1. **자가 개선 queue unblock (신호 layer는 해결됨):** `mechanism-review-candidates`와 `mutation-proposals`가 0개일 때 attention을 내보내는 문제는 해결됐다. 이제 좁은 comparable seed run 1건을 finalize해 실제 입력을 다시 만든다.
2. **learning admission hardening:** `session_reports_considered=0` 또는 bounded trial 상태를 confirmed learning에서 명시적으로 제외한다.
3. **complexity touched check skip 제거:** manifest 부재 시 silent skip하지 말고 fallback discovery 또는 attention artifact를 생성한다.
4. **artifact envelope 확산:** 이미 envelope가 붙은 핵심 report를 기준 모델로 삼아 supply-chain, SBOM, run artifact까지 확산한다.
5. **proposal-as-experiment 계약 도입(2단계):** `proposal_contract`는 queue가 다시 흐르기 시작한 뒤 hypothesis/evidence/metric/rollback 계약으로 도입한다.
6. **typed vocabulary registry 도입(2단계):** `StrEnum` 부재와 `dict[str, Any]` 잔존을 줄여 status drift를 막는다.
7. **AI/IP provenance gate 추가(후속 단계):** SBOM은 존재하지만 AI-generated snippet provenance, ai-slop score, unknown-license review queue는 아직 없다.

---

## 1. Reviewer·Validator 운영 방식

요청에 맞춰 이번 문서는 두 역할의 관점을 분리해 작성했다. 실제 코드 번들 안에도 `.codex/agents/reviewer.toml`과 `.codex/agents/validator.toml`이 존재하며, 두 agent charter는 다음 역할 분담과 잘 맞는다.

| 역할 | 이번 보고서에서의 책임 | 코드 내 agent charter와의 연결 |
|---|---|---|
| Reviewer | 기존 보고서의 과잉 주장, 누락, 오래된 수치, anti-slop blind spot, contract drift를 찾음 | `reviewer.toml`은 correctness, source fidelity, behavior regression, contract drift, missing tests를 중점으로 둠 |
| Validator | 실제 코드·report artifact·Makefile·schema·테스트 표면으로 reviewer 판단을 검증함 | `validator.toml`은 bounded validation, executable regression risk, policy/schema/script/test parity를 중점으로 둠 |

| 라운드 | Reviewer 지적 | Validator 확인 | 반영 결과 |
|---:|---|---|---|
| 1 | 기존 보고서의 “proposal 1개” 진단은 현재 코드와 맞지 않을 수 있음 | `mutation-proposals.json.summary.proposals_emitted=0`, `mechanism-review-candidates.summary.candidates_emitted=0` 확인 | self-improvement 병목을 “proposal 품질”보다 “queue empty”로 재분류 |
| 2 | 기존 보고서의 “core envelope 적용 필요”는 일부 해결됐을 가능성 있음 | `artifact-freshness`, `auto-improve-readiness`, `mutation-proposals`, `outcome-metrics`, `generated-artifact-index`, `structural-complexity-budget`에 artifact envelope 존재 확인 | 권고를 “도입”이 아니라 “coverage 확산 및 primary evidence gate화”로 수정 |
| 3 | 기존 보고서의 `--allow-learning-uncertain` 추가 권고는 현재 코드에서 이미 해결됐을 수 있음 | `auto_improve_loop.py`, `auto_improve_runtime.py`, 관련 테스트에서 flag와 `bounded_trial` 확인 | 신규 구현 항목에서 제거하고 semantic 검증·metric 오염 방지 항목으로 이동 |
| 4 | supply-chain pass가 evidence currentness를 의미하지는 않음 | `sbom-readiness-gate-report.json`, `supply-chain-gate-report.json`, `openvex-draft.json`은 pass/draft지만 artifact envelope 없음 | 공급망 report도 currentness gate 대상으로 승격 |
| 5 | complexity warning이 단순 스타일 문제가 아니라 self-improvement reliability 문제일 수 있음 | `auto_improve_readiness_runtime.py`가 1,216 nonempty lines, 44 functions, 86 branch nodes로 warning | readiness runtime 분해를 P1이 아니라 P0.5 수준으로 상향 |

---

## 2. 입력별 정합성 대조

### 2.1 업로드 기존 통합 보고서의 유효한 진단

업로드한 기존 보고서는 다음 관점에서 여전히 유효하다.

- report/schema/runtime 기반은 있으나 stale 또는 unknown evidence가 promotion/readiness 판단에 섞일 위험이 있다.
- self-improvement closed loop는 execution readiness와 learning readiness를 분리해야 한다.
- proposal은 단순 작업 후보가 아니라 실험 계약이어야 한다.
- session evidence가 outcome metrics의 primary evidence가 되어야 한다.
- SBOM/provenance가 존재해도 AI-generated snippet/IP provenance 문제는 별도로 봐야 한다.
- typed vocabulary와 metric registry 없이는 status/metric alias가 늘어난다.

### 2.2 기존 보고서에서 갱신해야 할 지점

| 기존 보고서 서술 | 현재 코드 확인 | 수정 판단 |
|---|---|---|
| `LLM Wiki vNext(30).zip`, 파일 1,618개 | `LLM Wiki vNext(31).zip`, 파일 1826개 | 수치 갱신 필요 |
| artifact freshness: stale 52, unknown 141, missing envelope 141 | stale 50, unknown 135, missing envelope 135 | 일부 개선됨 |
| learning readiness를 shadow에서 active/review gate로 승격해야 함 | `--allow-learning-uncertain`와 `bounded_trial` 구현 존재 | 구현 여부보다 “학습 집계 오염 방지” 검증이 핵심 |
| proposal 1개 존재 | 저장된 snapshot 기준 `proposals_emitted=0`; 현재 runtime contract는 empty/blocked-only에서 `status=attention` | status separation 자체는 해결됐고, 현재 병목은 candidate/proposal queue empty |
| mechanism review empty 상태가 success처럼 보임 | 저장된 snapshot 기준 `candidates_emitted=0`; 현재 runtime contract는 disabled/bootstrap/no-candidate에서 `status=attention` | report는 stored snapshot과 current code contract를 분리해 서술해야 함 |
| 핵심 5개 report에 envelope 적용 필요 | 핵심 6개 이상 report에 이미 envelope 존재 | 공급망·SBOM·run artifact·task observation으로 확산 필요 |
| execution readiness pass | 저장된 snapshot은 `execution_readiness.status=warn`, `can_run=False`; 현재 runtime contract는 upstream attention 요약도 추가 | 현재 자동 개선 실행 불가 상태이며, 진단 설명도 상류 attention을 직접 포함하도록 갱신 |
| Python interpreter/pytest 환경 불명확 | VS Code는 `${workspaceFolder}\\.venv\\Scripts\\python.exe`로 고정; targeted pytest slice 통과 | 검증 진입 경로를 문서에 명시해야 함 |

### 2.3 직전 생성 보고서의 유효한 진단

직전 생성 보고서는 현재 zip 기준 전수 수치와 검증 결과를 더 정확히 반영한다. 특히 다음은 이번 통합 보고서에서도 그대로 채택한다.

- zip manifest 기준 파일 1826개, 디렉터리 69개, Python 276개, Markdown 935개, JSON 211개, `.pyc` 275개.
- Python AST parse, JSON/YAML/TOML parse, schema meta validation, import surface, pytest collect-only 등의 정적 검증은 양호하다. 전체 pytest full sweep는 이번 문서 갱신 범위에서 다시 수행하지 않았지만, `${workspaceFolder}\\.venv\\Scripts\\python.exe` 기준 targeted pytest slice(`tests/test_auto_improve_readiness_runtime.py`, `tests/test_mechanism_review.py`, `tests/test_mutation_proposal.py`)는 통과했다.
- `auto-improve-readiness.json` 기준 현재 자동 개선 loop는 runnable 상태가 아니다.
- `mechanism-review-candidates.json`과 `mutation-proposals.json`이 empty output을 내는 것이 가장 직접적인 병목이다.
- 다만 저장된 `mechanism-review-candidates.json`, `mutation-proposals.json`, `auto-improve-readiness.json`은 late update 이전 snapshot일 수 있으므로, 현재 runtime contract를 설명할 때는 generated artifact와 코드를 분리해서 읽어야 한다.
- `auto_improve_readiness_runtime.py`, `auto_improve_runtime.py`, test seed helper들이 complexity warning 대상이다.

---

## 3. 현재 코드 스냅샷

### 3.1 zip manifest 기준 규모

| 항목 | 값 |
|---|---:|
| 전체 entries | 1895 |
| 파일 수 | 1826 |
| 디렉터리 수 | 69 |
| 비압축 크기 | 242,430,957 bytes |
| 압축 크기 | 191,944,314 bytes |
| Python 파일 | 276 |
| Markdown 파일 | 935 |
| JSON 파일 | 211 |
| `.pyc` 파일 | 275 |
| `ops/scripts/*.py` | 154 |
| `tests/*.py` | 116 |
| project script entrypoints | 44 |

### 3.2 최상위 경로별 파일 수

| `ops` | 547 |
| `raw` | 446 |
| `wiki` | 417 |
| `runs` | 156 |
| `tests` | 121 |
| `system` | 71 |
| `external-reports` | 26 |
| `root` | 19 |
| `.codex` | 10 |
| `.obsidian` | 5 |
| `tools` | 5 |
| `.github` | 2 |
| `.vscode` | 1 |

### 3.3 확장자별 파일 수

| `.md` | 935 |
| `.py` | 276 |
| `.pyc` | 275 |
| `.json` | 211 |
| `.pdf` | 62 |
| `.txt` | 28 |
| `.yaml` | 13 |
| `.toml` | 10 |
| `(none)` | 5 |
| `.jsonl` | 5 |
| `.yml` | 2 |
| `.docx` | 2 |
| `.ini` | 1 |
| `.lock` | 1 |

### 3.4 코드 계약 표면

| 항목 | 현재 확인값 | 판단 |
|---|---:|---|
| dataclass 사용 파일 | 49 | DTO 도입 기반은 있음 |
| dataclass 선언/사용 수 | 119 | 계약 모델링 경험 축적됨 |
| `dict[str, Any]` 사용 파일 | 36 | typed contract 전환 필요 |
| `dict[str, Any]` 사용 횟수 | 385 | report payload drift 위험 |
| `StrEnum` 사용 | 0 | 공통 vocabulary registry 부재 |
| `proposal_contract` 문자열 hit | 0 | proposal-as-experiment 미구현 |
| `ai_slop` 문자열 hit | 0 | AI-slop score runtime 미구현 |
| `snippet_provenance` 문자열 hit | 0 | snippet/IP provenance runtime 미구현 |
| `can_count_as_learning` 문자열 hit | 0 | learning 집계 eligibility 용어 미정착 |
| `allow-learning-uncertain` 문자열 hit | 5 | override flag는 구현됨 |
| `bounded_trial` 문자열 hit | 2 | bounded trial marker도 일부 구현됨 |

---

## 4. Report artifact 정합성 검토

### 4.1 핵심 report envelope 현황

| report | artifact_status | currentness.status | envelope 계열 필드 | 저장된 snapshot | 현재 runtime contract |
|---|---|---|---|---|---|
| `artifact-freshness-report.json` | `current` | `current` | 예 | `attention` | `attention` |
| `auto-improve-readiness.json` | `current` | `current` | 예 | `execution_readiness.status=warn`, upstream attention summary는 미반영일 수 있음 | `warn` 유지 + upstream attention을 `reasons`/`queue.evidence_gaps`에 요약 |
| `mutation-proposals.json` | `current` | `current` | 예 | `status=pass` (checked-in snapshot) | empty/blocked-only이면 `status=attention` |
| `outcome-metrics.json` | `current` | `current` | 예 | `-` | `-` |
| `generated-artifact-index.json` | `current` | `current` | 예 | `attention` | `attention` |
| `structural-complexity-budget.json` | `current` | `current` | 예 | `attention` | `attention` |
| `mechanism-review-candidates.json` | `current` | `current` | 예 | `status=pass` (checked-in snapshot) | disabled/bootstrap/no-candidate이면 `status=attention` |
| `sbom-readiness-gate-report.json` | `-` | `-` | 아니오 | `pass` | `pass` |
| `supply-chain-gate-report.json` | `-` | `-` | 아니오 | `pass` | `pass` |
| `openvex-draft.json` | `-` | `-` | 아니오 | `-` | `-` |

판단:

- 기존 보고서에서 P0로 권고한 “핵심 report envelope 도입”은 일부 완료됐다.
- 그러나 supply-chain gate, SBOM readiness, OpenVEX draft, legacy initial eval/lint/manifest, run archive artifact는 아직 envelope coverage 밖에 있다.
- 또한 현재 문서에서는 checked-in generated artifact snapshot과 current runtime contract를 구분해야 한다. 이번 late update는 runtime과 테스트 계약을 바꿨지만, 저장 artifact는 별도 재생성 전까지 이전 값을 유지할 수 있다.
- 따라서 다음 단계는 envelope schema 설계가 아니라 **coverage budget**, **primary evidence admission rule**, 그리고 **contract 변경 후 report 재생성 discipline**이다.

### 4.2 Artifact freshness 현재 상태

| metric | 값 |
|---|---:|
| artifact_count | 142 |
| json_artifact_count | 142 |
| scanned_text_artifact_count | 165 |
| stale_artifact_count | 50 |
| root_ephemeral_artifact_count | 0 |
| unknown_currentness_artifact_count | 135 |
| non_utf8_text_artifact_count | 0 |
| missing_schema_count | 47 |
| missing_artifact_envelope_count | 135 |

샘플 missing envelope artifact:

- `ops/reports/cyclonedx-bom.json`
- `ops/reports/eval-initial-2026-04-12.json`
- `ops/reports/lint-initial-2026-04-12.json`
- `ops/reports/manifest-2026-04-12.json`
- `ops/reports/manual-mutate-defect-registry.json`
- `ops/reports/openvex-draft.json`
- `ops/reports/promotion-decision-trends.json`
- `ops/reports/review-archive-report.json`
- `ops/reports/sbom-export-mapping.json`
- `ops/reports/sbom-readiness-gate-report.json`
- `ops/reports/supply-chain-gate-report.json`
- `ops/reports/supply-chain-provenance.json`
- `ops/reports/task-improvement-observations/task-20260416-detailed-review-reconciliation/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260416-standalone-observation-generalization/improvement-observations.json`
- `ops/reports/task-improvement-observations/task-20260418-policy-contract-registry-validation/improvement-observations.json`

샘플 stale mtime artifact:

- `ops/reports/review-archive-report.json`
- `ops/reports/sbom-export-mapping.json`
- `ops/reports/supply-chain-provenance.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-eval.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-lint.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-mechanism-assessment.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-eval.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-lint.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-mechanism-assessment.json`
- `runs/run-20260414-mechanism-planning-gate/baseline-eval.json`
- `runs/run-20260414-mechanism-planning-gate/baseline-lint.json`
- `runs/run-20260414-mechanism-planning-gate/baseline-mechanism-assessment.json`

샘플 missing schema artifact:

- `ops/reports/eval-initial-2026-04-12.json`
- `ops/reports/lint-initial-2026-04-12.json`
- `ops/reports/manifest-2026-04-12.json`
- `ops/reports/review-archive-report.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-eval.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/baseline-lint.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-eval.json`
- `runs/archive/run-20260415-mechanism-planning-gate-second-retry/candidate-lint.json`
- `runs/run-20260414-mechanism-planning-gate/baseline-eval.json`
- `runs/run-20260414-mechanism-planning-gate/baseline-lint.json`
- `runs/run-20260414-mechanism-planning-gate/candidate-eval.json`
- `runs/run-20260414-mechanism-planning-gate/candidate-lint.json`

### 4.3 Validator 판단

현재 freshness runtime은 “감지”에는 성공한다. 하지만 anti-slop 관점의 완성 조건은 감지가 아니라 입장 통제다.

```text
report가 promotion/readiness/outcome 판단의 primary evidence로 쓰이려면:
1. has_artifact_envelope == true
2. artifact_status == current
3. currentness.status == current
4. schema validation pass
5. source_revision 또는 source_tree_fingerprint 존재
```

위 조건을 만족하지 못하면 해당 artifact는 secondary context, historical context, migration candidate, archive candidate, manual review evidence로만 사용해야 한다.

---

## 5. Self-Improvement closed loop 진단

### 5.1 현재 readiness

| 항목 | 값 |
|---|---|
| execution status | `warn` |
| execution gate_effect | `active` |
| can_run | `False` |
| upstream mechanism attention summary (current runtime) | `mechanism_review.status=attention (bootstrap_history_insufficient; candidates_emitted=0)` |
| upstream proposal attention summary (current runtime) | `mutation_proposal.status=attention (no proposals emitted; proposals_emitted=0)` |
| runnable proposal count | 0 |
| blocked proposal count | 0 |
| learning status | `not_runnable` |
| learning gate_effect | `shadow` |
| likely_to_learn | `False` |

주요 이유:

- no runnable proposal is available
- mutation proposal generation emitted zero runnable proposals
- current readiness runtime은 위 queue empty 사유에 더해 upstream attention summary를 `execution_readiness.reasons`와 `queue.evidence_gaps`의 선두에 삽입한다.
- 다만 저장된 `auto-improve-readiness.json`은 이 late update 이전 snapshot일 수 있어, generated artifact만 보면 upstream attention summary가 아직 보이지 않을 수 있다.

권장 next step:

> Queue is empty and the fallback target family has no finalized comparable seed run yet. Finalize one narrow manual `system_mechanism` run for `ops/scripts/auto_improve_iteration_persistence_runtime.py` plus `tests/test_auto_improve_iteration_runtime.py`, then rerun `make auto-improve-readiness`.

### 5.2 현재 learning metrics

| metric | 값 |
|---|---:|
| attempts_considered | 7 |
| min_attempts_considered | 10 |
| session_reports_considered | 0 |
| session_calibration_status | `no_candidates` |
| rework_count | 5 |
| hold_moving_average | 0.2857 |
| discard_moving_average | 0.1429 |
| defect_escape_pair_count | 3 |

판단:

- `session_reports_considered=0`인 상태에서 self-improvement를 confirmed learning으로 집계하면 안 된다.
- `attempts_considered=7`은 최소 기준 10보다 낮다.
- `rework_count=5`, `defect_escape_pair_count=3`은 improvement loop가 아직 안정적으로 닫히지 않았다는 신호다.
- 기존 보고서의 “learning readiness active화” 권고는 현재 코드에서 일부 반영됐지만, `can_count_as_learning` 같은 명시적 eligibility vocabulary는 아직 없다.

### 5.3 Mutation proposal 상태

| metric | 값 |
|---|---:|
| source_candidates_read | 0 |
| log_entries_scanned | 5 |
| proposals_emitted | 0 |
| blocked_proposals | 0 |

queue pressure summary:

> no proposals emitted | mechanism review emitted zero candidates | outcome_metrics_calibration.status=no_candidates | outcome_metrics: attempts_considered=7 is below min_attempts_considered=10

checked-in artifact snapshot status:

> `mutation-proposals.json.status=pass` (late update 이전 generated artifact)

`mechanism-review-candidates.json.summary` 기준:

| metric | 값 |
|---|---:|
| runs_discovered | 7 |
| runs_considered | 0 |
| runs_skipped | 7 |
| candidates_emitted | 0 |

checked-in artifact snapshot status:

> `mechanism-review-candidates.json.status=pass` (late update 이전 generated artifact)

판단:

- 현재 mutation_proposal_runtime은 proposal 0개 또는 blocked-only queue를 `status=pass`가 아니라 `status=attention`으로 반환하도록 개선됐다.
- mechanism_review_runtime도 disabled/bootstrap/no-candidate 상태를 `status=attention`으로 반환하도록 개선됐다.
- 따라서 현재 가장 큰 병목은 proposal contract의 섬세함 이전에 **candidate/proposal 생성 입력이 비어 있다는 점**이다.
- `status=empty`, `status=no_candidates`, `status=blocked_no_seed` 같은 finer-grained vocabulary는 여전히 유익하지만, 다음 건강한 최소 수정의 선행 조건은 아니다. top-level success와 non-ready를 분리하는 최소 계약은 이미 반영됐다.

### 5.4 이미 구현된 learning override

현재 코드에는 CLI flag `--allow-learning-uncertain`, runtime parameter `allow_learning_uncertain`, `bounded_trial` marker, 관련 회귀 테스트가 이미 존재한다. 또한 readiness runtime은 이제 mechanism review와 mutation proposal의 upstream attention을 직접 요약한다. 따라서 기존 권고는 “flag 추가”가 아니라 아래 세 가지를 명시적으로 닫는 것으로 바뀌어야 한다.

1. bounded trial 결과를 confirmed learning summary에서 제외한다.
2. `session_reports_considered=0`이면 `learning_confirmation_eligible=false`를 자동으로 강제한다.
3. 위 두 상태가 outcome/session report 집계에 섞이지 않도록 회귀 테스트를 추가한다.

권장 field 예시:

```json
{
  "learning_confirmation_eligible": false,
  "bounded_trial": true,
  "pre_run_learning_status": "learning_uncertain",
  "excluded_from_outcome_learning_summary": true
}
```

---

## 6. Proposal-as-experiment gap

현재 코드에는 `proposal_contract` 문자열 hit가 없다. 즉, 기존 보고서의 proposal-as-experiment 방향은 아직 핵심 runtime/schema vocabulary로 정착되지 않았다.

권장 contract:

```json
{
  "proposal_contract": {
    "hypothesis": "무엇을 바꾸면 어떤 metric이 왜 움직일지",
    "evidence_refs": [],
    "expected_binary_signal": "어떤 테스트/게이트가 통과해야 하는지",
    "expected_metric_movement": [],
    "minimum_validation_artifacts": [],
    "rollback_trigger": [],
    "rollback_plan": "되돌리는 최소 경로",
    "disqualifying_evidence": [],
    "risk_class": "trivial|bounded|risky",
    "learning_value": "low|medium|high"
  }
}
```

gate rule:

```text
proposal_contract가 없으면:
- autonomous mutation 불가
- supervised seed run만 허용
- mutation-proposals report에는 status=no_contract 또는 review_required를 기록

evidence_refs가 stale/unknown/missing-envelope이면:
- runnable=false
- reason=evidence_not_current
- required_next_observation에 재생성 command 기록
```

Reviewer 판단:

```text
1. narrow seed run 1개 확정
2. mechanism review candidate가 1개 이상 나오도록 unblock
3. proposal generator가 proposal 1개 이상 생성
4. 그 proposal에 proposal_contract required 적용
5. 이후 autonomous mutation gate에 연결
```

---

## 7. Session evidence gap

현재 `outcome-metrics.json.summary.session_reports_considered=0`이다. 이 값이 0인 상태에서는 self-improvement가 실제로 무엇을 배웠는지 신뢰하기 어렵다.

| 항목 | 값 |
|---|---:|
| attempts_considered | 7 |
| recent_attempt_count | 7 |
| session_reports_considered | 0 |
| rework_count | 5 |
| rollback_signal_count | 0 |
| rollback_rehearsal_coverage_count | 1 |
| hold moving average | 0.2857 |
| discard moving average | 0.1429 |

권장 session envelope:

```json
{
  "session_id": "...",
  "operator_intent": "...",
  "proposal_contract_ref": "...",
  "pre_run_readiness": {
    "execution_status": "...",
    "learning_status": "...",
    "learning_confirmation_eligible": false
  },
  "role_dispatch": {
    "reviewer": {"scope": "...", "result": "..."},
    "validator": {"scope": "...", "result": "..."}
  },
  "post_run_outcome": {
    "decision": "promote|hold|discard|rollback",
    "observed_metric_movement": [],
    "rework_signal": false,
    "defect_escape_signal": false
  },
  "learned": {
    "confirmed": false,
    "why": "...",
    "evidence_refs": []
  }
}
```

gate rule:

```text
session envelope 없음:
- outcome metrics는 historical summary로만 사용
- learning readiness는 learning_ready가 될 수 없음
- promotion trend에는 반영 가능하지만 self-improvement learning summary에는 반영 금지
```

---

## 8. Complexity와 maintainability risk

### 8.1 structural complexity budget 현황

| metric | 값 |
|---|---:|
| profile_count | 3 |
| target_count | 22 |
| targets_with_attention_count | 4 |
| targets_with_failure_count | 0 |
| function_budget_candidate_count | 3 |

warning targets:

| path | profile | status | nonempty LOC | functions | branch nodes | over-budget |
|---|---|---|---:|---:|---:|---|
| `ops/scripts/auto_improve_runtime.py` | `critical_runtime_orchestrators` | `warn` | 699 | 27 | 29 | - |
| `ops/scripts/auto_improve_readiness_runtime.py` | `critical_runtime_orchestrators` | `warn` | 1216 | 44 | 86 | nonempty_line_count_total |
| `tests/minimal_vault_seed_core.py` | `high_complexity_helpers` | `warn` | 360 | 2 | 4 | - |
| `tests/minimal_vault_seed_smoke.py` | `high_complexity_helpers` | `warn` | 358 | 5 | 2 | - |

function budget candidates:

| file | symbol | function lines | params | branch nodes | triggered budgets |
|---|---|---:|---:|---:|---|
| `ops/scripts/auto_improve_runtime.py` | `run_auto_improve_session` | 60 | 11 | 4 | parameter_count |
| `tests/minimal_vault_seed_core.py` | `seed_minimal_vault` | 388 | 2 | 4 | function_lines |
| `tests/minimal_vault_seed_smoke.py` | `seed_open_question_smoke_vault` | 287 | 2 | 2 | function_lines |

### 8.2 anti-slop 판단

복잡도 warning 자체보다 더 큰 문제는 `Makefile`의 touched complexity check가 manifest나 명시 target이 없으면 skip될 수 있다는 점이다.

권장 변경:

```text
CHANGED_FILES_MANIFEST 있음 → manifest 사용
없음 + git diff 가능 → git diff --name-only 사용
없음 + git 불가 → 최근 수정 파일 또는 strict preview allowlist 사용
그래도 없음 → status=attention report 생성, silent skip 금지
```

### 8.3 readiness runtime 분해

| 신규 모듈 | 역할 |
|---|---|
| `readiness_inputs.py` | report/run/config 로딩, schema 검증, stale evidence 배제 |
| `readiness_policy.py` | execution gate, blocker, override semantics |
| `readiness_learning.py` | learning readiness, attempts threshold, session evidence 판단 |
| `readiness_queue.py` | candidate/proposal empty 상태 분류 |
| `readiness_render.py` | JSON report, summary, recommended next step |
| `readiness_contracts.py` | DTO/TypedDict/StrEnum adapter |

---

## 9. Supply-chain, SBOM, OpenVEX, AI/IP provenance

### 9.1 현재 장점

현재 코드에는 CycloneDX SBOM, SBOM export mapping, SBOM readiness gate, supply-chain provenance/gate, OpenVEX draft, in-toto statement, Sigstore bundle 계열 runtime이 존재한다. dependency inventory, release artifact provenance, public export contract는 이미 체계를 갖추고 있다.

### 9.2 현재 gap

하지만 현재 `sbom-readiness-gate-report.json`, `supply-chain-gate-report.json`, `openvex-draft.json`은 artifact envelope 계열 필드를 갖지 않는다. 또한 `openvex-draft.json`은 `statement_count=0`, `vulnerability_source=not_scanned` 상태다.

| 항목 | 값 |
|---|---|
| OpenVEX status | `draft` |
| component_count | 21 |
| statement_count | 0 |
| dependency_edge_count | 21 |
| vulnerability_source | `not_scanned` |

권고:

1. 공급망 관련 report에도 artifact envelope를 추가한다.
2. `statement_count=0`의 원인을 `not_scanned|no_known_vulnerabilities|scanner_unavailable|vex_deferred` 중 하나로 분리한다.
3. SBOM은 dependency inventory용으로 유지하고, AI-generated code/IP provenance는 별도 runtime으로 둔다.
4. `ai_slop_score_runtime.py`, `snippet_provenance_runtime.py`를 추가하고 promotion gate에 연결한다.

---

## 10. Typed contract와 vocabulary registry

현재 코드에는 dataclass 기반이 있지만 `StrEnum` 기반 공통 vocabulary는 확인되지 않는다. `dict[str, Any]`도 36개 파일에서 385회 확인된다.

self-improvement 시스템에서 다음 vocabulary drift가 생기면 gate가 느슨해진다.

```text
pass / ok / passed
warn / attention / warning
learning_likely / learning_ready
not_runnable / blocked / no_candidates
hold / review_required / shadow
```

권장 enum:

```python
from enum import StrEnum

class Verdict(StrEnum):
    PASS = "pass"
    WARN = "warn"
    ATTENTION = "attention"
    FAIL = "fail"

class GateEffect(StrEnum):
    ACTIVE = "active"
    SHADOW = "shadow"
    REVIEW_REQUIRED = "review_required"
    BLOCKING = "blocking"

class RunEligibility(StrEnum):
    RUNNABLE = "runnable"
    NOT_RUNNABLE = "not_runnable"
    BOUNDED_TRIAL_ONLY = "bounded_trial_only"

class LearningEligibility(StrEnum):
    CONFIRMABLE = "confirmable"
    NOT_CONFIRMABLE = "not_confirmable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class EvidenceCurrentness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
```

drift detector:

```text
tests/test_schema_enum_matches_vocabulary_runtime_enum.py
tests/test_report_status_values_are_registered.py
tests/test_metric_registry_covers_readiness_outcome_promotion_fields.py
```

---

## 11. Smallest Healthy Fix 기준 보완 로드맵

### Done

| 항목 | 반영 상태 |
|---|---|
| 상태 분리 | mechanism review와 mutation proposal runtime이 빈 queue, disabled, blocked-only 같은 비실행 상태를 success와 분리하도록 정리됐다. |
| readiness 요약 | readiness가 upstream attention을 직접 요약해, 상류 queue 병목이 즉시 보이도록 바뀌었다. |
| 개발 진입 경로 | 편집기 기본 Python 경로를 repo-local 가상환경으로 고정해 환경 드리프트를 줄였다. |
| 검증 | 위 변경을 커버하는 targeted pytest slice가 통과했다. |

### Next

| 우선순위 | 작업 | 완료 조건 |
|---:|---|---|
| 1 | queue unblock | narrow manual `system_mechanism` seed run 1건을 finalize하고 queue를 다시 생성해 candidate와 proposal이 0개 상태에서 벗어난다. |
| 2 | learning admission hardening | session rollup 부재와 bounded trial을 confirmed learning 집계에서 명시적으로 제외한다. |
| 3 | touched complexity skip 제거 | touched complexity check가 조용히 skip되지 않고, attention 또는 fallback discovery를 반드시 남긴다. |
| 4 | proposal_contract 도입 | queue가 다시 흐르기 시작한 뒤 proposal에 hypothesis, evidence, metric, rollback 계약을 required로 붙인다. |

### Deferred

| 작업 | 이유 |
|---|---|
| session envelope 우선 사용 | learning admission을 먼저 잠근 뒤 붙여도 되는 2단계 작업이다. |
| typed vocabulary와 readiness runtime 분해 | 유지보수성에는 중요하지만 현재 queue unblock의 선행조건은 아니다. |
| 공급망 envelope 확산, AI/IP provenance | governance 강화 항목이지만 현재 self-improvement 재가동 병목보다 뒤에 둔다. |

---

## 12. 우선 작업 큐

| 순서 | 작업 | 종료 조건 |
|---:|---|---|
| 1 | narrow manual seed run 1건 finalize | comparable `system_mechanism` run 1건이 생기고 queue 재평가의 입력이 확보된다. |
| 2 | refresh-generated와 auto-improve-readiness 재실행 | candidate/proposal queue와 readiness가 최신 runtime semantics로 다시 계산된다. |
| 3 | session evidence 없는 confirmed learning 차단 | `session_reports_considered=0`이면 confirmed learning이 불가하다. |
| 4 | bounded trial learning admission 차단 | override 또는 bounded trial 결과가 confirmed learning에 집계되지 않는다. |
| 5 | touched complexity check의 silent skip 제거 | changed-files manifest나 target이 없을 때도 skip echo 대신 attention 또는 fallback target set이 남는다. |
| 6 | changed-files 미제공 fallback 정착 | touched complexity가 manifest 부재만으로 공백 검사가 되지 않는다. |
| 7 | `proposal_contract` schema 초안 추가 | hypothesis, evidence_refs, expected_metric_movement, rollback 관련 필드가 필수가 된다. |
| 8 | proposal producer enforcement 연결 | contract가 빠진 proposal은 생성되거나 실행 큐에 들어가지 못한다. |

---

## 13. 외부 기준과의 정렬

| 외부 기준 | 연결되는 내부 권고 |
|---|---|
| GitHub Actions least privilege | CI workflow permissions/security report |
| GitHub Artifact Attestations | release artifact provenance, SBOM attestation |
| SLSA Build Provenance | source_revision, tree_fingerprint, build/run provenance |
| CycloneDX SBOM | dependency inventory, component relationship |
| CISA SBOM/VEX | vulnerability applicability context |
| OpenVEX | statement status, justification, affected/not_affected/fixed/under_investigation |
| OWASP LLM Top 10 2025 | prompt injection, insecure output handling, supply-chain, excessive agency |
| mypy strict optional checks | typed contract hardening |
| Ruff preview mode | unstable lint rules를 allowlist/touched-code gate로 단계적 도입 |
| pytest tmp_path/xdist | artifact writer 테스트 격리와 병렬 실행 전략 |

---

## 14. 최종 판단

현재 코드베이스는 “anti-slop 장치가 없는 상태”가 아니다. 오히려 report, schema, gate, SBOM, provenance, public export, agent profile, readiness runtime이 충분히 많다. 이제 위험은 장치 부족이 아니라 **장치가 많아졌지만 서로를 강제하지 못하는 상태**다.

최종적으로 가장 위험한 실패 모드는 다음이다.

1. 저장된 generated artifact snapshot이 이전 `pass` 상태를 유지해, 운영자가 현재 runtime contract까지 아직 `pass`로 오해한다.
2. session evidence 0개인데 outcome metrics가 학습 신호처럼 소비된다.
3. changed-files manifest 부재 시 touched complexity check가 조용히 skip되어 실제 touched surface가 비검사 상태로 지나간다.
4. 핵심 report 일부에 envelope가 생겼지만 supply-chain/run artifact는 unknown currentness로 남는다.
5. `--allow-learning-uncertain`가 bounded trial로 구현됐지만 confirmed learning exclusion이 완전히 제도화되지 않는다.
6. SBOM/provenance가 있다는 이유로 AI-generated snippet/IP provenance까지 해결됐다고 착각한다.
7. readiness runtime과 test fixture가 커져, self-improvement를 평가하는 장치 자체가 slop source가 된다.

> LLM Wiki vNext의 다음 개선은 status semantics를 다시 설계하는 것이 아니라, 이미 존재하는 anti-slop 장치를 “관찰 장치”에서 “입장 통제 장치”로 승격하고, 자가 개선 루프가 빈 queue·불확실한 학습·stale evidence를 성공으로 오인하지 못하게 만드는 것이다.

---

## Appendix A. 현재 코드 evidence quick map

| evidence | 현재 값 |
|---|---|
| manifest file count | 1826 |
| manifest dir count | 69 |
| Python file count | 276 |
| ops script count | 154 |
| tests Python file count | 121 |
| project script entrypoints | 44 |
| artifact freshness status | `attention` |
| missing artifact envelope | 135 |
| unknown currentness | 135 |
| stale artifact count | 50 |
| readiness execution | `warn` |
| readiness upstream attention summary | 예 (runtime/test 기준) |
| readiness can_run | `False` |
| learning readiness | `not_runnable` |
| session reports considered | 0 |
| mutation proposal snapshot status | `pass` (generated artifact) |
| mutation proposal current contract | empty/blocked-only -> `attention` |
| mutation proposals emitted | 0 |
| mechanism review snapshot status | `pass` (generated artifact) |
| mechanism review current contract | disabled/bootstrap/no-candidate -> `attention` |
| mechanism candidates emitted | 0 |
| structural warning targets | 4 |
| function budget candidates | 3 |
| OpenVEX statement count | 0 |
| `allow-learning-uncertain` implemented | 예 |
| VS Code interpreter pin | `${workspaceFolder}\\.venv\\Scripts\\python.exe` |
| targeted pytest slice | `tests/test_auto_improve_readiness_runtime.py`, `tests/test_mechanism_review.py`, `tests/test_mutation_proposal.py` 통과 |
| `proposal_contract` implemented | 아니오 |
| `ai_slop_score` implemented | 아니오 |
| `snippet_provenance` implemented | 아니오 |

## Appendix B. 파일별 우선 검토 대상

| 우선순위 | 파일 | 이유 |
|---:|---|---|
| 1 | `ops/scripts/auto_improve_iteration_persistence_runtime.py` + `tests/test_auto_improve_iteration_runtime.py` | queue unblock을 위한 narrow comparable seed run 후보 |
| 2 | `ops/scripts/auto_improve_readiness_runtime.py` | upstream attention 요약 이후 learning admission hardening 지점 |
| 3 | `ops/scripts/mutation_proposal_runtime.py` | queue 재생성 이후 proposal producer enforcement와 proposal contract 연결 지점 |
| 4 | `ops/scripts/mechanism_review_runtime.py` | candidate empty/non-ready attention semantics의 source of truth |
| 5 | `ops/scripts/auto_improve_runtime.py` | bounded trial, session state, execution guard |
| 6 | `ops/scripts/outcome_metrics.py` | session evidence primary 전환 지점 |
| 7 | `ops/scripts/structural_complexity_budget.py` | touched fallback discovery와 silent skip 제거 |
| 8 | `ops/scripts/artifact_freshness_runtime.py` | evidence admission rule과 regeneration discipline 확장 |
| 9 | `ops/scripts/sbom_readiness_gate_runtime.py` | supply-chain report envelope 적용 |
| 10 | `ops/scripts/supply_chain_gate_runtime.py` | supply-chain currentness admission |
| 11 | `ops/scripts/openvex_draft.py` | statement_count_reason, vulnerability_source semantics |
| 12 | `tests/test_auto_improve_runtime.py` | bounded trial/learning gate 회귀 테스트 |
| 13 | `tests/test_auto_improve_readiness_runtime.py` | upstream attention summary와 learning gate 회귀 테스트 |
| 14 | `tests/test_mutation_proposal.py` | proposal contract 회귀 테스트 |
| 15 | `tests/test_mechanism_review.py` | candidate generation 및 attention semantics 회귀 테스트 |
