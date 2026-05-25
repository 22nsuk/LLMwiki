from __future__ import annotations

import re
from pathlib import Path

from ops.scripts.policy_runtime import report_path

from .wiki_page_runtime import heading_body, load_text, section_body
from .wiki_quality_runtime import resolved_wikilink_targets

SUMMARY_COUNT_RE = re.compile(r"^\s*-\s*(?P<label>[^:]+):\s*`(?P<count>\d+)`\s*$", re.MULTILINE)
DEFAULT_EXTERNAL_REPORT_EXTENSIONS = (".pdf", ".docx")


def _summary_count(summary: str, label: str) -> int | None:
    for match in SUMMARY_COUNT_RE.finditer(summary):
        if match.group("label").strip() == label:
            return int(match.group("count"))
    return None


def _unique_wikilink_count(body: str | None, page_lookup: dict[str, str]) -> int:
    if not body:
        return 0
    return len(resolved_wikilink_targets(body, page_lookup))


def documentation_markdown_surfaces(vault: Path) -> list[tuple[str, Path]]:
    surfaces: list[tuple[str, Path]] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        relative = report_path(vault, path)
        if relative in seen:
            return
        seen.add(relative)
        surfaces.append((relative, path))

    for path in sorted(vault.glob("*.md")):
        add(path)
    for root_name in ("docs", "ops", "runs"):
        root = vault / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            add(path)

    return surfaces


def _registry_entry_count(registry_entries: list[dict], filters: dict[str, str] | None = None) -> int:
    if not filters:
        return len(registry_entries)
    return sum(
        1
        for entry in registry_entries
        if all(entry.get(key) == value for key, value in filters.items())
    )


def _actual_router_summary_metric(
    text: str,
    metric: dict,
    vault: Path,
    pages: dict[str, Path],
    page_lookup: dict[str, str],
    registry_entries: list[dict],
    *,
    relative_paths: dict[str, str] | None = None,
    prefix_count_cache: dict[str, int] | None = None,
) -> int:
    source = metric["source"]
    kind = source["kind"]
    if kind == "heading_unique_wikilinks":
        return _unique_wikilink_count(
            heading_body(text, source["heading"], level=source.get("heading_level", 3)),
            page_lookup,
        )
    if kind == "section_unique_wikilinks":
        return _unique_wikilink_count(section_body(text, source["section"]), page_lookup)
    if kind == "page_prefix_count":
        prefix = source["prefix"]
        if prefix_count_cache is not None and prefix in prefix_count_cache:
            return prefix_count_cache[prefix]
        page_relative_paths = (
            (
                relative_paths.get(stem)
                if relative_paths is not None
                else None
            )
            or report_path(vault, page_path)
            for stem, page_path in pages.items()
        )
        count = sum(1 for relative_path in page_relative_paths if relative_path.startswith(prefix))
        if prefix_count_cache is not None:
            prefix_count_cache[prefix] = count
        return count
    if kind == "registry_entry_count":
        return _registry_entry_count(registry_entries, source.get("filters"))
    raise ValueError(f"unsupported router summary metric kind: {kind}")


def router_summary_count_issues(
    vault: Path,
    pages: dict[str, Path],
    page_lookup: dict[str, str],
    registry_entries: list[dict],
    doc_audit_policy: dict,
    *,
    relative_paths: dict[str, str] | None = None,
) -> list[dict]:
    issues: list[dict] = []
    prefix_count_cache: dict[str, int] = {}
    router_targets = doc_audit_policy.get("router_summary_targets", [])
    for target in router_targets:
        page_relative = target["page"]
        target_path = vault / page_relative
        if not target_path.exists():
            continue
        text = load_text(target_path)
        summary = section_body(text, target.get("summary_section", "Summary")) or ""
        for metric in target["metrics"]:
            declared_count = _summary_count(summary, metric["label"])
            if declared_count is None:
                continue
            actual_count = _actual_router_summary_metric(
                text,
                metric,
                vault,
                pages,
                page_lookup,
                registry_entries,
                relative_paths=relative_paths,
                prefix_count_cache=prefix_count_cache,
            )
            if declared_count != actual_count:
                issues.append(
                    {
                        "type": "router_summary_count_drift",
                        "page": page_relative,
                        "detail": {
                            "label": metric["label"],
                            "declared": declared_count,
                            "actual": actual_count,
                        },
                    }
                )

    return issues


def _external_report_extensions(doc_audit_policy: dict | None) -> set[str]:
    configured = (
        doc_audit_policy.get("external_report_extensions", DEFAULT_EXTERNAL_REPORT_EXTENSIONS)
        if doc_audit_policy
        else DEFAULT_EXTERNAL_REPORT_EXTENSIONS
    )
    extensions: set[str] = set()
    for extension in configured:
        normalized = str(extension).strip().lower()
        if not normalized:
            continue
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        extensions.add(normalized)
    return extensions or set(DEFAULT_EXTERNAL_REPORT_EXTENSIONS)


def _known_external_report_names(vault: Path, doc_audit_policy: dict | None) -> list[str]:
    external_reports_dir = vault / "external-reports"
    if not external_reports_dir.exists():
        return []

    report_extensions = _external_report_extensions(doc_audit_policy)
    return sorted(
        path.name
        for path in external_reports_dir.iterdir()
        if path.is_file() and path.suffix.lower() in report_extensions
    )


def _external_report_reference_paths(basename: str) -> tuple[str, str]:
    return f"raw/{basename}", f"external-reports/{basename}"


def _corpus_external_report_surfaces(
    vault: Path,
    pages: dict[str, Path],
    relative_paths: dict[str, str] | None,
) -> list[tuple[str, Path]]:
    surfaces: list[tuple[str, Path]] = []
    for stem, path in sorted(pages.items(), key=lambda item: item[1].as_posix()):
        relative = relative_paths.get(stem) if relative_paths is not None else None
        if relative is None:
            relative = report_path(vault, path)
        if relative == "system/system-log.md":
            continue
        surfaces.append((relative, path))
    return surfaces


def _documentation_external_report_reference_issue(
    relative: str,
    basename: str,
    line: str,
    lineno: int,
) -> dict | None:
    raw_relative, external_relative = _external_report_reference_paths(basename)
    if basename not in line or external_relative in line:
        return None

    detail = {
        "basename": basename,
        "context": "documentation_surface_requires_external_reports_path",
        "line": lineno,
        "expected": external_relative,
    }
    if raw_relative in line:
        detail["found"] = raw_relative
    return {
        "type": "external_report_reference_mismatch",
        "page": relative,
        "detail": detail,
    }


def _documentation_external_report_reference_issues(
    documentation_surfaces: list[tuple[str, Path]],
    known_report_names: list[str],
) -> list[dict]:
    issues: list[dict] = []
    for relative, path in documentation_surfaces:
        text = load_text(path)
        for basename in known_report_names:
            for lineno, line in enumerate(text.splitlines(), start=1):
                issue = _documentation_external_report_reference_issue(
                    relative,
                    basename,
                    line,
                    lineno,
                )
                if issue is not None:
                    issues.append(issue)
    return issues


def _corpus_source_trace_external_report_issue(
    relative: str,
    basename: str,
    heading: str,
    body: str,
    *,
    raw_exists: bool,
) -> dict | None:
    raw_relative, external_relative = _external_report_reference_paths(basename)
    if not body or basename not in body:
        return None
    if external_relative in body and raw_exists:
        return {
            "type": "external_report_reference_mismatch",
            "page": relative,
            "detail": {
                "basename": basename,
                "section": heading,
                "expected": raw_relative,
                "found": external_relative,
            },
        }
    if raw_relative in body or external_relative in body:
        return None
    return {
        "type": "external_report_reference_mismatch",
        "page": relative,
        "detail": {
            "basename": basename,
            "section": heading,
            "context": "missing_canonical_prefix",
            "expected": [external_relative] + ([raw_relative] if raw_exists else []),
        },
    }


def _corpus_source_trace_external_report_issues(
    vault: Path,
    corpus_surfaces: list[tuple[str, Path]],
    known_report_names: list[str],
) -> list[dict]:
    issues: list[dict] = []
    for relative, path in corpus_surfaces:
        text = load_text(path)
        for basename in known_report_names:
            raw_relative, _ = _external_report_reference_paths(basename)
            raw_exists = (vault / raw_relative).exists()
            for heading in ("Source", "Source trace"):
                issue = _corpus_source_trace_external_report_issue(
                    relative,
                    basename,
                    heading,
                    section_body(text, heading) or "",
                    raw_exists=raw_exists,
                )
                if issue is not None:
                    issues.append(issue)
    return issues


def _manifest_external_report_reference_issues(
    vault: Path,
    known_report_names: list[str],
) -> list[dict]:
    manifest_path = vault / "ops" / "manifest.json"
    if not manifest_path.exists():
        return []

    issues: list[dict] = []
    manifest_text = manifest_path.read_text(encoding="utf-8")
    for basename in known_report_names:
        raw_relative, external_relative = _external_report_reference_paths(basename)
        raw_exists = (vault / raw_relative).exists()
        if basename not in manifest_text:
            continue
        if external_relative in manifest_text or (raw_exists and raw_relative in manifest_text):
            continue
        issues.append(
            {
                "type": "external_report_reference_mismatch",
                "page": "ops/manifest.json",
                "detail": {
                    "basename": basename,
                    "context": "stale_root_reference",
                    "expected": [external_relative] + ([raw_relative] if raw_exists else []),
                },
            }
        )
    return issues


def external_report_reference_issues(
    vault: Path,
    pages: dict[str, Path],
    *,
    doc_audit_policy: dict | None = None,
    relative_paths: dict[str, str] | None = None,
    documentation_surfaces: list[tuple[str, Path]] | None = None,
) -> list[dict]:
    """Detect inconsistencies between documentation and external-reports/ contents.

    This function serves as the canonical cross-reference validation for
    external reports.  A separate standalone manifest artifact is not required
    because validation is performed dynamically during doc audit.
    """
    known_report_names = _known_external_report_names(vault, doc_audit_policy)
    if not known_report_names:
        return []

    if documentation_surfaces is None:
        documentation_surfaces = documentation_markdown_surfaces(vault)
    corpus_surfaces = _corpus_external_report_surfaces(vault, pages, relative_paths)

    issues: list[dict] = []
    issues.extend(
        _documentation_external_report_reference_issues(
            documentation_surfaces,
            known_report_names,
        )
    )
    issues.extend(
        _corpus_source_trace_external_report_issues(
            vault,
            corpus_surfaces,
            known_report_names,
        )
    )
    issues.extend(_manifest_external_report_reference_issues(vault, known_report_names))
    return issues
