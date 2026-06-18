from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.registry.raw_registry_shard_policy_sync import (
    SCHEMA_PATH,
    build_report,
    main as sync_main,
    write_policy,
)
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 6, 17, 12, 0, tzinfo=dt.UTC),
    )


def _new_shard_page() -> str:
    return """---
title: "Wiki Raw Registry Shard - New Test Shard"
page_type: "registry-shard"
corpus: "system"
special_role: "raw-registry-shard"
aliases:
  - "new-test-shard"
tags:
  - "corpus/system"
  - "type/registry-shard"
---

# system-raw-registry/wiki/new-test-shard

## Summary
- corpus shard: `wiki`

## Registered raw sources
- none

## Related pages
- [[system-raw-registry]]

## Source trace
- `system/system-raw-registry/wiki/new-test-shard.md`
"""


class RawRegistryShardPolicySyncTests(unittest.TestCase):
    def test_write_synchronizes_minimal_fixture_policy_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)

            write_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["drift_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_new_shard_without_policy_surfaces_is_reported_as_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            write_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            shard = vault / "system" / "system-raw-registry" / "wiki" / "new-test-shard.md"
            shard.parent.mkdir(parents=True, exist_ok=True)
            shard.write_text(_new_shard_page(), encoding="utf-8")

            report = build_report(vault, context=fixed_context())

        self.assertEqual(report["status"], "fail")
        drift = report["drift"]
        self.assertIn(
            "system/system-raw-registry/wiki/new-test-shard.md",
            drift["missing_raw_registry_shard_pages"],
        )
        self.assertIn(
            "system/system-raw-registry/wiki/new-test-shard.md",
            drift["missing_raw_registry_entry_page_corpus"],
        )
        self.assertIn(
            "system/system-raw-registry/wiki/new-test-shard.md",
            drift["missing_special_required_sections"],
        )
        self.assertIn(
            "system/system-raw-registry/wiki/new-test-shard.md",
            drift["missing_frontmatter_special_pages"],
        )
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_write_synchronizes_missing_policy_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            seed_minimal_vault(vault)
            write_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            shard = vault / "system" / "system-raw-registry" / "wiki" / "new-test-shard.md"
            shard.parent.mkdir(parents=True, exist_ok=True)
            shard.write_text(_new_shard_page(), encoding="utf-8")

            write_policy(vault, "ops/policies/wiki-maintainer-policy.yaml")
            report = build_report(vault, context=fixed_context())

            policy = json.loads(json.dumps(report["policy"]))

        self.assertEqual(policy["path"], "ops/policies/wiki-maintainer-policy.yaml")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["drift_count"], 0)
        self.assertEqual(validate_with_schema(report, load_schema(SCHEMA_PATH)), [])

    def test_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            completed = invoke_cli_main(
                sync_main,
                [
                    "--vault",
                    str(vault),
                    "--out",
                    "reports/raw-registry/shard-policy-sync.json",
                    "--write",
                ],
                cwd=launcher,
            )
            self.assertEqual(completed.exit_code, 0, msg=completed.stderr or completed.stdout)

            report_path = vault / "reports" / "raw-registry" / "shard-policy-sync.json"
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], SCHEMA_PATH)
            self.assertEqual(payload["status"], "pass")

    def test_cli_write_refuses_absent_shard_root_without_mutating_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            policy_path = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
            before = policy_path.read_text(encoding="utf-8")
            shutil.rmtree(vault / "system" / "system-raw-registry")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                exit_code = sync_main(["--vault", str(vault), "--write"])

            self.assertEqual(exit_code, 1)
            self.assertIn("raw registry shard root is absent", stderr.getvalue())
            self.assertEqual(policy_path.read_text(encoding="utf-8"), before)
