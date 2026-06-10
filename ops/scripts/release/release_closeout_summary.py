#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from ops.scripts.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.learning_readiness_vocabulary import (
    LEARNING_REVIEW_REQUIRED_BLOCKER_ID,
)
from ops.scripts.output_runtime import display_path
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH

from . import (
    release_closeout_envelope_runtime,
    release_closeout_gate_runtime,
    release_closeout_render_runtime,
    release_closeout_risk_runtime,
    release_closeout_source_runtime,
)

DEFAULT_OUT = release_closeout_envelope_runtime.DEFAULT_OUT
FIXED_POINT_POLICY_PATH = release_closeout_envelope_runtime.FIXED_POINT_POLICY_PATH
LEARNING_SIGNOFF_PATH = release_closeout_envelope_runtime.LEARNING_SIGNOFF_PATH
LEARNING_DELTA_SCOREBOARD_PATH = release_closeout_envelope_runtime.LEARNING_DELTA_SCOREBOARD_PATH
LEARNING_SIGNOFF_ARTIFACT_KIND = release_closeout_envelope_runtime.LEARNING_SIGNOFF_ARTIFACT_KIND
PRODUCER = release_closeout_envelope_runtime.PRODUCER
SOURCE_COMMAND_TEMPLATE = release_closeout_envelope_runtime.SOURCE_COMMAND_TEMPLATE
CloseoutEnvelopeInputs = release_closeout_envelope_runtime.CloseoutEnvelopeInputs
CloseoutLoadedSources = release_closeout_envelope_runtime.CloseoutLoadedSources
CloseoutPreparedState = release_closeout_envelope_runtime.CloseoutPreparedState
CloseoutRenderInputs = release_closeout_envelope_runtime.CloseoutRenderInputs
_closeout_envelope = release_closeout_envelope_runtime.closeout_envelope
_load_closeout_sources = release_closeout_envelope_runtime.load_closeout_sources
_prepare_closeout_state = release_closeout_envelope_runtime.prepare_closeout_state
_closeout_render_inputs = release_closeout_envelope_runtime.closeout_render_inputs

LEARNING_REVIEW_BLOCKER_ID = LEARNING_REVIEW_REQUIRED_BLOCKER_ID
RELEASE_STATE_CLEAN_PASS = release_closeout_gate_runtime.RELEASE_STATE_CLEAN_PASS
RELEASE_STATE_CONDITIONAL_PASS = release_closeout_gate_runtime.RELEASE_STATE_CONDITIONAL_PASS
RELEASE_STATE_BLOCKED = release_closeout_gate_runtime.RELEASE_STATE_BLOCKED
RELEASE_STATE_UNKNOWN = release_closeout_gate_runtime.RELEASE_STATE_UNKNOWN
RELEASE_READINESS_STATES = release_closeout_gate_runtime.RELEASE_READINESS_STATES
ComponentInput = release_closeout_gate_runtime.ComponentInput
CloseoutComponentCollection = release_closeout_gate_runtime.CloseoutComponentCollection
CloseoutGates = release_closeout_gate_runtime.CloseoutGates
CloseoutRiskState = release_closeout_gate_runtime.CloseoutRiskState
CloseoutReadinessState = release_closeout_gate_runtime.CloseoutReadinessState
_artifact_freshness_gate = release_closeout_gate_runtime.artifact_freshness_gate
_closeout_gates = release_closeout_gate_runtime.closeout_gates

POLICY_ACCEPTED_RISK_METADATA = release_closeout_risk_runtime.POLICY_ACCEPTED_RISK_METADATA
POLICY_RISK_ACCEPTANCE_DAYS = release_closeout_risk_runtime.POLICY_RISK_ACCEPTANCE_DAYS
POLICY_RISK_ACCEPTED_BY = release_closeout_risk_runtime.POLICY_RISK_ACCEPTED_BY
TAXONOMY_COVERAGE_BLOCKER_ID = release_closeout_risk_runtime.TAXONOMY_COVERAGE_BLOCKER_ID
_accepted_risk_count_by_scope = release_closeout_risk_runtime.accepted_risk_count_by_scope
_annotated_blocks_source_clean_lane = release_closeout_risk_runtime.annotated_blocks_source_clean_lane
_blocks_source_clean_lane = release_closeout_risk_runtime.blocks_source_clean_lane
_finalize_accepted_risks = release_closeout_risk_runtime.finalize_accepted_risks
_issue = release_closeout_risk_runtime.release_closeout_issue
_policy_risk_acceptance = release_closeout_risk_runtime.policy_risk_acceptance
_risk_acceptance_is_active = release_closeout_risk_runtime.risk_acceptance_is_active
_risk_delta = release_closeout_risk_runtime.risk_delta
_taxonomy_coverage_blockers = release_closeout_risk_runtime.taxonomy_coverage_blockers

CloseoutStatusDecision = release_closeout_render_runtime.CloseoutStatusDecision
_closeout_snapshot_phase = release_closeout_render_runtime.closeout_snapshot_phase
_closeout_status_decision = release_closeout_render_runtime.closeout_status_decision
_closeout_summary_payload = release_closeout_render_runtime.closeout_summary_payload
_render_closeout_report = release_closeout_render_runtime.render_closeout_report
_status_semantics = release_closeout_render_runtime.status_semantics
_summary_batch_integrity_status = release_closeout_render_runtime.summary_batch_integrity_status
_summary_distribution_package_placeholder = (
    release_closeout_render_runtime.summary_distribution_package_placeholder
)

BASE_PROFILE = release_closeout_source_runtime.BASE_PROFILE
PROVENANCE_PROFILE = release_closeout_source_runtime.PROVENANCE_PROFILE
SBOM_PROFILE = release_closeout_source_runtime.SBOM_PROFILE
VALID_PROFILES = release_closeout_source_runtime.VALID_PROFILES
SourceSpec = release_closeout_source_runtime.SourceSpec
BASE_SOURCE_SPECS = release_closeout_source_runtime.BASE_SOURCE_SPECS
PROVENANCE_SOURCE_SPECS = release_closeout_source_runtime.PROVENANCE_SOURCE_SPECS
SBOM_SOURCE_SPECS = release_closeout_source_runtime.SBOM_SOURCE_SPECS
SOURCE_SPECS_BY_PROFILE = release_closeout_source_runtime.SOURCE_SPECS_BY_PROFILE
SOURCE_SPECS = release_closeout_source_runtime.SOURCE_SPECS
source_specs_for_profile = release_closeout_source_runtime.source_specs_for_profile
_load_source = release_closeout_source_runtime.load_closeout_source


def build_report(
    vault: Path,
    *,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
    profile: str = BASE_PROFILE,
) -> dict[str, Any]:
    loaded = _load_closeout_sources(
        vault,
        policy_path=policy_path,
        context=context,
        profile=profile,
    )
    prepared = _prepare_closeout_state(loaded)
    return _render_closeout_report(_closeout_render_inputs(loaded, prepared))


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=RELEASE_CLOSEOUT_SUMMARY_SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="release closeout summary schema validation failed",
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate release closeout readiness reports")
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument(
        "--profile",
        choices=VALID_PROFILES,
        default=BASE_PROFILE,
        help=(
            "Evidence profile to aggregate: base keeps the default release evidence; "
            "provenance also requires the supply-chain gate; sbom also requires SBOM readiness."
        ),
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Write the closeout summary even when machine_release_allowed is false and exit zero.",
    )
    parser.add_argument(
        "--allow-conditional",
        action="store_true",
        help="Exit zero for clean or operator-allowed conditional closeout state.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(vault, policy_path=args.policy_path, profile=args.profile)
    destination = write_report(vault, report, args.out)
    print(display_path(vault, destination))
    if args.no_fail:
        return 0
    if args.allow_conditional:
        return 0 if report.get("operator_release_allowed") else 1
    return 0 if report["machine_release_allowed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
