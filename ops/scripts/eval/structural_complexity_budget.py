#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.complexity_ratchet_runtime import RatchetCeiling, judge_ratchet
    from ops.scripts.policy_runtime import load_policy
    from ops.scripts.structural_complexity_budget_runtime import (
        DEFAULT_REPORT,
        DEFAULT_TARGET_PROFILES,
        build_report,
        target_paths_from_changed_files_manifest,
        touched_target_profiles,
        write_report,
    )
else:
    from ops.scripts.policy_runtime import load_policy

    from .complexity_ratchet_runtime import RatchetCeiling, judge_ratchet
    from .structural_complexity_budget_runtime import (
        DEFAULT_REPORT,
        DEFAULT_TARGET_PROFILES,
        build_report,
        target_paths_from_changed_files_manifest,
        touched_target_profiles,
        write_report,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", default=".")
    parser.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    parser.add_argument("--out", default=DEFAULT_REPORT)
    parser.add_argument(
        "--changed-files-manifest",
        help="Optional changed-files manifest used to narrow the report to touched paths.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Explicit relative path to include in a touched-surface report. May be repeated.",
    )
    parser.add_argument(
        "--fail-on-attention",
        action="store_true",
        help="Return a failing exit code when the preview report surfaces attention or failure targets.",
    )
    return parser.parse_args(argv)


def _complexity_ratchet_ceiling_from_policy(policy: dict) -> RatchetCeiling:
    ratchet = policy["system_refactor_policy"]["complexity_ratchet"]
    return RatchetCeiling(
        warn_targets=frozenset(str(path) for path in ratchet["warn_targets"]),
        resolved_targets=frozenset(str(path) for path in ratchet["resolved_targets"]),
    )


def _ratchet_failure_message(judgement: object) -> str:
    new_warn_targets = list(getattr(judgement, "new_warn_targets", ()))
    resurfaced_targets = list(getattr(judgement, "resurfaced_targets", ()))
    details: list[str] = []
    if new_warn_targets:
        details.append(f"new_warn_targets={','.join(new_warn_targets)}")
    if resurfaced_targets:
        details.append(f"resurfaced_targets={','.join(resurfaced_targets)}")
    return "complexity ratchet regression: " + "; ".join(details)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    vault = Path(args.vault)
    try:
        target_paths = list(args.target)
        if args.changed_files_manifest:
            target_paths.extend(target_paths_from_changed_files_manifest(vault, args.changed_files_manifest))
        target_profiles = (
            touched_target_profiles(DEFAULT_TARGET_PROFILES, target_paths)
            if args.changed_files_manifest or args.target
            else None
        )
        report = build_report(vault, args.policy, target_profiles=target_profiles)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(3) from exc
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(7) from exc

    write_report(vault, report, args.out)
    if args.fail_on_attention:
        if args.changed_files_manifest or args.target:
            if report["status"] == "fail":
                raise SystemExit(1)
            policy, _resolved_policy_path = load_policy(vault, args.policy)
            judgement = judge_ratchet(_complexity_ratchet_ceiling_from_policy(policy), report)
            if judgement.status != "pass":
                print(_ratchet_failure_message(judgement), file=sys.stderr)
                raise SystemExit(1)
        elif report["status"] != "pass":
            raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
