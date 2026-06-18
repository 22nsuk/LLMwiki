from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ops.scripts.core.gate_effect_vocabulary import GATE_EFFECT_BLOCKS_PROMOTION


@dataclass(frozen=True)
class RequirementSpec:
    passed: bool
    blocker_id: str
    source: str
    field_path: str
    observed: Any
    expected: str
    summary: str
    recommended_next_step: str
    gate_effect: str = GATE_EFFECT_BLOCKS_PROMOTION


def blocker_from_requirement(spec: RequirementSpec) -> dict[str, Any]:
    return {
        "id": spec.blocker_id,
        "source": spec.source,
        "field_path": spec.field_path,
        "observed": str(spec.observed),
        "expected": spec.expected,
        "gate_effect": spec.gate_effect,
        "summary": spec.summary,
        "recommended_next_step": spec.recommended_next_step,
    }


def append_requirement_blockers(
    blockers: list[dict[str, Any]],
    requirements: list[RequirementSpec],
) -> None:
    blockers.extend(
        blocker_from_requirement(requirement)
        for requirement in requirements
        if not requirement.passed
    )


def input_fingerprints(inputs: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {key: str(value["sha256"]) for key, value in inputs.items()}
