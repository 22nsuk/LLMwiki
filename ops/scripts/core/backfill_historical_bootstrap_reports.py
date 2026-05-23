#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
    from ops.scripts.artifact_io_runtime import read_json_object, write_schema_validated_json
    from ops.scripts.output_runtime import display_path
    from ops.scripts.policy_runtime import load_policy, report_path
    from ops.scripts.runtime_context import RuntimeContext
    from ops.scripts.schema_constants_runtime import (
        BUNDLE_MANIFEST_SCHEMA_PATH,
        EVAL_REPORT_SCHEMA_PATH,
        LINT_REPORT_SCHEMA_PATH,
    )
    from ops.scripts.schema_runtime import load_schema_with_vault_override
else:
    from .artifact_freshness_runtime import build_canonical_report_envelope
    from .artifact_io_runtime import read_json_object, write_schema_validated_json
    from .output_runtime import display_path
    from .policy_runtime import load_policy, report_path
    from .runtime_context import RuntimeContext
    from .schema_constants_runtime import (
        BUNDLE_MANIFEST_SCHEMA_PATH,
        EVAL_REPORT_SCHEMA_PATH,
        LINT_REPORT_SCHEMA_PATH,
    )
    from .schema_runtime import load_schema_with_vault_override


PRODUCER = "ops.scripts.backfill_historical_bootstrap_reports"
SCRIPT_PATH = "ops/scripts/backfill_historical_bootstrap_reports.py"
POLICY_PATH = "ops/policies/wiki-maintainer-policy.yaml"
POLICY_VERSION_SENTINEL = 0
ARCHIVE_REASON = "historical_bootstrap_snapshot_normalized_to_archive_contract"


@dataclass(frozen=True)
class BootstrapReportSpec:
    rel_path: str
    schema_path: str
    artifact_kind: str
    source_paths: tuple[str, ...]
    normalize_payload: Callable[[dict[str, Any], str], dict[str, Any]]


def _parse_timestamp(value: str) -> dt.datetime:
    if not value.strip():
        raise ValueError("historical bootstrap payload is missing generated_at")
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def _isoformat_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_generated_at(value: str) -> str:
    return _isoformat_z(_parse_timestamp(value))


def _normalize_recorded_path(value: str, recorded_vault: str) -> str:
    text = str(value).strip().replace("\\", "/")
    normalized_vault = str(recorded_vault).strip().replace("\\", "/")
    if not text:
        return text
    if normalized_vault and text == normalized_vault:
        return "."
    prefix = f"{normalized_vault.rstrip('/')}/" if normalized_vault else ""
    if prefix and text.startswith(prefix):
        relative = text[len(prefix) :].strip()
        return relative or "."
    return text


def _policy_identity() -> dict[str, Any]:
    return {
        "path": POLICY_PATH,
        "version": POLICY_VERSION_SENTINEL,
    }


def _historical_bootstrap_block(
    *,
    rel_path: str,
    normalized_at: str,
    original_generated_at: str,
    original_vault: str,
    original_producer: str,
    normalizations: list[str],
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "archive_reason": ARCHIVE_REASON,
        "source_artifact": rel_path,
        "original_generated_at": original_generated_at,
        "normalized_at": normalized_at,
        "original_producer": original_producer,
        "normalizations": normalizations,
    }
    if original_vault:
        block["original_vault"] = original_vault
    block["policy_identity"] = {
        **_policy_identity(),
        "status": "predates_versioned_policy_contract",
    }
    return block


def _normalize_eval_payload(payload: dict[str, Any], normalized_at: str) -> dict[str, Any]:
    original_generated_at = str(payload.get("generated_at", "")).strip()
    recorded_vault = str(payload.get("vault", "")).strip()
    normalizations = [
        "normalized_generated_at_to_utc_second_precision",
        "normalized_vault_to_repo_relative",
        "normalized_page_paths_to_repo_relative",
        "backfilled_archive_policy_identity",
        "derived_status_from_total_score",
    ]
    pages: list[dict[str, Any]] = []
    for item in payload.get("pages", []):
        if not isinstance(item, dict):
            continue
        normalized_item = dict(item)
        normalized_item["page"] = _normalize_recorded_path(str(item.get("page", "")), recorded_vault)
        pages.append(normalized_item)
    total_score = payload.get("total_score")
    max_score = payload.get("max_score")
    status = "pass" if isinstance(total_score, int) and isinstance(max_score, int) and total_score >= max_score else "fail"
    return {
        **payload,
        "vault": ".",
        "generated_at": _normalize_generated_at(original_generated_at),
        "status": status,
        "policy": _policy_identity(),
        "pages": pages,
        "historical_bootstrap": _historical_bootstrap_block(
            rel_path="ops/reports/eval-initial-2026-04-12.json",
            normalized_at=normalized_at,
            original_generated_at=original_generated_at,
            original_vault=recorded_vault,
            original_producer="ops.scripts.wiki_eval",
            normalizations=normalizations,
        ),
    }


def _normalize_lint_payload(payload: dict[str, Any], normalized_at: str) -> dict[str, Any]:
    original_generated_at = str(payload.get("generated_at", "")).strip()
    recorded_vault = str(payload.get("vault", "")).strip()
    normalizations = [
        "normalized_generated_at_to_utc_second_precision",
        "normalized_vault_to_repo_relative",
        "backfilled_empty_review_candidates",
        "backfilled_archive_policy_identity",
    ]
    stats = payload.get("stats")
    normalized_stats = dict(stats) if isinstance(stats, dict) else {}
    normalized_stats.setdefault("review_candidate_count", 0)
    return {
        **payload,
        "vault": ".",
        "generated_at": _normalize_generated_at(original_generated_at),
        "policy": _policy_identity(),
        "review_candidates": [],
        "stats": normalized_stats,
        "historical_bootstrap": _historical_bootstrap_block(
            rel_path="ops/reports/lint-initial-2026-04-12.json",
            normalized_at=normalized_at,
            original_generated_at=original_generated_at,
            original_vault=recorded_vault,
            original_producer="ops.scripts.wiki_lint",
            normalizations=normalizations,
        ),
    }


def _normalize_manifest_payload(payload: dict[str, Any], normalized_at: str) -> dict[str, Any]:
    original_generated_at = str(payload.get("generated_at", "")).strip()
    normalizations = [
        "normalized_generated_at_to_utc_second_precision",
        "added_archive_envelope",
    ]
    return {
        **payload,
        "generated_at": _normalize_generated_at(original_generated_at),
        "historical_bootstrap": _historical_bootstrap_block(
            rel_path="ops/reports/manifest-2026-04-12.json",
            normalized_at=normalized_at,
            original_generated_at=original_generated_at,
            original_vault="",
            original_producer="ops.scripts.wiki_manifest",
            normalizations=normalizations,
        ),
    }


BOOTSTRAP_REPORT_SPECS = {
    "ops/reports/eval-initial-2026-04-12.json": BootstrapReportSpec(
        rel_path="ops/reports/eval-initial-2026-04-12.json",
        schema_path=EVAL_REPORT_SCHEMA_PATH,
        artifact_kind="wiki_eval_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/wiki_eval.py"),
        normalize_payload=_normalize_eval_payload,
    ),
    "ops/reports/lint-initial-2026-04-12.json": BootstrapReportSpec(
        rel_path="ops/reports/lint-initial-2026-04-12.json",
        schema_path=LINT_REPORT_SCHEMA_PATH,
        artifact_kind="wiki_lint_report",
        source_paths=(SCRIPT_PATH, "ops/scripts/wiki_lint.py"),
        normalize_payload=_normalize_lint_payload,
    ),
    "ops/reports/manifest-2026-04-12.json": BootstrapReportSpec(
        rel_path="ops/reports/manifest-2026-04-12.json",
        schema_path=BUNDLE_MANIFEST_SCHEMA_PATH,
        artifact_kind="bundle_manifest",
        source_paths=(SCRIPT_PATH, "ops/scripts/wiki_manifest.py"),
        normalize_payload=_normalize_manifest_payload,
    ),
}


def _source_command(rel_path: str) -> str:
    return f"python -m ops.scripts.backfill_historical_bootstrap_reports --vault . --path {rel_path}"


def _build_archived_payload(
    vault: Path,
    *,
    rel_path: str,
    payload: dict[str, Any],
    original_text: str,
    spec: BootstrapReportSpec,
    normalized_at: str,
    resolved_policy_path: Path,
) -> dict[str, Any]:
    normalized_payload = spec.normalize_payload(payload, normalized_at)
    generated_at = str(normalized_payload.get("generated_at", "")).strip()
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=generated_at,
        artifact_kind=spec.artifact_kind,
        producer=PRODUCER,
        source_command=_source_command(rel_path),
        resolved_policy_path=resolved_policy_path,
        schema_path=spec.schema_path,
        source_paths=list(spec.source_paths),
        text_inputs={
            "historical_payload_before_backfill": original_text,
            "target_rel_path": rel_path,
        },
    )
    archived_payload = {
        **normalized_payload,
        **envelope,
    }
    archived_payload["artifact_status"] = "archived"
    archived_payload["retention_policy"] = "archive"
    archived_payload["currentness"] = {
        "status": "current",
        "checked_at": normalized_at,
    }
    return archived_payload


def backfill_historical_bootstrap_reports(
    vault: Path,
    rel_paths: list[str] | None = None,
    *,
    context: RuntimeContext | None = None,
    policy_path: str | None = None,
) -> list[str]:
    policy, resolved_policy_path = load_policy(vault, policy_path)
    runtime_context = context or RuntimeContext.from_policy(policy)
    normalized_at = runtime_context.isoformat_z()
    target_rel_paths = rel_paths or sorted(BOOTSTRAP_REPORT_SPECS)
    written: list[str] = []
    for rel_path in target_rel_paths:
        spec = BOOTSTRAP_REPORT_SPECS.get(rel_path)
        if spec is None:
            raise ValueError(f"unsupported historical bootstrap report path: {rel_path}")
        artifact_path = vault / rel_path
        original_text = artifact_path.read_text(encoding="utf-8")
        payload = read_json_object(artifact_path, context=rel_path)
        archived_payload = _build_archived_payload(
            vault,
            rel_path=rel_path,
            payload=payload,
            original_text=original_text,
            spec=spec,
            normalized_at=normalized_at,
            resolved_policy_path=resolved_policy_path,
        )
        schema = load_schema_with_vault_override(vault, spec.schema_path)
        write_schema_validated_json(
            artifact_path,
            archived_payload,
            schema,
            context=rel_path,
            trailing_newline=True,
        )
        written.append(report_path(vault, artifact_path))
    return written


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "Backfill the historical bootstrap reports under ops/reports/ into archived, "
            "schema-backed artifacts without treating them as current runtime evidence."
        )
    )
    ap.add_argument("--vault", type=Path, default=Path("."))
    ap.add_argument(
        "--path",
        dest="paths",
        action="append",
        choices=sorted(BOOTSTRAP_REPORT_SPECS),
        help="Specific historical bootstrap report path(s) to backfill in place.",
    )
    ap.add_argument("--policy-path")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    written = backfill_historical_bootstrap_reports(
        args.vault,
        rel_paths=args.paths,
        policy_path=args.policy_path,
    )
    for rel_path in written:
        print(display_path(args.vault, args.vault / rel_path))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())