from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .raw_intake_promotion_bridge_runtime import suggest_bridge_sources_for_family
from .raw_intake_promotion_shared_runtime import (
    _frontmatter_value,
    _json_load_object,
    _section_items,
    _section_links,
    _split_subheading_blocks,
    _string_list,
    _titleize_slug,
)
from ops.scripts.schema_constants_runtime import RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH
from ops.scripts.wiki_page_runtime import section_body

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REVIEWED_ROUTE_STATUSES = {"approved", "reviewed"}


def _matrix_entries(payload: dict) -> list[dict]:
    matrix = payload.get("matrix")
    if not isinstance(matrix, list):
        raise ValueError("matrix artifact must contain a top-level 'matrix' list")
    return [entry for entry in matrix if isinstance(entry, dict)]


def _review_status(entry: dict) -> str:
    return str(entry.get("review_status", "")).strip().lower()


def _review_status_counts(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        status = _review_status(entry) or "missing"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _page_date(matrix_path: Path, payload: dict, explicit_page_date: str | None) -> str:
    if isinstance(explicit_page_date, str) and explicit_page_date.strip():
        return explicit_page_date.strip()
    generated_at = payload.get("generated_at")
    if isinstance(generated_at, str):
        match = _DATE_RE.search(generated_at)
        if match:
            return match.group(0)
    match = _DATE_RE.search(matrix_path.name)
    if match:
        return match.group(0)
    raise ValueError("could not infer page_date from matrix payload or filename")


def _stem_from_source_page(source_page: str) -> str:
    return Path(source_page).stem


def _extract_page_date_from_stem(stem: str) -> str:
    matches = _DATE_RE.findall(stem)
    return matches[-1] if matches else ""


def _default_refresh_profile(target_stem: str, items: list[dict]) -> dict:
    base_slug = target_stem.removeprefix("synthesis--")
    profile_date = _extract_page_date_from_stem(target_stem)
    if profile_date and base_slug.endswith(f"-{profile_date}"):
        base_slug = base_slug[: -(len(profile_date) + 1)]
    new_source_stems = [
        _stem_from_source_page(source_page)
        for source_page in (item.get("source_page") for item in items)
        if isinstance(source_page, str) and source_page.strip()
    ]
    return {
        "target_stem": target_stem,
        "registry_ids": [item.get("registry_id") for item in items if item.get("registry_id")],
        "synthesis": {
            "stem": target_stem,
            "title": f"{_titleize_slug(base_slug)} {profile_date}".strip(),
            "created": profile_date,
            "question": "",
            "short_answer": "",
            "source_stems": new_source_stems,
            "bridge_source_stems": [],
            "integration_note": "",
            "bridge_integration": {"kind": ""},
            "analysis_blocks": [
                {"heading": "", "body": "", "purpose": ""},
                {"heading": "", "body": "", "purpose": ""},
                {"heading": "", "body": "", "purpose": ""},
            ],
            "what_this_synthesis_excludes": [],
            "tensions_and_contradictions": [],
            "implications_for_future_ingest": [],
            "decision_or_takeaway": "",
            "follow_up_questions": [],
            "related_pages": [],
            "source_trace": [],
        },
    }


def _scaffold_refresh_profile(vault: Path, target_stem: str, items: list[dict]) -> dict:
    profile = _default_refresh_profile(target_stem, items)
    target_path = vault / "wiki" / f"{target_stem}.md"
    if not target_path.exists():
        return profile

    text = target_path.read_text(encoding="utf-8")
    new_source_stems = _string_list(profile["synthesis"].get("source_stems"))
    existing_source_stems = [
        stem for stem in _section_links(text, "Evidence considered") if stem.startswith("source--")
    ]
    bridge_source_stems = [stem for stem in existing_source_stems if stem not in set(new_source_stems)]

    synthesis = profile["synthesis"]
    synthesis["title"] = _frontmatter_value(text, "title") or synthesis["title"]
    synthesis["created"] = _frontmatter_value(text, "created") or synthesis["created"]
    synthesis["question"] = (section_body(text, "Question") or "").strip()
    synthesis["short_answer"] = (section_body(text, "Short answer") or "").strip()
    synthesis["bridge_source_stems"] = bridge_source_stems
    synthesis["analysis_blocks"] = _split_subheading_blocks(section_body(text, "Analysis") or "")
    synthesis["what_this_synthesis_excludes"] = _section_items(text, "What this synthesis excludes")
    synthesis["tensions_and_contradictions"] = _section_items(text, "Tensions / contradictions")
    synthesis["implications_for_future_ingest"] = _section_items(text, "Implications for future ingest")
    synthesis["decision_or_takeaway"] = (section_body(text, "Decision / takeaway") or "").strip()
    synthesis["follow_up_questions"] = _section_items(text, "Follow-up questions")
    synthesis["related_pages"] = _section_links(text, "Related pages")
    synthesis["source_trace"] = _section_items(text, "Source trace")
    return profile


def _reviewed_route_groups(
    entries: list[dict],
) -> tuple[dict[str, list[dict]], dict[str, list[dict]], int]:
    reviewed_entries = [
        entry for entry in entries if _review_status(entry) in REVIEWED_ROUTE_STATUSES
    ]
    target_groups: dict[str, list[dict]] = defaultdict(list)
    refresh_groups: dict[str, list[dict]] = defaultdict(list)
    for entry in reviewed_entries:
        target = entry.get("target")
        if not isinstance(target, str) or not target.strip():
            continue
        if entry.get("proposed_action") == "create_new_synthesis_family":
            target_groups[target.strip()].append(entry)
        elif entry.get("proposed_action") == "refresh_existing_synthesis":
            refresh_groups[target.strip()].append(entry)
    return target_groups, refresh_groups, len(entries) - len(reviewed_entries)


def _source_stems(items: list[dict]) -> list[str]:
    return [
        _stem_from_source_page(source_page)
        for source_page in (item.get("source_page") for item in items)
        if isinstance(source_page, str) and source_page.strip()
    ]


def _new_family_profile(
    *,
    vault: Path | None,
    family_slug: str,
    items: list[dict],
    profile_date: str,
    bridge_limit: int,
) -> dict:
    source_stems = _source_stems(items)
    bridge_candidates = (
        suggest_bridge_sources_for_family(
            vault,
            family_slug,
            exclude_source_stems=source_stems,
            limit=bridge_limit,
        )
        if vault is not None
        else []
    )
    bridge_source_stems = [candidate["source_stem"] for candidate in bridge_candidates]
    return {
        "family_slug": family_slug,
        "registry_ids": [item.get("registry_id") for item in items if item.get("registry_id")],
        "bridge_source_candidates": bridge_candidates,
        "synthesis": {
            "stem": f"synthesis--{family_slug}-{profile_date}",
            "title": f"{_titleize_slug(family_slug)} {profile_date}",
            "created": profile_date,
            "question": "",
            "short_answer": "",
            "source_stems": source_stems,
            "bridge_source_stems": bridge_source_stems,
            "integration_note": "",
            "bridge_integration": {"kind": ""},
            "analysis_blocks": [
                {"heading": "", "body": "", "purpose": ""},
                {"heading": "", "body": "", "purpose": ""},
                {"heading": "", "body": "", "purpose": ""},
            ],
            "what_this_synthesis_excludes": [],
            "tensions_and_contradictions": [],
            "implications_for_future_ingest": [],
            "decision_or_takeaway": "",
            "follow_up_questions": [],
            "related_pages": [],
            "source_trace": [],
        },
        "concept": {
            "stem": f"concept--{family_slug}",
            "title": _titleize_slug(family_slug),
            "created": profile_date,
            "summary": "",
            "why_it_matters_here": "",
            "main_body_blocks": [
                {"heading": "", "body": ""},
                {"heading": "", "body": ""},
                {"heading": "", "body": ""},
            ],
            "scope_boundaries": [],
            "examples_and_non_examples": [],
            "how_to_reuse_this_concept": [],
            "focus_source_stems": source_stems[:4],
            "bridge_source_stems": bridge_source_stems,
            "continuity_resolution": {"status": ""},
            "carryover_decision": "",
            "related_pages": [],
            "open_questions": [],
            "source_trace": [],
        },
    }


def _family_profiles(
    target_groups: dict[str, list[dict]],
    *,
    vault: Path | None,
    profile_date: str,
    bridge_limit: int,
) -> list[dict]:
    families: list[dict] = []
    for family_slug in sorted(target_groups):
        items = sorted(target_groups[family_slug], key=lambda item: str(item.get("registry_id") or ""))
        families.append(
            _new_family_profile(
                vault=vault,
                family_slug=family_slug,
                items=items,
                profile_date=profile_date,
                bridge_limit=bridge_limit,
            )
        )
    return families


def _refresh_profiles(refresh_groups: dict[str, list[dict]], vault: Path | None) -> list[dict]:
    refreshes: list[dict] = []
    for target_stem in sorted(refresh_groups):
        items = sorted(refresh_groups[target_stem], key=lambda item: str(item.get("registry_id") or ""))
        if vault is None:
            refreshes.append(_default_refresh_profile(target_stem, items))
        else:
            refreshes.append(_scaffold_refresh_profile(vault, target_stem, items))
    return refreshes


def scaffold_profile_bundle(
    matrix_path: Path,
    *,
    page_date: str | None = None,
    vault: Path | None = None,
    bridge_limit: int = 3,
) -> dict:
    payload = _json_load_object(matrix_path)
    all_entries = _matrix_entries(payload)
    review_status_counts = _review_status_counts(all_entries)
    target_groups, refresh_groups, skipped_unreviewed_entry_count = _reviewed_route_groups(all_entries)
    profile_date = _page_date(matrix_path, payload, page_date)
    families = _family_profiles(
        target_groups,
        vault=vault,
        profile_date=profile_date,
        bridge_limit=bridge_limit,
    )
    refreshes = _refresh_profiles(refresh_groups, vault)

    return {
        "$schema": RAW_INTAKE_PROMOTION_PROFILE_BUNDLE_SCHEMA_PATH,
        "generated_from": matrix_path.as_posix(),
        "page_date": profile_date,
        "family_count": len(families),
        "refresh_count": len(refreshes),
        "metadata": {
            "properties": [
                {
                    "name": "reviewed_route_statuses",
                    "value": ",".join(sorted(REVIEWED_ROUTE_STATUSES)),
                },
                {
                    "name": "matrix_entry_count",
                    "value": str(len(all_entries)),
                },
                {
                    "name": "skipped_unreviewed_entry_count",
                    "value": str(skipped_unreviewed_entry_count),
                },
                {
                    "name": "review_status_counts",
                    "value": ",".join(f"{status}:{count}" for status, count in review_status_counts.items()),
                },
            ],
        },
        "instructions": (
            "Fill family and refresh profiles with mature analysis text. "
            "For new families, use synthesis.bridge_source_stems + synthesis.integration_note and "
            "concept.bridge_source_stems + carryover_decision to record source bridge review, but "
            "write the bridge interpretation directly into concept.main_body_blocks rather than "
            "adding a separate temporal continuity block. "
            "For refreshes, rewrite the full synthesis so bridge and intake evidence are merged into one coherent page."
        ),
        "families": families,
        "refreshes": refreshes,
    }
