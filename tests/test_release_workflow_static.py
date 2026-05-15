from __future__ import annotations

import unittest
from pathlib import Path


RELEASE_WORKFLOW = Path(".github/workflows/release.yml")


class ReleaseWorkflowStaticTests(unittest.TestCase):
    def test_release_workflow_enables_trusted_publishing_and_attestations(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("name: Release", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("upload_post_check_finalizer_artifact:", text)
        self.assertIn("types:", text)
        self.assertIn("published", text)
        self.assertIn("id-token: write", text)
        self.assertIn("attestations: write", text)
        self.assertIn("actions/attest-build-provenance@v2", text)
        self.assertIn("pypa/gh-action-pypi-publish@release/v1", text)
        self.assertIn("make openvex-draft-cached", text)
        self.assertIn("make supply-chain-benchmark", text)
        self.assertIn("REVIEW_ARCHIVE_PROFILE: clean", text)
        self.assertEqual(text.count("            uv.lock"), 2)
        self.assertEqual(text.count("uses: astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b"), 2)
        self.assertEqual(
            text.count("uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt"),
            2,
        )
        self.assertEqual(text.count("python -m pip install -r tmp/locked-requirements.ci.txt"), 2)
        self.assertNotIn("python -m pip install -r requirements-dev.txt build", text)

    def test_publish_consumes_verify_job_live_release_artifacts(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            "make release-distribution-zip RELEASE_DISTRIBUTION_ZIP_OUT=build/release/live-source.zip",
            text,
        )
        self.assertIn(
            "make external-report-reference-manifest-release-check EXTERNAL_REPORT_CURRENT_DISTRIBUTION_ZIP_PATH=build/release/live-source.zip",
            text,
        )
        self.assertIn(
            "make release-provenance-clean RELEASE_CLOSEOUT_DISTRIBUTION_ZIP=build/release/live-source.zip RELEASE_CLOSEOUT_BATCH_MANIFEST_ZIP_METADATA=build/release/live-source.zip",
            text,
        )
        self.assertIn("make release-closeout-post-check-finalizer-ci-artifact", text)
        self.assertIn("name: post-check-finalizer-diagnostics", text)
        self.assertIn("tmp/release-closeout-post-check-finalizer.json", text)
        self.assertIn(
            "tmp/release-closeout-post-check-finalizer-recommended-targets.txt", text
        )
        self.assertIn("tmp/release-closeout-post-check-finalizer-plan.json", text)
        self.assertIn(
            "make release-post-seal-attestation RELEASE_POST_SEAL_ATTESTATION_SOURCE_ZIP=build/release/live-source.zip",
            text,
        )
        self.assertIn("make release-audit-pack RELEASE_AUDIT_PACK_OUT=tmp/release-evidence-bundle.zip", text)
        self.assertIn("ops.scripts.release.release_live_artifact_attestation build", text)
        self.assertIn("ops.scripts.release.release_live_artifact_attestation verify", text)
        self.assertIn("Verify live release authority", text)
        self.assertIn("--source-zip-path \"$SOURCE_ZIP\"", text)
        self.assertIn("--evidence-bundle-path \"$EVIDENCE_BUNDLE\"", text)
        self.assertIn("--batch-manifest-path \"$BATCH_MANIFEST\"", text)
        self.assertIn("--self-check-path \"$SELF_CHECK\"", text)
        self.assertIn("build/release/release-post-seal-attestation.json", text)
        self.assertIn("ops/reports/release-closeout-finality-attestation.json", text)
        self.assertIn("name: verified-source-zip", text)
        self.assertIn("name: verified-evidence-bundle", text)
        self.assertIn("name: verified-release-attestation", text)
        self.assertIn("build/release/live-source.zip", text)
        self.assertNotIn("tmp/live-review-archive-report.json", text)
        self.assertNotIn("ops/reports/review-archive-report.json", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn("tmp/live-release/source", text)
        self.assertIn("tmp/live-release/evidence", text)
        self.assertIn("tmp/live-release/attestation", text)
        self.assertNotIn("json.load(open('ops/reports/release-closeout-summary.json'))", text)


if __name__ == "__main__":
    unittest.main()
