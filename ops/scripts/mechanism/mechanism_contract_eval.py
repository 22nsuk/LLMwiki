#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.mechanism.mechanism_contract_eval_runtime import (
        MechanismContractEvalRequest,
        write_mechanism_contract_eval_pair,
        write_mechanism_contract_eval_report,
    )
else:
    from ops.scripts.core.policy_runtime import load_policy
    from ops.scripts.core.runtime_context import RuntimeContext

    from .mechanism_contract_eval_runtime import (
        MechanismContractEvalRequest,
        write_mechanism_contract_eval_pair,
        write_mechanism_contract_eval_report,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build baseline/candidate mechanism-local contract eval reports for a run.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--phase",
        choices=("baseline", "candidate", "pair"),
        default="pair",
    )
    parser.add_argument("--changed-files-manifest")
    parser.add_argument("--behavior-delta")
    return parser.parse_args(argv)


def _request(args: argparse.Namespace) -> MechanismContractEvalRequest:
    vault = Path(args.vault).resolve()
    policy, resolved_policy_path = load_policy(vault, args.policy)
    return MechanismContractEvalRequest(
        vault=vault,
        run_id=args.run_id,
        policy=policy,
        resolved_policy_path=resolved_policy_path,
        policy_path_text=args.policy,
        changed_files_manifest_path=args.changed_files_manifest or "",
        behavior_delta_path=args.behavior_delta or "",
        context=RuntimeContext.from_policy(policy),
    )


def _write_reports(args: argparse.Namespace) -> dict[str, str]:
    request = _request(args)
    if args.phase == "pair":
        return write_mechanism_contract_eval_pair(request)
    return {
        args.phase: write_mechanism_contract_eval_report(
            request,
            phase=args.phase,
        )
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        artifacts = _write_reports(args)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 7
    print(json.dumps({"artifacts": artifacts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
