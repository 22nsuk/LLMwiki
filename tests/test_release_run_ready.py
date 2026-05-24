from __future__ import annotations

import pytest

from ops.scripts.release.release_run_ready import _release_steps

pytestmark = pytest.mark.public


def test_release_run_ready_uses_source_package_check_for_stage2_evidence() -> None:
    assert _release_steps("make") == [
        ("release-test-current", ["make", "release-test-current"]),
        ("release-public-current", ["make", "release-public-current"]),
        ("release-source-package-check", ["make", "release-source-package-check"]),
    ]

