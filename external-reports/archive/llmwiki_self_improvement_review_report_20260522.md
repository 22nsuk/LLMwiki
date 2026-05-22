# LLMwiki 자가 개선 관점 리뷰 보고서

_로컬 원본 저장소 압축본 + 연결 GitHub 프로젝트 기준_

- **검토 대상**: /mnt/data/LLMwiki(8).zip (로컬 원본 저장소 압축본)
- **연결 origin**: https://github.com/22nsuk/LLMwiki.git
- **검토 시점 HEAD**: a644b37 — Close active external report remediation
- **HEAD 시각**: 2026-05-22T19:35:49+09:00
- **검토 일시**: 2026-05-22
- **기준 원칙**: 자가 개선의 안전한 실행·증거·승격 가능성 평가

> 총평: 이 저장소는 ‘자가 개선을 함부로 승격하지 않도록 막는 시스템’으로서는 상당히 성숙하지만, ‘가볍고 반복 가능한 자가 개선 승격 시스템’으로 보기는 아직 이르다. 현재 상태의 권고는 trial 허용·promotion 금지 유지다.

## 1. 결론 요약

이 프로젝트의 가장 큰 강점은 통제와 증거다. schema-backed report, release closeout evidence, public export, 공급망 산출물, 외부 리뷰 action matrix, 그리고 광범위한 테스트가 하나의 운영 체계로 묶여 있다. 단순히 기능이 많은 저장소가 아니라, ‘무엇을 왜 막는지’까지 기록하는 저장소다.

반대로 가장 큰 약점은 경계의 무게다. README와 ARCHITECTURE가 public mirror와 private canonical vault를 분리 가능한 구조로 설명하고 있음에도, 실제 압축본은 raw/wiki/system/runs/external-reports까지 함께 추적하는 full-vault 상태다. 그 결과 저장소 이력은 generated artifact와 대형 raw 파일에 크게 끌리고, 코드 변경·정책 변경·운영 증거 갱신이 한 저장소와 한 히스토리에서 뒤섞인다.

자가 개선 관점에서 보면 현재 시스템은 ‘실행 자체’보다 ‘실행 결과의 승격’을 더 엄격히 통제한다. 실제 checked-in evidence에서 auto-improve readiness는 실행 가능(can_execute_trial=true)하지만 결과 승격은 금지(can_promote_result=false)다. 이 판단은 과도한 보수성이 아니라, 현재 남아 있는 세 가지 blocker를 정확히 반영한 결과로 보인다.

따라서 지금 필요한 일은 새로운 self-improvement 메커니즘을 더 붙이는 것이 아니다. 첫째, repo boundary를 분리해 개발 표면을 가볍게 만들고, 둘째, release authority/clean lane/conditional lane 의미를 한 번에 읽히게 정규화하고, 셋째, 복잡도 hotspot과 거대 테스트를 잘라서 ‘고장 원인과 고장 위치가 빨리 드러나는’ 구조로 만드는 일이다.

## 2. 핵심 판정표

| 항목 | 판정 | 메모 |
|---|---|---|
| 가드레일 성숙도 | 강함 | 증거·차단·회귀 방지 체계가 잘 설계되어 있음 |
| 자가 개선 실행 가능성 | 중간 | trial/queue/readiness는 동작하지만 승격은 차단됨 |
| 자가 개선 승격 가능성 | 낮음 | batch manifest / worktree guard / backlog blocker 미해결 |
| 저장소 경계 위생 | 낮음 | private vault·generated evidence·code surface가 같은 history에 공존 |
| 공개 재현성 | 높음 | public export 재현 가능, checked-in public check도 pass |

## 3. 검토 범위와 방법

이번 리뷰는 단순 코드 리뷰가 아니라, 로컬 원본 저장소 압축본이라는 전제를 적극 반영한 운영 리뷰다. 즉 working tree뿐 아니라 .git 메타데이터, checked-in canonical report, release/workflow 정의, public export 정책, 그리고 실제 실행 재검증 결과를 함께 봤다.

또한 연결 GitHub 프로젝트는 origin URL로 확인했지만, 웹에서 직접 열람한 저장소 엔드포인트는 이 환경의 비인증 컨텍스트에서 404를 반환했다. 따라서 branch protection, ruleset, PR 이력, security 탭 설정 같은 ‘서버 측 GitHub 설정’은 직접 검증하지 못했고, 저장소 내부 설정 파일과 GitHub 공식 문서를 근거로 개선안을 도출했다.

직접 재실행한 항목과 checked-in evidence를 구분해 판단했다.

| 직접 재실행 항목 | 결과 | 비고 |
|---|---|---|
| make dev-install | pass | Python 3.13 계열 .venv 생성 및 개발 의존성 설치 |
| make static | pass | ruff 통과, mypy 통과 |
| make artifact-freshness-check | pass | artifact freshness runtime 재검증 |
| make eval | pass | 총점 4792/4792 |
| make lint | pass | 에러/경고 0, review candidate 35개 |
| 선별 pytest 묶음 1 | pass | import_fallback, script_module_surface, release_closeout_batch_manifest 등 |
| 선별 pytest 묶음 2 | pass | public_surface_policy, export_public_repo, mechanism_review |

| checked-in 증거 | 상태 | 핵심 값 |
|---|---|---|
| artifact-freshness-report.json | pass | artifact 1095개, stale 0, schema invalid 0 |
| public-check-summary.json | pass | export 689개, pytest passed 469 |
| test-execution-summary.json | pass | suite=report-contract-summary |
| test-execution-summary-full.json | pass | suite=full |
| release-smoke-report.json | pass | checked-in release smoke pass |

## 4. 스냅샷 사실관계

| 항목 | 관찰값 |
|---|---|
| origin | https://github.com/22nsuk/LLMwiki.git |
| 로컬/원격 브랜치 | local main과 remotes/origin/main이 같은 HEAD를 가리킴 |
| HEAD | a644b37 — Close active external report remediation |
| 커밋 수 | 172 |
| 커밋 작성자 | 22nsuk 단일 작성자 172회 |
| 커밋 분포 | 현재 히스토리 전부 2026-05 한 달에 집중 |
| 추적 파일 수 | 2,107 |
| 작업 트리 크기 | 약 545M (설치한 .venv 제외) |
| Git pack 크기 | 184.04 MiB |
| public export 재현 | 689 files / 9.0M |

특히 주목할 점은, README/.gitignore/ARCHITECTURE가 설명하는 public-safe tracked surface와 실제 로컬 원본 스냅샷이 다르다는 것이다. 문서상으로는 raw/, wiki/, system/, runs/, external-reports/와 generated report가 public mirror에서 제외되어야 하지만, 현재 스냅샷은 이들 surface를 실제로 추적한다. 즉 이 압축본은 ‘public code repo’가 아니라 ‘canonical private full-vault repo’로 보는 것이 맞다.

| 주요 surface | tracked 파일 수 |
|---|---|
| ops/ | 586 |
| raw/ | 446 |
| wiki/ | 417 |
| runs/ | 263 |
| tests/ | 206 |
| external-reports/ | 72 |
| system/ | 71 |

| 대표 대형 tracked raw 파일 | 크기 |
|---|---|
| raw/ai_index_report_2026.pdf | 36.9 MiB |
| raw/Queued Up 2025 Edition.pdf | 23.6 MiB |
| raw/mythosreadyv92.pdf | 19.7 MiB |
| raw/2305.16291v2.pdf | 18.0 MiB |
| raw/complete-1769602232.pdf | 9.7 MiB |
| raw/EnergyandAI.pdf | 7.8 MiB |
| raw/foods-12-02871.pdf | 6.2 MiB |
| raw/foods-10-01347.pdf | 5.9 MiB |

## 5. 강점

1. 증거 중심 운영이 강하다. artifact-freshness-report는 1,095개 artifact에 대해 stale 0, missing schema 0, schema invalid 0을 보고하고 있고, release closeout·lane summary·remediation backlog·external report action matrix가 서로 연결된 형태로 존재한다.

2. 공개/비공개 분리 아이디어 자체는 우수하다. public export를 직접 재현해 보니 545M급 full snapshot이 9.0M / 689개 파일짜리 공개 표면으로 축소되었다. 즉 구조 설계는 이미 맞는 방향을 보고 있다.

3. 정적 품질 게이트가 탄탄하다. 직접 재실행한 make static에서 ruff와 mypy가 통과했고, eval도 4792/4792 만점을 재현했다.

4. release/supply-chain 의식 수준이 높다. release workflow는 배포물, SBOM, OpenVEX, in-toto, provenance artifact를 생산하고 attest-build-provenance까지 사용한다. GitHub 공식 문서 기준으로 artifact attestation은 provenance 보강의 핵심 수단이며, reusable workflow와 결합하면 더 높은 SLSA 성숙도 방향으로 확장할 수 있다. (GH-3)

5. 외부 리뷰를 ‘읽고 끝내지 않는다’. external-report-action-matrix는 active report 3건, archived report 67건, action item 28건 중 28건 구현 완료를 보여 주며 unmatched active report가 없다.

## 6. 핵심 문제와 자가 개선 리스크

### 6.1 저장소 경계 붕괴와 저장 비용

문서화된 의도는 분명하다. README와 ARCHITECTURE는 public mirror가 runtime/test/tooling만 공유하고 실제 raw/corpus/live run state는 private vault에 두는 구조를 설명한다. 그런데 실제 원본 스냅샷은 그 private surface를 모두 같은 Git history 안에 넣고 있다.

이 상태는 두 가지 문제를 만든다. 첫째, code review와 operator evidence refresh가 한 저장소에서 서로 잡음을 만든다. 둘째, 실수로 민감하거나 불필요하게 무거운 surface를 함께 운용할 가능성이 높아진다. GitHub 공식 문서는 저장소 크기를 이상적으로 1GB 미만으로 유지하라고 권고하고, 큰 binary와 generated file은 Git 외부 저장소나 Git LFS를 고려하라고 안내한다. 또한 generated file을 Git에 저장하는 관행을 피하라고 명시한다. (GH-1, GH-2)

권고: canonical private vault와 public/dev repo를 물리적으로 분리하는 편이 가장 좋다. 최소한이라도 raw 대형 PDF, live run state, archived external reports, 반복 생성되는 non-decision-grade report는 메인 개발 히스토리에서 떼어내야 한다.

| 항목 | 문서상 의도 | 실제 스냅샷 |
|---|---|---|
| raw/wiki/system | public mirror에서 제외 | 실제 tracked |
| runs/ | 로컬/운영 상태로 분리 | 실제 tracked |
| external-reports/ | public surface 제외 | 실제 tracked |
| generated report | 선별적 canonical 유지 | 대량 tracked 및 높은 churn |
| root .gitignore | public-safe allowlist | 현재 full-vault 현실과 불일치 |

### 6.2 generated artifact가 commit churn을 지배

최근 히스토리의 상위 churn 파일이 거의 모두 ops/reports 계열이다. 이는 이 프로젝트가 ‘운영 증거를 버전 관리한다’는 점에서는 장점이지만, 코드 변경의 의미를 읽기 어렵게 만들고 PR review 비용을 높인다.

| 상위 churn 파일 | 변경 횟수 |
|---|---|
| ops/reports/auto-improve-readiness.json | 107 |
| ops/script-output-surfaces.json | 83 |
| ops/reports/artifact-freshness-report.json | 80 |
| ops/reports/generated-artifact-index.json | 80 |
| ops/reports/release-risk-taxonomy-matrix.json | 72 |
| ops/reports/release-risk-taxonomy-matrix.md | 72 |
| ops/reports/rework-closures.json | 72 |
| ops/operator/artifact-relocation-audit.json | 71 |

권고: commit을 ‘코드/정책 변경’과 ‘evidence convergence’로 분리하거나, canonical로 남길 보고서 집합을 더 좁히고 나머지는 artifact storage나 archive branch로 보내는 것이 좋다.

### 6.3 복잡도 hotspot이 내부 예산을 초과

이 저장소의 좋은 점은 복잡도 예산을 스스로 정의하고 있다는 것이다. 더 좋은 점은 그 예산 초과 지점이 명확히 보고된다는 것이다. 문제는 중요한 orchestrator와 release/report builder가 그 경고 상단에 몰려 있다는 점이다.

| 파일 | LOC | 함수 | 분기 | 예산 |
|---|---|---|---|---|
| ops/scripts/mechanism/auto_improve_readiness_runtime.py | 2493 | 77 | 146 | 900/45/110 |
| ops/scripts/mechanism/mutation_proposal_runtime.py | 1566 | 62 | 142 | 900/45/110 |
| ops/scripts/core/policy_validation_runtime.py | 664 | 25 | 66 | 650/24/70 |
| ops/scripts/release/release_closeout_batch_manifest.py | 1451 | 59 | 81 | 1200/50/90 |
| ops/scripts/release/release_evidence_dashboard.py | 1947 | 68 | 72 | 1200/50/90 |
| ops/scripts/release/release_closeout_summary.py | 2195 | 69 | 111 | 1200/50/90 |

권고: refactor의 첫 타겟은 auto_improve_readiness_runtime, mutation_proposal_runtime, release_closeout_summary, release_evidence_dashboard, test_execution_summary다. 방향은 동일하다. ‘사실 수집’, ‘정책 판정’, ‘artifact 직렬화’를 분리하고, 거대한 dict 조립부를 typed intermediate object로 끊는 것이다.

### 6.4 테스트 topology가 비대해지는 징후

가장 긴 Python 파일과 가장 긴 함수가 테스트 영역에 몰려 있다는 점도 중요하다. 예를 들어 tests/test_makefile_static_gates.py는 약 3,687 non-empty LOC이고, 단일 테스트 하나가 733라인에 이른다. 이는 coverage가 나쁘다는 뜻이 아니라, 실패 원인을 빨리 찾기 어려운 구조라는 뜻이다.

| 긴 함수/테스트 | 라인 수 | 위치 |
|---|---|---|
| test_makefile_static_gates.py::test_auto_improve_goal_targets_write_contract_and_status_report | 733 | line 2969-3701 |
| test_external_report_action_matrix.py::test_goal_native_actions_require_current_canonical_runtime_reports | 295 | line 381-675 |
| goal_run_status.py::build_report | 240 | line 219-458 |
| test_makefile_static_gates.py::test_release_smoke_targets_expose_fast_and_full_profiles | 213 | line 1430-1642 |
| test_makefile_static_gates.py::test_test_execution_summary_target_wraps_report_contracts | 207 | line 2563-2769 |
| test_run_mechanism_experiment.py::test_wrapper_ignores_ephemeral_workspace_noise_in_changed_manifest | 192 | line 950-1141 |

권고: release/workflow/goal-runtime/makefile static gate를 fixture builder와 helper assertion으로 분해해, 한 테스트가 하나의 lane 규칙만 검증하도록 좁히는 편이 좋다.

### 6.5 release authority는 강하지만 읽기 어렵다

checked-in evidence에서 release-closeout-summary는 pass지만, release-lane-summary는 attention이며 machine_release_status는 blocked다. operator_release_status는 allowed이고 release_authority_status는 conditional_pass다. 즉 시스템은 매우 세밀한 상태를 표현하지만, 한눈에 ‘그래서 지금 무엇이 가능한가’를 읽기가 쉽지 않다.

| release authority 상태 | 현재 값 |
|---|---|
| clean_lane_status | fail |
| conditional_lane_status | pass |
| machine_release_status | blocked |
| operator_release_status | allowed |
| sealed_release_status | unsealed_distribution_not_provided |

권고: top-level authority matrix 하나로 ‘human review allowed? machine promotion allowed? learning claim allowed? sealed distribution ready?’를 동시에 보여 주고, 각 False/blocked 판단이 어느 artifact의 어느 blocker에서 왔는지 역추적되게 만드는 편이 좋다.

### 6.6 자가 개선은 막혀 있는 것이 아니라, 올바르게 차단되고 있다

auto-improve-readiness를 보면 can_execute_trial은 true지만 can_promote_result는 false다. 이 구분은 매우 중요하다. 시스템은 실행과 승격을 분리하고 있고, 현재는 승격만 금지하고 있다.

| blocker | 근거 | 범위 |
|---|---|---|
| release batch manifest failure | sealed distribution 미제공, machine release blocked | release_gate |
| goal worktree guard failure | requested git / detected git_worktree, dirty_entry_count=84 | worktree_guard |
| remediation backlog open | open_total_count=9, open_promotion_count=6, open_repeat_count=3 | remediation_backlog |

이 의미는 명확하다. 지금의 병목은 ‘아이디어 생성’이 아니라 ‘승격 전제 조건 정리’다. 따라서 next best action은 메커니즘을 더 추가하는 것이 아니라, 이 3개 blocker를 닫는 것이다.

추가로 remediation backlog report는 backlog_item_count=10, active_blocker_count=7, repeated_blocker_count=3를 보고한다. 반복 blocker가 남아 있다는 사실 자체가 자가 개선 루프의 신뢰도를 잠식한다.

### 6.7 GitHub-native 자동화 보강 여지

로컬 스냅샷 기준으로 .github/workflows에는 ci.yml과 release.yml만 있고, Dependabot 설정, CodeQL workflow, dependency review workflow는 보이지 않는다. 또한 현재 workflow에는 concurrency 키가 없고, 외부 action 참조는 setup-uv만 full SHA로 pin되어 있으며 checkout/setup-python/upload/download/pypi publish/attest-build-provenance는 태그 참조다.

GitHub 공식 문서는 CodeQL code scanning, Dependabot version update, dependency review를 각기 별도의 보안/유지보수 레이어로 제공한다. 또한 concurrency를 사용하면 중복 workflow/job 실행을 제어할 수 있고, full-length commit SHA pinning이 action을 immutable하게 쓰는 유일한 방법이라고 설명한다. required status check와 protected branch/ruleset은 이런 검사를 merge 전제 조건으로 묶는 수단이다. (GH-4, GH-5, GH-6, GH-7, GH-8, GH-9)

권고: 현재 프로젝트가 이미 공급망/증거 수준을 높게 가져가고 있는 만큼, GitHub-native 보안 자동화도 같은 레벨로 올리는 편이 좋다. 특히 public export나 release 관련 PR에 dependency review와 required status check를 물리면 효과가 크다.

### 6.8 clock skew 경고

직접 재실행 시 여러 make target에서 'Clock skew detected' 경고가 출력됐다. 이 스냅샷에는 미래 시각으로 찍힌 report 파일이 다수 포함되어 있었고, 이는 incremental build나 freshness 판단을 불안정하게 만들 수 있다. 심각한 설계 결함은 아니지만, canonical evidence를 시간에 매우 민감하게 다루는 저장소에서는 조용한 오판 원인이 될 수 있다.

## 7. 자가 개선 관점의 해석

이 프로젝트의 자가 개선 체계는 두 층으로 나뉜다. 첫 층은 mutation candidate를 만들고 실행 readiness를 계산하는 층이고, 둘째 층은 release authority와 learning claim을 판정하는 층이다. 현재 문제는 첫 층이 부실해서가 아니라, 둘째 층의 전제 조건이 아직 닫히지 않았다는 데 있다.

즉 이 저장소는 ‘자가 개선을 과신하지 않는 태도’가 잘 구현되어 있다. 이것은 긍정적이다. 다만 운영 단위가 너무 무겁고, 많은 canonical report가 같은 repo 안에서 함께 흔들리기 때문에, self-improvement가 실험적으로는 돌아도 프로덕션 수준의 승격 리듬으로 연결되기 어렵다.

한 문장으로 정리하면 이렇다. 현재 LLMwiki는 ‘잘 막는 self-improving repository’이지, 아직 ‘가볍게 반복 승격되는 self-improving repository’는 아니다.

## 8. 우선순위 개선안

| 우선순위 | 개선안 | 구체 실행 | 효과 |
|---|---|---|---|
| P0 | 3개 promotion blocker 해소 | sealed distribution 제공, goal worktree guard clean pass, remediation backlog 정리 후 promotion rehearsal 1회 성공 | 승격 가능성 회복 |
| P0 | vault/code 경계 분리 | public/dev repo를 주 개발 표면으로 승격, raw/runs/archive/generated bulk를 분리 | clone/리뷰/누수 리스크 감소 |
| P0 | GitHub-native 보안 자동화 추가 | Dependabot, CodeQL, dependency review, required status check, concurrency, action pinning 정책 | PR 단계 방어 강화 |
| P1 | 복잡도 hotspot 분해 | auto_improve_readiness_runtime 등 5개 상위 파일부터 orchestrator 분리 | 고장 위치 가시성 향상 |
| P1 | 거대 테스트 분해 | fixture builder와 helper assertion 추출, lane 단위 검증으로 재편 | 디버깅 비용 감소 |
| P1 | generated artifact 분류 재정의 | decision-grade vs ephemeral 구분 후 tracked 집합 축소 | history noise 감소 |
| P2 | reusable workflow 기반 provenance 강화 | release/provenance lane 공통 workflow화 | 공급망 일관성 강화 |
| P2 | public export를 1급 개발 표면화 | export tree 기준 문서·테스트·CI를 우선 설계 | public reproducibility 증가 |
| P2 | 협업 거버넌스 준비 | PR template, CODEOWNERS, commit taxonomy | 단일 작성자 의존 완화 |

## 9. 30/60/90일 로드맵 제안

| 기간 | 목표 | 핵심 작업 | 완료 기준 |
|---|---|---|---|
| 0-30일 | 승격 차단 해소 | 3개 blocker 종료, clean/conditional/operator 상태표 단순화, promotion rehearsal 1회 | can_promote_result를 true로 만들 수 있는 근거 확보 |
| 31-60일 | repo 경량화 | public/dev repo 분리 또는 partial split, generated artifact commit policy 정리, raw 저장 정책 결정 | 개발 표면과 private vault 경계가 문서/CI/실무에 일치 |
| 61-90일 | 구조적 유지보수성 개선 | 상위 hotspot refactor, giant test 분해, GitHub 보안 자동화 전면 적용 | failure localization과 review throughput 개선 |

## 10. 실행 로그 요약

이번 세션에서 직접 재실행한 대표 명령은 아래와 같다.

```bash
make dev-install
make static
make artifact-freshness-check
make eval
make lint
python -m pytest -q tests/test_import_fallback_contract.py tests/test_script_module_surface_contract.py tests/test_release_closeout_batch_manifest.py tests/test_release_evidence_closeout_self_check.py tests/test_release_sealing_lane.py tests/test_command_runtime_subprocess.py
python -m pytest -q tests/test_public_surface_policy.py tests/test_export_public_repo.py tests/test_mechanism_review.py
python -m ops.scripts.public.export_public_repo --out /mnt/data/llmwiki_public_export
```

참고로 make public-check 전체 재실행은 이 환경의 실행 한계 때문에 끝까지 완료하지 못했다. 다만 checked-in public-check-summary는 pass였고, public export 자체는 직접 재현했다. 이 차이를 구분해서 결론에 반영했다.

## 11. 참고 문헌 및 외부 기준

아래 외부 기준은 GitHub 서버 측 설정을 직접 볼 수 없었던 부분을 보완하기 위해 사용했다. 저장소 자체 진단의 근거는 어디까지나 로컬 원본 스냅샷이다.

| ID | 문서 | URL |
|---|---|---|
| GH-1 | GitHub Docs, About large files on GitHub | https://docs.github.com/repositories/working-with-files/managing-large-files/about-large-files-on-github |
| GH-2 | GitHub Docs, Repository limits | https://docs.github.com/repositories/creating-and-managing-repositories/repository-limits |
| GH-3 | GitHub Docs, Artifact attestations | https://docs.github.com/en/actions/concepts/security/artifact-attestations |
| GH-4 | GitHub Docs, Code scanning with CodeQL | https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql |
| GH-5 | GitHub Docs, Dependabot version updates | https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/about-dependabot-version-updates |
| GH-6 | GitHub Docs, Dependency review | https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review |
| GH-7 | GitHub Docs, Control the concurrency of workflows and jobs | https://docs.github.com/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs |
| GH-8 | GitHub Docs, Secure use reference | https://docs.github.com/en/actions/reference/security/secure-use |
| GH-9 | GitHub Docs, About protected branches / rulesets | https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches |

## 12. 최종 판단

> 권고 결론: 새로운 자가 개선 기능을 더 추가하기 전에, (1) promotion blocker 3건 해소, (2) private vault와 개발 표면 분리, (3) 복잡도 hotspot 및 giant test 분해를 먼저 수행하는 것이 최적이다. 이 순서를 지키면 현재의 강한 guardrail을 유지한 채 실제 승격 가능한 self-improvement 체계로 넘어갈 수 있다.