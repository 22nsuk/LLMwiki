from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.public

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "ops" / "runtime-decomposition-plan.md"


def _plan_text() -> str:
    return PLAN_PATH.read_text(encoding="utf-8")


def test_runtime_decomposition_plan_records_responsibility_split_contract() -> None:
    text = _plan_text()

    for phrase in (
        "## Responsibility Split Plan",
        "## Preservation And Delete-First Ledger",
        "### Pre-Split Golden Baseline",
        "tests/test_runtime_hotspot_facade_golden_outputs.py",
        "Loader",
        "Decision",
        "Renderer",
        "Promotion rule",
        "ops/scripts/mechanism/finalize_run.py",
        "finalize_run_runtime.py",
        "schema-backed report payloads",
        "No dead or duplicate implementation is intentionally preserved by this plan.",
    ):
        assert phrase in text


@pytest.mark.parametrize(
    ("relative_path", "facade_symbol"),
    (
        ("ops/scripts/mechanism/mutation_proposal_runtime.py", "def build_report("),
        ("ops/scripts/mechanism/auto_improve_runtime.py", "def run_auto_improve_session("),
        ("ops/scripts/release/release_evidence_dashboard.py", "def build_report("),
        ("ops/scripts/release/release_closeout_summary.py", "def build_report("),
        ("ops/scripts/mechanism/finalize_run.py", "def main("),
        ("ops/scripts/mechanism/finalize_run_runtime.py", "def finalize_run("),
    ),
)
def test_runtime_decomposition_plan_references_existing_facades(
    relative_path: str,
    facade_symbol: str,
) -> None:
    plan_text = _plan_text()
    source_path = REPO_ROOT / relative_path

    assert relative_path in plan_text
    assert source_path.is_file()
    assert facade_symbol in source_path.read_text(encoding="utf-8")
