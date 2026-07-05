from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path

import pytest

pytestmark = pytest.mark.subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]


class SyncDerivedConvergenceTests(unittest.TestCase):
    def test_sync_derived_does_not_change_git_status(self) -> None:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        before_status = _git_status_porcelain()

        completed = subprocess.run(
            ["make", "sync-derived", "PYTHON=.venv/bin/python"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                "make sync-derived failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            ),
        )
        self.assertEqual(_git_status_porcelain(), before_status)


def _git_status_porcelain() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if status.returncode != 0:
        raise AssertionError(status.stderr)
    return status.stdout
