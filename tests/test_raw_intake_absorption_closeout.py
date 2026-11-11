from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry.raw_intake_route_proposal import build_report, main
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_raw_intake_route_proposal import SCHEMA_PATH, matrix_entry, write_matrix


@pytest.fixture
def intake(tmp_path):
    seed_minimal_vault(tmp_path)
    entry = matrix_entry(
        title="Fake Source", raw_path="raw/fake.pdf", source_page="wiki/source--fake.md"
    )
    return tmp_path, entry


def report_for(vault, entry, mode="absorption_closeout"):
    write_matrix(vault / "matrix.json", [entry])
    report = build_report(
        vault,
        matrix_path="matrix.json",
        mode=mode,
        context=RuntimeContext(
            display_timezone=dt.UTC,
            clock=lambda: dt.datetime(2026, 11, 12, tzinfo=dt.UTC),
        ),
    )
    assert validate_with_schema(report, load_schema(SCHEMA_PATH)) == []
    return report


def test_reviewed_missing_target_is_proposal_only_and_cli_blocks_closeout(intake):
    vault, entry = intake
    proposal = report_for(vault, entry, "route_proposal")
    assert proposal["status"] == "pass"
    assert proposal["proposals"][0]["closeout_status"] == "not_checked"
    assert proposal["summary"]["closeout_pass_count"] == 0
    report = report_for(vault, entry)
    assert report["status"] == "fail"
    assert report["proposals"][0]["route_status"] == "pass"
    assert report["proposals"][0]["review_gate"] == "satisfied"

    def cli_main(argv):
        raise SystemExit(main(argv))

    result = invoke_cli_main(
        cli_main,
        [
            "--vault",
            str(vault),
            "--matrix",
            "matrix.json",
            "--mode",
            "absorption_closeout",
            "--out",
            "report.json",
            "--fail-on-fail",
        ],
    )
    assert result.exit_code == 1
    assert json.loads((vault / "report.json").read_text())["status"] == "fail"


@pytest.mark.parametrize(
    "link,passes",
    [
        ("[[source--fake]]", True),
        ("[[wiki/source--fake#Summary|Evidence]]", True),
        ("[[wiki/source--fake.md]]", True),
        ("source--fake", False),
        ("[[source--fake-other]]", False),
        ("<!-- [[source--fake]] -->", False),
        ("`[[source--fake]]`", False),
        ("    [[source--fake]]\n", False),
        (r"\[[source--fake]]", False),
        ("```md\n[[source--fake]]\n```", False),
        ("---\nsource: '[[source--fake]]'\n---\n# Routing metadata only", False),
    ],
)
def test_closeout_requires_visible_target_to_source_wikilink(intake, link, passes):
    vault, entry = intake
    (vault / "wiki/synthesis--target.md").write_text(link, encoding="utf-8")
    report = report_for(vault, entry)
    assert report["status"] == ("pass" if passes else "fail")
    assert report["summary"]["absorption_pass_count"] == int(passes)


@pytest.mark.parametrize(
    "state", ["missing", "directory", "unreadable", "outside", "symlink"]
)
def test_closeout_rejects_unavailable_target(intake, state):
    vault, entry = intake
    entry["target_page"] = "wiki/synthesis--target.md"
    path = vault / entry["target_page"]
    if state == "directory":
        path.mkdir()
    elif state == "unreadable":
        path.write_text("[[source--fake]]")
    elif state in {"outside", "symlink"}:
        outside = vault.parent / f"{vault.name}-outside.md"
        outside.write_text("[[source--fake]]")
        if state == "outside":
            entry["target_page"] = f"../{outside.name}"
        else:
            path.symlink_to(outside)
    original_open = Path.open

    def denied_target(p, *args, **kwargs):
        if state == "unreadable" and p == path:
            raise PermissionError("synthetic denial")
        return original_open(p, *args, **kwargs)

    with patch.object(Path, "open", denied_target):
        assert report_for(vault, entry)["status"] == "fail"


def test_family_label_requires_concrete_target_and_binds_target_bytes(intake):
    vault, entry = intake
    entry.update(proposed_action="create_new_synthesis_family", target="new-family")
    path = vault / "system/synthesis--target.md"
    path.write_text("[[wiki/source--fake]]\n")
    assert report_for(vault, entry)["status"] == "fail"
    entry["target_page"] = "system/synthesis--target.md"
    first = report_for(vault, entry)
    assert first["status"] == "pass"
    assert first == report_for(vault, entry)
    path.write_text(path.read_text() + "\nAdditional conclusion.\n")
    edited = report_for(vault, entry)
    assert edited["status"] == "pass"
    assert (
        edited["input_fingerprints"]["target_pages"]
        != first["input_fingerprints"]["target_pages"]
    )
    assert (
        edited["input_fingerprints"]["matrix"] == first["input_fingerprints"]["matrix"]
    )
    path.unlink()
    missing = report_for(vault, entry)
    assert missing["status"] == "fail"
    assert (
        missing["input_fingerprints"]["target_pages"]
        != edited["input_fingerprints"]["target_pages"]
    )
    path.write_text("[[wiki/source--fake]]\n")
    assert report_for(vault, entry)["input_fingerprints"] == first["input_fingerprints"]


def test_ambiguous_stems_require_qualified_target_and_source_link(intake):
    vault, entry = intake
    (vault / "system/source--fake.md").write_text("Other source")
    for root in ("wiki", "system"):
        (vault / root / "synthesis--target.md").write_text("[[source--fake]]")
    assert report_for(vault, entry)["status"] == "fail"
    entry["target_page"] = "wiki/synthesis--target.md"
    assert report_for(vault, entry)["status"] == "fail"
    (vault / entry["target_page"]).write_text("[[wiki/source--fake]]")
    assert report_for(vault, entry)["status"] == "pass"


@pytest.mark.parametrize(
    "action",
    ["keep_source_only_seed", "discard_from_active_routes", "update_existing_source"],
)
def test_source_only_actions_do_not_require_a_synthesis(intake, action):
    vault, entry = intake
    entry.update(proposed_action=action, target="source--fake")
    report = report_for(vault, entry)
    assert report["status"] == "pass"
    expected = "pass" if action == "update_existing_source" else "not_applicable"
    assert report["proposals"][0]["absorption_audit"]["status"] == expected
    (vault / entry["source_page"]).unlink()
    report = report_for(vault, entry)
    # A discard is a reviewed disposition; it does not assert a retained source.
    assert report["status"] == (
        "pass" if action == "discard_from_active_routes" else "fail"
    )


def test_missing_source_and_raw_binding_cannot_close_out(intake):
    vault, entry = intake
    (vault / "wiki/synthesis--target.md").write_text("[[source--fake]]")
    (vault / entry["source_page"]).write_text("A source note without its raw binding.")
    report = report_for(vault, entry)
    assert report["status"] == "fail"
    assert "source_raw_path_not_bound" in report["proposals"][0]["issues"]


def test_source_path_must_identify_the_actual_markdown_page(intake):
    vault, entry = intake
    original = vault / entry["source_page"]
    entry["source_page"] = "wiki/source--fake.txt"
    original.rename(vault / entry["source_page"])
    (vault / "wiki/synthesis--target.md").write_text("[[wiki/source--fake.txt]]")
    assert report_for(vault, entry)["status"] == "fail"


def test_v2_schema_rejects_unchecked_or_failed_completion_and_accepts_legacy(intake):
    vault, entry = intake
    report = report_for(vault, entry)
    report["proposals"][0]["closeout_status"] = "pass"
    assert validate_with_schema(report, load_schema(SCHEMA_PATH))
    report = report_for(vault, entry, "route_proposal")
    report["schema_version"] = 1
    row = report["proposals"][0]
    del row["route_status"], row["absorption_audit"]
    row["closeout_status"] = "pass"
    for key in (
        "closeout_not_checked_count",
        "absorption_pass_count",
        "absorption_not_applicable_count",
    ):
        del report["summary"][key]
    assert validate_with_schema(report, load_schema(SCHEMA_PATH)) == []
