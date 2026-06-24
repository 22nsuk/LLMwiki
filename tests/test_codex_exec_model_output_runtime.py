from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from ops.scripts.core.codex_exec_model_output_runtime import (
    read_model_output,
    scope_freeze_input_digest,
    validate_model_output_contract,
)
from tests.executor_model_output_test_utils import build_valid_model_output_payload
from tests.minimal_vault_runtime import REPO_ROOT

pytestmark = pytest.mark.report_contract


class _Request:
    artifact_root: Path
    run_id: str
    role: str
    scope_freeze: dict[str, object]

    def __init__(
        self,
        artifact_root: Path,
        run_id: str,
        role: str,
        scope_freeze: dict[str, object],
    ) -> None:
        self.artifact_root = artifact_root
        self.run_id = run_id
        self.role = role
        self.scope_freeze = scope_freeze


def _seed_schema(vault: Path) -> None:
    schema_path = vault / "ops" / "schemas" / "executor-report.schema.json"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        (REPO_ROOT / "ops" / "schemas" / "executor-report.schema.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _seed_routing_report(vault: Path, *, run_id: str, role: str) -> None:
    routing_dir = vault / "runs" / run_id
    routing_dir.mkdir(parents=True, exist_ok=True)
    (routing_dir / f"subagent-routing.{role}.json").write_text(
        json.dumps(
            {
                "routing_decision": {
                    "sandbox_mode": "workspace-write",
                    "model": "gpt-5.5",
                    "reasoning_effort": "high",
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )


class CodexExecModelOutputRuntimeTests(unittest.TestCase):
    def test_read_model_output_rejects_invalid_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "model-output.json"
            path.write_text("[]\n", encoding="utf-8")
            result = read_model_output(path)
            self.assertEqual(result.status, "invalid_root")

    def test_validate_model_output_contract_accepts_valid_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            _seed_schema(vault)
            scope_freeze = {"run_id": "run-a", "proposal_id": "proposal-a"}
            (vault / "scope-freeze.json").write_text(json.dumps(scope_freeze) + "\n", encoding="utf-8")
            _seed_routing_report(vault, run_id="run-a", role="worker")
            payload = build_valid_model_output_payload(
                vault,
                run_id="run-a",
                role="worker",
                notes=["ok"],
                scope_freeze_rel="scope-freeze.json",
            )
            path = vault / "out.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            model_output = read_model_output(path)
            assert model_output.payload is not None
            validated = validate_model_output_contract(
                model_output,
                request=_Request(vault, "run-a", "worker", scope_freeze),
            )
            self.assertEqual(validated.status, "ok")
            self.assertIsNotNone(validated.payload)

    def test_validate_model_output_contract_rejects_missing_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            _seed_schema(vault)
            scope_freeze = {"run_id": "run-a"}
            payload = {"status": "pass", "run_id": "run-a", "role": "worker"}
            path = vault / "out.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            model_output = read_model_output(path)
            assert model_output.payload is not None
            validated = validate_model_output_contract(
                model_output,
                request=_Request(vault, "run-a", "worker", scope_freeze),
            )
            self.assertEqual(validated.status, "schema_invalid")

    def test_validate_model_output_contract_rejects_missing_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            _seed_schema(vault)
            scope_freeze = {"run_id": "run-a", "proposal_id": "proposal-a"}
            (vault / "scope-freeze.json").write_text(json.dumps(scope_freeze) + "\n", encoding="utf-8")
            _seed_routing_report(vault, run_id="run-a", role="worker")
            payload = build_valid_model_output_payload(
                vault,
                run_id="run-a",
                role="worker",
                notes=["ok"],
                scope_freeze_rel="scope-freeze.json",
            )
            payload.pop("status")
            path = vault / "out.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            model_output = read_model_output(path)
            assert model_output.payload is not None
            validated = validate_model_output_contract(
                model_output,
                request=_Request(vault, "run-a", "worker", scope_freeze),
            )
            self.assertEqual(validated.status, "schema_invalid")

    def test_validate_model_output_contract_rejects_run_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            _seed_schema(vault)
            scope_freeze = {"run_id": "run-a", "proposal_id": "proposal-a"}
            (vault / "scope-freeze.json").write_text(json.dumps(scope_freeze) + "\n", encoding="utf-8")
            _seed_routing_report(vault, run_id="run-a", role="worker")
            payload = build_valid_model_output_payload(
                vault,
                run_id="run-a",
                role="worker",
                notes=["ok"],
                scope_freeze_rel="scope-freeze.json",
            )
            path = vault / "out.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            model_output = read_model_output(path)
            assert model_output.payload is not None
            validated = validate_model_output_contract(
                model_output,
                request=_Request(vault, "run-b", "worker", scope_freeze),
            )
            self.assertEqual(validated.status, "identity_mismatch")

    def test_validate_model_output_contract_rejects_input_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            _seed_schema(vault)
            scope_freeze = {"run_id": "run-a", "proposal_id": "proposal-a"}
            (vault / "scope-freeze.json").write_text(json.dumps(scope_freeze) + "\n", encoding="utf-8")
            _seed_routing_report(vault, run_id="run-a", role="worker")
            payload = build_valid_model_output_payload(
                vault,
                run_id="run-a",
                role="worker",
                notes=["ok"],
                scope_freeze_rel="scope-freeze.json",
            )
            payload["input_digest"] = "0" * 64
            path = vault / "out.json"
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            model_output = read_model_output(path)
            assert model_output.payload is not None
            validated = validate_model_output_contract(
                model_output,
                request=_Request(vault, "run-a", "worker", scope_freeze),
            )
            self.assertEqual(validated.status, "identity_mismatch")
            self.assertIn("input_digest", validated.note)

    def test_scope_freeze_input_digest_is_stable(self) -> None:
        scope_freeze = {"run_id": "run-a", "proposal_id": "proposal-a", "status": "runnable"}
        self.assertEqual(
            scope_freeze_input_digest(scope_freeze),
            scope_freeze_input_digest({"status": "runnable", "proposal_id": "proposal-a", "run_id": "run-a"}),
        )
