from __future__ import annotations

from pathlib import Path

from ops.scripts.core.schema_constants_runtime import (
    RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
)
from ops.scripts.eval.source_page_substance_runtime import (
    evaluate_source_page_substance,
)

from .raw_intake_promotion_shared_runtime import (
    CONCEPT_ANALYSIS_SCAFFOLD_HEADINGS,
    SYNTHESIS_ANALYSIS_SCAFFOLD_HEADINGS,
    _dedupe,
    _evidence_map_rows,
    _json_load_object,
    _string_list,
)

SYNTHESIS_ROUTE_MEMO_MARKERS = (
    "Why this deserved a new synthesis",
    "이 묶음이 새로 더하는 것",
    "source 신호",
    "라우팅 기준",
    "이 route를 다시 쓰는 법",
    "새 synthesis로 분리",
    "품질 판단",
    "route target:",
    "evidence role:",
    "absorbed into:",
    "semantic route",
    "provenance",
    "이번 batch",
)
SYNTHESIS_ANALYSIS_TEMPLATE_MARKERS = SYNTHESIS_ROUTE_MEMO_MARKERS
SYNTHESIS_DOMAIN_CONCLUSION_MARKERS = (*SYNTHESIS_ROUTE_MEMO_MARKERS, "intake")
SYNTHESIS_FOLLOW_UP_SPLIT_MARKERS = (
    "### 2026-04-21 후속 근거",
    "follow-up는",
    "후속 intake",
)
CONCEPT_CONTINUITY_MARKERS = (
    "보강",
    "확장",
    "연결",
    "함께",
    "겹치",
    "묶",
    "더 분명",
    "더 선명",
    "보여 줬",
)
CONCEPT_SPLIT_CONTINUITY_HEADINGS = (
    "기존 corpus와 이번 intake",
    "older/newer",
    "old/new",
)


def _empty_messages() -> tuple[list[dict], list[dict]]:
    return [], []


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _required_string_field_errors(
    profile: dict,
    *,
    family_slug: str,
    fields: tuple[str, ...],
    error_type: str,
) -> list[dict]:
    return [
        {"type": error_type, "family_slug": family_slug, "field": field}
        for field in fields
        if not _is_nonempty_string(profile.get(field))
    ]


def _validate_page_stem(
    *,
    family_slug: str,
    stem: object,
    required_prefix: str,
    invalid_type: str,
    seen_page_stems: set[str],
) -> list[dict]:
    if not isinstance(stem, str) or not stem.startswith(required_prefix):
        return [{"type": invalid_type, "family_slug": family_slug}]
    if stem in seen_page_stems:
        return [{"type": "duplicate_page_stem", "family_slug": family_slug, "stem": stem}]
    seen_page_stems.add(stem)
    return []


def _missing_list_field_errors(
    profile: dict,
    *,
    family_slug: str,
    fields: tuple[str, ...],
) -> list[dict]:
    return [
        {"type": f"missing_{field}", "family_slug": family_slug}
        for field in fields
        if not _string_list(profile.get(field))
    ]


def _profile_source_stem_bindings(payload: dict) -> list[tuple[str, str]]:
    bindings: list[tuple[str, str]] = []
    raw_families = payload.get("families")
    if not isinstance(raw_families, list):
        return bindings
    for index, family in enumerate(raw_families):
        if not isinstance(family, dict):
            continue
        family_slug = family.get("family_slug")
        if not isinstance(family_slug, str) or not family_slug.strip():
            family_slug = f"family-{index}"
        synthesis = family.get("synthesis")
        concept = family.get("concept")
        synthesis = synthesis if isinstance(synthesis, dict) else {}
        concept = concept if isinstance(concept, dict) else {}
        for stem in _dedupe(
            _string_list(synthesis.get("source_stems"))
            + _string_list(synthesis.get("bridge_source_stems"))
            + _string_list(concept.get("focus_source_stems"))
            + _string_list(concept.get("bridge_source_stems"))
        ):
            bindings.append((family_slug, stem))

    raw_refreshes = payload.get("refreshes", [])
    if not isinstance(raw_refreshes, list):
        return bindings
    for index, refresh in enumerate(raw_refreshes):
        if not isinstance(refresh, dict):
            continue
        target_stem = refresh.get("target_stem")
        if not isinstance(target_stem, str) or not target_stem.strip():
            target_stem = f"refresh-{index}"
        synthesis = refresh.get("synthesis")
        synthesis = synthesis if isinstance(synthesis, dict) else {}
        for stem in _dedupe(
            _string_list(synthesis.get("source_stems"))
            + _string_list(synthesis.get("bridge_source_stems"))
        ):
            bindings.append((target_stem, stem))
    return bindings


def _validate_promotion_source_page_substance(
    vault: Path,
    payload: dict,
) -> list[dict]:
    errors: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for scope_slug, stem in _profile_source_stem_bindings(payload):
        key = (scope_slug, stem)
        if key in seen:
            continue
        seen.add(key)
        source_page = f"wiki/{stem}.md"
        source_path = (vault / source_page).resolve()
        if not source_path.is_file():
            errors.append(
                {
                    "type": "missing_promotion_source_page",
                    "family_slug": scope_slug,
                    "source_stem": stem,
                    "source_page": source_page,
                }
            )
            continue
        substance = evaluate_source_page_substance(source_path.read_text(encoding="utf-8", errors="replace"))
        if substance.get("pass"):
            continue
        errors.append(
            {
                "type": "source_page_substance_admission_failed",
                "family_slug": scope_slug,
                "source_stem": stem,
                "source_page": source_page,
                "failures": list(substance.get("failures", [])),
            }
        )
    return errors


def validate_profile_bundle_data(payload: dict, *, vault: Path | None = None) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    raw_families = payload.get("families")
    if not isinstance(raw_families, list):
        raise ValueError("manifest must contain a top-level 'families' list")
    raw_refreshes = payload.get("refreshes", [])
    if raw_refreshes is None:
        raw_refreshes = []
    if not isinstance(raw_refreshes, list):
        raise ValueError("manifest 'refreshes' must be a list when present")

    seen_family_slugs: set[str] = set()
    seen_page_stems: set[str] = set()
    family_count = 0
    refresh_count = 0
    for index, family in enumerate(raw_families):
        if not isinstance(family, dict):
            errors.append({"type": "invalid_family_entry", "family_index": index})
            continue
        family_count += 1
        family_slug = family.get("family_slug")
        if not isinstance(family_slug, str) or not family_slug.strip():
            errors.append({"type": "missing_family_slug", "family_index": index})
            family_slug = f"family-{index}"
        elif family_slug in seen_family_slugs:
            errors.append({"type": "duplicate_family_slug", "family_slug": family_slug})
        else:
            seen_family_slugs.add(family_slug)

        synthesis = family.get("synthesis")
        concept = family.get("concept")
        if not isinstance(synthesis, dict):
            errors.append({"type": "missing_synthesis_profile", "family_slug": family_slug})
            synthesis = {}
        if not isinstance(concept, dict):
            errors.append({"type": "missing_concept_profile", "family_slug": family_slug})
            concept = {}

        synthesis_errors, synthesis_warnings = _validate_synthesis_profile(
            family_slug,
            synthesis,
            seen_page_stems,
        )
        concept_errors, concept_warnings = _validate_concept_profile(
            family_slug,
            concept,
            seen_page_stems,
        )
        errors.extend(synthesis_errors)
        errors.extend(concept_errors)
        warnings.extend(synthesis_warnings)
        warnings.extend(concept_warnings)

    for index, refresh in enumerate(raw_refreshes):
        if not isinstance(refresh, dict):
            errors.append({"type": "invalid_refresh_entry", "refresh_index": index})
            continue
        refresh_count += 1
        target_stem = refresh.get("target_stem")
        if not isinstance(target_stem, str) or not target_stem.startswith("synthesis--"):
            errors.append({"type": "invalid_refresh_target_stem", "refresh_index": index})
            target_stem = f"refresh-{index}"
        synthesis = refresh.get("synthesis")
        if not isinstance(synthesis, dict):
            errors.append({"type": "missing_refresh_synthesis_profile", "target_stem": target_stem})
            synthesis = {}
        synthesis_errors, synthesis_warnings = _validate_synthesis_profile(
            target_stem,
            synthesis,
            seen_page_stems,
        )
        errors.extend(synthesis_errors)
        warnings.extend(synthesis_warnings)

    if vault is not None:
        errors.extend(_validate_promotion_source_page_substance(vault.resolve(), payload))

    return {
        "$schema": RAW_INTAKE_PROMOTION_REPORT_SCHEMA_PATH,
        "status": "fail" if errors else "pass",
        "family_count": family_count,
        "refresh_count": refresh_count,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def validate_profile_bundle(manifest_path: Path, *, vault: Path | None = None) -> dict:
    payload = _json_load_object(manifest_path)
    report = validate_profile_bundle_data(payload, vault=vault)
    report["manifest"] = manifest_path.as_posix()
    return report


def _validate_synthesis_sources(
    family_slug: str,
    synthesis: dict,
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    source_stems = _string_list(synthesis.get("source_stems"))
    bridge_source_stems = _string_list(synthesis.get("bridge_source_stems"))
    if not source_stems and not bridge_source_stems:
        errors.append({"type": "missing_synthesis_sources", "family_slug": family_slug})
    if "bridge_source_stems" in synthesis and not isinstance(synthesis.get("bridge_source_stems"), list):
        errors.append({"type": "invalid_bridge_source_stems", "family_slug": family_slug})
    if bridge_source_stems:
        integration_note = synthesis.get("integration_note")
        if not isinstance(integration_note, str) or not integration_note.strip():
            errors.append({"type": "missing_synthesis_integration_note", "family_slug": family_slug})
    elif "integration_note" in synthesis and not isinstance(synthesis.get("integration_note"), str):
        errors.append({"type": "invalid_synthesis_integration_note", "family_slug": family_slug})
    return errors, warnings


def _analysis_block_marker_messages(
    *,
    family_slug: str,
    block_index: int,
    heading: object,
    body: object,
) -> tuple[list[dict], list[dict]]:
    text = f"{heading}\n{body}"
    errors: list[dict] = []
    warnings: list[dict] = []
    markers = [marker for marker in SYNTHESIS_ANALYSIS_TEMPLATE_MARKERS if marker in text]
    if markers:
        errors.append(
            {
                "type": "analysis_template_marker_present",
                "family_slug": family_slug,
                "block_index": block_index,
                "markers": markers,
            }
        )
    split_markers = [marker for marker in SYNTHESIS_FOLLOW_UP_SPLIT_MARKERS if marker in text]
    if split_markers:
        errors.append(
            {
                "type": "analysis_follow_up_split_marker_present",
                "family_slug": family_slug,
                "block_index": block_index,
                "markers": split_markers,
            }
        )
    return errors, warnings


def _validate_analysis_block(
    *,
    family_slug: str,
    block_index: int,
    block: object,
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    if not isinstance(block, dict):
        return [
            {
                "type": "invalid_analysis_block",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        ], []
    heading = block.get("heading")
    body = block.get("body")
    if not _is_nonempty_string(heading):
        errors.append(
            {
                "type": "missing_analysis_heading",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        )
    if not _is_nonempty_string(body):
        errors.append(
            {
                "type": "missing_analysis_body",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        )
    marker_errors, marker_warnings = _analysis_block_marker_messages(
        family_slug=family_slug,
        block_index=block_index,
        heading=heading,
        body=body,
    )
    errors.extend(marker_errors)
    warnings.extend(marker_warnings)
    purpose = block.get("purpose")
    if not _is_nonempty_string(purpose):
        warnings.append(
            {
                "type": "analysis_block_purpose_missing",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        )
    return errors, warnings


def _validate_synthesis_analysis_blocks(
    family_slug: str,
    synthesis: dict,
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    analysis_blocks = synthesis.get("analysis_blocks")
    if not isinstance(analysis_blocks, list) or len(analysis_blocks) < 3:
        errors.append({"type": "insufficient_analysis_blocks", "family_slug": family_slug})
        return errors, warnings
    for block_index, block in enumerate(analysis_blocks):
        block_errors, block_warnings = _validate_analysis_block(
            family_slug=family_slug,
            block_index=block_index,
            block=block,
        )
        errors.extend(block_errors)
        warnings.extend(block_warnings)
    headings = {
        block.get("heading", "").strip()
        for block in analysis_blocks
        if isinstance(block, dict) and isinstance(block.get("heading"), str)
    }
    missing_headings = [
        heading for heading in SYNTHESIS_ANALYSIS_SCAFFOLD_HEADINGS if heading not in headings
    ]
    if missing_headings:
        errors.append(
            {
                "type": "missing_synthesis_analysis_scaffold_headings",
                "family_slug": family_slug,
                "missing_headings": missing_headings,
            }
        )
    return errors, warnings


def _validate_synthesis_evidence_map(family_slug: str, synthesis: dict) -> list[dict]:
    rows = _evidence_map_rows(synthesis.get("evidence_map"))
    if not rows:
        return [{"type": "missing_synthesis_evidence_map", "family_slug": family_slug}]

    errors: list[dict] = []
    for row_index, row in enumerate(rows):
        missing_fields = [
            field
            for field in ("channel", "sources", "what_they_show", "caveat")
            if not row.get(field, "").strip()
        ]
        if missing_fields:
            errors.append(
                {
                    "type": "incomplete_synthesis_evidence_map_row",
                    "family_slug": family_slug,
                    "row_index": row_index,
                    "missing_fields": missing_fields,
                }
            )
    return errors


def _validate_synthesis_domain_conclusion_fields(family_slug: str, synthesis: dict) -> list[dict]:
    errors: list[dict] = []
    for field in ("short_answer", "decision_or_takeaway"):
        value = synthesis.get(field)
        if not isinstance(value, str):
            continue
        markers = [marker for marker in SYNTHESIS_DOMAIN_CONCLUSION_MARKERS if marker in value]
        if markers:
            errors.append(
                {
                    "type": "synthesis_route_memo_marker_present",
                    "family_slug": family_slug,
                    "field": field,
                    "markers": markers,
                }
            )
    return errors


def _validate_synthesis_tail_fields(family_slug: str, synthesis: dict) -> list[dict]:
    errors: list[dict] = []
    for field in (
        "what_this_synthesis_excludes",
        "tensions_and_contradictions",
        "implications_for_future_ingest",
        "wiki_placement_note",
    ):
        if not _string_list(synthesis.get(field)):
            errors.append({"type": f"missing_synthesis_{field}", "family_slug": family_slug})
    if not _string_list(synthesis.get("follow_up_questions")):
        errors.append({"type": "missing_synthesis_follow_up_questions", "family_slug": family_slug})
    if not _string_list(synthesis.get("source_trace")):
        errors.append({"type": "missing_synthesis_source_trace", "family_slug": family_slug})
    return errors


def _validate_synthesis_bridge_integration(
    family_slug: str,
    synthesis: dict,
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    bridge_source_stems = _string_list(synthesis.get("bridge_source_stems"))
    bridge_integration = synthesis.get("bridge_integration")
    if bridge_integration is not None and not isinstance(bridge_integration, dict):
        errors.append({"type": "invalid_synthesis_bridge_integration", "family_slug": family_slug})
        return errors, warnings
    bridge_kind = ""
    if isinstance(bridge_integration, dict):
        bridge_kind = str(bridge_integration.get("kind", "")).strip()
    if bridge_source_stems and not bridge_kind:
        warnings.append({"type": "synthesis_bridge_integration_kind_missing", "family_slug": family_slug})
    return errors, warnings


def _validate_synthesis_profile(
    family_slug: str,
    synthesis: dict,
    seen_page_stems: set[str],
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    errors.extend(
        _validate_page_stem(
            family_slug=family_slug,
            stem=synthesis.get("stem"),
            required_prefix="synthesis--",
            invalid_type="invalid_synthesis_stem",
            seen_page_stems=seen_page_stems,
        )
    )
    errors.extend(
        _required_string_field_errors(
            synthesis,
            family_slug=family_slug,
            fields=("title", "created", "question", "short_answer", "decision_or_takeaway"),
            error_type="missing_synthesis_field",
        )
    )
    errors.extend(_validate_synthesis_domain_conclusion_fields(family_slug, synthesis))
    errors.extend(_validate_synthesis_evidence_map(family_slug, synthesis))
    for validator in (
        _validate_synthesis_sources,
        _validate_synthesis_analysis_blocks,
        _validate_synthesis_bridge_integration,
    ):
        new_errors, new_warnings = validator(family_slug, synthesis)
        errors.extend(new_errors)
        warnings.extend(new_warnings)
    errors.extend(_validate_synthesis_tail_fields(family_slug, synthesis))
    return errors, warnings


def _validate_concept_profile(
    family_slug: str,
    concept: dict,
    seen_page_stems: set[str],
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    errors.extend(
        _validate_page_stem(
            family_slug=family_slug,
            stem=concept.get("stem"),
            required_prefix="concept--",
            invalid_type="invalid_concept_stem",
            seen_page_stems=seen_page_stems,
        )
    )
    errors.extend(
        _required_string_field_errors(
            concept,
            family_slug=family_slug,
            fields=("title", "created", "summary", "why_it_matters_here", "carryover_decision"),
            error_type="missing_concept_field",
        )
    )
    source_errors = _validate_concept_source_fields(family_slug, concept)
    main_body_errors, main_body_text_parts = _validate_concept_main_body_blocks(family_slug, concept)
    continuity_errors, continuity_warnings = _validate_concept_continuity(
        family_slug,
        concept,
        main_body_text_parts,
    )
    errors.extend(source_errors)
    errors.extend(main_body_errors)
    errors.extend(continuity_errors)
    errors.extend(
        _missing_list_field_errors(
            concept,
            family_slug=family_slug,
            fields=(
                "scope_boundaries",
                "examples_and_non_examples",
                "how_to_reuse_this_concept",
                "open_questions",
                "source_trace",
            ),
        )
    )
    warnings.extend(continuity_warnings)
    return errors, warnings


def _validate_concept_source_fields(family_slug: str, concept: dict) -> list[dict]:
    errors: list[dict] = []
    if not _string_list(concept.get("focus_source_stems")):
        errors.append({"type": "missing_concept_focus_sources", "family_slug": family_slug})
    if "bridge_source_stems" not in concept or not isinstance(concept.get("bridge_source_stems"), list):
        errors.append({"type": "missing_bridge_source_stems", "family_slug": family_slug})
    return errors


def _validate_concept_body_block(
    *,
    family_slug: str,
    block_index: int,
    block: object,
) -> tuple[list[dict], str]:
    if not isinstance(block, dict):
        return [
            {
                "type": "invalid_concept_main_body_block",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        ], ""
    errors: list[dict] = []
    heading = block.get("heading")
    body = block.get("body")
    if not _is_nonempty_string(heading):
        errors.append(
            {
                "type": "missing_concept_main_body_heading",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        )
    if not _is_nonempty_string(body):
        errors.append(
            {
                "type": "missing_concept_main_body_body",
                "family_slug": family_slug,
                "block_index": block_index,
            }
        )
    return errors, f"{heading}\n{body}"


def _validate_concept_main_body_blocks(
    family_slug: str,
    concept: dict,
) -> tuple[list[dict], list[str]]:
    errors: list[dict] = []
    main_body_blocks = concept.get("main_body_blocks")
    main_body_text_parts: list[str] = []
    if not isinstance(main_body_blocks, list) or len(main_body_blocks) < len(CONCEPT_ANALYSIS_SCAFFOLD_HEADINGS):
        return [{"type": "insufficient_concept_main_body_blocks", "family_slug": family_slug}], []
    for block_index, block in enumerate(main_body_blocks):
        block_errors, block_text = _validate_concept_body_block(
            family_slug=family_slug,
            block_index=block_index,
            block=block,
        )
        errors.extend(block_errors)
        if block_text:
            main_body_text_parts.append(block_text)
    headings = {
        block.get("heading", "").strip()
        for block in main_body_blocks
        if isinstance(block, dict) and isinstance(block.get("heading"), str)
    }
    missing_headings = [
        heading for heading in CONCEPT_ANALYSIS_SCAFFOLD_HEADINGS if heading not in headings
    ]
    if missing_headings:
        errors.append(
            {
                "type": "missing_concept_main_body_scaffold_headings",
                "family_slug": family_slug,
                "missing_headings": missing_headings,
            }
        )
    return errors, main_body_text_parts


def _continuity_status(
    family_slug: str,
    continuity_resolution: object,
) -> tuple[list[dict], str]:
    if continuity_resolution is None:
        return [], ""
    if not isinstance(continuity_resolution, dict):
        return [{"type": "invalid_continuity_resolution", "family_slug": family_slug}], ""
    return [], str(continuity_resolution.get("status", "")).strip()


def _continuity_missing_warnings(
    *,
    family_slug: str,
    main_body_text_parts: list[str],
) -> list[dict]:
    warnings: list[dict] = [{"type": "concept_continuity_resolution_status_missing", "family_slug": family_slug}]
    main_body_text = "\n".join(main_body_text_parts)
    if any(marker in main_body_text for marker in CONCEPT_SPLIT_CONTINUITY_HEADINGS):
        warnings.append({"type": "concept_continuity_split_heading_present", "family_slug": family_slug})
    if not any(marker in main_body_text for marker in CONCEPT_CONTINUITY_MARKERS):
        warnings.append({"type": "concept_bridge_integration_missing", "family_slug": family_slug})
    return warnings


def _validate_concept_continuity(
    family_slug: str,
    concept: dict,
    main_body_text_parts: list[str],
) -> tuple[list[dict], list[dict]]:
    errors, warnings = _empty_messages()
    bridge_source_stems = _string_list(concept.get("bridge_source_stems"))
    continuity_blocks = concept.get("continuity_blocks")
    if isinstance(continuity_blocks, list) and continuity_blocks:
        errors.append({"type": "concept_continuity_split_block_present", "family_slug": family_slug})
    continuity_errors, continuity_status = _continuity_status(family_slug, concept.get("continuity_resolution"))
    errors.extend(continuity_errors)
    if bridge_source_stems and not continuity_status:
        warnings.extend(
            _continuity_missing_warnings(
                family_slug=family_slug,
                main_body_text_parts=main_body_text_parts,
            )
        )
    return errors, warnings
