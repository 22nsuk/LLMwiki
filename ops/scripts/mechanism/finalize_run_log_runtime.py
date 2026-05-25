from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext

from .finalize_run_artifact_runtime import (
    CHANGED_FILES_MANIFEST_SCHEMA,
    load_validated_json,
)
from .finalize_run_errors_runtime import FinalizeRunUsageError, FinalizeRunWriteError


def slugify_heading(text: str) -> str:
    slug = text.strip().lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def timestamp_strings(context: RuntimeContext, now: dt.datetime | None) -> tuple[str, str]:
    if now is not None:
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.UTC)
        override_context = RuntimeContext(
            display_timezone=context.display_timezone,
            clock=lambda: now,
            session_id=context.session_id,
            iteration=context.iteration,
            executor_id=context.executor_id,
        )
        return override_context.local_heading_timestamp(), override_context.isoformat_z()
    return context.local_heading_timestamp(), context.isoformat_z()


def log_text_with_appended_entry(existing: str, entry: str) -> str:
    addition = "\n---\n\n" + entry.strip() + "\n"
    if existing.rstrip():
        return existing.rstrip() + addition
    return entry.strip() + "\n"


def existing_text_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FinalizeRunWriteError(str(exc)) from exc


def entry_ref(log_page: str, heading_text: str) -> str:
    return f"{log_page}#{slugify_heading(heading_text)}"


def system_log_has_anchor(log_path: Path, entry_ref_value: str) -> bool:
    if "#" not in entry_ref_value or not log_path.exists():
        return False
    anchor = entry_ref_value.split("#", 1)[1]
    text = log_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("# ").strip()
            if slugify_heading(heading) == anchor:
                return True
    return False


def ordered_unique(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def log_artifacts_for_finalized_run(
    vault: Path,
    report: dict,
    *,
    promotion_report_rel: str,
    run_ledger_rel: str,
) -> list[str]:
    artifacts = [promotion_report_rel, run_ledger_rel]
    inputs = report.get("inputs", {})
    manifest_rel = inputs.get("changed_files_manifest") if isinstance(inputs, dict) else None
    if isinstance(manifest_rel, str) and manifest_rel:
        manifest = load_validated_json(
            vault,
            (vault / manifest_rel).resolve(),
            CHANGED_FILES_MANIFEST_SCHEMA,
            context=f"schema validation failed for {manifest_rel}",
        )
        artifacts.append(manifest_rel)
        manifest_files = manifest.get("files", [])
        if isinstance(manifest_files, list):
            for item in manifest_files:
                if not isinstance(item, dict):
                    continue
                path = item.get("path")
                if isinstance(path, str) and path:
                    artifacts.append(path)
        return ordered_unique(artifacts)

    fallback_targets = [
        *list(report.get("primary_targets", [])),
        *list(report.get("supporting_targets", [])),
    ]
    fallback_artifacts = [
        artifact for artifact in fallback_targets if isinstance(artifact, str) and artifact
    ]
    artifacts.extend(fallback_artifacts)
    return ordered_unique(artifacts)


def build_log_entry_markdown(
    *,
    run_id: str,
    decision: str,
    summary: str,
    artifacts: list[str],
    promotion_report_rel: str,
    run_ledger_rel: str,
    local_heading_ts: str,
) -> tuple[str, str]:
    heading_text = f"[{local_heading_ts}] improve | Finalize mechanism run {run_id} ({decision})"
    heading = f"## {heading_text}"
    artifact_list = ordered_unique([promotion_report_rel, run_ledger_rel, *artifacts])
    artifact_lines = "\n".join(f"- `{artifact}`" for artifact in artifact_list)
    consequence_lines = "\n".join(
        [
            f"- Decision: `{decision}`",
            "- Promotion report log status is now recorded.",
            "- This run is available as historical input for mechanism review and mutation proposal.",
        ]
    )
    entry = (
        f"{heading}\n\n"
        "### Summary\n"
        f"{summary}\n\n"
        "### Artifacts\n"
        f"{artifact_lines}\n\n"
        "### Consequence\n"
        f"{consequence_lines}\n"
    )
    return entry, slugify_heading(heading_text)


def resolve_finalize_log_state[LogStateT](
    vault: Path,
    *,
    report: dict,
    run_id: str,
    decision: str,
    promotion_report_rel: str,
    run_ledger_rel: str,
    context: RuntimeContext,
    now: dt.datetime | None,
    log_state_factory: Callable[..., LogStateT],
) -> tuple[LogStateT, str]:
    log = report.get("log", {})
    if not isinstance(log, dict):
        raise FinalizeRunUsageError("promotion report log must be an object")

    local_heading_ts, utc_ts = timestamp_strings(context, now)
    if not bool(log.get("required")):
        return (
            log_state_factory(
                required=False,
                entry_ref="",
                log_path=None,
                final_log_text=None,
            ),
            utc_ts,
        )

    log_page = log.get("page")
    if not isinstance(log_page, str) or not log_page:
        raise FinalizeRunUsageError("promotion report log.page is missing")
    log_path = (vault / log_page).resolve()

    if log.get("status") == "recorded" and isinstance(log.get("entry_ref"), str) and log.get("entry_ref"):
        existing_entry_ref = log["entry_ref"]
        if not system_log_has_anchor(log_path, existing_entry_ref):
            raise FinalizeRunUsageError(
                "promotion report claims log is recorded, but entry_ref is missing from system-log"
            )
        return (
            log_state_factory(
                required=True,
                entry_ref=existing_entry_ref,
                log_path=log_path,
                final_log_text=None,
            ),
            utc_ts,
        )

    log_artifacts = log_artifacts_for_finalized_run(
        vault,
        report,
        promotion_report_rel=promotion_report_rel,
        run_ledger_rel=run_ledger_rel,
    )
    entry_markdown, anchor = build_log_entry_markdown(
        run_id=run_id,
        decision=decision,
        summary=report["summary"],
        artifacts=log_artifacts,
        promotion_report_rel=promotion_report_rel,
        run_ledger_rel=run_ledger_rel,
        local_heading_ts=local_heading_ts,
    )
    existing_log_text = existing_text_or_none(log_path) or ""
    return (
        log_state_factory(
            required=True,
            entry_ref=entry_ref(log_page, anchor),
            log_path=log_path,
            final_log_text=log_text_with_appended_entry(existing_log_text, entry_markdown),
        ),
        utc_ts,
    )
