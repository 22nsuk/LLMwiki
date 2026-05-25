from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from ops.scripts.policy_runtime import report_path
from ops.scripts.yaml_runtime import parse_simple_yaml

FRONTMATTER_FIELD_ORDER = [
    "title",
    "source",
    "author",
    "published",
    "created",
    "description",
    "tags",
]
REQUIRED_METADATA_FIELDS = ("title", "source", "published", "created")
OPTIONAL_METADATA_FIELDS = ("author", "description", "tags")
TRANSPORT_HEADER_PREFIXES = (
    "Title:",
    "URL Source:",
    "Published Time:",
    "Number of Pages:",
    "Markdown Content:",
)
COOKIE_BLOCK_START_MARKERS = (
    "[](https://www.cookiebot.com/",
    "This website uses cookies",
    "Consent Selection",
)
COOKIE_BLOCK_END_MARKERS = (
    "Allow all Customize Allow selection Deny",
)
COOKIE_NOISE_MARKERS = (
    "cookiebot.com",
    "This website uses cookies",
    "Consent Selection",
    "[#GPC_",
    "[[#IABV2SETTINGS#]]",
    "[#IABV2_",
    "Cookie declaration last updated",
    "Please state your consent ID and date",
    "Allow all Customize Allow selection Deny",
    "Do not sell or share my personal information",
    "[Cross-domain consent",
    "List of domains your consent applies to:",
)
COOKIE_OPTION_RE = re.compile(
    r"^(?:\*\*(?:Necessary|Preferences|Statistics|Marketing)\*\*|"
    r"(?:Necessary|Preferences|Statistics|Marketing)\s+\d+-\s+\[x\]|"
    r"-\s+\[x\]\s*)$"
)
TITLE_LINE_RE = re.compile(r"^Title:\s*(.+?)\s*$", re.MULTILINE)
URL_SOURCE_LINE_RE = re.compile(r"^URL Source:\s*(https?://\S+)\s*$", re.MULTILINE)
URL_LINE_RE = re.compile(r"^- URL:\s*(https?://\S+)\s*$", re.MULTILINE)
ABSOLUTE_URL_RE = re.compile(r"https?://[^\s)>]+")
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
PUBLISHED_TIME_RE = re.compile(r"^Published Time:\s*(.+?)\s*$", re.MULTILINE)
LAST_UPDATED_RE = re.compile(r"^\*\*Last Updated:\*\*\s*(.+?)(?:\s*\|.*)?\s*$", re.MULTILINE)
CAPTURE_DATE_RE = re.compile(r"^- Capture date:\s*(.+?)\s*$", re.MULTILINE)
URL_DATE_RE = re.compile(r"/(20\d{2})[-_/](\d{2})[-_/](\d{2})(?:[/?#]|$)")
BLOB_LOCALHOST_RE = re.compile(r"^.*blob:http://localhost[^\n]*\n?", re.MULTILINE)
REPLACEMENT_CHAR = "\ufffd"


@dataclass(frozen=True)
class RawMarkdownDocument:
    path: Path
    text: str
    frontmatter_present: bool
    frontmatter: dict[str, Any]
    body: str


@dataclass(frozen=True)
class RawMarkdownQualityReport:
    path: str
    frontmatter_present: bool
    missing_title: bool
    missing_source: bool
    blank_published: bool
    blank_created: bool
    transport_noise_present: bool
    cookie_noise_present: bool
    blob_noise_present: bool
    replacement_char_present: bool
    manual_review_required: bool
    manual_review_reasons: list[str]


@dataclass(frozen=True)
class RawMarkdownNormalizationResult:
    path: str
    changed: bool
    frontmatter_present_before: bool
    pre_sha256: str
    post_sha256: str
    metadata: dict[str, Any]
    removed_noise_classes: list[str]
    manual_review_required: bool
    manual_review_reasons: list[str]
    quality: RawMarkdownQualityReport
    text: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_frontmatter(text: str) -> tuple[bool, dict[str, Any], str]:
    normalized = _normalized_newlines(text)
    if not normalized.startswith("---\n"):
        return False, {}, normalized

    marker = "\n---\n"
    end_index = normalized.find(marker, 4)
    if end_index == -1:
        return False, {}, normalized

    frontmatter_text = normalized[4:end_index]
    body = normalized[end_index + len(marker) :]
    try:
        frontmatter = parse_simple_yaml(frontmatter_text)
    except Exception:  # broad-exception: tolerant_parse_boundary
        return False, {}, normalized
    return True, frontmatter, body


def load_raw_markdown_document(path: Path) -> RawMarkdownDocument:
    text = _normalized_newlines(path.read_text(encoding="utf-8"))
    frontmatter_present, frontmatter, body = split_frontmatter(text)
    return RawMarkdownDocument(
        path=path,
        text=text,
        frontmatter_present=frontmatter_present,
        frontmatter=frontmatter,
        body=body,
    )


def iter_raw_markdown_paths(base_path: Path) -> list[Path]:
    if base_path.is_file():
        return [base_path] if base_path.suffix.lower() == ".md" else []
    if not base_path.exists():
        return []
    return sorted(path for path in base_path.rglob("*.md") if path.is_file())


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = _string_value(item)
            if text is not None:
                result.append(text)
        return result
    text = _string_value(value)
    return [text] if text is not None else []


def _humanize_filename(path: Path) -> str | None:
    stem = path.stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or None


def _normalized_title_token(value: str | None) -> str:
    if not value:
        return ""
    collapsed = re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip().lower()
    collapsed = re.sub(r"[^0-9a-z가-힣]+", "", collapsed)
    return collapsed


def _parse_date_to_iso(value: str | None) -> str | None:
    text = _string_value(value)
    if text is None:
        return None
    if text.lower() == "unknown":
        return "unknown"

    normalized = text.replace("\u00a0", " ").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(normalized, fmt).date().isoformat()
        except ValueError:
            continue

    try:
        return parsedate_to_datetime(normalized).date().isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _extract_title(document: RawMarkdownDocument) -> str | None:
    frontmatter_title = _string_value(document.frontmatter.get("title"))
    if frontmatter_title is not None:
        return frontmatter_title

    match = TITLE_LINE_RE.search(document.body)
    if match:
        value = _string_value(match.group(1))
        if value is not None:
            return value

    match = H1_RE.search(document.body)
    if match:
        value = _string_value(match.group(1))
        if value is not None:
            return value

    return _humanize_filename(document.path)


def _extract_source(document: RawMarkdownDocument) -> str | None:
    frontmatter_source = _string_value(document.frontmatter.get("source"))
    if frontmatter_source is not None:
        return frontmatter_source

    match = URL_SOURCE_LINE_RE.search(document.body)
    if match:
        value = _string_value(match.group(1))
        if value is not None:
            return value

    match = URL_LINE_RE.search(document.body)
    if match:
        value = _string_value(match.group(1))
        if value is not None:
            return value

    match = ABSOLUTE_URL_RE.search(document.body)
    if match:
        value = _string_value(match.group(0))
        if value is not None:
            return value

    return None


def _extract_published(document: RawMarkdownDocument) -> str | None:
    frontmatter_published = _string_value(document.frontmatter.get("published"))
    if frontmatter_published is not None:
        normalized = _parse_date_to_iso(frontmatter_published)
        return normalized or frontmatter_published

    match = PUBLISHED_TIME_RE.search(document.body)
    if match:
        value = _parse_date_to_iso(match.group(1))
        if value is not None:
            return value

    match = LAST_UPDATED_RE.search(document.body)
    if match:
        value = _parse_date_to_iso(match.group(1))
        if value is not None:
            return value

    source = _extract_source(document)
    if source:
        match = URL_DATE_RE.search(source)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    return "unknown"


def _extract_created(document: RawMarkdownDocument) -> str | None:
    frontmatter_created = _string_value(document.frontmatter.get("created"))
    if frontmatter_created is not None:
        normalized = _parse_date_to_iso(frontmatter_created)
        return normalized or frontmatter_created

    match = CAPTURE_DATE_RE.search(document.body)
    if match:
        value = _parse_date_to_iso(match.group(1))
        if value is not None:
            return value

    return "unknown"


def _preserved_frontmatter_metadata(document: RawMarkdownDocument) -> dict[str, Any]:
    preserved: dict[str, Any] = {}
    for key, value in document.frontmatter.items():
        if key == "tags":
            preserved[key] = _list_value(value)
            continue
        preserved[key] = value
    return preserved


def _frontmatter_field_changed(current: Any, target: Any, *, key: str) -> bool:
    if key == "tags":
        return _list_value(current) != _list_value(target)
    return _string_value(current) != _string_value(target)


def _metadata_changed(document: RawMarkdownDocument, metadata: dict[str, Any]) -> bool:
    if not document.frontmatter_present:
        return True
    for key, target in metadata.items():
        if _frontmatter_field_changed(document.frontmatter.get(key), target, key=key):
            return True
    return False


def _body_changed(original: str, cleaned: str) -> bool:
    return _normalized_newlines(original).rstrip("\n") != _normalized_newlines(cleaned).rstrip("\n")


def _build_normalized_metadata(document: RawMarkdownDocument) -> dict[str, Any]:
    metadata = _preserved_frontmatter_metadata(document)
    metadata["title"] = _extract_title(document)
    metadata["source"] = _extract_source(document)
    metadata["published"] = _extract_published(document) or "unknown"
    metadata["created"] = _extract_created(document) or "unknown"
    return metadata


def _leading_transport_header_range(lines: list[str]) -> tuple[int, list[str]]:
    index = 0
    removed: list[str] = []
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if any(stripped.startswith(prefix) for prefix in TRANSPORT_HEADER_PREFIXES):
            removed.append(stripped)
            index += 1
            continue
        break
    return index, removed


def _strip_transport_headers(body: str) -> tuple[str, bool]:
    lines = body.splitlines()
    index, removed = _leading_transport_header_range(lines)
    if not removed:
        return body, False
    return "\n".join(lines[index:]), True


def _strip_cookie_block(body: str) -> tuple[str, bool]:
    lines = body.splitlines()
    start_index: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if any(marker in stripped for marker in COOKIE_BLOCK_START_MARKERS):
            start_index = index
            break
    if start_index is None:
        return body, False

    end_index: int | None = None
    for index in range(start_index, len(lines)):
        stripped = lines[index].strip()
        if any(marker in stripped for marker in COOKIE_BLOCK_END_MARKERS):
            end_index = index + 1
            break
        if index > start_index and H1_RE.match(stripped):
            end_index = index
            break
    if end_index is None:
        end_index = len(lines)
    return "\n".join(lines[:start_index] + lines[end_index:]), True


def _strip_blob_localhost(body: str) -> tuple[str, bool]:
    updated, count = BLOB_LOCALHOST_RE.subn("", body)
    return updated, count > 0


def _strip_duplicate_preface(body: str, title: str | None) -> str:
    if not title:
        return body
    title_token = _normalized_title_token(title)
    if not title_token:
        return body

    matches = list(H1_RE.finditer(body))
    title_matches = [
        match
        for match in matches
        if _normalized_title_token(match.group(1)) == title_token
    ]
    if len(title_matches) < 2:
        return body
    return body[title_matches[-1].start() :]


def _cleanup_body(body: str, *, title: str | None) -> tuple[str, list[str]]:
    removed_noise_classes: list[str] = []
    updated = body

    updated, removed_transport = _strip_transport_headers(updated)
    if removed_transport:
        removed_noise_classes.append("transport_header")

    updated, removed_cookie = _strip_cookie_block(updated)
    if removed_cookie:
        removed_noise_classes.append("cookie_banner")

    updated, removed_blob = _strip_blob_localhost(updated)
    if removed_blob:
        removed_noise_classes.append("blob_localhost")

    updated = _strip_duplicate_preface(updated, title)
    updated = updated.strip("\n")
    if updated:
        updated += "\n"
    else:
        updated = ""
    return updated, removed_noise_classes


def _render_frontmatter(metadata: dict[str, Any]) -> str:
    ordered_keys = [key for key in FRONTMATTER_FIELD_ORDER if key in metadata]
    ordered_keys.extend(key for key in metadata if key not in ordered_keys)

    lines = ["---"]
    for key in ordered_keys:
        value = metadata[key]
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(str(item), ensure_ascii=False)}")
            continue
        scalar = _string_value(value)
        if scalar is None:
            lines.append(f"{key}:")
            continue
        lines.append(f"{key}: {json.dumps(str(scalar), ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def _compose_text(metadata: dict[str, Any], body: str) -> str:
    frontmatter = _render_frontmatter(metadata)
    if body:
        return f"{frontmatter}\n\n{body.lstrip()}"
    return f"{frontmatter}\n"


def raw_markdown_quality_report(vault: Path, path: Path) -> RawMarkdownQualityReport:
    document = load_raw_markdown_document(path)
    body = document.body
    title = _string_value(document.frontmatter.get("title"))
    source = _string_value(document.frontmatter.get("source"))
    published = _string_value(document.frontmatter.get("published"))
    created = _string_value(document.frontmatter.get("created"))

    transport_noise_present = any(
        body_line.strip().startswith(prefix)
        for body_line in body.splitlines()
        for prefix in TRANSPORT_HEADER_PREFIXES
    )
    cookie_noise_present = any(
        marker in body
        for marker in COOKIE_NOISE_MARKERS
    ) or any(COOKIE_OPTION_RE.match(line.strip()) for line in body.splitlines())
    blob_noise_present = "blob:http://localhost" in body
    replacement_char_present = REPLACEMENT_CHAR in body
    manual_review_reasons: list[str] = []
    if replacement_char_present:
        manual_review_reasons.append("replacement_char")
    if source is None:
        manual_review_reasons.append("missing_source")

    return RawMarkdownQualityReport(
        path=report_path(vault, path),
        frontmatter_present=document.frontmatter_present,
        missing_title=title is None,
        missing_source=source is None,
        blank_published=published is None,
        blank_created=created is None,
        transport_noise_present=transport_noise_present,
        cookie_noise_present=cookie_noise_present,
        blob_noise_present=blob_noise_present,
        replacement_char_present=replacement_char_present,
        manual_review_required=bool(manual_review_reasons),
        manual_review_reasons=manual_review_reasons,
    )


def normalize_raw_markdown_file(vault: Path, path: Path) -> RawMarkdownNormalizationResult:
    document = load_raw_markdown_document(path)
    metadata = _build_normalized_metadata(document)
    cleaned_body, removed_noise_classes = _cleanup_body(document.body, title=_string_value(metadata.get("title")))

    manual_review_reasons: list[str] = []
    if REPLACEMENT_CHAR in cleaned_body:
        manual_review_reasons.append("replacement_char")
    if _string_value(metadata.get("source")) is None:
        manual_review_reasons.append("missing_source")

    semantic_change = _metadata_changed(document, metadata) or _body_changed(document.body, cleaned_body)
    normalized_text = document.text
    if not document.frontmatter_present or semantic_change:
        normalized_text = _compose_text(metadata, cleaned_body)
    pre_sha256 = _sha256_text(document.text)
    post_sha256 = _sha256_text(normalized_text)

    return RawMarkdownNormalizationResult(
        path=report_path(vault, path),
        changed=document.text != normalized_text,
        frontmatter_present_before=document.frontmatter_present,
        pre_sha256=pre_sha256,
        post_sha256=post_sha256,
        metadata=metadata,
        removed_noise_classes=removed_noise_classes,
        manual_review_required=bool(manual_review_reasons),
        manual_review_reasons=manual_review_reasons,
        quality=raw_markdown_quality_report(vault, path),
        text=normalized_text,
    )


def apply_raw_markdown_normalization(vault: Path, path: Path) -> RawMarkdownNormalizationResult:
    result = normalize_raw_markdown_file(vault, path)
    if result.changed:
        path.write_text(result.text, encoding="utf-8")
    return result


def raw_markdown_quality_pass(
    vault: Path,
    *,
    emitter: Any,
    raw_markdown_contract: dict | None = None,
    base_path: Path | None = None,
) -> list[RawMarkdownQualityReport]:
    del raw_markdown_contract
    raw_root = base_path or vault / "raw"
    reports = [raw_markdown_quality_report(vault, path) for path in iter_raw_markdown_paths(raw_root)]

    for report in reports:
        page = report.path
        if not report.frontmatter_present:
            emitter.issue(
                {
                    "type": "raw_markdown_missing_frontmatter",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_missing_frontmatter",
            )
            continue

        if report.missing_title:
            emitter.issue(
                {
                    "type": "raw_markdown_missing_title",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_missing_title",
            )
        if report.missing_source:
            emitter.issue(
                {
                    "type": "raw_markdown_missing_source",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_missing_source",
            )
        if report.blank_published:
            emitter.issue(
                {
                    "type": "raw_markdown_blank_published",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_blank_published",
            )
        if report.blank_created:
            emitter.issue(
                {
                    "type": "raw_markdown_blank_created",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_blank_created",
            )
        if report.transport_noise_present:
            emitter.issue(
                {
                    "type": "raw_markdown_transport_noise",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_transport_noise",
            )
        if report.cookie_noise_present:
            emitter.issue(
                {
                    "type": "raw_markdown_cookie_noise",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_cookie_noise",
            )
        if report.blob_noise_present:
            emitter.issue(
                {
                    "type": "raw_markdown_blob_noise",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_blob_noise",
            )
        if report.replacement_char_present:
            emitter.issue(
                {
                    "type": "raw_markdown_replacement_char",
                    "page": page,
                    "detail": page,
                },
                "raw_markdown_replacement_char",
            )

    return reports
