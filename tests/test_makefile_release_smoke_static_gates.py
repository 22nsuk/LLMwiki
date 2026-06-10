from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from tests.makefile_static_helpers import _makefile_text, _recipe_lines, _target_block

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

DOCS_RELEASE = Path("docs/release.md")


class MakefileReleaseSmokeStaticGateTests(unittest.TestCase):
    def test_release_smoke_targets_expose_fast_and_full_profiles(self) -> None:
        text = _makefile_text()

        self.assertIn("release-smoke-fast", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full-reuse", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-full-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-fast-current-check", _target_block(text, ".PHONY"))
        self.assertIn("release-smoke-fast-refresh-check", _target_block(text, ".PHONY"))
        self.assertIn(
            "RELEASE_SMOKE_OUT ?= ops/reports/release-smoke-report.json", text
        )
        self.assertIn(
            "RELEASE_SMOKE_FAST_OUT ?= ops/reports/release-smoke-report-fast.json",
            text,
        )
        self.assertIn(
            "RELEASE_SMOKE_ARCHIVE_OUT ?= build/release/release-smoke.zip",
            text,
        )
        self.assertIn(
            "RELEASE_SMOKE_FAST_ARCHIVE_OUT ?= build/release/release-smoke-fast.zip",
            text,
        )
        self.assertIn(
            "RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT ?= tmp/release-smoke-report-fast-current-check.json",
            text,
        )
        self.assertIn("RELEASE_SMOKE_REUSE_FROM ?= $(RELEASE_SMOKE_OUT)", text)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile full --archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_OUT)"',
            _target_block(text, "release-smoke"),
        )
        self.assertIn("release-smoke-full: release-smoke", text)
        reuse_block = _target_block(text, "release-smoke-full-reuse")
        self.assertIn('--archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)"', reuse_block)
        self.assertIn("--reuse-if-current", reuse_block)
        self.assertIn('--reuse-from "$(RELEASE_SMOKE_REUSE_FROM)"', reuse_block)
        current_check_block = _target_block(text, "release-smoke-full-current-check")
        self.assertIn('--archive-out "$(RELEASE_SMOKE_ARCHIVE_OUT)"', current_check_block)
        self.assertIn("--reuse-if-current", current_check_block)
        self.assertIn("--reuse-only", current_check_block)
        self.assertIn('--out "$(RELEASE_SMOKE_CURRENT_CHECK_OUT)"', current_check_block)
        self.assertIn(
            '$(PYTHON) -m ops.scripts.release.release_smoke --vault "$(VAULT)" --profile fast --archive-out "$(RELEASE_SMOKE_FAST_ARCHIVE_OUT)" --out "$(RELEASE_SMOKE_FAST_OUT)"',
            _target_block(text, "release-smoke-fast"),
        )
        fast_current_check_block = _target_block(text, "release-smoke-fast-current-check")
        self.assertIn('--archive-out "$(RELEASE_SMOKE_FAST_ARCHIVE_OUT)"', fast_current_check_block)
        self.assertIn("--reuse-if-current", fast_current_check_block)
        self.assertIn("--reuse-only", fast_current_check_block)
        self.assertIn('--reuse-from "$(RELEASE_SMOKE_FAST_OUT)"', fast_current_check_block)
        self.assertIn(
            '--out "$(RELEASE_SMOKE_FAST_CURRENT_CHECK_OUT)"',
            fast_current_check_block,
        )
        self.assertEqual(
            _recipe_lines(text, "release-smoke-fast-refresh-check"),
            [
                '@if $(MAKE) release-smoke-fast-current-check; then \\',
                'echo "fast release smoke evidence is current; reused $(RELEASE_SMOKE_FAST_OUT)"; \\',
                "else \\",
                "$(MAKE) release-smoke-fast; \\",
                "$(MAKE) release-smoke-fast-current-check; \\",
                "fi",
            ],
        )
        release_doc_text = DOCS_RELEASE.read_text(encoding="utf-8")
        self.assertIn(
            "developer/package precheck이며 canonical release evidence로 쓰지 않는다",
            release_doc_text,
        )
        self.assertIn(
            "canonical release evidence는 이 full 단일 report인 `ops/reports/release-smoke-report.json`이다",
            release_doc_text,
        )
