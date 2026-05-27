from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
from ops.scripts.artifact_freshness_runtime import build_canonical_report_envelope
from ops.scripts.source_revision_runtime import resolve_source_revision

from ops.scripts.release.release_run_manifest import git_commit
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = pytest.mark.public


def test_source_revision_uses_typed_source_package_status_without_git() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()

        revision = resolve_source_revision(vault)

        assert revision.revision == "source_package_without_git"
        assert revision.status == "source_package_without_git"


def test_release_authority_git_commit_uses_typed_source_package_status_without_git() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()

        assert git_commit(vault) == "source_package_without_git"


def test_source_revision_uses_git_head_when_git_metadata_exists() -> None:
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("git metadata is not present in this source package")

    expected = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()

    revision = resolve_source_revision(REPO_ROOT)

    assert revision.revision == expected
    assert revision.status == "git_head"
    assert revision.revision != "unknown"


def test_canonical_report_envelope_avoids_unknown_source_revision() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        vault = Path(temp_dir) / "vault"
        vault.mkdir()
        seed_minimal_vault(vault)

        envelope = build_canonical_report_envelope(
            vault,
            generated_at="2026-05-25T12:00:00Z",
            artifact_kind="example_report",
            producer="tests.example_report",
            source_command="pytest",
            resolved_policy_path=vault / "ops" / "policies" / "wiki-maintainer-policy.yaml",
            schema_path="ops/schemas/artifact-envelope.schema.json",
            source_paths=[],
        )

        assert envelope["source_revision"] == "source_package_without_git"
        assert "source_revision_status" not in envelope
