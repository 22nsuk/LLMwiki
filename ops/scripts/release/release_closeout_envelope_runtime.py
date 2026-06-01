from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.schema_constants_runtime import RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH

FIXED_POINT_POLICY_PATH = "ops/policies/release-closeout-fixed-point.json"
LEARNING_SIGNOFF_PATH = "ops/reports/learning-readiness-signoff.json"
LEARNING_DELTA_SCOREBOARD_PATH = "ops/reports/learning-delta-scoreboard.json"
LEARNING_SIGNOFF_ARTIFACT_KIND = "learning_readiness_signoff"
PRODUCER = "ops.scripts.release_closeout_summary"
SOURCE_COMMAND_TEMPLATE = "python -m ops.scripts.release_closeout_summary --vault . --profile {profile}"


@dataclass(frozen=True)
class CloseoutEnvelopeInputs:
    vault: Path
    resolved_policy_path: Path
    profile: str
    source_specs: tuple[Any, ...]
    generated_at: str
    gates: Any
    learning_signoff: dict[str, Any]
    learning_claim_context: dict[str, Any]
    dependency_reproducibility: dict[str, Any]


def closeout_file_inputs(
    vault: Path,
    source_specs: tuple[Any, ...],
    dependency_reproducibility: dict[str, Any],
) -> dict[str, str]:
    file_inputs = {spec.name: spec.path for spec in source_specs}
    file_inputs["release_risk_taxonomy"] = "ops/policies/release-risk-taxonomy.json"
    for dependency_file in dependency_reproducibility["dependency_files"]:
        if dependency_file["exists"]:
            file_inputs[f"dependency::{dependency_file['path']}"] = str(
                dependency_file["path"]
            )
    if (vault / LEARNING_DELTA_SCOREBOARD_PATH).exists():
        file_inputs["learning_delta_scoreboard"] = LEARNING_DELTA_SCOREBOARD_PATH
    return file_inputs


def closeout_envelope(inputs: CloseoutEnvelopeInputs) -> dict[str, Any]:
    return build_canonical_report_envelope(
        inputs.vault,
        generated_at=inputs.generated_at,
        artifact_kind="release_closeout_summary",
        producer=PRODUCER,
        source_command=SOURCE_COMMAND_TEMPLATE.format(profile=inputs.profile),
        resolved_policy_path=inputs.resolved_policy_path,
        schema_path=RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH,
        source_paths=[
            "ops/scripts/release/release_closeout_summary.py",
            "ops/scripts/release/release_closeout_envelope_runtime.py",
            "ops/scripts/release/release_closeout_source_runtime.py",
            "ops/scripts/release/release_closeout_risk_runtime.py",
            "ops/scripts/release/release_closeout_render_runtime.py",
            "ops/scripts/release/release_dependency_reproducibility_runtime.py",
            "ops/scripts/release/release_freshness_gate_runtime.py",
        ],
        file_inputs=closeout_file_inputs(
            inputs.vault,
            inputs.source_specs,
            inputs.dependency_reproducibility,
        ),
        text_inputs={
            "profile": inputs.profile,
            "learning_signoff_path": LEARNING_SIGNOFF_PATH,
            "learning_signoff_status": str(inputs.learning_signoff["signoff_status"]),
            "learning_claim_context": (
                f"load_status={inputs.learning_claim_context['load_status']}; "
                f"claims_learning_improved={inputs.learning_claim_context['claims_learning_improved']}; "
                f"learning_claim_guard_status={inputs.learning_claim_context['learning_claim_guard_status']}"
            ),
            "test_failure_lane_count": str(len(inputs.gates.test_failure_lanes)),
        },
    )
