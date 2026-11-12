from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry import raw_intake_route_proposal, raw_intake_source_quality
from ops.scripts.registry.raw_intake_input_runtime import IntakeMatrixError
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault
from tests.test_raw_intake_route_proposal import matrix_entry, write_matrix
from tests.test_raw_intake_source_quality import write_source


@pytest.fixture
def intake(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    seed_minimal_vault(tmp_path)
    entry = matrix_entry(proposed_action="keep_source_only_seed")
    raw = tmp_path / entry["raw_path"]
    raw.parent.mkdir(exist_ok=True)
    raw.write_text(
        "---\ntitle: Deterministic route\n---\n\n"
        "This canonical article contains a sufficiently long first paragraph "
        "to pass the cleaned lead admission threshold on its own.\n\nOriginal tail.\n",
        encoding="utf-8",
    )
    source = tmp_path / entry["source_page"]
    write_source(
        source,
        summary=(
            "A controlled experiment measured a reduction in energy use. "
            "The comparison kept production volume constant across both treatments."
        ),
        key_points=[
            "The measured energy reduction came from the experimental treatment.",
            "Production volume remained constant in the control and treatment groups.",
            "The sample covered one facility during a limited observation period.",
            "The authors did not measure long-term equipment maintenance costs.",
        ],
    )
    source.write_text(
        source.read_text(encoding="utf-8")
        + "\n## Title\nDeterministic route\n\n## Source\n- `raw/source.md`\n",
        encoding="utf-8",
    )
    write_matrix(tmp_path / "matrix.json", [entry])
    return tmp_path, entry


@pytest.fixture(params=["quality", "route_proposal", "absorption_closeout"])
def report_builder(request):
    def build(vault: Path):
        kwargs = {
            "matrix_path": "matrix.json",
            "context": RuntimeContext(
                display_timezone=dt.UTC,
                clock=lambda: dt.datetime(2026, 11, 11, tzinfo=dt.UTC),
            ),
        }
        if request.param == "quality":
            report = raw_intake_source_quality.build_report(vault, **kwargs)
        else:
            report = raw_intake_route_proposal.build_report(vault, mode=request.param, **kwargs)
        assert validate_with_schema(report, load_schema(REPO_ROOT / report["$schema"])) == []
        return report

    return build


@pytest.mark.parametrize("suffix", [".md", ".pdf"])
@pytest.mark.parametrize("state", ["missing_file", "missing_path", "not_file", "unreadable"])
def test_raw_admission_blocks_unavailable_file(intake, report_builder, suffix, state):
    vault, entry = intake
    raw = vault / entry["raw_path"]
    if suffix == ".pdf":
        raw.rename(raw.with_suffix(suffix))
        raw = raw.with_suffix(suffix)
        raw.write_bytes(b"%PDF-1.7\nsynthetic binary input\x00\xff")
        source = vault / entry["source_page"]
        source.write_text(source.read_text().replace("raw/source.md", "raw/source.pdf"))
        entry["raw_path"] = "raw/source.pdf"
        write_matrix(vault / "matrix.json", [entry])
    assert report_builder(vault)["status"] == "pass"

    original_open = Path.open

    def open_with_denied_raw(path, *args, **kwargs):
        if state == "unreadable" and path == raw:
            raise PermissionError("synthetic raw read denial")
        return original_open(path, *args, **kwargs)

    if state in {"missing_file", "not_file"}:
        raw.unlink()
        if state == "not_file":
            raw.mkdir()
    elif state == "missing_path":
        entry["raw_path"] = ""
        write_matrix(vault / "matrix.json", [entry])
    with patch.object(Path, "open", open_with_denied_raw):
        report = report_builder(vault)
    assert report["status"] == "fail"
    if "findings" in report:
        assert report["findings"][0]["cleaned_raw_lead"]["status"] == state
    else:
        assert report["proposals"][0]["identity_audit"]["status"] == "fail"


@pytest.mark.parametrize("cli", ["quality", "closeout"])
def test_cli_returns_failure_for_missing_raw(intake, cli):
    vault, entry = intake
    (vault / entry["raw_path"]).unlink()
    main = raw_intake_source_quality.main if cli == "quality" else raw_intake_route_proposal.main
    args = ["--vault", str(vault), "--matrix", "matrix.json", "--out", "report.json", "--fail-on-fail"]
    if cli == "closeout":
        args.extend(["--mode", "absorption_closeout"])
    def cli_main(argv):
        raise SystemExit(main(argv))

    completed = invoke_cli_main(cli_main, args)
    assert completed.exit_code == 1, completed.stderr
    assert json.loads((vault / "report.json").read_text())["status"] == "fail"


@pytest.mark.parametrize(
    ("prefix", "body", "minimum", "expected_status", "expected_lead"),
    [
        ("A photograph of the experimental equipment. Credit: Example.", "Article body " * 10, 80, "pass", "Article body " * 10),
        ("A brief but substantive introduction to the article's subject.", "Article body " * 10, 80, "pass", "Article body " * 10),
        ("Short introduction.", "x" * 80, 80, "pass", "x" * 80),
        ("Short introduction.", "x" * 79, 80, "attention", "Short introduction."),
        ("", "Brief source text.", 10, "pass", "Brief source text."),
        ("x" * 90, "y" * 140, 120, "pass", "y" * 140),
        ("x" * 90, "y" * 750, 701, "pass", "y" * 702),
        ("x" * 90, "y" * 700 + " zzz", 701, "pass", "y" * 700 + " z"),
        ("", "y" * 699 + " zzz", 700, "pass", "y" * 699 + " z"),
        ("x" * 90, "y" * 140, 80, "pass", "x" * 90),
        ("", "A photograph of the experimental equipment. Credit: Example.", 80, "attention", "A photograph of the experimental equipment. Credit: Example."),
        ("x" * 45, "y" * 45, 80, "attention", "x" * 45),
        ("", "# Heading\n\n[Home](/)\n\n![image](photo.png)", 80, "fail", ""),
        ("", "", 80, "fail", ""),
    ],
)
def test_quality_lead_selects_a_paragraph_meeting_the_configured_minimum(
    intake, prefix, body, minimum, expected_status, expected_lead,
):
    vault, entry = intake
    (vault / entry["raw_path"]).write_text(f"{prefix}\n\n{body}\n", encoding="utf-8")
    report = raw_intake_source_quality.build_report(
        vault, matrix_path="matrix.json", min_raw_lead_chars=minimum,
    )
    assert validate_with_schema(report, load_schema(REPO_ROOT / report["$schema"])) == []
    finding = report["findings"][0]
    expected_lead = expected_lead.strip()
    assert report["status"] == expected_status
    assert finding["cleaned_raw_lead"] == {
        "status": "empty" if not expected_lead else "ok" if len(expected_lead) >= minimum else "insufficient",
        "char_count": len(expected_lead),
        "sha256": hashlib.sha256(expected_lead.encode()).hexdigest() if expected_lead else "",
    }
    assert ("cleaned_raw_lead_below_min_chars" in finding["issues"]) == (len(expected_lead) < minimum)
    assert ("raw_body_empty" in finding["issues"]) == (not expected_lead)


def test_quality_cli_uses_custom_lead_minimum(intake):
    vault, entry = intake
    (vault / entry["raw_path"]).write_text("x" * 90 + "\n\n" + "y" * 140)

    def cli_main(argv):
        raise SystemExit(raw_intake_source_quality.main(argv))

    completed = invoke_cli_main(
        cli_main,
        ["--vault", str(vault), "--matrix", "matrix.json", "--out", "report.json",
         "--min-raw-lead-chars", "120", "--fail-on-attention"],
    )
    assert completed.exit_code == 0, completed.stderr
    report = json.loads((vault / "report.json").read_text())
    assert report["status"] == "pass"
    assert report["findings"][0]["cleaned_raw_lead"]["char_count"] == 140


def test_content_fingerprints_bind_full_contents_and_absence(intake, report_builder):
    vault, entry = intake
    original = report_builder(vault)
    source = vault / entry["source_page"]
    source_text = source.read_text()
    source.write_text(source_text + "\nAdditional source detail.\n")
    source_changed = report_builder(vault)
    assert original["input_fingerprints"] != source_changed["input_fingerprints"]
    assert original["input_fingerprints"]["matrix"] == source_changed["input_fingerprints"]["matrix"]
    source.write_text(source_text)
    assert original["input_fingerprints"] == report_builder(vault)["input_fingerprints"]
    source.unlink()
    assert original["input_fingerprints"] != report_builder(vault)["input_fingerprints"]
    source.write_text(source_text)

    raw = vault / entry["raw_path"]
    raw_bytes = raw.read_bytes()
    raw.write_bytes(raw_bytes + b"\nChanged tail after the unchanged lead.\n")
    tail_changed = report_builder(vault)
    assert original["input_fingerprints"] != tail_changed["input_fingerprints"]
    if "findings" in original:
        assert original["findings"][0]["cleaned_raw_lead"] == tail_changed["findings"][0]["cleaned_raw_lead"]
    raw.unlink()
    missing = report_builder(vault)
    assert missing["input_fingerprints"] != original["input_fingerprints"]
    raw.write_bytes(raw_bytes)
    assert original["input_fingerprints"] == report_builder(vault)["input_fingerprints"]


def test_content_fingerprints_are_order_independent_and_bind_file_set(intake, report_builder):
    vault, entry = intake
    other = {**entry, "registry_id": "W-002", "raw_path": "raw/other.md", "source_page": "wiki/source--other.md"}
    for field in ("raw_path", "source_page"):
        (vault / other[field]).write_bytes((vault / entry[field]).read_bytes())
    write_matrix(vault / "matrix.json", [entry, other])
    first = report_builder(vault)
    write_matrix(vault / "matrix.json", [other, entry])
    reordered = report_builder(vault)
    for key in ("raw_files", "source_pages"):
        assert first["input_fingerprints"][key] == reordered["input_fingerprints"][key]
    write_matrix(vault / "matrix.json", [entry, other, {**entry, "registry_id": "W-003"}])
    duplicated = report_builder(vault)
    for key in ("raw_files", "source_pages"):
        assert first["input_fingerprints"][key] == duplicated["input_fingerprints"][key]
    write_matrix(vault / "matrix.json", [entry])
    reduced = report_builder(vault)
    for key in ("raw_files", "source_pages"):
        assert first["input_fingerprints"][key] != reduced["input_fingerprints"][key]


def test_binary_fingerprint_tracks_bytes_without_text_decoding(intake, report_builder):
    vault, entry = intake
    raw = vault / "raw/source.pdf"
    raw.write_bytes(b"%PDF-1.7\x00\xffFirst binary payload")
    entry["raw_path"] = "raw/source.pdf"
    source = vault / entry["source_page"]
    source.write_text(source.read_text().replace("raw/source.md", "raw/source.pdf"))
    write_matrix(vault / "matrix.json", [entry])
    original = report_builder(vault)
    assert original["status"] == "pass"
    raw.write_bytes(raw.read_bytes() + b"\x00\xfeChanged binary tail")
    changed = report_builder(vault)
    assert changed["status"] == "pass"
    assert original["input_fingerprints"]["raw_files"] != changed["input_fingerprints"]["raw_files"]


@pytest.mark.parametrize("path_kind", ["absolute", "outside", "symlink", "null"])
def test_unusable_raw_path_cannot_admit(intake, report_builder, path_kind):
    vault, entry = intake
    if path_kind == "absolute":
        entry["raw_path"] = str(vault / entry["raw_path"])
    elif path_kind == "null":
        entry["raw_path"] = None
    else:
        outside = vault.parent / f"{vault.name}-outside.md"
        outside.write_bytes((vault / entry["raw_path"]).read_bytes())
        entry["raw_path"] = f"../{outside.name}"
        if path_kind == "symlink":
            (vault / "raw/link.md").symlink_to(outside)
            entry["raw_path"] = "raw/link.md"
    write_matrix(vault / "matrix.json", [entry])
    if path_kind == "null":
        with pytest.raises(IntakeMatrixError, match="raw_path"):
            report_builder(vault)
    else:
        assert report_builder(vault)["status"] == "fail"


def test_line_endings_keep_checks_stable_but_bind_original_bytes(intake, report_builder):
    vault, entry = intake
    original = report_builder(vault)
    for field in ("raw_path", "source_page"):
        path = vault / entry[field]
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    changed = report_builder(vault)
    assert original["status"] == changed["status"] == "pass"
    rows = "findings" if "findings" in original else "proposals"
    assert original[rows] == changed[rows]
    for key in ("raw_files", "source_pages"):
        assert original["input_fingerprints"][key] != changed["input_fingerprints"][key]
