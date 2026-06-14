from __future__ import annotations

import json
import unittest

from ops.scripts.mechanism.auto_improve_readiness_loader_runtime import (
    load_readiness_report_payloads,
)
from tests.auto_improve_readiness_test_runtime import (
    AutoImproveReadinessRuntimeFixture,
)


class AutoImproveReadinessLoaderRuntimeTests(
    AutoImproveReadinessRuntimeFixture,
    unittest.TestCase,
):
    def test_loader_rejects_disk_report_without_artifact_envelope(self) -> None:
        self._write_ready_queue_reports()
        self._write_report(
            "ops/reports/outcome-metrics.json",
            {
                "summary": {
                    "attempts_considered": 12,
                    "recent_window": 20,
                    "recent_attempt_count": 12,
                    "session_reports_considered": 2,
                }
            },
            enveloped=False,
        )

        loaded = load_readiness_report_payloads(self.vault)

        self.assertFalse(loaded.reports_present)
        self.assertEqual(loaded.reports["outcome_metrics"], {})
        self.assertTrue(loaded.reports["mechanism_review"])
        self.assertTrue(loaded.reports["mutation_proposal"])

    def test_loader_accepts_injected_required_reports_without_disk_envelopes(self) -> None:
        loaded = load_readiness_report_payloads(
            self.vault,
            outcome_metrics_report={"summary": {"attempts_considered": 3}},
            mechanism_review_report={"summary": {"candidates_emitted": 1}},
            mutation_proposal_report={"proposals": [{"proposal_id": "proposal-ready"}]},
        )

        self.assertTrue(loaded.reports_present)
        self.assertEqual(
            loaded.reports["outcome_metrics"],
            {"summary": {"attempts_considered": 3}},
        )
        self.assertEqual(
            loaded.reports["mechanism_review"],
            {"summary": {"candidates_emitted": 1}},
        )
        self.assertEqual(
            loaded.reports["mutation_proposal"],
            {"proposals": [{"proposal_id": "proposal-ready"}]},
        )

    def test_loader_keeps_selected_contract_when_only_currentness_is_stale(self) -> None:
        selected_contract_path = self.vault / "ops" / "reports" / "test-execution-summary.json"
        payload = json.loads(selected_contract_path.read_text(encoding="utf-8"))
        payload["currentness"] = {"status": "stale"}
        selected_contract_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        loaded = load_readiness_report_payloads(
            self.vault,
            outcome_metrics_report={"summary": {"attempts_considered": 3}},
            mechanism_review_report={"summary": {"candidates_emitted": 1}},
            mutation_proposal_report={"proposals": [{"proposal_id": "proposal-ready"}]},
        )

        self.assertEqual(
            loaded.reports["selected_contract"].get("currentness"),
            {"status": "stale"},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
