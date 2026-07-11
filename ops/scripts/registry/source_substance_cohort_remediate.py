#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ops.scripts.core.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.core.artifact_io_runtime import (
    SchemaBackedReportWriteRequest,
    write_schema_backed_report,
)
from ops.scripts.core.filesystem_runtime import AtomicTextUpdate, atomic_multi_write
from ops.scripts.core.frontmatter_runtime import parse_frontmatter
from ops.scripts.core.policy_runtime import load_policy, report_path
from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import (
    load_schema_with_vault_override,
    validate_or_raise,
)
from ops.scripts.eval.source_page_substance_runtime import (
    evaluate_source_page_substance,
)
from ops.scripts.registry.source_substance_cohort_classify import (
    build_report as build_classification_report,
)

DEFAULT_OUT = "tmp/source-substance-cohort-remediation.json"
SCHEMA_PATH = "ops/schemas/source-substance-cohort-remediation.schema.json"
PRODUCER = "ops.scripts.registry.source_substance_cohort_remediate"
SOURCE_COMMAND = "python -m ops.scripts.registry.source_substance_cohort_remediate --vault ."
PAGE_ROOTS = ("wiki", "system")
TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".text"})
SUMMARY_FAILURES = frozenset(
    {"summary_repeats_title", "summary_lacks_source_specific_facts"}
)
KEY_POINT_FAILURES = frozenset(
    {
        "key_points_below_minimum",
        "first_key_point_repeats_title",
        "truncated_key_point",
        "boilerplate_key_point_pattern",
    }
)

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|\Z)", re.DOTALL)
_FENCED_BLOCK_RE = re.compile(r"^\s*(```|~~~).*?^\s*\1\s*$", re.MULTILINE | re.DOTALL)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_REFERENCE_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")
_MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)")
_SENTENCE_RE = re.compile(r"[^.!?。！？\n]+[.!?。！？](?=\s|$)")
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_COPYRIGHT_MARKERS = (
    "copyright",
    "all rights reserved",
    "©",
    "무단 전재",
    "무단전재",
    "재배포 금지",
    "저작권자",
)


class PdfExtractor(Protocol):
    def extract(self, path: Path) -> str: ...


PdfCommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SubprocessPdfExtractor:
    """PDF adapter whose executable and process runner are both injectable."""

    executable: str = "pdftotext"
    runner: PdfCommandRunner = subprocess.run

    def extract(self, path: Path) -> str:
        completed = self.runner(
            [self.executable, str(path), "-"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "pdf text extraction failed").strip()
            raise RuntimeError(detail)
        return completed.stdout


@dataclass(frozen=True)
class _Candidate:
    page_path: Path
    before_text: str
    after_text: str
    raw_path: Path
    raw_sha256: str


@dataclass(frozen=True)
class RemediationBuild:
    report: dict[str, Any]
    candidates: tuple[_Candidate, ...]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _relative_path(vault: Path, path: Path) -> str:
    return path.relative_to(vault).as_posix()


def _discover_source_pages(vault: Path) -> list[Path]:
    pages: list[Path] = []
    for root_name in PAGE_ROOTS:
        root = vault / root_name
        if root.is_dir():
            pages.extend(root.rglob("source--*.md"))
    return sorted(path for path in pages if path.is_file())


def _normalize_raw_text(text: str, *, markdown: bool) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        normalized = _FRONTMATTER_RE.sub("", normalized, count=1)
        normalized = _FENCED_BLOCK_RE.sub("", normalized)
    normalized = _IMAGE_RE.sub("", normalized)
    normalized = _LINK_RE.sub(r"\1", normalized)
    normalized = _REFERENCE_LINK_RE.sub(r"\1", normalized)
    normalized = _URL_RE.sub("", normalized)
    normalized = _HTML_RE.sub("", normalized)

    retained: list[str] = []
    for source_line in normalized.splitlines():
        line = _MARKDOWN_PREFIX_RE.sub("", source_line).strip()
        if not line:
            retained.append("")
            continue
        lowered = line.casefold()
        if any(marker in lowered for marker in _COPYRIGHT_MARKERS):
            continue
        if re.fullmatch(r"[:|\-\s]+", line):
            continue
        retained.append(line)
    return re.sub(r"[ \t]+", " ", "\n".join(retained)).strip()


def extract_complete_sentences(normalized_raw_text: str) -> list[str]:
    sentences: list[str] = []
    seen: set[str] = set()
    for match in _SENTENCE_RE.finditer(normalized_raw_text):
        sentence = re.sub(r"\s+", " ", match.group(0)).strip()
        if sentence.endswith(("...", "…")):
            continue
        if len(sentence) < 12 or len(_WORD_RE.findall(sentence)) < 3:
            continue
        identity = sentence.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        sentences.append(sentence)
    return sentences


def _replace_section(text: str, heading: str, body: str) -> str:
    heading_match = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    if heading_match is None:
        return text
    next_heading = re.search(r"^#{1,2}\s+", text[heading_match.end() :], re.MULTILINE)
    end = (
        heading_match.end() + next_heading.start()
        if next_heading is not None
        else len(text)
    )
    return text[: heading_match.end()] + f"\n\n{body}\n\n" + text[end:]


def _resolve_raw_path(
    vault: Path, raw_path_value: Any
) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path_value, str) or not raw_path_value.strip():
        return None, "raw_path_missing_frontmatter"
    relative = Path(raw_path_value)
    if relative.is_absolute():
        return None, "raw_path_outside_vault"
    resolved = (vault / relative).resolve()
    try:
        resolved.relative_to(vault)
    except ValueError:
        return None, "raw_path_outside_vault"
    if not resolved.is_file():
        return None, "raw_path_not_file"
    return resolved, None


def _extract_raw_text(
    raw_path: Path,
    *,
    pdf_extractor: PdfExtractor,
) -> tuple[str | None, str | None]:
    suffix = raw_path.suffix.casefold()
    if suffix in TEXT_SUFFIXES:
        try:
            return raw_path.read_text(encoding="utf-8"), None
        except (OSError, UnicodeError):
            return None, "raw_text_read_failed"
    if suffix == ".pdf":
        try:
            return pdf_extractor.extract(raw_path), None
        except FileNotFoundError:
            return None, "pdf_extractor_unavailable"
        except (OSError, RuntimeError, UnicodeError):
            return None, "pdf_extraction_failed"
    return None, "unsupported_raw_type"


def _new_entry(
    *,
    vault: Path,
    page_path: Path,
    page_text: str,
    initial_eval: dict[str, Any],
    classification_route: str,
) -> dict[str, Any]:
    return {
        "page": _relative_path(vault, page_path),
        "status": "operator_review",
        "classification_route": classification_route,
        "reason_codes": [],
        "remediation_reasons": list(initial_eval["failures"]),
        "page_sha256_before": _sha256_text(page_text),
        "page_sha256_candidate": None,
        "page_sha256_after": None,
        "source_raw_sha256": None,
        "normalized_raw_sha256": None,
        "extracted_sentence_count": 0,
        "used_sentence_count": 0,
        "summary_sentence_digests": [],
        "key_point_sentence_digests": [],
        "initial_eval": initial_eval,
        "candidate_eval": None,
    }


def _build_page_candidate(
    vault: Path,
    page_path: Path,
    *,
    pdf_extractor: PdfExtractor,
    classification_route: str,
) -> tuple[dict[str, Any] | None, _Candidate | None]:
    page_text = page_path.read_text(encoding="utf-8")
    initial_eval = evaluate_source_page_substance(page_text)
    if initial_eval["pass"]:
        return None, None

    entry = _new_entry(
        vault=vault,
        page_path=page_path,
        page_text=page_text,
        initial_eval=initial_eval,
        classification_route=classification_route,
    )
    if classification_route in {"no_action", "retained_operator_review"}:
        entry["reason_codes"] = ["classification_requires_operator_review"]
        return entry, None
    try:
        frontmatter = parse_frontmatter(page_text)
    except ValueError:
        entry["reason_codes"] = ["invalid_frontmatter"]
        return entry, None
    raw_path, path_error = _resolve_raw_path(vault, (frontmatter or {}).get("raw_path"))
    if path_error is not None or raw_path is None:
        entry["reason_codes"] = [path_error]
        return entry, None

    raw_bytes = raw_path.read_bytes()
    raw_sha256 = _sha256_bytes(raw_bytes)
    entry["source_raw_sha256"] = raw_sha256
    raw_text, extraction_error = _extract_raw_text(
        raw_path, pdf_extractor=pdf_extractor
    )
    if extraction_error is not None or raw_text is None:
        entry["reason_codes"] = [extraction_error]
        return entry, None
    if _sha256_bytes(raw_path.read_bytes()) != raw_sha256:
        entry["reason_codes"] = ["raw_changed_during_extraction"]
        return entry, None

    normalized_raw = _normalize_raw_text(
        raw_text, markdown=raw_path.suffix.casefold() in {".md", ".markdown"}
    )
    sentences = extract_complete_sentences(normalized_raw)
    entry["normalized_raw_sha256"] = _sha256_text(normalized_raw)
    entry["extracted_sentence_count"] = len(sentences)

    failures = set(initial_eval["failures"])
    repair_summary = bool(failures & SUMMARY_FAILURES)
    repair_key_points = bool(failures & KEY_POINT_FAILURES)
    if not repair_summary and not repair_key_points:
        entry["reason_codes"] = ["no_supported_section_repair"]
        return entry, None
    if repair_summary and len(sentences) < 2:
        entry["reason_codes"].append("insufficient_summary_sentences")
    if repair_key_points and len(sentences) < 4:
        entry["reason_codes"].append("insufficient_key_point_sentences")
    if entry["reason_codes"]:
        return entry, None

    summary_sentences = sentences[:2] if repair_summary else []
    key_point_sentences = sentences[:4] if repair_key_points else []
    candidate_text = page_text
    if repair_summary:
        candidate_text = _replace_section(
            candidate_text, "Summary", " ".join(summary_sentences)
        )
    if repair_key_points:
        candidate_text = _replace_section(
            candidate_text,
            "Key points",
            "\n".join(f"- {sentence}" for sentence in key_point_sentences),
        )

    used_sentences = list(dict.fromkeys(summary_sentences + key_point_sentences))
    fidelity_ok = all(sentence in normalized_raw for sentence in used_sentences)
    entry["used_sentence_count"] = len(used_sentences)
    entry["summary_sentence_digests"] = [
        _sha256_text(sentence) for sentence in summary_sentences
    ]
    entry["key_point_sentence_digests"] = [
        _sha256_text(sentence) for sentence in key_point_sentences
    ]
    if not fidelity_ok:
        entry["reason_codes"] = ["raw_fidelity_failed"]
        return entry, None

    candidate_eval = evaluate_source_page_substance(candidate_text)
    entry["candidate_eval"] = candidate_eval
    entry["page_sha256_candidate"] = _sha256_text(candidate_text)
    if not candidate_eval["pass"]:
        entry["reason_codes"] = ["candidate_eval_failed"]
        return entry, None

    entry["status"] = "candidate_ready"
    entry["reason_codes"] = ["deterministic_raw_repair_candidate"]
    return (
        entry,
        _Candidate(
            page_path=page_path,
            before_text=page_text,
            after_text=candidate_text,
            raw_path=raw_path,
            raw_sha256=raw_sha256,
        ),
    )


def _report_status(entries: Sequence[dict[str, Any]]) -> str:
    if any(entry["status"] == "operator_review" for entry in entries):
        return "operator_review"
    return "ready"


def _raw_input_paths(vault: Path, pages: Sequence[Path]) -> list[str]:
    raw_paths: list[str] = []
    for page_path in pages:
        try:
            frontmatter = parse_frontmatter(page_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        raw_path = (frontmatter or {}).get("raw_path")
        if not isinstance(raw_path, str) or Path(raw_path).is_absolute():
            continue
        if (vault / raw_path).is_file() and raw_path not in raw_paths:
            raw_paths.append(raw_path)
    return sorted(raw_paths)


def _canonical_envelope(
    vault: Path,
    *,
    context: RuntimeContext,
    pages: Sequence[Path],
    source_command: str,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    policy, resolved_policy_path = load_policy(vault)
    envelope = build_canonical_report_envelope(
        vault,
        generated_at=context.isoformat_z(),
        artifact_kind="source_substance_cohort_remediation",
        producer=PRODUCER,
        source_command=source_command,
        resolved_policy_path=resolved_policy_path,
        schema_path=SCHEMA_PATH,
        source_paths=[
            "ops/scripts/registry/source_substance_cohort_remediate.py",
            "ops/scripts/registry/source_substance_cohort_classify.py",
            "ops/scripts/eval/source_page_substance_runtime.py",
        ],
        path_group_inputs={
            "source_pages": [report_path(vault, page_path) for page_path in pages],
            "raw_sources": _raw_input_paths(vault, pages),
        },
    )
    return envelope, policy, resolved_policy_path


def build_remediation(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    pdf_extractor: PdfExtractor | None = None,
) -> RemediationBuild:
    resolved_vault = vault.resolve()
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    extractor = pdf_extractor or SubprocessPdfExtractor()
    pages = _discover_source_pages(resolved_vault)
    classification = build_classification_report(
        resolved_vault,
        context=runtime_context,
    )
    classification_routes = {
        str(entry["page"]): str(entry["remediation_route"])
        for entry in classification["entries"]
        if isinstance(entry, dict)
    }
    entries: list[dict[str, Any]] = []
    candidates: list[_Candidate] = []
    for page_path in pages:
        entry, candidate = _build_page_candidate(
            resolved_vault,
            page_path,
            pdf_extractor=extractor,
            classification_route=classification_routes.get(
                _relative_path(resolved_vault, page_path),
                "operator_review",
            ),
        )
        if entry is not None:
            entries.append(entry)
        if candidate is not None:
            candidates.append(candidate)

    envelope, policy, resolved_policy_path = _canonical_envelope(
        resolved_vault,
        context=runtime_context,
        pages=pages,
        source_command=SOURCE_COMMAND,
    )
    report = {
        **envelope,
        "schema_version": 1,
        "vault": report_path(resolved_vault, resolved_vault),
        "policy": {
            "path": report_path(resolved_vault, resolved_policy_path),
            "version": policy.get("version"),
        },
        "artifact_kind": "source_substance_cohort_remediation",
        "mode": "dry_run",
        "status": _report_status(entries),
        "summary": {
            "source_pages_scanned": len(pages),
            "failed_pages": len(entries),
            "candidate_ready": len(candidates),
            "applied": 0,
            "operator_review": sum(
                entry["status"] == "operator_review" for entry in entries
            ),
        },
        "entries": entries,
    }
    validate_or_raise(
        report,
        load_schema_with_vault_override(resolved_vault, SCHEMA_PATH),
        "source substance cohort remediation report",
    )
    return RemediationBuild(report=report, candidates=tuple(candidates))


def apply_remediation(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    pdf_extractor: PdfExtractor | None = None,
) -> dict[str, Any]:
    build = build_remediation(vault, context=context, pdf_extractor=pdf_extractor)
    resolved_vault = vault.resolve()
    for candidate in build.candidates:
        current_text = candidate.page_path.read_text(encoding="utf-8")
        if _sha256_text(current_text) != _sha256_text(candidate.before_text):
            raise RuntimeError(
                f"source page changed during remediation: "
                f"{_relative_path(resolved_vault, candidate.page_path)}"
            )
        if _sha256_bytes(candidate.raw_path.read_bytes()) != candidate.raw_sha256:
            raise RuntimeError(
                f"raw source changed during remediation: "
                f"{_relative_path(resolved_vault, candidate.raw_path)}"
            )
    atomic_multi_write(
        [
            AtomicTextUpdate(path=candidate.page_path, text=candidate.after_text)
            for candidate in build.candidates
        ]
    )

    report = build.report
    report["mode"] = "apply"
    report["source_command"] = f"{SOURCE_COMMAND} --apply"
    report["summary"]["applied"] = len(build.candidates)
    report["summary"]["candidate_ready"] = 0
    for entry in report["entries"]:
        if entry["status"] != "candidate_ready":
            continue
        page_path = resolved_vault / entry["page"]
        entry["status"] = "applied"
        entry["reason_codes"] = ["atomic_raw_repair_applied"]
        entry["page_sha256_after"] = _sha256_text(page_path.read_text(encoding="utf-8"))
    report["status"] = _report_status(report["entries"])
    runtime_context = context or RuntimeContext(display_timezone=dt.UTC)
    refreshed, _policy, _resolved_policy_path = _canonical_envelope(
        resolved_vault,
        context=runtime_context,
        pages=_discover_source_pages(resolved_vault),
        source_command=f"{SOURCE_COMMAND} --apply",
    )
    for key in (
        "$schema",
        "generated_at",
        "source_revision",
        "source_tree_fingerprint",
        "input_fingerprints",
        "currentness",
    ):
        report[key] = refreshed[key]
    validate_or_raise(
        report,
        load_schema_with_vault_override(resolved_vault, SCHEMA_PATH),
        "source substance cohort remediation report",
    )
    return report


def write_report(
    vault: Path,
    report: dict[str, Any],
    out_path: str | None = None,
) -> Path:
    return write_schema_backed_report(
        SchemaBackedReportWriteRequest(
            vault=vault,
            payload=report,
            schema_path=SCHEMA_PATH,
            out_path=out_path,
            default_relative_path=DEFAULT_OUT,
            context="source substance cohort remediation schema validation failed",
        )
    )


def build_report(
    vault: Path,
    *,
    context: RuntimeContext | None = None,
    pdf_extractor: PdfExtractor | None = None,
) -> dict[str, Any]:
    return build_remediation(vault, context=context, pdf_extractor=pdf_extractor).report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic raw-backed repairs for failing source page substance. "
            "The default is a no-write JSON dry run."
        )
    )
    parser.add_argument("--vault", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    vault = Path(args.vault)
    report = apply_remediation(vault) if args.apply else build_report(vault)
    if args.out:
        print(report_path(vault.resolve(), write_report(vault, report, args.out)))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
