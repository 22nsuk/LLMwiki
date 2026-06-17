#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.wiki_page_runtime import section_body
else:
    from ops.scripts.core.artifact_freshness_runtime import (
        build_canonical_report_envelope,
    )
    from ops.scripts.core.artifact_io_runtime import (
        SchemaBackedReportWriteRequest,
        write_schema_backed_report,
    )
    from ops.scripts.core.output_runtime import display_path
    from ops.scripts.core.policy_runtime import load_policy, report_path
    from ops.scripts.core.runtime_context import RuntimeContext
    from ops.scripts.eval.wiki_page_runtime import section_body


DEFAULT_MATRIX = (
    "runs/run-20260422-raw-intake-registration-and-promotion/"
    "absorption/raw-intake-absorption-matrix-2026-04-22.json"
)
DEFAULT_OUT = "tmp/raw-intake-source-quality-report.json"
PRODUCER = "ops.scripts.raw_intake_source_quality"
SCHEMA_PATH = "ops/schemas/raw-intake-source-quality-report.schema.json"
SOURCE_COMMAND = "python -m ops.scripts.raw_intake_source_quality"
REVIEWED_ROUTE_STATUSES = {"approved", "reviewed"}
TEXTUAL_RAW_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm"}
BOILERPLATE_PATTERNS = (
    re.compile(r"^(skip to|본문 바로가기|메뉴|로그인|회원가입|구독|공유|광고)\b", re.I),
    re.compile(r"^(copyright|all rights reserved)\b", re.I),
    re.compile(r"(무단전재|재배포 금지|저작권)", re.I),
)


def _resolved_input_path(vault: Path, path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    return (vault / resolved).resolve()


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    return text[end + 5 :]


def _is_boilerplate_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith(("![", "<!--")):
        return True
    if re.fullmatch(r"[-*_`#>\s]+", stripped):
        return True
    if re.fullmatch(r"\[[^\]]+\]\([^\)]+\)", stripped):
        return True
    return any(pattern.search(stripped) for pattern in BOILERPLATE_PATTERNS)


def extract_clean_lead(text: str, *, max_chars: int = 700) -> str:
    body = _strip_frontmatter(text)
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            continue
        if _is_boilerplate_line(stripped):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
        stripped = re.sub(r"!\[[^\]]*\]\([^\)]+\)", "", stripped)
        stripped = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", stripped)
        current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    for paragraph in paragraphs:
        normalized = re.sub(r"\s+", " ", paragraph).strip()
        if len(normalized) >= 40:
            return normalized[:max_chars].rstrip()
    return ""


def _section_text(text: str, heading: str) -> str:
    return (section_body(text, heading) or "").strip()


def _bullet_count(section_text: str) -> int:
    return sum(1 for line in section_text.splitlines() if line.strip().startswith("- "))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _raw_lead_state(vault: Path, raw_path: str) -> dict[str, Any]:
    raw_path = raw_path.strip()
    if not raw_path:
        return {"status": "missing_path", "char_count": 0, "sha256": ""}
    resolved = _resolved_input_path(vault, raw_path)
    if not resolved.exists():
        return {"status": "missing_file", "char_count": 0, "sha256": ""}
    if resolved.suffix.lower() not in TEXTUAL_RAW_SUFFIXES:
        return {"status": "not_textual", "char_count": 0, "sha256": ""}
    lead = extract_clean_lead(resolved.read_text(encoding="utf-8", errors="replace"))
    return {
        "status": "ok" if lead else "empty",
        "char_count": len(lead),
        "sha256": _sha256_text(lead) if lead else "",
    }


def _source_quality_for_entry(
    vault: Path,
    entry: dict[str, Any],
    *,
    min_summary_chars: int,
    min_key_points: int,
    min_key_point_chars: int,
    min_raw_lead_chars: int,
) -> dict[str, Any]:
    source_page = str(entry.get("source_page", "")).strip()
    raw_path = str(entry.get("raw_path", "")).strip()
    review_status = str(entry.get("review_status", "")).strip()
    proposed_action = str(entry.get("proposed_action", "")).strip()
    source_path = _resolved_input_path(vault, source_page)
    issues: list[str] = []
    source_page_status = "ok"
    summary_chars = 0
    key_point_count = 0
    key_point_chars = 0

    if not source_page or not source_path.exists():
        source_page_status = "missing"
        issues.append("missing_source_page")
    else:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        summary = _section_text(source_text, "Summary")
        key_points = _section_text(source_text, "Key points")
        summary_chars = len(re.sub(r"\s+", " ", summary).strip())
        key_point_count = _bullet_count(key_points)
        key_point_chars = len(re.sub(r"\s+", " ", key_points).strip())
        if summary_chars < min_summary_chars:
            issues.append("summary_below_min_chars")
        if key_point_count < min_key_points:
            issues.append("key_points_below_min_count")
        if key_point_chars < min_key_point_chars:
            issues.append("key_points_below_min_chars")

    raw_lead = _raw_lead_state(vault, raw_path)
    if raw_lead["status"] in {"ok", "empty"} and raw_lead["char_count"] < min_raw_lead_chars:
        issues.append("cleaned_raw_lead_below_min_chars")

    reviewed = review_status in REVIEWED_ROUTE_STATUSES
    hard_source_page_issue_names = {
        "missing_source_page",
        "key_points_below_min_count",
        "key_points_below_min_chars",
    }
    has_hard_source_page_issue = any(issue in hard_source_page_issue_names for issue in issues)
    if not issues:
        quality_status = "pass"
    elif not reviewed:
        quality_status = "fail"
    elif proposed_action == "keep_source_only_seed":
        quality_status = "review"
    elif has_hard_source_page_issue:
        quality_status = "fail"
    else:
        quality_status = "review"

    return {
        "registry_id": str(entry.get("registry_id", "")).strip(),
        "source_page": source_page,
        "raw_path": raw_path,
        "proposed_action": proposed_action,
        "review_status": review_status,
        "source_page_status": source_page_status,
        "summary_char_count": summary_chars,
        "key_point_count": key_point_count,
        "key_point_char_count": key_point_chars,
        "cleaned_raw_lead": raw_lead,
        "quality_status": quality_status,
        "issues": issues,
    }


def load_matrix(matrix_path: Path) -> dict[str, Any]:
    return json.loads(matrix_path.read_text(encoding="utf-8"))


def build_report(
    vault: Path,
    *,
    matrix_path: str | Path = DEFAULT_MATRIX,
    min_summary_chars: int = 80,
    min_key_points: int = 2,
    min_key_point_chars: int = 80,
    min_raw_lead_chars: int = 80,
    context: RuntimeContext | None = None,
) -> dict[str, Any]:
    policy, resolved_policy_path = load_policy(vault)
    runtime_context = context or RuntimeContext.from_policy(policy)
    generated_at = runtime_context.isoformat_z()
    resolved_matrix_path = _resolved_input_path(vault, matrix_path)
    matrix = load_matrix(resolved_matrix_path)
    entries = matrix.get("matrix")
    if not isinstance(entries, list):
        entries = []
    rows = [
        _source_quality_for_entry(
            vault,
            entry,
            min_summary_chars=min_summary_chars,
            min_key_points=min_key_points,
            min_key_point_chars=min_key_point_chars,
            min_raw_lead_chars=min_raw_lead_chars,
        )
        for entry in entries
        if isinstance(entry, dict)
    ]
    counts = Counter(row["quality_status"] for row in rows)
    status = "fail" if counts.get("fail", 0) else "attention" if counts.get("review", 0) else "pass"

    return {
        **build_canonical_report_envelope(
            vault,
            generated_at=generated_at,
            artifact_kind="raw_intake_source_quality_report",
            producer=PRODUCER,
            source_command=SOURCE_COMMAND,
            resolved_policy_path=resolved_policy_path,
            schema_path=SCHEMA_PATH,
            source_paths=["ops/scripts/registry/raw_intake_source_quality.py"],
            file_inputs={"matrix": resolved_matrix_path},
            text_inputs={
                "min_summary_chars": str(min_summary_chars),
                "min_key_points": str(min_key_points),
                "min_key_point_chars": str(min_key_point_chars),
                "min_raw_lead_chars": str(min_raw_lead_chars),
            },
        ),
        "vault": report_path(vault, vault),
        "status": status,
        "matrix": {
            "path": report_path(vault, resolved_matrix_path),
            "scope": str(matrix.get("scope", "")).strip(),
            "entry_count": len(rows),
        },
        "policy": {
            "path": report_path(vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "thresholds": {
            "min_summary_chars": min_summary_chars,
            "min_key_points": min_key_points,
            "min_key_point_chars": min_key_point_chars,
            "min_raw_lead_chars": min_raw_lead_chars,
        },
        "summary": {
            "entry_count": len(rows),
            "pass_count": int(counts.get("pass", 0)),
            "review_count": int(counts.get("review", 0)),
            "fail_count": int(counts.get("fail", 0)),
        },
        "findings": rows,
    }


def write_report(vault: Path, report: dict[str, Any], out_path: str | None = None) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="raw intake source quality schema validation failed",
            trailing_newline=True,
        )
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check raw-intake source-only notes with a cleaned lead extractor.",
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--matrix", default=DEFAULT_MATRIX)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--min-summary-chars", type=int, default=80)
    parser.add_argument("--min-key-points", type=int, default=2)
    parser.add_argument("--min-key-point-chars", type=int, default=80)
    parser.add_argument("--min-raw-lead-chars", type=int, default=80)
    parser.add_argument("--fail-on-attention", action="store_true")
    parser.add_argument("--fail-on-fail", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault).resolve()
    report = build_report(
        vault,
        matrix_path=args.matrix,
        min_summary_chars=args.min_summary_chars,
        min_key_points=args.min_key_points,
        min_key_point_chars=args.min_key_point_chars,
        min_raw_lead_chars=args.min_raw_lead_chars,
    )
    path = write_report(vault, report, args.out)
    print(display_path(vault, path))
    if args.fail_on_attention and report["status"] in {"attention", "fail"}:
        return 1
    if args.fail_on_fail and report["status"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
