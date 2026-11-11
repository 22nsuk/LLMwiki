from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ops.scripts.registry import (
    raw_intake_route_proposal as route,
    raw_intake_source_quality as quality,
)
from ops.scripts.registry.raw_intake_input_runtime import IntakeMatrixError
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault
from tests.test_raw_intake_route_proposal import matrix_entry, write_matrix


@pytest.fixture(params=["quality", "route_proposal", "absorption_closeout"])
def gate(tmp_path, request):
    seed_minimal_vault(tmp_path)
    module = quality if request.param == "quality" else route
    kwargs = {} if module is quality else {"mode": request.param}
    return tmp_path, module, kwargs


def invalid_matrix(case):
    row = matrix_entry()
    payload = {
        "$schema": "ops/schemas/raw-intake-absorption-matrix.schema.json",
        "generated_at": "2026-11-12T00:00:00Z",
        "scope": "synthetic-admission-test",
        "source_count": 1,
        "action_counts": {row["proposed_action"]: 1},
        "confidence_counts": {row["confidence"]: 1},
        "target_counts": {row["target"]: 1},
        "matrix": [row],
    }
    if case == "missing_matrix":
        del payload["matrix"]
    elif case == "wrong_rows_type":
        payload["matrix"] = {}
    elif case == "null_row":
        payload["matrix"] = [None]
    elif case == "mixed_rows":
        payload["matrix"].append(None)
    elif case == "duplicate_id":
        payload["matrix"].append(dict(row))
        payload["source_count"] = 2
        for key in ("action_counts", "confidence_counts", "target_counts"):
            payload[key] = dict.fromkeys(payload[key], 2)
    elif case == "source_count":
        payload["source_count"] = 0
    elif case == "boolean_count":
        payload["source_count"] = True
    elif case in {"action_counts", "confidence_counts", "target_counts"}:
        payload[case] = {}
    elif case == "empty_id":
        row["registry_id"] = ""
    elif case == "padded_id":
        row["registry_id"] = " W-001 "
    elif case == "newline_id":
        row["registry_id"] = "W-001\n"
    elif case == "missing_row_field":
        del row["source_page"]
    elif case == "unknown_row_field":
        row["soruce_page"] = row["source_page"]
    elif case == "null_path":
        row["raw_path"] = None
    elif case == "wrong_schema":
        payload["$schema"] = "https://example.invalid/permissive.schema.json"
    return payload


@pytest.mark.parametrize(
    "case",
    [
        "missing_matrix",
        "wrong_rows_type",
        "null_row",
        "mixed_rows",
        "duplicate_id",
        "source_count",
        "boolean_count",
        "action_counts",
        "confidence_counts",
        "target_counts",
        "empty_id",
        "padded_id",
        "newline_id",
        "missing_row_field",
        "unknown_row_field",
        "null_path",
        "wrong_schema",
    ],
)
def test_invalid_batch_is_rejected_before_any_corpus_read(gate, case):
    vault, module, kwargs = gate
    (vault / "matrix.json").write_text(json.dumps(invalid_matrix(case)))
    with patch.object(
        module, "read_intake_inputs", side_effect=AssertionError("must not read corpus")
    ), pytest.raises(IntakeMatrixError):
        module.build_report(vault, matrix_path="matrix.json", **kwargs)


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        "null",
        "true",
        '"text"',
        "{",
        '{"matrix": [null], "matrix": []}',
        '{"matrix": NaN}',
        '{"matrix": [], "metadata": {"x": 1, "x": 2}}',
    ],
)
def test_cli_admission_error_is_nonzero_without_fail_flags_and_preserves_old_output(
    gate, raw
):
    vault, module, kwargs = gate
    (vault / "matrix.json").write_text(raw)
    out = vault / "report.json"
    old = b'{"status":"pass","historical":true}\n'
    out.write_bytes(old)
    args = ["--vault", str(vault), "--matrix", "matrix.json", "--out", "report.json"]
    if kwargs:
        args += ["--mode", kwargs["mode"]]

    def main(argv):
        raise SystemExit(module.main(argv))

    result = invoke_cli_main(main, args)
    assert result.exit_code == 2
    assert "intake matrix admission failed" in result.stderr
    assert not result.stdout
    assert out.read_bytes() == old
    out.unlink()
    assert invoke_cli_main(main, args).exit_code == 2
    assert not out.exists()


@pytest.mark.parametrize("state", ["absent", "directory", "bad_utf8"])
def test_unreadable_matrix_cannot_produce_a_report(gate, state):
    vault, module, kwargs = gate
    path = vault / "matrix.json"
    if state == "directory":
        path.mkdir()
    elif state == "bad_utf8":
        path.write_bytes(b"\xff")
    with pytest.raises(IntakeMatrixError, match="cannot read JSON matrix"):
        module.build_report(vault, matrix_path=path, **kwargs)


def test_explicit_empty_batch_is_a_valid_no_work_report(gate):
    vault, module, kwargs = gate
    write_matrix(vault / "matrix.json", [])
    report = module.build_report(vault, matrix_path="matrix.json", **kwargs)
    assert report["status"] == "pass"
    assert report["matrix"]["entry_count"] == 0
    assert report["summary"]["entry_count"] == 0
    path = module.write_report(vault, report, "empty-report.json")
    assert json.loads(path.read_text())["status"] == "pass"


def test_installed_contract_is_not_overridden_by_the_vault(gate):
    vault, module, kwargs = gate
    (vault / "matrix.json").write_text("{}")
    (vault / "ops/schemas/raw-intake-absorption-matrix.schema.json").write_text("{}")
    with pytest.raises(IntakeMatrixError):
        module.build_report(vault, matrix_path="matrix.json", **kwargs)
