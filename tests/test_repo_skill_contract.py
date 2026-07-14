from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.eval.doc_graph_integrity import build_report as build_doc_graph_report
from ops.scripts.public.export_public_repo import should_export_public
from ops.scripts.public.public_surface_policy import PUBLIC_LOCAL_ABSOLUTE_PATH_RE

pytestmark = [pytest.mark.public, pytest.mark.report_contract, pytest.mark.report_contract_core]

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"


def _frontmatter(text: str) -> dict[str, object]:
    opening, separator, remainder = text.partition("---\n")
    assert opening == ""
    assert separator
    payload, closing, _body = remainder.partition("\n---\n")
    assert closing
    parsed = yaml.safe_load(payload)
    assert isinstance(parsed, dict)
    return parsed


def _skill_roots(skills_root: Path) -> list[Path]:
    roots = sorted(path for path in skills_root.iterdir() if path.is_dir())
    assert roots, "expected at least one repository skill"
    return roots


def _local_path_leaks(paths: list[Path]) -> list[str]:
    leaks: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if PUBLIC_LOCAL_ABSOLUTE_PATH_RE.search(line):
                leaks.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}:{line_number}: {line.strip()}"
                )
    return leaks


@pytest.mark.parametrize(
    "skill_root",
    _skill_roots(SKILLS_ROOT),
    ids=lambda path: path.name,
)
def test_repo_skill_package_is_complete_and_public(skill_root: Path) -> None:
    skill_path = skill_root / "SKILL.md"
    openai_yaml_path = skill_root / "agents" / "openai.yaml"
    assert skill_path.is_file(), skill_path.relative_to(REPO_ROOT).as_posix()
    assert openai_yaml_path.is_file(), openai_yaml_path.relative_to(
        REPO_ROOT
    ).as_posix()
    text = skill_path.read_text(encoding="utf-8")
    metadata = _frontmatter(text)

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == skill_root.name
    assert str(metadata["description"]).strip()
    assert "TODO" not in text

    payload = yaml.safe_load(openai_yaml_path.read_text(encoding="utf-8"))
    interface = payload["interface"]
    assert str(interface["display_name"]).strip()
    assert str(interface["short_description"]).strip()
    assert f"${skill_root.name}" in interface["default_prompt"]
    assert isinstance(payload["policy"]["allow_implicit_invocation"], bool)

    files = [path for path in skill_root.rglob("*") if path.is_file()]
    assert skill_path in files
    assert openai_yaml_path in files
    assert _local_path_leaks(files) == []
    for path in files:
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        assert should_export_public(rel_path), rel_path


def test_skill_root_discovery_includes_incomplete_package_directories(
    tmp_path: Path,
) -> None:
    incomplete_root = tmp_path / "incomplete"
    (incomplete_root / "agents").mkdir(parents=True)
    (incomplete_root / "agents" / "openai.yaml").write_text(
        "interface: {}\n",
        encoding="utf-8",
    )

    assert _skill_roots(tmp_path) == [incomplete_root]


def test_repo_skill_markdown_doc_graph_is_current() -> None:
    context = RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 7, 14, tzinfo=dt.UTC),
    )
    report = build_doc_graph_report(REPO_ROOT, context=context)
    failures = {
        key: report[key]
        for key in ("missing_links", "unallowed_orphans", "stale_allowlist")
        if report[key]
    }

    assert report["status"] == "pass", failures


def test_test_lane_skill_is_registry_backed() -> None:
    text = (SKILLS_ROOT / "llmwiki-test-lane-maintenance" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "ops/test-lane-registry.json" in text
    assert "do not copy a complete selector inventory" in text
    assert "make changed-path-minimum-test" in text
    assert "make sync-derived" in text


def test_external_report_skill_owns_reconciliation_workflow() -> None:
    text = (SKILLS_ROOT / "external-report-reconciliation" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for marker in (
        "canonical reconciliation workflow",
        "ACTION_CATALOG",
        "action status:",
        "action lifecycle:",
        "evidence condition:",
        "archive implication:",
        "build/release/*manifest.json",
        "mk/release-evidence.mk",
        "mk/release-learning.mk",
        "Do not infer archive readiness",
    ):
        assert marker in text
