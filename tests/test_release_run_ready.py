from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.command_runtime import TimedProcessResult

from ops.scripts.release.release_run_ready import _command_step, _release_steps

pytestmark = pytest.mark.public


def test_release_run_ready_uses_source_package_check_for_stage2_evidence() -> None:
    assert _release_steps("make") == [
        ("release-test-current", ["make", "release-test-current"]),
        ("release-public-current", ["make", "release-public-current"]),
        ("release-smoke-full-reuse", ["make", "release-smoke-full-reuse"]),
        ("release-source-package-check", ["make", "release-source-package-check"]),
    ]


def test_command_step_records_reused_summary_mode_for_public_current(tmp_path: Path) -> None:
    vault = tmp_path

    with patch(
        "ops.scripts.release.release_run_ready.run_with_timeout",
        return_value=TimedProcessResult(
            args=["make", "release-public-current"],
            returncode=0,
            stdout="public check summary is current; reused ops/reports/public-check-summary.json",
            stderr="",
            timed_out=False,
            timeout_seconds=60,
            termination_reason="completed",
        ),
    ), patch(
        "ops.scripts.release.release_run_ready.release_source_tree_fingerprint",
        return_value="fp-current",
    ):
        step = _command_step(
            vault=vault,
            name="release-public-current",
            command=["make", "release-public-current"],
            expected_fingerprint="fp-current",
            timeout_seconds=60,
        )

    assert step["summary_mode"] == "reused"


def test_command_step_records_executed_summary_mode_for_mixed_source_package_step(tmp_path: Path) -> None:
    vault = tmp_path
    stdout = "\n".join(
        [
            "release distribution zip evidence is current; reused build/release/release-distribution-zip-smoke.json",
            "source package smoke evidence is current; reused build/source-package-smoke/source-package-smoke.json",
        ]
    )

    with patch(
        "ops.scripts.release.release_run_ready.run_with_timeout",
        return_value=TimedProcessResult(
            args=["make", "release-source-package-check"],
            returncode=0,
            stdout=stdout,
            stderr="",
            timed_out=False,
            timeout_seconds=60,
            termination_reason="completed",
        ),
    ), patch(
        "ops.scripts.release.release_run_ready.release_source_tree_fingerprint",
        return_value="fp-current",
    ):
        step = _command_step(
            vault=vault,
            name="release-source-package-check",
            command=["make", "release-source-package-check"],
            expected_fingerprint="fp-current",
            timeout_seconds=60,
        )

    assert step["summary_mode"] == "executed"
