from __future__ import annotations

import copy

import pytest
from ops.scripts.goal_contract_digest_runtime import semantic_goal_contract_digest

from tests.test_codex_goal_contract import sample_goal_contract

pytestmark = pytest.mark.public


def _with_artifact_envelope(contract: dict, value: str) -> dict:
    payload = copy.deepcopy(contract)
    metadata = payload.setdefault("metadata", {})
    metadata.setdefault("contract_family", "bounded_auto_improve")
    metadata.setdefault("properties", []).append(
        {
            "name": "urn:openai:artifact-envelope",
            "value": value,
        }
    )
    return payload


def test_semantic_goal_contract_digest_ignores_artifact_envelope_metadata() -> None:
    contract = sample_goal_contract()
    first = _with_artifact_envelope(contract, '{"generated_at":"2026-06-15T00:00:00Z"}')
    second = _with_artifact_envelope(contract, '{"generated_at":"2026-06-15T01:00:00Z"}')

    assert semantic_goal_contract_digest(first) == semantic_goal_contract_digest(second)


def test_semantic_goal_contract_digest_keeps_non_envelope_metadata() -> None:
    contract = sample_goal_contract()
    first = _with_artifact_envelope(contract, '{"generated_at":"2026-06-15T00:00:00Z"}')
    second = _with_artifact_envelope(contract, '{"generated_at":"2026-06-15T01:00:00Z"}')
    second["metadata"]["claim_policy"] = "stricter_claim_policy"

    assert semantic_goal_contract_digest(first) != semantic_goal_contract_digest(second)
