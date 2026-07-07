from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from tests.makefile_static_helpers import (
    MakeTargetContract,
    _assert_assignment_values,
    _assert_make_target_contracts,
    _assert_text_contains_tokens,
    _makefile_text,
)

pytestmark = [
    pytest.mark.public,
    pytest.mark.report_contract,
    pytest.mark.report_contract_core,
    pytest.mark.schema_static_smoke,
]

DOCS_RELEASE = Path("docs/release.md")

_RELEASE_SMOKE_ASSIGNMENTS = (
    ("RELEASE_SMOKE_OUT", "ops/reports/release-smoke-report.json"),
    ("RELEASE_SMOKE_FAST_OUT", "ops/reports/release-smoke-report-fast.json"),
    ("RELEASE_SMOKE_ARCHIVE_OUT", "build/release/release-smoke.zip"),
    ("RELEASE_SMOKE_FAST_ARCHIVE_OUT", "build/release/release-smoke-fast.zip"),
    (
        "RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT",
        "tmp/release-smoke-report-fast-current-check.json",
    ),
    ("RELEASE_SMOKE_REUSE_FROM", "$(RELEASE_SMOKE_OUT)"),
)

_RELEASE_SMOKE_TARGET_CONTRACTS = (
    MakeTargetContract(
        "release-smoke",
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile full --archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-smoke-full",
        phony=True,
        required_tokens=("release-smoke-full: release-smoke",),
    ),
    MakeTargetContract(
        "release-smoke-full-reuse",
        phony=True,
        required_tokens=(
            '--archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)"',
            "--reuse-if-current",
            '--reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"',
        ),
    ),
    MakeTargetContract(
        "release-smoke-full-current-check",
        phony=True,
        required_tokens=(
            '--archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)"',
            "--reuse-if-current",
            "--reuse-only",
            '--out "$(RELEASE_SMOKE_CURRENT_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-smoke-fast",
        phony=True,
        required_tokens=(
            '$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_SMOKE_FAST_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_FAST_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-smoke-fast-current-check",
        phony=True,
        required_tokens=(
            '--archive-out "$(RELEASE_SMOKE_FAST_ARCHIVE_OUT)"',
            "--reuse-if-current",
            "--reuse-only",
            '--reuse-from "$(RELEASE_SMOKE_FAST_OUT)"',
            '--out "$(RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT)"',
        ),
    ),
    MakeTargetContract(
        "release-smoke-fast-refresh-check",
        phony=True,
        exact_recipe=(
            '@if $(MAKE) release-smoke-fast-current-check; then \\',
            'echo "fast release smoke evidence is current; reused $(RELEASE_SMOKE_FAST_OUT)"; \\',
            "else \\",
            "$(MAKE) release-smoke-fast; \\",
            "$(MAKE) release-smoke-fast-current-check; \\",
            "fi",
        ),
    ),
)

_RELEASE_SMOKE_DOC_TOKENS = (
    "`make release-smoke-fast`",
    "`make release-smoke`",
    "ops/reports/release-smoke-report.json",
)


class MakefileReleaseSmokeStaticGateTests(unittest.TestCase):
    def test_release_smoke_targets_expose_fast_and_full_profiles(self) -> None:
        text = _makefile_text()

        _assert_assignment_values(self, text, _RELEASE_SMOKE_ASSIGNMENTS)
        _assert_make_target_contracts(self, text, _RELEASE_SMOKE_TARGET_CONTRACTS)

        release_doc_text = DOCS_RELEASE.read_text(encoding="utf-8")
        _assert_text_contains_tokens(
            self,
            release_doc_text,
            _RELEASE_SMOKE_DOC_TOKENS,
            surface="docs/release.md",
        )
