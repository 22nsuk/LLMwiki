from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline

from ops.scripts.eval.wikilink_runtime import WIKILINK_RE

from .raw_intake_input_runtime import IntakeFile, read_intake_file


def corpus_page_paths(vault: Path) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {}
    for root in ("wiki", "system"):
        for path in (vault / root).glob("*.md"):
            paths.setdefault(path.stem, []).append(path.relative_to(vault).as_posix())
    return paths


def _resolve_page(page_paths: dict[str, list[str]], ref: str) -> tuple[str, str]:
    """Resolve an explicit corpus path or a unique flat page stem, never a family label."""
    path = PurePosixPath(ref)
    if not ref or "\\" in ref or path.is_absolute() or ".." in path.parts:
        return "", "invalid_page_reference"
    if len(path.parts) > 1:
        if path.parts[0] not in {"wiki", "system"} or path.suffix not in {"", ".md"}:
            return "", "invalid_page_reference"
        candidate = path if path.suffix == ".md" else PurePosixPath(f"{path}.md")
        return candidate.as_posix(), "resolved"
    stem = path.stem if path.suffix == ".md" else ref
    candidates = page_paths.get(stem, [])
    if len(candidates) == 1:
        return candidates[0], "resolved"
    return "", "ambiguous_page_reference" if candidates else "unresolved_page_reference"


def _wikilink_rule(state: StateInline, silent: bool) -> bool:
    match = WIKILINK_RE.match(state.src, state.pos, state.posMax)
    if match is None:
        return False
    if not silent:
        token = state.push("wikilink", "", 0)
        token.content = match[1]
    state.pos = match.end()
    return True


def _body_evidence(text: str) -> tuple[bool, list[str]]:
    """Read prose and wikilinks from Markdown structure, not rendered text.

    Recognize wikilinks during inline parsing so escaped/entity-decoded brackets,
    code, comments and link destinations cannot manufacture evidence.
    """
    text = re.sub(r"\A---\s*\n.*?\n---\s*(?:\n|$)", "", text, flags=re.DOTALL)
    parser = MarkdownIt("commonmark").enable("table")
    parser.inline.ruler.before("link", "wikilink", _wikilink_rule)
    has_prose = False
    links: list[str] = []
    for block in parser.parse(text):
        if block.type != "inline":
            continue
        for token in block.children or []:
            if token.type in {"text", "wikilink"} and token.content.strip():
                has_prose = True
            if token.type == "wikilink":
                links.append(token.content)
    return has_prose, links


def _check(name: str, expected: str, observed: str) -> dict[str, str]:
    return {
        "name": name,
        "status": "pass" if expected == observed else "fail",
        "expected": expected,
        "observed": observed,
    }


def absorption_audit(
    vault: Path,
    entry: dict[str, Any],
    inputs: dict[str, IntakeFile],
    page_paths: dict[str, list[str]],
) -> dict[str, Any]:
    action = str(entry.get("proposed_action") or "").strip()
    audit: dict[str, Any] = {
        "status": "not_applicable",
        "target_page": "",
        "checks": [],
    }
    if action == "discard_from_active_routes":
        return audit
    source = str(entry.get("source_page") or "").strip()
    source_path, source_resolution = _resolve_page(page_paths, source)
    source_file = inputs[source]
    source_status = source_file.status
    if (
        source_resolution != "resolved"
        or source != source_path
        or not Path(source_path).stem.startswith("source--")
    ):
        source_status = "invalid_source_page"
    elif source_status == "present":
        has_prose, _ = _body_evidence(source_file.text)
        if not has_prose:
            source_status = "empty_source_page"
    checks = audit["checks"]
    checks.append(_check("source_page_readable", "present", source_status))
    if action != "keep_source_only_seed":
        ref = str(entry.get("target_page") or entry.get("target") or "").strip()
        target_path, resolution = _resolve_page(page_paths, ref)
        audit["target_page"] = target_path
        checks.append(_check("target_page_resolved", "resolved", resolution))
        if target_path:
            if target_path not in inputs:
                inputs[target_path] = read_intake_file(vault, target_path)
            target_file = inputs[target_path]
            checks.append(_check("target_page_readable", "present", target_file.status))
            if action == "update_existing_source":
                checks.append(_check("updated_source_target", source_path, target_path))
            else:
                target_kind = (
                    "concept_or_synthesis"
                    if Path(target_path).stem.startswith(("concept--", "synthesis--"))
                    else "other"
                )
                checks.append(
                    _check(
                        "absorption_target_kind", "concept_or_synthesis", target_kind
                    )
                )
                _, links = _body_evidence(target_file.text)
                linked = any(
                    _resolve_page(page_paths, link) == (source_path, "resolved")
                    for link in links
                )
                checks.append(
                    _check(
                        "target_links_source",
                        "linked",
                        "linked" if linked else "not_linked",
                    )
                )
    if any(check["status"] == "fail" for check in checks):
        audit["status"] = "fail"
    elif action != "keep_source_only_seed":
        audit["status"] = "pass"
    return audit


def absorption_content_inputs(
    audits: list[dict[str, Any]],
    inputs: dict[str, IntakeFile],
    page_paths: dict[str, list[str]],
) -> dict[str, str]:
    paths = sorted({audit["target_page"] for audit in audits if audit["target_page"]})
    manifest = [
        {"path": path, "status": inputs[path].status, "sha256": inputs[path].sha256}
        for path in paths
    ]
    return {
        "target_pages": json.dumps(manifest, sort_keys=True, ensure_ascii=False),
        "absorption_page_paths": json.dumps(
            sorted(path for paths in page_paths.values() for path in paths),
            ensure_ascii=False,
        ),
    }
