from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings
from ops.scripts.uplift_promotion_runtime import (
    is_promotable,
    lint_promotion_order,
    type_promotion_order,
)

RULE_IDS = st.sampled_from(["B904", "I001", "SIM117", "UP006", "UP035"])
TYPE_FLAGS = st.sampled_from(
    [
        "check_untyped_defs",
        "disallow_incomplete_defs",
        "disallow_untyped_defs",
    ]
)


@st.composite
def rule_count_maps(draw: st.DrawFn) -> dict[str, int]:
    keys = draw(st.lists(RULE_IDS, min_size=1, max_size=5, unique=True))
    return {key: draw(st.integers(min_value=0, max_value=20)) for key in keys}


@st.composite
def type_count_maps(draw: st.DrawFn) -> dict[str, int]:
    keys = draw(st.lists(TYPE_FLAGS, min_size=1, max_size=3, unique=True))
    return {key: draw(st.integers(min_value=0, max_value=20)) for key in keys}


@given(plan_counts=rule_count_maps(), audit_counts=rule_count_maps())
@settings(max_examples=100)
def test_property_4_lint_promotion_order_sorts_by_remaining_violations(
    plan_counts: dict[str, int],
    audit_counts: dict[str, int],
) -> None:
    """Feature: runtime-codehealth-hardening, Property 4: lint_promotion_order의 결과는 잔여 위반 수 오름차순이며 위반 0건 rule이 항상 위반이 남은 rule보다 앞선다"""
    plan = {"remaining_violations": plan_counts}
    audit = {"ruff": {"rule_counts": audit_counts}}
    order = lint_promotion_order(plan, audit)

    combined = set(plan_counts) | set(audit_counts)
    assert order == sorted(
        combined,
        key=lambda rule: (
            max(plan_counts.get(rule, 0), audit_counts.get(rule, 0)),
            rule,
        ),
    )

    zero_rules = [
        rule
        for rule in order
        if max(plan_counts.get(rule, 0), audit_counts.get(rule, 0)) == 0
    ]
    nonzero_rules = [
        rule
        for rule in order
        if max(plan_counts.get(rule, 0), audit_counts.get(rule, 0)) > 0
    ]
    if zero_rules and nonzero_rules:
        assert max(order.index(rule) for rule in zero_rules) < min(
            order.index(rule) for rule in nonzero_rules
        )


def test_lint_promotion_order_does_not_treat_missing_audit_rule_as_zero_debt() -> None:
    plan = {"remaining_violations": {"B": 4, "I": 0}}
    audit: dict[str, object] = {"ruff": {"rule_counts": {}}}

    assert lint_promotion_order(plan, audit) == ["I", "B"]


def test_lint_promotion_order_aggregates_audit_rule_ids_for_family_debt() -> None:
    plan = {"remaining_violations": {"B": 0, "I": 0}}
    audit = {"ruff": {"rule_counts": {"B904": 2}}}

    assert lint_promotion_order(plan, audit).index("I") < lint_promotion_order(
        plan, audit
    ).index("B")


@given(remaining_violations=st.integers(min_value=0, max_value=1000))
@settings(max_examples=100)
def test_property_6_is_promotable_iff_remaining_violations_is_zero(
    remaining_violations: int,
) -> None:
    """Feature: runtime-codehealth-hardening, Property 6: 어떤 rule 또는 mypy 플래그의 enforced 승격은 잔여 위반/오류 수 n==0일 때 그리고 오직 그때만 허용된다(is_promotable(n)이 n==0과 동치)"""
    assert is_promotable(remaining_violations) is (remaining_violations == 0)


@given(plan_counts=type_count_maps())
@settings(max_examples=100)
def test_property_5_type_promotion_order_sorts_by_remaining_errors(
    plan_counts: dict[str, int],
) -> None:
    """Feature: runtime-codehealth-hardening, Property 5: type_promotion_order의 결과는 잔여 오류 수 오름차순이며 오류 0건 플래그/모듈이 항상 오류가 남은 것보다 앞선다"""
    plan = {"remaining_errors": plan_counts}
    audit = {"mypy": {"error_count": 0}}
    order = type_promotion_order(plan, audit)

    combined = {
        "check_untyped_defs",
        "disallow_untyped_defs",
        "disallow_incomplete_defs",
        *plan_counts,
    }
    expected = sorted(combined, key=lambda flag: (plan_counts.get(flag, 0), flag))
    assert order == expected

    zero_flags = [flag for flag in order if plan_counts.get(flag, 0) == 0]
    nonzero_flags = [flag for flag in order if plan_counts.get(flag, 0) > 0]
    if zero_flags and nonzero_flags:
        assert max(order.index(flag) for flag in zero_flags) < min(
            order.index(flag) for flag in nonzero_flags
        )
