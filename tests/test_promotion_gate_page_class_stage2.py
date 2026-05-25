from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops.scripts.policy_runtime import load_policy
from ops.scripts.promotion_gate import build_log, build_signoff, page_class_report

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "ops" / "policies" / "wiki-maintainer-policy.yaml"
POLICY_SCHEMA_PATH = REPO_ROOT / "ops" / "schemas" / "wiki-maintainer-policy.schema.json"
LIVE_POLICY_VERSION = load_policy(REPO_ROOT)[0]["version"]


class _Args:
    require_signoff = False
    signoff_status = None
    signoff_by = None
    signoff_ts = None
    log_recorded = False
    log_entry_ref = None
    log_summary = "stage2 page gate"


def seed_policy(vault: Path) -> None:
    (vault / "ops" / "policies").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "schemas").mkdir(parents=True, exist_ok=True)
    (vault / "ops" / "policies" / "wiki-maintainer-policy.yaml").write_text(
        POLICY_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (vault / "ops" / "schemas" / "wiki-maintainer-policy.schema.json").write_text(
        POLICY_SCHEMA_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def lint_report() -> dict:
    return {
        "$schema": "ops/schemas/lint-report.schema.json",
        "vault": ".",
        "generated_at": "2026-04-13T00:00:00Z",
        "artifact_kind": "wiki_lint_report",
        "producer": "tests.test_promotion_gate_page_class_stage2",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture"
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": "2026-04-13T00:00:00Z"
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": "pass",
        "errors": [],
        "warnings": [],
        "review_candidates": [],
        "stats": {
            "error_count": 0,
            "warning_count": 0,
            "review_candidate_count": 0,
        },
    }


def eval_report(page: str) -> dict:
    return {
        "$schema": "ops/schemas/eval-report.schema.json",
        "vault": ".",
        "generated_at": "2026-04-13T00:00:00Z",
        "artifact_kind": "wiki_eval_report",
        "producer": "tests.test_promotion_gate_page_class_stage2",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture"
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": "2026-04-13T00:00:00Z"
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": "pass",
        "max_score": 1,
        "total_score": 1,
        "pages": [
            {
                "page": page,
                "score": 1,
                "max_score": 1,
                "results": [],
            }
        ],
    }


def stage2_report(page: str, *, score: int, max_score: int, status: str = "pass") -> dict:
    pages = []
    if max_score:
        pages.append(
            {
                "page": page,
                "score": score,
                "max_score": max_score,
                "results": [
                    {
                        "eval": "seed_source_has_absorption_hint",
                        "pass": score == max_score,
                        "detail": {},
                    }
                ],
            }
        )
    return {
        "$schema": "ops/schemas/wiki-stage2-eval-report.schema.json",
        "vault": ".",
        "generated_at": "2026-04-13T00:00:00Z",
        "artifact_kind": "wiki_stage2_eval_report",
        "producer": "tests.test_promotion_gate_page_class_stage2",
        "source_command": "pytest",
        "source_revision": "unknown",
        "source_tree_fingerprint": "fixture",
        "input_fingerprints": {
            "policy": "fixture",
            "schema": "fixture",
            "artifact_envelope_schema": "fixture"
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": "2026-04-13T00:00:00Z"
        },
        "policy": {
            "path": "ops/policies/wiki-maintainer-policy.yaml",
            "version": LIVE_POLICY_VERSION,
        },
        "status": status,
        "max_score": max_score,
        "total_score": score,
        "pages": pages,
    }


class PromotionGatePageClassStage2Test(unittest.TestCase):
    def test_page_class_discards_when_applicable_stage2_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            target = vault / "wiki" / "source--seed.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# source--seed\n", encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault, None)
            signoff = build_signoff(policy, "wiki_source", _Args())
            log = build_log(policy, _Args())

            with patch("ops.scripts.promotion_gate.lint_wiki", return_value=lint_report()), patch(
                "ops.scripts.promotion_gate.evaluate_wiki",
                return_value=eval_report("wiki/source--seed.md"),
            ), patch(
                "ops.scripts.promotion_gate.evaluate_stage2",
                return_value=stage2_report("wiki/source--seed.md", score=0, max_score=1, status="fail"),
            ):
                report = page_class_report(
                    vault,
                    "run-page-stage2",
                    None,
                    policy,
                    resolved_policy_path,
                    "wiki_source",
                    ["wiki/source--seed.md"],
                    [],
                    signoff,
                    log,
                )

            self.assertEqual(report["decision"], "DISCARD")
            check = next(check for check in report["checks"] if check["id"] == "primary_target_stage2_full_pass")
            self.assertEqual(check["status"], "FAIL")
            self.assertEqual(
                report["decision_record"]["reason_detail"],
                (
                    "Page primary Stage 2 full-pass gate emitted FAIL: "
                    "primary_target_stage2_full_pass=FAIL: targets without full Stage 2 eval score: "
                    "wiki/source--seed.md"
                ),
            )
            self.assertEqual(report["inputs"]["current_stage2"]["status"], "fail")

    def test_page_class_promotes_when_no_stage2_checks_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_policy(vault)
            target = vault / "wiki" / "concept--plain.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# concept--plain\n", encoding="utf-8")

            policy, resolved_policy_path = load_policy(vault, None)
            signoff = build_signoff(policy, "wiki_concept", _Args())
            log = build_log(policy, _Args())

            with patch("ops.scripts.promotion_gate.lint_wiki", return_value=lint_report()), patch(
                "ops.scripts.promotion_gate.evaluate_wiki",
                return_value=eval_report("wiki/concept--plain.md"),
            ), patch(
                "ops.scripts.promotion_gate.evaluate_stage2",
                return_value=stage2_report("wiki/concept--plain.md", score=0, max_score=0, status="pass"),
            ):
                report = page_class_report(
                    vault,
                    "run-page-stage2",
                    None,
                    policy,
                    resolved_policy_path,
                    "wiki_concept",
                    ["wiki/concept--plain.md"],
                    [],
                    signoff,
                    log,
                )

            self.assertEqual(report["decision"], "PROMOTE")
            check = next(check for check in report["checks"] if check["id"] == "primary_target_stage2_full_pass")
            self.assertEqual(check["status"], "PASS")
            self.assertIn("no Stage 2 checks applied", check["detail"])


if __name__ == "__main__":
    unittest.main()
