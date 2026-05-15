from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateRuleSpec:
    rule_id: str
    candidate_type: str
    applies: Callable[[Any], bool]
    build_candidate: Callable[[Any], dict]


def evaluate_candidate_rules(
    contexts: Iterable[Any],
    rules: Iterable[CandidateRuleSpec],
) -> list[dict]:
    candidates: list[dict] = []
    ordered_rules = list(rules)
    for context in contexts:
        for rule in ordered_rules:
            if not rule.applies(context):
                continue
            candidate = rule.build_candidate(context)
            if candidate.get("type") != rule.candidate_type:
                raise ValueError(
                    f"candidate rule '{rule.rule_id}' emitted unexpected type: "
                    f"{candidate.get('type')}"
                )
            candidates.append(candidate)
    return candidates


__all__ = [
    "CandidateRuleSpec",
    "evaluate_candidate_rules",
]
