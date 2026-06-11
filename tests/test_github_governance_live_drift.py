from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext

from ops.scripts.release.github_governance_live_drift import build_report, write_report
from tests.minimal_vault_runtime import seed_minimal_vault


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 6, 9, 12, 0, tzinfo=dt.UTC),
    )


class GitHubGovernanceLiveDriftTests(unittest.TestCase):
    def _seed_governance_contract(self, vault: Path) -> None:
        path = vault / ".github" / "release-governance.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    "version: 1",
                    "publication_target:",
                    "  protected_branches:",
                    "    - main",
                    "required_status_checks:",
                    "  ci_matrix:",
                    "    python_versions:",
                    '      - "3.12"',
                    "    tiers:",
                    "      - fast",
                    "  singleton_checks:",
                    '    - "dependency review"',
                    "branch_protection:",
                    "  require_pull_request: true",
                    "  require_review_before_merge: true",
                    "  require_required_status_checks: true",
                    "  require_branches_up_to_date: true",
                    "  require_linear_history: true",
                    "  allow_force_pushes: false",
                    "  allow_deletions: false",
                    "  main_direct_push: forbidden",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def _seed_live_input(self, vault: Path, payload: dict[str, object]) -> Path:
        path = vault / "tmp" / "github-live.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def test_build_report_passes_from_sanitized_live_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            self._seed_governance_contract(vault)
            live_input = self._seed_live_input(
                vault,
                {
                    "protected_branches": ["main"],
                    "required_status_checks": [
                        "dependency review",
                        "fast / py3.12",
                    ],
                    "branch_protection": {
                        "main": {
                            "require_pull_request": True,
                            "require_review_before_merge": True,
                            "require_required_status_checks": True,
                            "require_branches_up_to_date": True,
                            "require_linear_history": True,
                            "allow_force_pushes": False,
                            "allow_deletions": False,
                            "main_direct_push": "forbidden",
                        }
                    },
                    "raw_ruleset_payload": {
                        "token": "SECRET_TOKEN_SHOULD_NOT_LEAK"
                    },
                },
            )

            report = build_report(vault, live_input=live_input, context=fixed_context())
            destination = write_report(vault, report, "ops/reports/github-governance-live-drift.json")
            persisted_text = destination.read_text(encoding="utf-8")
            persisted = json.loads(persisted_text)

            self.assertEqual(persisted["status"], "pass")
            self.assertEqual(persisted["summary"]["missing_required_check_count"], 0)
            self.assertEqual(persisted["summary"]["mismatched_branch_protection_count"], 0)
            self.assertFalse(persisted["redaction"]["raw_live_payload_retained"])
            self.assertNotIn("SECRET_TOKEN_SHOULD_NOT_LEAK", persisted_text)

    def test_build_report_honors_ci_matrix_excludes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            path = vault / ".github" / "release-governance.yml"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(
                    [
                        "version: 1",
                        "publication_target:",
                        "  protected_branches:",
                        "    - main",
                        "required_status_checks:",
                        "  ci_matrix:",
                        "    python_versions:",
                        '      - "3.12"',
                        '      - "3.13"',
                        "    tiers:",
                        "      - fast",
                        "      - slow",
                        "    exclude:",
                        "      - tier: slow",
                        '        python-version: "3.13"',
                        "  singleton_checks:",
                        '    - "dependency review"',
                        "branch_protection:",
                        "  require_pull_request: true",
                        "  require_review_before_merge: true",
                        "  require_required_status_checks: true",
                        "  require_branches_up_to_date: true",
                        "  require_linear_history: true",
                        "  allow_force_pushes: false",
                        "  allow_deletions: false",
                        "  main_direct_push: forbidden",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            live_input = self._seed_live_input(
                vault,
                {
                    "protected_branches": ["main"],
                    "required_status_checks": [
                        "dependency review",
                        "fast / py3.12",
                        "fast / py3.13",
                        "slow / py3.12",
                    ],
                    "branch_protection": {
                        "main": {
                            "require_pull_request": True,
                            "require_review_before_merge": True,
                            "require_required_status_checks": True,
                            "require_branches_up_to_date": True,
                            "require_linear_history": True,
                            "allow_force_pushes": False,
                            "allow_deletions": False,
                            "main_direct_push": "forbidden",
                        }
                    },
                },
            )

            report = build_report(vault, live_input=live_input, context=fixed_context())

            self.assertEqual(report["status"], "pass")
            self.assertNotIn("slow / py3.13", report["required_status_checks"]["expected"])

    def test_build_report_fails_on_missing_check_and_branch_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            self._seed_governance_contract(vault)
            live_input = self._seed_live_input(
                vault,
                {
                    "protected_branches": ["main"],
                    "required_status_checks": ["fast / py3.12"],
                    "branch_protection": {
                        "main": {
                            "require_pull_request": True,
                            "require_review_before_merge": False,
                            "require_required_status_checks": True,
                            "require_branches_up_to_date": True,
                            "require_linear_history": True,
                            "allow_force_pushes": False,
                            "allow_deletions": False,
                            "main_direct_push": "forbidden",
                        }
                    },
                },
            )

            report = build_report(vault, live_input=live_input, context=fixed_context())

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["required_status_checks"]["missing"], ["dependency review"])
            self.assertEqual(
                report["branch_protection"][0]["mismatched_fields"],
                ["require_review_before_merge"],
            )

    def test_build_report_marks_missing_live_input_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            self._seed_governance_contract(vault)

            report = build_report(vault, live_input="tmp/missing-live.json", context=fixed_context())

            self.assertEqual(report["status"], "attention")
            self.assertEqual(report["unavailable_reasons"], ["live_input_missing"])
            self.assertFalse(report["live_input"]["available"])


if __name__ == "__main__":
    unittest.main()
