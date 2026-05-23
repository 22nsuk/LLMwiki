#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.cyclonedx_sbom import DEFAULT_OUT as CYCLONEDX_DEFAULT_OUT, build_bom, write_bom
    from ops.scripts.in_toto_statement import DEFAULT_OUT as IN_TOTO_DEFAULT_OUT, build_in_toto_statement, write_in_toto_statement
    from ops.scripts.openvex_draft import DEFAULT_OUT as OPENVEX_DEFAULT_OUT, build_openvex_draft, write_openvex_draft
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.security_advisories import DEFAULT_OUT as SECURITY_ADVISORIES_DEFAULT_OUT, build_report as build_security_advisories_report, write_report as write_security_advisories_report
    from ops.scripts.sbom_export_mapping import DEFAULT_OUT as MAPPING_DEFAULT_OUT, build_report as build_sbom_export_mapping_report, write_report as write_sbom_export_mapping_report
    from ops.scripts.sbom_readiness_gate_runtime import GATE_REPORT_REL_PATH as SBOM_READINESS_GATE_DEFAULT_OUT, build_gate_report as build_sbom_readiness_gate_report, write_gate_report as write_sbom_readiness_gate_report
    from ops.scripts.sigstore_bundle import DEFAULT_OUT as SIGSTORE_BUNDLE_DEFAULT_OUT, build_bundle_verification, write_bundle_verification
    from ops.scripts.spdx_sbom import DEFAULT_OUT as SPDX_DEFAULT_OUT, build_spdx_sbom, write_spdx_sbom
    from ops.scripts.supply_chain_artifact_model import DEFAULT_OUT as MODEL_DEFAULT_OUT, build_model, write_model
    from ops.scripts.supply_chain_gate_runtime import GATE_REPORT_REL_PATH as SUPPLY_CHAIN_GATE_DEFAULT_OUT, build_gate_report as build_supply_chain_gate_report, write_gate_report as write_supply_chain_gate_report
    from ops.scripts.supply_chain_provenance import DEFAULT_OUT as PROVENANCE_DEFAULT_OUT, build_report as build_supply_chain_provenance_report, write_report as write_supply_chain_provenance_report
else:
    from .cyclonedx_sbom import DEFAULT_OUT as CYCLONEDX_DEFAULT_OUT, build_bom, write_bom
    from .in_toto_statement import DEFAULT_OUT as IN_TOTO_DEFAULT_OUT, build_in_toto_statement, write_in_toto_statement
    from .openvex_draft import DEFAULT_OUT as OPENVEX_DEFAULT_OUT, build_openvex_draft, write_openvex_draft
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.runtime_context import RuntimeContext
    from .security_advisories import DEFAULT_OUT as SECURITY_ADVISORIES_DEFAULT_OUT, build_report as build_security_advisories_report, write_report as write_security_advisories_report
    from .sbom_export_mapping import DEFAULT_OUT as MAPPING_DEFAULT_OUT, build_report as build_sbom_export_mapping_report, write_report as write_sbom_export_mapping_report
    from .sbom_readiness_gate_runtime import GATE_REPORT_REL_PATH as SBOM_READINESS_GATE_DEFAULT_OUT, build_gate_report as build_sbom_readiness_gate_report, write_gate_report as write_sbom_readiness_gate_report
    from .sigstore_bundle import DEFAULT_OUT as SIGSTORE_BUNDLE_DEFAULT_OUT, build_bundle_verification, write_bundle_verification
    from .spdx_sbom import DEFAULT_OUT as SPDX_DEFAULT_OUT, build_spdx_sbom, write_spdx_sbom
    from .supply_chain_artifact_model import DEFAULT_OUT as MODEL_DEFAULT_OUT, build_model, write_model
    from .supply_chain_gate_runtime import GATE_REPORT_REL_PATH as SUPPLY_CHAIN_GATE_DEFAULT_OUT, build_gate_report as build_supply_chain_gate_report, write_gate_report as write_supply_chain_gate_report
    from .supply_chain_provenance import DEFAULT_OUT as PROVENANCE_DEFAULT_OUT, build_report as build_supply_chain_provenance_report, write_report as write_supply_chain_provenance_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate supply-chain provenance, gates, CycloneDX, and OpenVEX artifacts "
            "in one in-process pipeline to reuse intermediate reports."
        )
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy-path")
    parser.add_argument("--provenance-out", default=PROVENANCE_DEFAULT_OUT)
    parser.add_argument("--gate-out", default=SUPPLY_CHAIN_GATE_DEFAULT_OUT)
    parser.add_argument("--security-advisories-out", default=SECURITY_ADVISORIES_DEFAULT_OUT)
    parser.add_argument("--mapping-out", default=MAPPING_DEFAULT_OUT)
    parser.add_argument("--readiness-out", default=SBOM_READINESS_GATE_DEFAULT_OUT)
    parser.add_argument("--model-out", default=MODEL_DEFAULT_OUT)
    parser.add_argument("--cyclonedx-out", default=CYCLONEDX_DEFAULT_OUT)
    parser.add_argument("--spdx-out", default=SPDX_DEFAULT_OUT)
    parser.add_argument("--openvex-out", default=OPENVEX_DEFAULT_OUT)
    parser.add_argument("--in-toto-out", default=IN_TOTO_DEFAULT_OUT)
    parser.add_argument("--sigstore-out", default=SIGSTORE_BUNDLE_DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    policy, _ = load_policy(vault, args.policy_path)
    runtime_context = RuntimeContext.from_policy(policy)

    provenance_report = build_supply_chain_provenance_report(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
    )
    provenance_destination = write_supply_chain_provenance_report(vault, provenance_report, args.provenance_out)

    supply_chain_gate_report = build_supply_chain_gate_report(
        vault,
        runtime_context,
        provenance_report=provenance_report,
    )
    supply_chain_gate_destination = write_supply_chain_gate_report(vault, supply_chain_gate_report, args.gate_out)

    security_advisories_report = build_security_advisories_report(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
    )
    security_advisories_destination = write_security_advisories_report(
        vault,
        security_advisories_report,
        args.security_advisories_out,
    )

    mapping_report = build_sbom_export_mapping_report(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
        provenance_report=provenance_report,
    )
    mapping_destination = write_sbom_export_mapping_report(vault, mapping_report, args.mapping_out)

    readiness_gate_report = build_sbom_readiness_gate_report(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
        mapping_report=mapping_report,
    )
    readiness_gate_destination = write_sbom_readiness_gate_report(vault, readiness_gate_report, args.readiness_out)

    model_report = build_model(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
        provenance_report=provenance_report,
        mapping_report=mapping_report,
        security_advisories_report=security_advisories_report,
    )
    model_destination = write_model(vault, model_report, args.model_out)

    bom = build_bom(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
        provenance_report=provenance_report,
        mapping_report=mapping_report,
    )
    bom_destination = write_bom(vault, bom, args.cyclonedx_out)

    spdx_report = build_spdx_sbom(
        vault,
        policy_path=args.policy_path,
        artifact_model=model_report,
    )
    spdx_destination = write_spdx_sbom(vault, spdx_report, args.spdx_out)

    openvex_report = build_openvex_draft(
        vault,
        policy_path=args.policy_path,
        context=runtime_context,
        cyclonedx_bom_ref=args.cyclonedx_out,
        use_existing_bom=False,
        cyclonedx_bom=bom,
        artifact_model=model_report,
        security_advisories_report=security_advisories_report,
    )
    openvex_destination = write_openvex_draft(vault, openvex_report, args.openvex_out)

    in_toto_report = build_in_toto_statement(
        vault,
        policy_path=args.policy_path,
        artifact_model=model_report,
        provenance_report=provenance_report,
    )
    in_toto_destination = write_in_toto_statement(vault, in_toto_report, args.in_toto_out)

    sigstore_report = build_bundle_verification(
        vault,
        policy_path=args.policy_path,
        artifact_model=model_report,
    )
    sigstore_destination = write_bundle_verification(vault, sigstore_report, args.sigstore_out)

    for destination in (
        provenance_destination,
        supply_chain_gate_destination,
        security_advisories_destination,
        mapping_destination,
        readiness_gate_destination,
        model_destination,
        bom_destination,
        spdx_destination,
        openvex_destination,
        in_toto_destination,
        sigstore_destination,
    ):
        print(display_path(vault, destination))

    return 0 if supply_chain_gate_report["status"] == "pass" and readiness_gate_report["status"] == "pass" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
