# LLMwiki 두 통합 리뷰 및 실제 파일 대조 개선 보고서

| 항목 | 내용 |
| --- | --- |
| 작성일시 | 2026-05-06 KST |
| 작성 언어 | 한국어 |
| 출력 파일 | `llmwiki_two_integrated_reviews_actual_crosscheck_report_20260506.md` |
| 검토 대상 1 | `llmwiki_integrated_review_report_20260506.md` |
| 검토 대상 2 | `llmwiki_integrated_improvement_report_20260506.md` |
| 기존 리뷰 | `llmwiki_external_reports_improvement_report.md` |
| 실제 저장소 원본 ZIP | `LLMwiki(21).zip` |
| 검토 방식 | 두 신규 리뷰 전문 검토 → 기존 리뷰와 항목별 대조 → ZIP/추출 파일/JSON evidence/Makefile/pyproject 정합성 검증 → 보정된 개선안 도출 |

---

## 1. 최종 결론

두 신규 리뷰는 기존 리뷰의 핵심 판단을 뒤집지 않는다. 오히려 기존 리뷰의 P0 축을 대부분 유지하면서, 첫 번째 신규 리뷰는 `distribution contract closure`라는 상위 개념으로 문제를 더 정확히 묶고, 두 번째 신규 리뷰는 실행 순서와 Definition of Done을 더 간결한 개선 계획으로 재정리한다. 실제 ZIP 및 저장소 파일을 대조한 결과, **핵심 결론은 유효**하다.

가장 중요한 판정은 다음과 같다.

1. 현재 ZIP은 release source package가 아니라 **private/full repository snapshot**이다. `raw/`, `wiki/`, `runs/`, `external-reports/`, `.obsidian/`, `.vscode/` 포함은 원본 저장소 압축본이라는 전제에서는 오염이 아니지만, release/public/source package로 소비되면 위험하다.

2. Release lane은 내부 evidence 기준으로 강하다. `clean_release_ready=true`, clean blocker 0, full-suite `944 passed` artifact가 존재한다.

3. Distribution sealing은 아직 닫히지 않았다. `report-reference-manifest.json`의 `current_distribution_zip`은 비어 있고, `release-closeout-batch-manifest.json`은 `distribution_package.status=not_provided` 상태에서도 clean release 계열 판정을 담는다.

4. Learning lane은 보수적으로 차단되어 있으며, 이는 적절하다. same-eval typed evidence가 0이므로 `learning_claim_allowed=false`가 유지되어야 한다.

5. 두 신규 리뷰 모두 대체로 정확하지만, 일부 표현은 보정이 필요하다. 특히 `telemetry_coverage_ratio=1.0`은 `auto-improve-readiness.json` 기준으로는 맞지만, `learning-delta-scoreboard.json`의 summary 기준은 `0.75`/`partial`이다. 또한 몇몇 release 상태 필드는 top-level이 아니라 nested `summary` 안에 있다.

---

## 2. 입력 파일 Inventory

| 파일 | bytes | lines | SHA-256 | 역할 |
| --- | ---: | ---: | --- | --- |
| 기존 리뷰: `llmwiki_external_reports_improvement_report.md` | 33,850 | 497 | `bdbe5ab26a50ca885de4e583140ae3805330e03726c89ea77ba73f4e111639f6` | 이전 차수의 기준 개선 보고서 |
| 신규 리뷰 A: `llmwiki_integrated_review_report_20260506.md` | 43,436 | 756 | `8e927a3092bcd44c65c57f4945ab402d129b1ac210010bb0dd7e9bd182f42eb6` | 더 긴 통합·메타분석 보고서 |
| 신규 리뷰 B: `llmwiki_integrated_improvement_report_20260506.md` | 26,494 | 508 | `3f7a8ec0e4fd29ceb682cc580d4a1a41ab9518c3ed3929cf239dd8b080f62881` | 더 간결한 운영형 통합 개선 보고서 |
| 원본 ZIP: `LLMwiki(21).zip` | 191,977,871 | N/A | `ca035e1125ce6ca4409e415ed0845bfdb6fe95396ac906079898aedbb82e1767` | 실제 저장소 스냅샷 |

### 2.1 두 신규 리뷰의 구조적 차이

| 구분 | 신규 리뷰 A: `llmwiki_integrated_review_report_20260506.md` | 신규 리뷰 B: `llmwiki_integrated_improvement_report_20260506.md` | 판정 |
| --- | --- | --- | --- |
| 분량 | 756 lines / 43,436 bytes | 508 lines / 26,494 bytes | A가 더 포괄적, B가 더 실행 요약형 |
| 문서 성격 | 메타분석, 잔존 문제, 관점 차이, branch roadmap, DoD까지 폭넓게 정리 | 공통 결론, P0/P1/P2 개선안, 실행 순서 중심 | 둘 다 유효. A를 canonical review로, B를 operator action plan으로 쓰는 것이 적절 |
| 기존 리뷰 반영 | 기존 리뷰의 기술 검증, 감사 보고서, 재구성 보고서를 모두 동등하게 통합 | 동일하나 상대적으로 압축 | 누락이라기보다 상세도 차이 |
| 고유 강점 | 리뷰 간 표현 차이와 현재 폐기해야 할 과거 주장까지 분리 | 실행 순서와 완료 조건이 짧고 명확 | 상호 보완 |
| 주의점 | 일부 수치는 artifact별 nested 위치를 구분해서 읽어야 함 | 일부 P1/P2 분류가 A와 다름 | 우선순위 체계는 본 보고서에서 재정렬 |

---

## 3. 실제 ZIP 및 저장소 파일 대조 결과

### 3.1 ZIP Inventory

| 항목 | 실제 확인값 | 신규 리뷰 주장과의 관계 |
| --- | ---: | --- |
| ZIP SHA-256 | `ca035e1125ce6ca4409e415ed0845bfdb6fe95396ac906079898aedbb82e1767` | 두 신규 리뷰 및 기존 리뷰와 일치 |
| ZIP 크기 | 191,977,871 bytes | 일치 |
| ZIP entry 수 | 1,853 | 일치 |
| 파일 entry 수 | 1,754 | 일치 |
| 디렉터리 entry 수 | 99 | 일치 |
| 비압축 총 바이트 | 243,780,682 bytes | 일치 |
| timestamp 최소/최대 | (2026, 4, 12, 16, 3, 6) ~ (2026, 5, 6, 21, 9, 34) | 일치 |
| unique timestamp 수 | 전체 entry 기준 827, 파일 entry 기준 807 | 리뷰의 `807~827` 표기는 기준 차이로 타당 |
| `tmp` 관련 entry | `tmp/` | ZIP에는 빈 `tmp/` directory entry만 있음. 실제 추출 디렉터리에서는 빈 dir가 생략될 수 있음 |

### 3.2 디렉터리별 파일 분포

| prefix | 실제 파일 수 | 해석 |
| --- | ---: | --- |
| `raw` | 446 | 원본 PDF/웹 snapshot. public/source package에서는 제외 후보 |
| `wiki` | 417 | content corpus. public mirror 기본 제외 후보 |
| `ops` | 403 | runtime/schema/policy/generated evidence 혼재 |
| `runs` | 166 | live/historical run artifact. source manifest 밖 |
| `tests` | 152 | 테스트 코드와 fixture |
| `system` | 71 | maintainer/system corpus |
| `external-reports` | 57 | active reports + archive + manifest |
| `root` | 18 | README/Makefile/pyproject 등 루트 파일 |
| `.codex` | 10 | agent profile |
| `.obsidian` | 5 | local vault/editor state |
| `tools` | 5 | helper tools |
| `.github` | 2 | CI/release workflow |
| `.ouroboros` | 1 | local/eval config |
| `.vscode` | 1 | local editor setting |

### 3.3 Source Manifest 대비 ZIP 차이

| 항목 | 실제 확인값 | 판정 |
| --- | ---: | --- |
| `ops/manifest.json` source file count | 1,422 | 두 신규 리뷰와 일치 |
| ZIP file count | 1,754 | 두 신규 리뷰와 일치 |
| ZIP-only path count | 332 | 두 신규 리뷰와 일치 |
| manifest-only path count | 0 | 두 신규 리뷰와 일치 |

이 332개 초과분은 원본 저장소 snapshot이라는 전제에서는 자연스럽다. 그러나 `source_content_package` 또는 `public_code_mirror`로 평가하면 drift/오염으로 판정되어야 한다. 따라서 두 신규 리뷰가 말한 archive profile 분리는 실제 파일과 정확히 맞는다.

### 3.4 `external-reports/` 활성/보관 파일 대조

실제 ZIP의 `external-reports/` 파일은 총 57개이고, root 활성 파일은 4개, archive 파일은 53개다. 활성 파일은 3개 Markdown 보고서와 1개 manifest이며, 두 신규 리뷰의 숫자와 일치한다.

| 활성 파일 | bytes | lines | SHA-256 | 판정 |
| --- | ---: | ---: | --- | --- |
| `LMMwiki교차검증 개선 보고서_20260506.md` | 45,363 | 754 | `cda2b6fb1931fff70f383a2d00d2c477d1d697182535c1339feb569ed5f45a27` | 리뷰 기재값과 일치 |
| `integrated_improvement_report_v3.md` | 24,710 | 599 | `9a2fdf8861f544fec14eb1741d7b7192f7517e018ddb2d7bb9cd0e50ec387cc7` | 리뷰 기재값과 일치 |
| `llmwiki_two_review_actual_crosscheck_improvement_report.md` | 43,832 | 699 | `0eeb75734621c10ccdafd73281ce8f7dcc286c868367b51373b614b69df3e9fc` | 리뷰 기재값과 일치 |
| `report-reference-manifest.json` | 3,569 | 85 | `38522d6be3d4c11fdfa8954bb4311dfd985677cd22c5cdc70d5dd4b5e8ece8db` | 리뷰 기재값과 일치 |

---

## 4. 기존 리뷰 및 두 신규 리뷰의 핵심 주장 대조

### 4.1 핵심 P0 주장별 대조표

| 항목 | 기존 리뷰 | 신규 리뷰 A | 신규 리뷰 B | 실제 파일 대조 판정 | 보정/추가 의견 |
| --- | --- | --- | --- | --- | --- |
| Archive profile 미명시 | P0-1로 제시 | P0-1 및 Branch 3으로 확장 | P0-1 및 1단계 Hotfix에 포함 | 확인됨 | 현재 ZIP은 full snapshot이므로 “포함 자체가 오염”이 아니라 “profile 없는 소비가 위험”이라는 표현이 정확하다. |
| External report manifest current distribution 공란 | P0-2 | P0-2 및 Branch 1 | P0-2 | 확인됨 | checked-in manifest는 current ZIP을 모른다. 직접 실행 시 계산 가능하므로 기능 부재가 아니라 운영 target 미적용 문제다. |
| Release closeout batch manifest distribution 미결박 | P0-3 | P0-3 및 Branch 2 | P0-3 | 확인됨 | 직접 ZIP 바인딩 시 `drift`와 `zip_only_path_count=332`가 나왔다. 이는 source package profile로 full snapshot을 평가한 결과다. |
| Full-suite evidence nodeid digest skipped | P0-4 | P0-4 및 Branch 4 | P0-4 | 확인됨 | `944 passed` evidence는 존재하지만 무엇을 944개로 세었는지를 nodeid digest로 봉인해야 한다. |
| Learning typed evidence 0 | P0-5 | P0-5 및 Branch 5 | P0-5 | 확인됨 | auto readiness 기준 telemetry coverage는 1.0이나 scoreboard summary는 0.75/partial이다. typed coverage 3종 0은 공통 확인. |
| Pytest/runner shutdown timeout | P0-6 | P0-6 및 Branch 4에 포함 | P0-6 및 3단계 | 재현됨 | targeted pytest는 dots 출력 후 종료 지연/timeout. batch manifest도 파일 생성 후 프로세스 종료가 timeout으로 수렴했다. |

### 4.2 기존 리뷰에서 신규 리뷰가 보강한 내용

| 보강 주제 | 어느 신규 리뷰에서 두드러지는가 | 실제 채택 여부 | 이유 |
| --- | --- | --- | --- |
| `distribution contract closure`라는 상위 프레임 | A | 채택 | 개별 P0를 하나의 계약 미봉합 문제로 묶어 원인-결과 관계가 명확해짐 |
| Truth ladder | A/B 모두, B가 별도 P2로 명시 | 채택 | live gate, generated artifact, historical report, narrative review의 권위 차이를 표현해야 함 |
| Evidence bundle + attestation 3종 계약 | A/B 모두 | 채택 | source package, evidence bundle, full snapshot을 분리해야 배포 claim이 봉인됨 |
| Dashboard wording 개선 | A/B 모두, A가 더 구체 | 채택 | release clean과 learning uncertainty가 동시에 보일 때 operator 오해를 줄임 |
| Historical external report lifecycle | A/B 모두 | 채택 | archive 53개와 active 3개의 관계를 machine-readable하게 관리해야 반복 검토 비용이 줄어듦 |
| Coverage denominator semantics | A/B 모두 | 채택 | denominator 0, no evidence, not applicable, partial을 구분해야 pass 오인을 막음 |

### 4.3 두 신규 리뷰 사이의 우선순위 차이

두 신규 리뷰는 결론이 충돌하지 않지만, 일부 항목의 priority 분류가 다르다. 본 보고서의 권장 정렬은 다음과 같다.

| 항목 | 신규 리뷰 A 분류 | 신규 리뷰 B 분류 | 본 보고서 보정 분류 | 이유 |
| --- | --- | --- | --- | --- |
| 대형 runtime/test 파일 분해 | P2/장기 | P1/P2 모두 언급 | P2 | 계약 봉인 전 대형 refactor는 risk surface를 키울 수 있음 |
| Evidence bundle + attestation | P2로 상세 설계 | P1-6 | P1 | P0 sealing 직후 release 재현성을 닫는 데 필요하므로 P1로 올리는 것이 실무적으로 적절 |
| Source manifest vs full snapshot diff 자동 보고 | P1 | P1/P0 보조 | P1 | P0 archive profile이 먼저이며, diff report는 운영 편의 강화 |
| Release workflow live authority | P1 | P1 | P1 | checked-in JSON 의존성은 release safety 문제지만 P0 sealing 이후 처리하는 것이 순서상 안전 |
| Dashboard wording | P1 | P1 | P1 | 실제 release blocker는 아니나 operator decision quality에 중요 |

---

## 5. 실제 Evidence Artifact 상세 검증

### 5.1 Test execution summary

| artifact | 실제 값 | 판정 |
| --- | --- | --- |
| `test-execution-summary-full.json` suite | `full` | full-suite artifact 존재 |
| full represents_full_suite | `True` | 과거 “full-suite evidence 부재” 주장은 폐기 |
| full counts | `{"passed": 944, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "warnings": 0}` | `944 passed` 확인 |
| full returncode/duration | `0` / `203490` ms | pass 기록 존재 |
| full nodeid digest | `{"status": "skipped", "command": "", "nodeid_count": 0, "sha256": "", "reason": "no pytest selectors were resolved"}` | skipped 상태. P0-4 유효 |
| targeted suite | `report-contract-summary`, counts `{"passed": 135, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0, "xpassed": 0, "warnings": 0}` | report-contract-summary는 full suite가 아님 |
| targeted nodeid digest | status `collected`, nodeid_count `135` | targeted artifact는 nodeid digest가 collected |

추가 보정: full summary의 `source_command`는 `.venv/bin/python -m pytest`를 포함하지만, 압축본에는 `.venv/`가 없다. 따라서 full-suite 재현에는 lock/toolchain identity 또는 builder image attestation이 필요하다.

### 5.2 Release lane artifacts

| artifact | 실제 핵심값 | 판정 |
| --- | --- | --- |
| `release-closeout-summary.json` | `status=pass`, `clean_release_ready=True`, `machine_release_allowed=True`, `operator_release_allowed=True` | 내부 workspace evidence 기준 release clean |
| `release-clean-blocker-ledger.json` | summary `{"blocker_count": 0, "accepted_risk_family_count": 0, "accepted_risk_instance_count": 0, "clean_lane_blocking_family_count": 0, "learning_claim_blocking_family_count": 0, "advisory_lifecycle_family_count": 0, "clean_lane_status": "pass", "conditional_lane_status": "pass", "machine_release_status": "allowed", "operator_release_status": "allowed", "release_authority_status": "clean_pass", "learning_claim_guard_status": "pass", "learning_claim_allowed": false, "same_eval_reason_coverage_status": "none", "strict_secondary_improvement_coverage_status": "none", "behavior_delta_digest_coverage_status` | blocker 0, machine/operator allowed, release_authority clean_pass는 nested summary 기준 확인 |
| `release-evidence-dashboard.json` | summary `{"gate_count": 12, "authoritative_gate_count": 11, "checked_in_fail_count": 0, "live_rerun_fail_count": 0, "live_rerun_not_run_count": 0, "accepted_risk_count": 0, "gate_attention_count": 1, "required_input_fail_count": 0, "learning_claim_guard_status": "pass", "learning_claim_allowed": false, "same_eval_reason_coverage_status": "none", "strict_secondary_improvement_coverage_status": "none", "behavior_delta_digest_coverage_status": "none", "placeholder_audit_status": "pass"}` | dashboard status attention, gate_attention_count 1은 nested summary 기준 확인 |
| `release-closeout-batch-manifest.json` checked-in | distribution_package `{"status": "not_provided", "archive_profile": "local_workspace", "path": "", "sha256": "", "entry_count": 0, "file_count": 0, "directory_entry_count": 0, "uncompressed_size_bytes": 0, "root_prefix": "", "timestamp_semantics": "not_applicable", "timestamp_unique_count": 0, "timestamp_min": "", "timestamp_max": "", "source_manifest_file_count": 1422, "source_manifest_digest": "82bbf44036a384104e1990fde77c2ef02b887094ce398af0e54e91b0ca1b0047", "archive_manifest_digest": "", "path_set_matches_release_manifest": false, "content_digest_matches_release_manifest": false, "zip_only_path_count": 0, "manifest_only_path_count": 0, "zip_only_paths": [], "manifest_only_paths": [], "summary": "distribution` | `not_provided` 상태. P0-3 유효 |

### 5.3 External report manifest

| 필드 | checked-in 실제값 | 판정 |
| --- | --- | --- |
| `review_basis_zip` | `{"name": "LLMwiki.zip", "sha256": "0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93", "entry_count": 1819, "source": "reported"}` | 현재 ZIP과 불일치하는 과거 basis |
| `basis_zip` | `{"name": "LLMwiki.zip", "sha256": "0a547950871ebd749bf6523cbc1d1a33a58a793168f3b6514b26a8b796869c93", "entry_count": 1819, "source": "reported"}` | 동일하게 과거 basis |
| `current_distribution_zip` | `{"name": "", "sha256": "", "entry_count": null, "source": "unspecified"}` | 공란. P0-2 유효 |
| `excluded_file_count` | `53` | archive 제외 53개 확인 |
| `references` | `3` | active Markdown report 3개만 provenance 대상 |

직접 실행으로 확인한 보정 사항: `external_report_reference_manifest` 스크립트는 `--current-distribution-zip-path /mnt/data/LLMwiki(21).zip`를 받으면 current distribution을 계산한다. 따라서 “구현이 없음”이 아니라 “운영 target이 현재 ZIP을 필수 입력으로 결박하지 않음”이 정확한 문제 정의다.

```json

{
  "artifact_status": "current",
  "current_distribution_zip": {
    "name": "LLMwiki(21).zip",
    "sha256": "ca035e1125ce6ca4409e415ed0845bfdb6fe95396ac906079898aedbb82e1767",
    "entry_count": 1853,
    "source": "computed"
  },
  "excluded_file_count": 53,
  "note": "직접 실행한 external_report_reference_manifest에 --current-distribution-zip-path를 제공하면 current_distribution_zip가 계산됨. 다만 basis 값을 보존하려면 운영 target에서 basis/current 인자를 명시적으로 전달해야 함."
}

```

### 5.4 ZIP을 distribution package로 직접 바인딩한 batch manifest 관찰

`release_closeout_batch_manifest`에 실제 ZIP을 제공하면 임시 JSON은 생성되며, distribution package가 `drift`로 판정된다. 이는 full snapshot을 source package profile로 평가했기 때문에 발생하는 정상적인 profile mismatch다. 다만 명령 프로세스는 파일 생성 후에도 timeout으로 수렴하여 runner shutdown 문제를 재확인했다.

```json

{
  "status": "drift",
  "archive_profile": "source_content_package",
  "sha256": "ca035e1125ce6ca4409e415ed0845bfdb6fe95396ac906079898aedbb82e1767",
  "entry_count": 1853,
  "file_count": 1754,
  "directory_entry_count": 99,
  "uncompressed_size_bytes": 243780682,
  "timestamp_unique_count_file_only": 807,
  "path_set_matches_release_manifest": false,
  "content_digest_matches_release_manifest": false,
  "zip_only_path_count": 332,
  "manifest_only_path_count": 0,
  "note": "직접 실행에서 JSON 파일은 생성되었으나 wrapper/프로세스 종료가 timeout으로 수렴하여 runner shutdown 문제도 재확인됨."
}

```

### 5.5 Learning lane artifacts

| artifact | 실제 핵심값 | 판정 |
| --- | --- | --- |
| `learning-delta-scoreboard.json` | `status=pass`, summary `{"claims_learning_improved": false, "learning_claim_allowed": false, "telemetry_coverage_ratio": 0.75, "telemetry_coverage_status": "partial", "same_eval_run_count": 4, "same_eval_reason_coverage_ratio": 0.0, "same_eval_reason_coverage_status": "none", "strict_secondary_improvement_coverage_ratio": 0.0, "strict_secondary_improvement_coverage_status": "none", "behavior_delta_digest_coverage_ratio": 0.0, "behavior_delta_digest_coverage_status": "none", "placeholder_count": 0, "evidence_scope_count": 6}` | guardrail 정상 작동. `learning_claim_allowed=false` |
| `auto-improve-readiness.json` | `can_execute_trial=True`, `can_promote_result=False`, learning status `learning_uncertain` | trial 가능, promotion 차단 |
| readiness metrics | `{"attempts_considered": 9, "min_attempts_considered": 10, "session_reports_considered": 3, "session_calibration_status": "active", "telemetry_coverage_ratio": 1.0, "same_eval_run_count": 4, "same_eval_reason_code_coverage_ratio": 0.0, "strict_secondary_improvement_coverage_ratio": 0.0, "behavior_delta_digest_coverage_ratio": 0.0, "rework_count": 3, "hold_moving_average": 0.3333, "discard_moving_average": 0.2222, "defect_escape_pair_count": 3}` | same-eval run 4개이나 typed coverage 3종 0 |
| `learning-readiness-signoff-revalidation.json` | `status=attention`, revalidation `{"status": "due", "window_days": 7, "window_ends_at": "2026-05-13T12:09:11Z", "clean_closeout_required": true, "status_reason": "learning readiness signoff expires within the revalidation window; clean release evidence closeout is required before release or renewal; release effect: release_readiness_state=clean_pass; machine_release_allowed=True; operator_release_allowed=True; requires_accepted_risk_review=False"}` | signoff revalidation due, release effect는 clean_allowed |

보정: 신규 리뷰 A가 일반 telemetry coverage를 1.0으로 적은 것은 `auto-improve-readiness.json` metrics 기준으로는 맞다. 그러나 `learning-delta-scoreboard.json` summary에서는 `telemetry_coverage_ratio=0.75`, `telemetry_coverage_status=partial`이다. 앞으로 보고서에서는 artifact별 출처를 분리해야 한다.

---

## 6. 직접 수행한 검증

| 검증 | 결과 | 해석 |
| --- | --- | --- |
| ZIP inventory 계산 | PASS | SHA/entry/file/dir/prefix 분포가 두 신규 리뷰와 일치 |
| JSON parse | 315/315 PASS | JSON syntax debt 없음 |
| schema file count | 86 | 신규 리뷰의 86개 schema claim과 일치 |
| Python AST parse | 335/335 PASS | Python syntax-level debt 없음 |
| AST 기반 test function count | 944 | full-suite passed count 944와 정합 |
| `python -m compileall -q ops tests tools` | PASS | import 전 compile 수준 정상 |
| `pyproject.toml` project scripts | 55개 | 신규/기존 리뷰의 55개 console script claim과 일치 |
| `Makefile release-evidence-closeout` | learning-delta-scoreboard 포함 여부: `True` | 과거 “scoreboard 미연결” 주장은 폐기 |
| targeted pytest 직접 실행 | TIMEOUT | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`에서도 dots 출력 후 종료 지연. runner shutdown class로 분리 필요 |
| `external_report_reference_manifest` current ZIP 바인딩 | PASS | current distribution 계산 가능. 운영 target 보강 필요 |
| `release_closeout_batch_manifest` ZIP 바인딩 | PARTIAL/TIMEOUT | JSON은 생성되어 drift 확인. 프로세스 종료 timeout으로 P0-6 재확인 |

### 6.1 LOC 및 대형 파일 확인

`ops` Python LOC는 57,211, `tests` Python LOC는 44,412로 두 신규 리뷰의 수치와 일치한다. 상위 대형 파일은 다음과 같다.

| LOC | 파일 |
| ---: | --- |
| 1,967 | `tests/test_mechanism_review.py` |
| 1,791 | `ops/scripts/auto_improve_readiness_runtime.py` |
| 1,474 | `ops/scripts/release_closeout_summary.py` |
| 1,464 | `tests/test_mutation_proposal.py` |
| 1,461 | `ops/scripts/mutation_proposal_runtime.py` |
| 1,407 | `ops/scripts/artifact_freshness_runtime.py` |
| 1,365 | `ops/scripts/test_execution_summary.py` |
| 1,356 | `tests/test_auto_improve_readiness_runtime.py` |
| 1,332 | `tests/test_generated_report_contracts.py` |
| 1,301 | `tests/test_makefile_static_gates.py` |

---

## 7. 보정된 문제 정의

### 7.1 폐기해야 할 문제 정의

| 폐기/보정 대상 주장 | 이유 | 실제 상태 |
| --- | --- | --- |
| “full-suite evidence가 없다” | 현재는 `test-execution-summary-full.json` 존재 | `944 passed`, returncode 0 |
| “learning-delta-scoreboard가 release gate에 연결되지 않았다” | Makefile target에 포함됨 | `release-evidence-closeout` 내 반복 호출 확인 |
| “console script drift가 남아 있다” | pyproject scripts 55개 확인, 기존 리뷰의 direct fallback 대조와 모순 없음 | 추가 static drift 증거 없음 |
| “tmp 파일 오염이 있다” | ZIP에는 `tmp/` directory entry 1개뿐, 파일 없음 | empty dir semantics로 처리 |
| “현재 ZIP 자체가 오염 파일” | 사용자가 원본 저장소 압축본이라고 명시 | 문제는 포함 자체가 아니라 archive profile 미명시 |

### 7.2 계속 유효한 문제 정의

| 유효 문제 | 정확한 표현 | 우선순위 |
| --- | --- | --- |
| Archive profile 부재 | ZIP만 보고 full snapshot/source package/public mirror/review bundle인지 판단할 수 없음 | P0 |
| External manifest stale/current 공란 | active report provenance가 현재 ZIP SHA `ca035e...`에 결박되지 않음 | P0 |
| Release distribution sealing 미완성 | local workspace evidence clean과 distribution ZIP clean이 같은 claim으로 보임 | P0 |
| Full-suite forensic evidence 부족 | full suite pass는 존재하나 nodeid digest/log/shard policy가 부족 | P0 |
| Learning typed evidence 부족 | run은 있으나 same-eval reason/secondary improvement/behavior digest가 비어 promotion 차단 | P0 |
| Runner shutdown timeout | 테스트/manifest 명령이 본문 작업 후 종료되지 않는 별도 안정성 문제 | P0 |

---

## 8. 개선 방안 — 파일 단위 실행 계획

### P0-1. Archive profile 및 package profile schema 추가

**수정 대상 후보**

- `ops/schemas/archive-manifest.schema.json` 신규 추가
- `ops/scripts/archive_manifest.py` 또는 기존 packaging runtime 확장
- `Makefile`에 `archive-manifest`, `package-profile-check`, `full-snapshot-profile-check`, `source-package-profile-check` target 추가
- `ops/policies/wiki-maintainer-policy.yaml`에 profile별 include/exclude matrix 추가


**필수 필드**

```json

{
  "archive_profile": "full_repository_snapshot | source_content_package | public_code_mirror | release_evidence_bundle | review_bundle",
  "zip_sha256": "ca035e1125ce6ca4409e415ed0845bfdb6fe95396ac906079898aedbb82e1767",
  "entry_count": 1853,
  "file_count": 1754,
  "directory_entry_count": 99,
  "source_manifest_file_count": 1422,
  "zip_only_path_count": 332,
  "contains_raw": true,
  "contains_wiki": true,
  "contains_runs": true,
  "contains_external_reports": true,
  "contains_generated_evidence": true,
  "public_safe": false,
  "not_a_release_source_package": true
}

```

**DoD:** profile 없는 ZIP은 release/public consumer가 거부한다. full snapshot은 `public_safe=false`를 명시한다. source/public profile에서는 `.obsidian/`, `.vscode/`, `runs/`, `external-reports/`, `raw/`, `wiki/` 포함 여부를 fail-fast로 처리한다.

### P0-2. `external-reports/report-reference-manifest.json` current distribution 결박

**수정 대상 후보**

- `ops/scripts/external_report_reference_manifest.py`
- `ops/schemas/external-report-reference-manifest.schema.json`
- `Makefile`의 external report manifest 생성 target


**개선 내용**

1. release/review closeout mode에서는 `--current-distribution-zip-path`를 필수화한다.
2. `review_basis_zip`/`basis_zip`와 `current_distribution_zip`의 의미를 명확히 분리한다.
3. `basis_zip_matches_current_distribution=false` 및 `artifact_status=stale_basis` 또는 별도 warning field를 추가한다.
4. active references 3개와 archive excluded 53개를 top-level summary로 노출한다.

**DoD:** checked-in manifest만 읽어도 현재 ZIP SHA, entry count, active report count, archive excluded count, basis/current mismatch 여부가 보인다.

### P0-3. `release-closeout-batch-manifest` distribution sealing

**수정 대상 후보**

- `ops/scripts/release_closeout_batch_manifest.py`
- `ops/schemas/release-closeout-batch-manifest.schema.json`
- `Makefile`의 `release-closeout-batch-manifest-promote`, `release-closeout-batch-manifest-verify`


**개선 내용**

1. release claim mode와 local workspace diagnostic mode를 분리한다.
2. release claim mode에서 distribution ZIP이 없으면 `machine_release_status=not_sealed` 또는 `unknown`을 출력한다.
3. `distribution_package.status=not_provided`와 `release_authority_status=clean_pass`가 동시에 release claim으로 소비되지 않도록 schema/runtime/test를 보강한다.
4. ZIP hashing과 path digest 계산에 progress logging, content hash cache, bounded deadline을 추가한다.
5. `archive_profile`이 `source_content_package`인지 `full_repository_snapshot`인지에 따라 expected diff를 다르게 판정한다.

**DoD:** 현재 ZIP을 `full_repository_snapshot`으로 평가하면 expected 포함물로 인정하되 `public_safe=false`; `source_content_package`로 평가하면 332개 zip-only path가 fail로 드러난다.

### P0-4. Full-suite evidence hardening

**수정 대상 후보**

- `ops/scripts/test_execution_summary.py`
- `ops/schemas/test-execution-summary.schema.json`
- `tests/test_test_execution_summary.py` 및 report contract tests


**개선 내용**

1. selector가 없는 full suite에서도 `pytest --collect-only -q`를 실행한다.
2. `nodeid_count`와 `passed+skipped+xfailed` count consistency check를 추가한다.
3. full log, JUnit XML 또는 compressed stdout/stderr artifact를 evidence bundle에 포함한다.
4. shard를 쓰지 않는 정책이면 `sharding_policy=not_used`와 이유를 명시한다. 쓰는 정책이면 shard aggregate digest를 봉인한다.
5. `.venv` 미포함 package에서 재현 가능한 toolchain identity를 별도 artifact로 남긴다.

**DoD:** full summary에서 `pytest_collect_nodeid_digest.status=collected`, `nodeid_count≈944`, source command/toolchain/log digest가 함께 보인다.

### P0-5. Same-eval typed learning evidence 보강

**수정 대상 후보**

- run telemetry writer
- `ops/scripts/auto_improve_readiness_runtime.py`
- `ops/scripts/learning_delta_scoreboard.py`
- promotion gate 관련 runtime/test


**개선 내용**

1. `same_eval_reason_code` enum을 추가한다.
2. `strict_secondary_improvement_present`, `secondary_improvement_axes[]`, `behavior_delta_digest`를 run telemetry에 기록한다.
3. scoreboard/readiness/promotion gate가 같은 field와 blocker taxonomy를 소비하도록 한다.
4. legacy run은 backfill 가능 여부를 판정하고, 불가능하면 `legacy_unavailable` reason을 명시한다.
5. equal-score promotion은 strict secondary improvement evidence 없이는 차단한다.

**DoD:** typed coverage 3종이 0에서 상승하거나, legacy unavailable이 machine-readable하게 기록된다. `learning_claim_allowed=true`는 machine-check evidence 없이는 열리지 않는다.

### P0-6. Runner shutdown timeout 진단 lane 분리

**수정 대상 후보**

- `ops/scripts/command_runtime.py` 또는 pytest wrapper
- test execution summary producer
- subprocess-heavy tests


**개선 내용**

1. monotonic deadline과 process group kill을 추가한다.
2. timeout 시 process tree, stdout/stderr tail, last phase, thread/atexit hint를 diagnostic artifact로 남긴다.
3. test body pass 후 shutdown hang을 `runner_shutdown_timeout`으로 분류한다.
4. release blocker와 diagnostic timeout을 분리하되, release evidence 재현성에는 attention으로 표시한다.

**DoD:** dots 출력 후 hang 케이스가 정해진 시간 안에 wrapper 종료와 diagnostic JSON 생성을 보장한다.

---

## 9. P1/P2 개선 로드맵

### P1 — P0 봉합 직후 처리

| 항목 | 실행 내용 | 완료 조건 |
| --- | --- | --- |
| Evidence bundle + attestation | source ZIP, evidence ZIP, full snapshot, attestation JSON 분리 | attestation만으로 source/evidence/snapshot SHA와 claim state 재구성 가능 |
| Release workflow live authority | `.github/workflows/release.yml` publish job이 checked-in JSON이 아니라 live gate output을 신뢰 | live result SHA와 published artifact SHA가 provenance에 기록 |
| Dashboard wording | release claim, learning claim, signoff, sealed distribution status 분리 | `release_clean_but_learning_revalidation_due` 같은 명시 필드 제공 |
| Coverage denominator semantics | `full/partial/none/not_applicable/no_evidence` 분리 | denominator 0이 pass처럼 보이지 않음 |
| Source/full diff report | source manifest vs full snapshot diff 자동 요약 | prefix별 zip-only breakdown과 policy reason 출력 |
| External report lifecycle | archive/active/superseded 상태 관리 | 이전 권고가 반영/부분반영/무효화로 추적됨 |

### P2 — 구조 개선

| 항목 | 실행 내용 | 주의점 |
| --- | --- | --- |
| 대형 runtime/test 파일 분해 | collector → normalizer → classifier → scorer → writer → diagnostics | P0 sealing 전 대규모 refactor 금지 |
| 공통 artifact envelope/writer | currentness, source command, input fingerprint, distribution binding 공통화 | schema migration과 fixture regeneration을 같이 진행 |
| Package naming 분리 | `public export`, `source package`, `full snapshot`, `evidence bundle` target/file name 분리 | 운영자가 파일명만 보고 목적을 알 수 있어야 함 |
| Truth ladder 문서화 | live gate > same-fingerprint artifact > accepted risk > historical report > narrative review | UI/dashboard에서도 권위 차이를 보여야 함 |

---

## 10. 실행 순서 — 보정된 권장 Branch Plan

1. **Manifest Closure Hotfix**: `report-reference-manifest.json` current ZIP 결박, stale basis 표시, active/archive summary 추가.

2. **Distribution Sealing**: batch manifest release mode에서 distribution ZIP 필수화, not_sealed 상태 도입, profile-aware diff 판정.

3. **Archive Profile Schema**: full snapshot/source/public/evidence/review bundle include/exclude matrix와 `ARCHIVE-MANIFEST.json` 도입.

4. **Full-suite Forensic Evidence**: nodeid digest 수집, log/JUnit/compressed evidence, shard policy 명시.

5. **Runner Timeout Diagnostic**: command runtime deadline/process group kill/termination_reason 도입.

6. **Learning Typed Evidence**: same-eval typed fields, behavior delta digest, backfill/legacy unavailable 처리.

7. **Evidence Bundle + Attestation**: source/evidence/full snapshot 3종 artifact와 attestation JSON 생성.

8. **Release Workflow Authority**: live gate output을 publish authority로 사용.

9. **Runtime/Test Decomposition**: P0/P1 계약 봉합 후 대형 파일 점진 분해.

---

## 11. 두 신규 리뷰의 섹션 커버리지 확인

아래 목록은 두 신규 리뷰의 주요 heading을 직접 추출한 것이다. 본 보고서의 각 장은 이 heading들을 빠짐없이 반영하도록 구성했다.

<details>
<summary>신규 리뷰 A heading 목록</summary>


- LLMwiki 통합 개선 보고서
-   목차
-   1. 통합 개요 및 메타분석
-     1.1 세 리뷰의 성격과 위치
-     1.2 리뷰들이 공통으로 전제한 근본 명제
-   2. 검토 대상 기준 입력 확인
-     2.1 업로드 ZIP 기본 정보
-     2.2 디렉터리별 파일 분포
-     2.3 source manifest 대비 ZIP 차이 분석
-     2.4 active external reports 파일 목록
-   3. 세 리뷰의 핵심 합의 지점
-     3.1 현재 ZIP은 release source package가 아니라 full repository snapshot이다
-     3.2 release lane과 learning lane은 분리해서 읽어야 한다
-     3.3 distribution contract closure가 핵심 잔여 과제다
-     3.4 same-eval typed telemetry가 learning 차단의 핵심 원인이다
-   4. 이미 해소된 문제 — 더 이상 유효하지 않은 과거 주장
-   5. 현재 생성 evidence artifact 종합 상태
-     5.1 learning-delta-scoreboard의 정확한 해석
-     5.2 release-closeout-batch-manifest의 정확한 해석
-   6. 잔존 문제 종합 분석
-     6.1 P0 — 즉시 해결이 필요한 핵심 문제
-     6.2 P1 — 중요하나 P0 다음에 처리할 문제
-     6.3 P2 — 장기적으로 처리할 개선 사항
-   7. 우선순위별 개선 로드맵
-     Branch 1: Manifest Closure (즉시 실행)
-     Branch 2: Distribution Sealing (즉시 실행)
-     Branch 3: Archive Profile (즉시 실행)
-     Branch 4: Full-Suite Evidence Hardening
-     Branch 5: Learning Evidence
-     Branch 6: Release Workflow Live Authority
-     Branch 7: Runtime/Test Decomposition (장기)
-   8. 직접 수행한 검증 종합
-     8.1 성공한 검증
-     8.2 완료되지 않은 검증
-     8.3 검증 한계 명시
-   9. 리뷰 간 관점 차이 및 보완적 판단
-     9.1 Archive Profile 문제의 표현 차이
-     9.2 Full-Suite Evidence 평가의 미세 차이
-     9.3 Learning Readiness Signoff 문제
-   10. Definition of Done 통합
-     10.1 P0 완료 조건
-     10.2 P1 완료 조건
-     10.3 P2 완료 조건
-   11. 최종 판정
-     11.1 현재 저장소의 전반적 상태
-     11.2 가장 중요한 단 하나의 문장
-     11.3 권장 실행 우선순위 요약

</details>

<details>
<summary>신규 리뷰 B heading 목록</summary>


- LLMwiki 외부 보고서 통합 개선 보고서
-   1. 통합 결론 요약
-     1.1 세 보고서의 공통 핵심 판단
-     1.2 세 보고서의 상호 보완적 관점
-   2. ZIP 및 저장소 기본 정보 (세 보고서 공통 확인)
-     2.1 디렉터리별 파일 수 (공통)
-   3. 활성 외부 보고서 파일 확인 (공통)
-   4. 기존 보고서 주장의 현재 유효성 보정 (재구성 보고서 중심)
-     4.1 이미 해소된 문제 (세 보고서 모두 확인)
-     4.2 여전히 유효한 핵심 문제 (세 보고서 공통 지적)
-   5. 생성 Evidence Artifact 현재 상태 (공통 대조)
-     5.1 Release Lane vs Learning Lane 분리 현황
-   6. 직접 수행한 검증 결과 통합 (세 보고서 병합)
-   7. 주요 Gap 및 개선 방안 통합 (P0 중심)
-     P0-1. Archive Profile 명시 (세 보고서 공통 최우선)
-     P0-2. External Report Provenance 결박 (세 보고서 공통)
-     P0-3. Release Closeout Distribution Sealing (세 보고서 공통)
-     P0-4. Full-Suite Evidence 보강 (개선보고서, 감사보고서)
-     P0-5. Same-Eval Typed Learning Evidence (세 보고서 공통)
-     P0-6. Pytest/Runner Shutdown Timeout (개선보고서, 감사보고서)
-   8. P1 개선 방안 통합
-     P1-1. 대형 Runtime/Test 파일 분해 (개선보고서)
-     P1-2. Release Workflow Live Authority (개선보고서)
-     P1-3. Public/Private Boundary Regression Gate (개선보고서, 감사보고서)
-     P1-4. Dashboard Wording 개선 (감사보고서)
-     P1-5. Coverage Denominator Semantics 개선 (감사보고서)
-     P1-6. Evidence Bundle + Attestation 생성 (감사보고서, 재구성보고서)
-   9. P2 개선 방안 통합
-     P2-1. 대형 Runtime 점진 분해 (감사보고서)
-     P2-2. 공통 Artifact Envelope/Writer 강화 (감사보고서)
-     P2-3. Package Naming 분리 (재구성보고서)
-     P2-4. Historical External Reports Lifecycle (감사보고서)
-     P2-5. Truth Ladder 명확화 (재구성보고서)
-   10. 권장 실행 순서 (통합)
-     1단계: Archive Profile / Provenance Hotfix (P0-1, P0-2, P0-3)
-     2단계: Full-Suite Evidence Hardening (P0-4)
-     3단계: Runner Shutdown Timeout (P0-6)
-     4단계: Learning Evidence Backfill (P0-5)
-     5단계: Evidence Bundle / Attestation (P1-6)
-     6단계: Release Workflow Live Authority (P1-2)
-     7단계: Runtime/Test Decomposition (P1-1, P2-1)
-   11. Definition of Done (통합)
-     P0 완료 조건
-     P1 완료 조건
-     P2 완료 조건
-   12. 최종 통합 판정
-     12.1 현재 저장소의 성숙도 평가
-     12.2 핵심 메시지
-     12.3 권장 우선순위

</details>

---

## 12. 최종 판정

두 신규 리뷰는 **채택 가능**하다. 단, 그대로 복사해 실행 계획으로 쓰기보다 다음 보정과 함께 사용해야 한다.

- 신규 리뷰 A를 canonical meta-review로 삼고, 신규 리뷰 B를 operator-facing action plan으로 삼는다.

- `telemetry_coverage_ratio`와 release/dashboard 상태값은 artifact별 source와 nested 위치를 명시한다.

- “ZIP에 source manifest 밖 파일이 있다”는 말을 오염으로 단정하지 않는다. 현재 ZIP은 원본 저장소 snapshot이므로, 문제는 profile과 distribution contract의 부재다.

- P0의 첫 세 항목은 하나의 작업으로 묶어야 한다: archive profile → external report current ZIP provenance → batch manifest distribution sealing. 이 세 개가 닫혀야 release evidence가 portable claim이 된다.

- Learning lane은 release lane과 분리하여 유지한다. typed evidence가 채워지기 전까지 `learning_claim_allowed=false`는 올바른 상태다.


**최종 핵심 문장:** 현재 저장소는 기능 구현보다 artifact/evidence/package의 계약 경계를 봉인하는 일이 우선이며, 두 신규 리뷰와 기존 리뷰는 이 결론에서 실질적으로 일치한다.
