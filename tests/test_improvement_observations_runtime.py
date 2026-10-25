from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.mechanism.improvement_observations_runtime import (
    backfill_improvement_observations,
    build_run_improvement_observations,
    main,
    task_improvement_observations_rel,
    update_improvement_observation,
    write_run_improvement_observations,
    write_task_improvement_observations,
)
from tests.minimal_vault_runtime import seed_minimal_vault

pytestmark = pytest.mark.report_contract


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 27, 12, 0, tzinfo=dt.UTC),
    )


def observation(observation_id: str, *, status: str = "open") -> dict:
    return {
        "observation_id": observation_id,
        "surface": f"ops/scripts/{observation_id}.py",
        "problem": f"{observation_id} still needs a durable resolution",
        "why_it_matters": "follow-up state should remain canonical",
        "automation_candidate": f"automate {observation_id}",
        "suggested_followup": f"plan {observation_id}",
        "resolution_evidence": [f"source:{observation_id}"],
        "status": status,
    }


class ImprovementObservationsRuntimeTests(unittest.TestCase):
    def test_build_run_improvement_observations_validates_against_schema(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        schema = load_schema(repo_root / "ops" / "schemas" / "improvement-observations.schema.json")
        payload = build_run_improvement_observations(
            "run-improvement-observations",
            context=fixed_context(),
        )
        self.assertEqual(validate_with_schema(payload, schema), [])
        self.assertEqual(payload["artifact_kind"], "run_improvement_observations")
        self.assertEqual(payload["generated_at"], "2026-04-27T12:00:00Z")
        self.assertEqual(payload["currentness"], {"status": "current", "checked_at": "2026-04-27T12:00:00Z"})
        self.assertEqual(payload["record_id"], "run-improvement-observations")
        self.assertEqual(payload["run_id"], "run-improvement-observations")
        self.assertEqual(payload["scope"], "system_mechanism_run")

    def test_write_task_improvement_observations_uses_default_task_report_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)

            rel_path = write_task_improvement_observations(
                vault,
                task_id="task-runtime-refactor",
                context=fixed_context(),
            )

            self.assertEqual(
                rel_path,
                task_improvement_observations_rel("task-runtime-refactor"),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")
            self.assertEqual(validate_with_schema(payload, schema), [])
            self.assertEqual(payload["artifact_kind"], "task_improvement_observations")
            self.assertEqual(payload["generated_at"], "2026-04-27T12:00:00Z")
            self.assertEqual(payload["record_id"], "task-runtime-refactor")
            self.assertEqual(payload["task_id"], "task-runtime-refactor")
            self.assertEqual(payload["scope"], "repo_maintenance_task")

    def test_backfill_improvement_observations_preserves_observations_and_captured_at(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            rel_path = task_improvement_observations_rel("task-legacy")
            legacy_path = vault / rel_path
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                json.dumps(
                    {
                        "$schema": "ops/schemas/improvement-observations.schema.json",
                        "record_id": "task-legacy",
                        "task_id": "task-legacy",
                        "captured_at": "2026-04-20T00:00:00Z",
                        "scope": "repo_maintenance_task",
                        "summary": "legacy task observation",
                        "observations": [
                            {
                                "observation_id": "legacy_followup",
                                "surface": "ops/scripts/example.py",
                                "problem": "manual follow-up is easy to lose",
                                "why_it_matters": "automation backlog should be durable",
                                "automation_candidate": "add a report writer",
                                "suggested_followup": "backfill the artifact envelope",
                                "resolution_evidence": [
                                    "source:ops/scripts/mechanism/improvement_observations_runtime.py",
                                    "test:tests/test_improvement_observations_runtime.py",
                                ],
                                "status": "planned",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            written = backfill_improvement_observations(
                vault,
                [rel_path],
                context=fixed_context(),
            )
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")

            self.assertEqual(written, [rel_path])
            self.assertEqual(validate_with_schema(payload, schema), [])
            self.assertEqual(payload["captured_at"], "2026-04-20T00:00:00Z")
            self.assertEqual(payload["generated_at"], "2026-04-27T12:00:00Z")
            self.assertEqual(payload["observations"][0]["observation_id"], "legacy_followup")
            self.assertEqual(
                payload["observations"][0]["resolution_evidence"],
                [
                    "source:ops/scripts/mechanism/improvement_observations_runtime.py",
                    "test:tests/test_improvement_observations_runtime.py",
                ],
            )

    def test_backfill_improvement_observations_converts_legacy_root_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            rel_path = task_improvement_observations_rel("task-legacy-list")
            legacy_path = vault / rel_path
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "release_closeout_summary_run_manifest_check_alignment",
                            "status": "open",
                            "summary": "Release preseal cleared one blocker but run manifest evidence was stale.",
                            "suggested_followup": "Regenerate run-ready evidence when source edits invalidate the run manifest.",
                            "evidence": [
                                "ops/scripts/release/release_closeout_summary.py",
                                "build/release/release-run-manifest.json",
                            ],
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            written = backfill_improvement_observations(
                vault,
                [rel_path],
                context=fixed_context(),
            )
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")

            self.assertEqual(written, [rel_path])
            self.assertEqual(validate_with_schema(payload, schema), [])
            self.assertEqual(payload["record_id"], "task-legacy-list")
            self.assertEqual(payload["task_id"], "task-legacy-list")
            self.assertEqual(
                payload["observations"][0]["observation_id"],
                "release_closeout_summary_run_manifest_check_alignment",
            )
            self.assertIn("release_closeout_summary.py", payload["observations"][0]["surface"])

    def test_update_task_observation_cli_rebuilds_envelope_and_preserves_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            rel_path = write_task_improvement_observations(
                vault,
                task_id="task-semantic-update",
                context=fixed_context(),
                observations=[observation("untouched"), observation("target")],
                summary="Keep this stable summary.",
            )
            artifact_path = vault / rel_path
            before = json.loads(artifact_path.read_text(encoding="utf-8"))
            before["record_id"] = "stable-record-id"
            artifact_path.write_text(
                json.dumps(before, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            stdout = StringIO()

            with mock.patch(
                "ops.scripts.mechanism.improvement_observations_runtime.timestamp",
                return_value="2026-04-28T12:00:00Z",
            ), redirect_stdout(stdout):
                result = main(
                    [
                        "--vault",
                        str(vault),
                        "--task-id",
                        "task-semantic-update",
                        "--update-observation-id",
                        "target",
                        "--status",
                        "automated",
                        "--suggested-followup",
                        "Retain the regression test as the closeout guard.",
                        "--resolution-evidence",
                        "source:ops/scripts/mechanism/improvement_observations_runtime.py",
                        "--resolution-evidence",
                        "test:tests/test_improvement_observations_runtime.py",
                    ]
                )

            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            schema = load_schema(vault / "ops" / "schemas" / "improvement-observations.schema.json")
            output = json.loads(stdout.getvalue())

            self.assertEqual(result, 0)
            self.assertEqual(output["path"], rel_path)
            self.assertEqual(output["observation_id"], "target")
            self.assertEqual(validate_with_schema(payload, schema), [])
            self.assertEqual(payload["generated_at"], "2026-04-28T12:00:00Z")
            self.assertEqual(payload["record_id"], "stable-record-id")
            self.assertEqual(payload["task_id"], before["task_id"])
            self.assertEqual(payload["captured_at"], before["captured_at"])
            self.assertEqual(payload["summary"], before["summary"])
            self.assertEqual(payload["observations"][0], before["observations"][0])
            self.assertEqual(
                [item["observation_id"] for item in payload["observations"]],
                ["untouched", "target"],
            )
            target = payload["observations"][1]
            expected_target = {
                **before["observations"][1],
                "status": "automated",
                "suggested_followup": "Retain the regression test as the closeout guard.",
                "resolution_evidence": [
                    "source:ops/scripts/mechanism/improvement_observations_runtime.py",
                    "test:tests/test_improvement_observations_runtime.py",
                ],
            }
            self.assertEqual(target, expected_target)
            self.assertNotEqual(
                payload["input_fingerprints"]["observations"],
                before["input_fingerprints"]["observations"],
            )

    def test_update_run_observation_changes_only_supplied_semantic_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            rel_path = write_run_improvement_observations(
                vault,
                run_id="run-semantic-update",
                context=fixed_context(),
                observations=[observation("run_target", status="planned")],
                summary="Stable run summary.",
            )
            before = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            written = update_improvement_observation(
                vault,
                run_id="run-semantic-update",
                observation_id="run_target",
                status="automated",
                context=fixed_context(),
            )
            payload = json.loads((vault / rel_path).read_text(encoding="utf-8"))

            self.assertEqual(written, rel_path)
            self.assertEqual(payload["record_id"], before["record_id"])
            self.assertEqual(payload["run_id"], before["run_id"])
            self.assertEqual(payload["captured_at"], before["captured_at"])
            self.assertEqual(payload["summary"], before["summary"])
            self.assertEqual(payload["observations"][0]["status"], "automated")
            self.assertEqual(
                payload["observations"][0]["suggested_followup"],
                before["observations"][0]["suggested_followup"],
            )
            self.assertEqual(
                payload["observations"][0]["resolution_evidence"],
                before["observations"][0]["resolution_evidence"],
            )

    def test_update_observation_rejects_missing_and_duplicate_exact_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            seed_minimal_vault(vault)
            write_task_improvement_observations(
                vault,
                task_id="task-exact-match",
                context=fixed_context(),
                observations=[observation("exact_id")],
            )

            with self.assertRaisesRegex(ValueError, "observation_id not found: EXACT_ID"):
                update_improvement_observation(
                    vault,
                    task_id="task-exact-match",
                    observation_id="EXACT_ID",
                    status="planned",
                    context=fixed_context(),
                )

            rel_path = write_task_improvement_observations(
                vault,
                task_id="task-duplicate-id",
                context=fixed_context(),
                observations=[observation("duplicate"), observation("duplicate")],
            )
            before = (vault / rel_path).read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate observation_id values: duplicate"):
                update_improvement_observation(
                    vault,
                    task_id="task-duplicate-id",
                    observation_id="duplicate",
                    status="planned",
                    context=fixed_context(),
                )
            self.assertEqual((vault / rel_path).read_text(encoding="utf-8"), before)

    def test_update_cli_rejects_noop_and_incompatible_modes(self) -> None:
        cases = [
            (
                ["--task-id", "task", "--update-observation-id", "observation"],
                "requires at least one",
            ),
            (
                ["--task-id", "task", "--status", "planned"],
                "require --update-observation-id",
            ),
            (
                [
                    "--task-id",
                    "task",
                    "--update-observation-id",
                    "observation",
                    "--status",
                    "planned",
                    "--summary",
                    "scaffold summary",
                ],
                "cannot be combined with scaffold options",
            ),
            (
                [
                    "--backfill-existing",
                    "--update-observation-id",
                    "observation",
                    "--status",
                    "planned",
                ],
                "cannot be combined with scaffold or observation-update options",
            ),
        ]
        for argv, message in cases:
            with self.subTest(argv=argv), self.assertRaisesRegex(SystemExit, message):
                main(argv)


if __name__ == "__main__":
    unittest.main()
