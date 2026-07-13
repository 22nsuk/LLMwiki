from __future__ import annotations

import datetime as dt
import json
import re
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from ops.scripts.core.runtime_context import RuntimeContext
from ops.scripts.core.schema_runtime import load_schema, validate_with_schema
from ops.scripts.eval.lint_uplift_plan import build_report as build_lint_uplift_report
from ops.scripts.eval.type_uplift_plan import build_report as build_type_uplift_report
from ops.scripts.public.public_surface_policy import PUBLIC_LOCAL_ABSOLUTE_PATH_RE
from tests.minimal_vault_runtime import REPO_ROOT, seed_minimal_vault

pytestmark = [pytest.mark.public, pytest.mark.report_contract]

_UPLIFT_VAULT_TEMP: tempfile.TemporaryDirectory[str] | None = None

STRICT_LINT_SCHEMA = REPO_ROOT / "ops" / "schemas" / "strict-lint-inventory.schema.json"
STRICT_TYPE_SCHEMA = REPO_ROOT / "ops" / "schemas" / "strict-type-inventory.schema.json"

RUNTIME_CODEHEALTH_TIME_GUARD_PATHS = (
    REPO_ROOT / "ops" / "scripts" / "core" / "codex_exec_executor.py",
    REPO_ROOT / "ops" / "scripts" / "eval" / "complexity_ratchet_runtime.py",
    REPO_ROOT / "ops" / "scripts" / "eval" / "lint_uplift_plan.py",
    REPO_ROOT / "ops" / "scripts" / "eval" / "structural_complexity_budget.py",
    REPO_ROOT / "ops" / "scripts" / "eval" / "type_uplift_plan.py",
    REPO_ROOT / "ops" / "scripts" / "eval" / "uplift_promotion_runtime.py",
    REPO_ROOT / "ops" / "scripts" / "mechanism" / "auto_improve_readiness_runtime.py",
    REPO_ROOT
    / "ops"
    / "scripts"
    / "mechanism"
    / "auto_improve_maintenance_decision_runtime.py",
    REPO_ROOT
    / "ops"
    / "scripts"
    / "mechanism"
    / "mutation_proposal_promotion_runtime.py",
    REPO_ROOT / "ops" / "scripts" / "release" / "release_closeout_envelope_runtime.py",
    REPO_ROOT / "ops" / "scripts" / "release" / "release_evidence_dashboard.py",
    REPO_ROOT
    / "ops"
    / "scripts"
    / "release"
    / "release_evidence_dashboard_render_runtime.py",
    REPO_ROOT / "ops" / "scripts" / "release" / "release_run_ready.py",
    REPO_ROOT / "ops" / "scripts" / "release" / "release_status_surface.py",
)

RUNTIME_CODEHEALTH_PUBLIC_TEXT_PATHS = (
    REPO_ROOT / "docs" / "development.md",
    REPO_ROOT / "docs" / "release.md",
    REPO_ROOT / "ops" / "runtime-decomposition-plan.md",
    *RUNTIME_CODEHEALTH_TIME_GUARD_PATHS,
)
LOCAL_ONLY_PUBLIC_TEXT_PREFIXES = (
    ".kiro/",
    ".obsidian/",
    ".ouroboros/",
    ".serena/",
    ".vscode/",
    "external-reports/",
    "raw/",
    "runs/",
    "system/",
    "wiki/",
)

DIRECT_WALL_CLOCK_RE = re.compile(
    r"\b(?:datetime|dt\.datetime)\.(?:now|utcnow)\s*\("
    r"|\b(?:date|dt\.date)\.today\s*\("
    r"|\btime\.time\s*\("
)


def _seed_uplift_vault(vault: Path) -> None:
    seed_minimal_vault(vault)
    (vault / "mk").mkdir(exist_ok=True)
    (vault / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    (vault / "tests").mkdir(exist_ok=True)
    (vault / "tools").mkdir(exist_ok=True)
    (vault / "ops" / "scripts" / "alpha.py").write_text("x = 1\n", encoding="utf-8")
    (vault / "tests" / "test_alpha.py").write_text(
        "def test_alpha(): pass\n", encoding="utf-8"
    )
    (vault / "tools" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    (vault / "tools" / "ruff_strict_preview.py").write_text("", encoding="utf-8")
    (vault / "tools" / "strict_preview_audit.py").write_text("", encoding="utf-8")
    (vault / "mk" / "static.mk").write_text(
        "RUFF_STRICT_PREVIEW_TARGETS ?= ops/scripts tests tools\n"
        "MYPY_TARGETS ?= ops/scripts tests tools\n"
        "MYPY_STRICT_PREVIEW_TARGETS ?= ops/scripts tests tools\n"
        "ruff-strict-preview:\n"
        '\tpython tools/ruff_strict_preview.py --targets "$(RUFF_STRICT_PREVIEW_TARGETS)"\n',
        encoding="utf-8",
    )
    (vault / "pyproject.toml").write_text(
        "[tool.ruff]\n"
        'target-version = "py312"\n\n'
        "[tool.ruff.lint]\n"
        'select = ["E4", "E7", "E9", "F", "B", "SIM", "UP", "I"]\n\n'
        "[tool.mypy]\n"
        'python_version = "3.12"\n'
        "check_untyped_defs = true\n"
        "disallow_untyped_defs = true\n"
        "disallow_incomplete_defs = true\n",
        encoding="utf-8",
    )
    (vault / "tmp").mkdir(exist_ok=True)
    (vault / "tmp" / "strict-preview-audit.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "summary": {
                    "total_error_count": 0,
                    "ruff_error_count": 0,
                    "mypy_error_count": 0,
                },
                "ruff": {"rule_counts": {}},
                "mypy": {"error_count": 0},
            }
        ),
        encoding="utf-8",
    )


def _uplift_vault() -> Path:
    global _UPLIFT_VAULT_TEMP
    if _UPLIFT_VAULT_TEMP is None:
        _UPLIFT_VAULT_TEMP = tempfile.TemporaryDirectory()
        vault = Path(_UPLIFT_VAULT_TEMP.name) / "vault"
        vault.mkdir()
        _seed_uplift_vault(vault)
    return Path(_UPLIFT_VAULT_TEMP.name) / "vault"


def _envelope_stub(_vault: Path, **kwargs: object) -> dict[str, object]:
    generated_at = str(kwargs["generated_at"])
    return {
        "$schema": str(kwargs["schema_path"]),
        "artifact_kind": str(kwargs["artifact_kind"]),
        "generated_at": generated_at,
        "producer": str(kwargs["producer"]),
        "source_command": str(kwargs["source_command"]),
        "source_revision": "test-source-revision",
        "source_tree_fingerprint": "test-source-tree-fingerprint",
        "input_fingerprints": {
            "policy": "test-policy",
            "schema": "test-schema",
            "source_paths": "test-source-paths",
        },
        "schema_version": 1,
        "artifact_status": "current",
        "retention_policy": "canonical_report",
        "encoding": "utf-8",
        "currentness": {
            "status": "current",
            "checked_at": generated_at,
        },
    }


def _cheap_report_patches(vault: Path) -> tuple[Any, ...]:
    policy = {"version": 4}
    resolved_policy = vault / "ops" / "policies" / "wiki-maintainer-policy.yaml"
    return (
        mock.patch(
            "ops.scripts.eval.lint_uplift_plan.load_policy",
            return_value=(policy, resolved_policy),
        ),
        mock.patch(
            "ops.scripts.eval.type_uplift_plan.load_policy",
            return_value=(policy, resolved_policy),
        ),
        mock.patch(
            "ops.scripts.eval.lint_uplift_plan.build_canonical_report_envelope",
            side_effect=_envelope_stub,
        ),
        mock.patch(
            "ops.scripts.eval.type_uplift_plan.build_canonical_report_envelope",
            side_effect=_envelope_stub,
        ),
    )


@given(offset_seconds=st.integers(min_value=0, max_value=31_536_000))
@settings(max_examples=100)
def test_property_7_uplift_reports_are_deterministic_under_injected_clock(
    offset_seconds: int,
) -> None:
    """Feature: runtime-codehealth-hardening, Property 7: generated_at/날짜 파생 필드를 가진 분해/교정 모듈의 생성 결과는 동일 입력과 임의 고정 injected clock에서 두 번 생성해도 byte 단위로 동일하며 generated_at은 wall-clock이 아니라 injected clock 파생값과 같다"""
    clock_value = dt.datetime(2026, 1, 1, tzinfo=dt.UTC) + dt.timedelta(
        seconds=offset_seconds
    )
    context = RuntimeContext(display_timezone=dt.UTC, clock=lambda: clock_value)
    vault = _uplift_vault()
    patches = _cheap_report_patches(vault)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
    ):
        first = {
            "lint": build_lint_uplift_report(
                vault,
                targets=["ops/scripts", "tests", "tools"],
                context=context,
            ),
            "type": build_type_uplift_report(
                vault,
                targets=["ops/scripts", "tests", "tools"],
                context=context,
            ),
        }
        second = {
            "lint": build_lint_uplift_report(
                vault,
                targets=["ops/scripts", "tests", "tools"],
                context=context,
            ),
            "type": build_type_uplift_report(
                vault,
                targets=["ops/scripts", "tests", "tools"],
                context=context,
            ),
        }

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["lint"]["generated_at"] == context.isoformat_z()
    assert first["type"]["generated_at"] == context.isoformat_z()


@given(offset_seconds=st.integers(min_value=0, max_value=31_536_000))
@settings(max_examples=100)
def test_property_1_uplift_reports_preserve_schema_backed_contracts(
    offset_seconds: int,
) -> None:
    """Feature: runtime-codehealth-hardening, Property 1: 분해되거나 교정된 모듈의 build_* façade가 생성하는 report는 해당 schema 검증을 통과하고 필드 집합·필드 타입·필수/선택 여부가 분해/교정 전과 동일하다"""
    clock_value = dt.datetime(2026, 1, 1, tzinfo=dt.UTC) + dt.timedelta(
        seconds=offset_seconds
    )
    context = RuntimeContext(display_timezone=dt.UTC, clock=lambda: clock_value)
    vault = _uplift_vault()
    patches = _cheap_report_patches(vault)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
    ):
        lint_report = build_lint_uplift_report(
            vault,
            targets=["ops/scripts", "tests", "tools"],
            context=context,
        )
        type_report = build_type_uplift_report(
            vault,
            targets=["ops/scripts", "tests", "tools"],
            context=context,
        )

    assert validate_with_schema(lint_report, load_schema(STRICT_LINT_SCHEMA)) == []
    assert validate_with_schema(type_report, load_schema(STRICT_TYPE_SCHEMA)) == []
    assert set(lint_report) >= {"enforced_rule_families", "remaining_violations"}
    assert set(type_report) >= {"enforced_flags", "remaining_errors"}


def test_runtime_codehealth_changed_modules_do_not_use_direct_wall_clock() -> None:
    offenders: list[str] = []
    for path in RUNTIME_CODEHEALTH_TIME_GUARD_PATHS:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if DIRECT_WALL_CLOCK_RE.search(line):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}"
                )

    assert offenders == []


def test_runtime_codehealth_public_text_does_not_leak_local_absolute_paths() -> None:
    offenders: list[str] = []
    scanned_paths: list[Path] = []
    for path in RUNTIME_CODEHEALTH_PUBLIC_TEXT_PATHS:
        if not path.exists():
            continue
        scanned_paths.append(path)
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if PUBLIC_LOCAL_ABSOLUTE_PATH_RE.search(line):
                offenders.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: {line.strip()}"
                )

    assert scanned_paths
    assert offenders == []


def test_runtime_codehealth_public_text_guard_uses_public_safe_surfaces() -> None:
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in RUNTIME_CODEHEALTH_PUBLIC_TEXT_PATHS
        if any(
            path.relative_to(REPO_ROOT).as_posix().startswith(prefix)
            for prefix in LOCAL_ONLY_PUBLIC_TEXT_PREFIXES
        )
    ]

    assert offenders == []
