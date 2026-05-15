#!/usr/bin/env python3
from __future__ import annotations
import sys

import argparse
import json
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.output_runtime import resolve_output_path, write_output_text
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.raw_markdown_runtime import (
        apply_raw_markdown_normalization,
        iter_raw_markdown_paths,
        normalize_raw_markdown_file,
    )
    from ops.scripts.schema_constants_runtime import RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH
else:
    from ops.scripts.output_runtime import resolve_output_path, write_output_text
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from .raw_markdown_runtime import (
        apply_raw_markdown_normalization,
        iter_raw_markdown_paths,
        normalize_raw_markdown_file,
    )
    from ops.scripts.schema_constants_runtime import RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH


def build_report(
    vault: Path,
    target_path: Path,
    *,
    write: bool,
    policy_path: str | None = None,
    context: RuntimeContext | None = None,
) -> dict:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    results = []
    changed_count = 0
    manual_review_count = 0

    for path in iter_raw_markdown_paths(target_path):
        result = (
            apply_raw_markdown_normalization(vault, path)
            if write
            else normalize_raw_markdown_file(vault, path)
        )
        if result.changed:
            changed_count += 1
        if result.manual_review_required:
            manual_review_count += 1
        results.append(
            {
                "path": result.path,
                "changed": result.changed,
                "frontmatter_present_before": result.frontmatter_present_before,
                "pre_sha256": result.pre_sha256,
                "post_sha256": result.post_sha256,
                "metadata": result.metadata,
                "removed_noise_classes": result.removed_noise_classes,
                "manual_review_required": result.manual_review_required,
                "manual_review_reasons": result.manual_review_reasons,
            }
        )

    mode = "write" if write else "report-only"
    return {
        "$schema": RAW_MARKDOWN_NORMALIZATION_REPORT_SCHEMA_PATH,
        "vault": report_path(vault, vault),
        "generated_at": runtime_context.isoformat_z(),
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "mode": mode,
        "target_path": report_path(vault, target_path),
        "stats": {
            "file_count": len(results),
            "changed_count": changed_count,
            "manual_review_count": manual_review_count,
        },
        "results": results,
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".")
    ap.add_argument("--policy", default="ops/policies/wiki-maintainer-policy.yaml")
    ap.add_argument("--path", default="raw")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--report-out")
    args = ap.parse_args(argv)

    vault = Path(args.vault)
    target_path = resolve_output_path(vault, args.path, default_relative_path="raw")
    report = build_report(vault, target_path, write=args.write, policy_path=args.policy)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report_out:
        destination = resolve_output_path(vault, args.report_out)
        write_output_text(destination, text)
    else:
        print(text)


if __name__ == "__main__":
    main()
