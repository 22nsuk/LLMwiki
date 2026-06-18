from __future__ import annotations

from copy import deepcopy

import hypothesis.strategies as st
from hypothesis import given, settings

from ops.scripts.eval.complexity_ratchet_runtime import (
    RatchetCeiling,
    current_warn_targets,
    judge_ratchet,
)

SAFE_PATH = st.from_regex(r"(?:ops|tests|tools)/[a-z0-9_./-]+\.py", fullmatch=True)


@st.composite
def target_reports(draw: st.DrawFn) -> dict[str, object]:
    path = draw(SAFE_PATH)
    over_budget_metrics = draw(
        st.one_of(
            st.just([]),
            st.lists(
                st.sampled_from(
                    [
                        "nonempty_line_count_total",
                        "python_function_count",
                        "python_branch_node_count",
                    ]
                ),
                unique=True,
                max_size=3,
            ),
        )
    )
    function_budget_candidate_count = draw(st.integers(min_value=0, max_value=3))
    return {
        "path": path,
        "over_budget_metrics": over_budget_metrics,
        "function_budget_candidate_count": function_budget_candidate_count,
    }


@st.composite
def budget_reports(draw: st.DrawFn) -> dict[str, object]:
    targets = draw(
        st.lists(target_reports(), min_size=0, max_size=8, unique_by=lambda item: item["path"])
    )
    return {"targets": targets}


@given(report=budget_reports())
@settings(max_examples=100)
def test_property_2_warn_target_classification_matches_budget_signals(report: dict[str, object]) -> None:
    """Feature: runtime-codehealth-hardening, Property 2: complexity-budget target은 over_budget_metrics가 비어있지 않거나 function_budget_candidate_count>=1일 때 그리고 오직 그때만 current_warn_targets에 포함된다"""
    observed = current_warn_targets(report)
    targets = report.get("targets")
    assert isinstance(targets, list)
    expected = {
        str(target.get("path", ""))
        for target in targets
        if isinstance(target, dict)
        and (
            target.get("over_budget_metrics")
            or int(target.get("function_budget_candidate_count", 0)) >= 1
        )
    }

    assert observed == expected


@given(
    ceiling_paths=st.sets(SAFE_PATH, min_size=0, max_size=8),
    report=budget_reports(),
)
@settings(max_examples=100)
def test_property_3_ratchet_judgement_splits_new_and_resolved_without_mutation(
    ceiling_paths: set[str],
    report: dict[str, object],
) -> None:
    """Feature: runtime-codehealth-hardening, Property 3: judge_ratchet은 ceiling에 없던 새 warn 또는 해소 후 재악화 target이 있으면 regression을 반환하고 해당 target을 식별하며, warn→pass 전환은 resolved로 보고되고 입력 report/ceiling을 mutate하지 않는다"""
    ceiling = RatchetCeiling(warn_targets=frozenset(ceiling_paths))
    report_before = deepcopy(report)
    ceiling_before = RatchetCeiling(
        warn_targets=frozenset(ceiling.warn_targets),
        resolved_targets=frozenset(ceiling.resolved_targets),
    )

    current = current_warn_targets(report)
    judgement = judge_ratchet(ceiling, report)

    assert report == report_before
    assert ceiling == ceiling_before
    assert judgement.new_warn_targets == tuple(sorted(current - ceiling.warn_targets))
    assert judgement.resolved_targets == tuple(sorted(ceiling.warn_targets - current))
    assert judgement.resurfaced_targets == ()
    expected_status = "regression" if judgement.new_warn_targets else "pass"
    assert judgement.status == expected_status


def test_judge_ratchet_marks_new_warn_targets_as_regression() -> None:
    ceiling = RatchetCeiling(
        warn_targets=frozenset({"ops/scripts/mechanism/auto_improve_runtime.py"}),
        resolved_targets=frozenset({"ops/scripts/release/release_closeout_summary.py"}),
    )
    report = {
        "targets": [
            {
                "path": "ops/scripts/mechanism/auto_improve_runtime.py",
                "over_budget_metrics": ["nonempty_line_count_total"],
                "function_budget_candidate_count": 0,
            },
            {
                "path": "ops/scripts/core/codex_exec_executor.py",
                "over_budget_metrics": [],
                "function_budget_candidate_count": 1,
            },
        ]
    }

    judgement = judge_ratchet(ceiling, report)

    assert judgement.status == "regression"
    assert judgement.new_warn_targets == ("ops/scripts/core/codex_exec_executor.py",)
    assert judgement.resurfaced_targets == ()
    assert judgement.resolved_targets == ()


def test_judge_ratchet_marks_resurfaced_targets_as_regression() -> None:
    ceiling = RatchetCeiling(
        warn_targets=frozenset({"ops/scripts/mechanism/auto_improve_runtime.py"}),
        resolved_targets=frozenset({"ops/scripts/release/release_closeout_summary.py"}),
    )
    report = {
        "targets": [
            {
                "path": "ops/scripts/release/release_closeout_summary.py",
                "over_budget_metrics": ["python_branch_node_count"],
                "function_budget_candidate_count": 0,
            }
        ]
    }

    judgement = judge_ratchet(ceiling, report)

    assert judgement.status == "regression"
    assert judgement.new_warn_targets == ()
    assert judgement.resurfaced_targets == (
        "ops/scripts/release/release_closeout_summary.py",
    )
    assert judgement.resolved_targets == ("ops/scripts/mechanism/auto_improve_runtime.py",)
