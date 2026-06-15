from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

ARTIFACT_ENVELOPE_PROPERTY_NAME = "urn:openai:artifact-envelope"


def semantic_goal_contract_payload(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Return the goal contract payload with report-envelope metadata removed."""
    payload = deepcopy(dict(contract))
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return payload

    properties = metadata.get("properties")
    if isinstance(properties, list):
        retained_properties = [
            item
            for item in properties
            if not (
                isinstance(item, Mapping)
                and str(item.get("name", "")).strip() == ARTIFACT_ENVELOPE_PROPERTY_NAME
            )
        ]
        if retained_properties:
            metadata["properties"] = retained_properties
        else:
            metadata.pop("properties", None)

    if not metadata:
        payload.pop("metadata", None)
    return payload


def semantic_goal_contract_digest(contract: Mapping[str, Any]) -> str:
    payload = semantic_goal_contract_payload(contract)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
