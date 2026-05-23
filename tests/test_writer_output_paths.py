from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.mechanism_assess import main as mechanism_assess_main
from ops.scripts.output_runtime import resolve_output_path, write_output_text
from ops.scripts.path_runtime import stable_report_path
from ops.scripts.planning_gate_validate import main as planning_gate_validate_main
from ops.scripts.policy_runtime import load_policy
from ops.scripts.promotion_gate import main as promotion_gate_main
from ops.scripts.raw_registry_export import main as raw_registry_export_main
from ops.scripts.raw_registry_preflight import main as raw_registry_preflight_main
from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.schema_constants_runtime import RAW_REGISTRY_EXPORT_SCHEMA_PATH, WIKI_MANIFEST_SCHEMA_PATH
from ops.scripts.schema_runtime import load_schema, validate_with_schema
from ops.scripts.script_output_surfaces import build_registry as build_script_output_surface_registry
from ops.scripts.select_subagent_rung import main as select_subagent_rung_main
from ops.scripts.starter_bundle_runtime import DEFAULT_STARTER_BUNDLE, starter_bundle_path
from ops.scripts.wiki_eval import main as wiki_eval_main
from ops.scripts.wiki_eval_coverage import main as wiki_eval_coverage_main
from ops.scripts.wiki_lint import main as wiki_lint_main
from ops.scripts.wiki_manifest import main as wiki_manifest_main
from ops.scripts.wiki_stage2_eval import main as wiki_stage2_eval_main
from tests.cli_test_runtime import invoke_cli_main
from tests.minimal_vault_runtime import seed_minimal_vault, seed_planning_artifacts, seed_subagent_profiles


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_RUNTIME_FILE = "ops/scripts/core/output_runtime.py"
SCRIPT_OUTPUT_SURFACES = Path("ops/script-output-surfaces.json")
SCRIPT_OUTPUT_SURFACES_SCHEMA = Path("ops/schemas/script-output-surfaces.schema.json")
OUTPUT_WRITER_CLASSIFICATIONS = {"repo_artifact", "user_export", "mixed"}
PUBLIC_EXPORT_MANIFEST = REPO_ROOT / "PUBLIC-EXPORT-MANIFEST.json"


def _script_tree(rel_path: str) -> ast.AST:
    path = REPO_ROOT / rel_path
    return ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)


def _referenced_names(rel_path: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_script_tree(rel_path)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _output_option_names(rel_path: str) -> set[str]:
    options: set[str] = set()
    for node in ast.walk(_script_tree(rel_path)):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        for arg in node.args:
            if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                continue
            if arg.value == "--out" or arg.value.endswith("-out"):
                options.add(arg.value)
    return options


def _ops_script_files() -> list[str]:
    return sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "ops" / "scripts").rglob("*.py")
        if path.name != "__init__.py"
    )


def _script_output_surface_registry() -> dict:
    return json.loads(SCRIPT_OUTPUT_SURFACES.read_text(encoding="utf-8"))


def _runtime_context_for_generated_at(iso_z: str) -> RuntimeContext:
    import datetime as dt

    instant = dt.datetime.fromisoformat(iso_z.replace("Z", "+00:00"))
    return RuntimeContext(display_timezone=dt.timezone.utc, clock=lambda: instant)


def _script_output_surface_entries() -> list[dict]:
    return list(_script_output_surface_registry()["surfaces"])


def _files_with_output_options() -> set[str]:
    return {rel_path for rel_path in _ops_script_files() if _output_option_names(rel_path)}


def _files_referencing(name: str) -> set[str]:
    return {
        rel_path
        for rel_path in _ops_script_files()
        if rel_path != OUTPUT_RUNTIME_FILE and name in _referenced_names(rel_path)
    }


class WriterOutputPathsTest(unittest.TestCase):
    def run_main(self, main_fn, *args: str, cwd: Path) -> None:
        result = invoke_cli_main(main_fn, list(args), cwd=cwd)
        self.assertEqual(
            result.exit_code,
            0,
            msg=result.stderr or result.stdout,
        )

    def test_resolve_output_path_uses_vault_for_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            resolved = resolve_output_path(vault, "reports/result.json")
            self.assertEqual(resolved, (vault / "reports" / "result.json").resolve())

    def test_resolve_output_path_uses_default_relative_path_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            vault.mkdir()
            resolved = resolve_output_path(
                vault,
                None,
                default_relative_path="runs/run-test/promotion-report.json",
            )
            self.assertEqual(
                resolved,
                (vault / "runs" / "run-test" / "promotion-report.json").resolve(),
            )

    def test_write_output_text_creates_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "nested" / "dir" / "report.json"
            write_output_text(destination, "{}")
            self.assertTrue(destination.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "{}")

    def test_script_output_surface_registry_schema_validates(self) -> None:
        registry = _script_output_surface_registry()
        schema = load_schema(SCRIPT_OUTPUT_SURFACES_SCHEMA)
        schema_errors = validate_with_schema(registry, schema)

        self.assertEqual(
            schema_errors,
            [],
            msg=(
                "script-output-surfaces schema validation failed; this is a schema/shape "
                "error in ops/script-output-surfaces.json, not an AST inventory mismatch: "
                + "; ".join(schema_errors[:5])
            ),
        )
        self.assertEqual(registry["artifact_kind"], "script_output_surfaces")
        self.assertEqual(registry["producer"], "ops.scripts.script_output_surfaces")
        self.assertEqual(registry["currentness"]["status"], "current")
        self.assertEqual(
            set(registry["classification_values"]),
            {"repo_artifact", "user_export", "mixed", "no_output", "diagnostic_only"},
        )
        paths = [entry["path"] for entry in registry["surfaces"]]
        self.assertEqual(len(paths), len(set(paths)))

    @unittest.skipIf(
        PUBLIC_EXPORT_MANIFEST.exists(),
        (
            "script-output-surfaces is generated from the full-vault source tree; "
            "public exports validate schema and writer classifications without "
            "requiring full-vault fingerprint equality"
        ),
    )
    def test_script_output_surface_registry_matches_current_ast_inventory(self) -> None:
        actual = _script_output_surface_registry()
        expected = build_script_output_surface_registry(
            REPO_ROOT,
            context=_runtime_context_for_generated_at(str(actual.get("generated_at"))),
        )

        self.maxDiff = None
        self.assertEqual(actual["surfaces"], expected["surfaces"])
        self.assertEqual(actual["classification_values"], expected["classification_values"])

    def test_output_option_writers_are_classified(self) -> None:
        registry_files = {entry["path"] for entry in _script_output_surface_entries() if entry["output_options"]}
        inventory_files = _files_with_output_options()
        self.assertEqual(
            inventory_files,
            registry_files,
            msg=(
                "output option surface mismatch: the AST inventory of scripts declaring "
                "`--out`/`*-out` does not match ops/script-output-surfaces.json. "
                f"missing_from_registry={sorted(inventory_files - registry_files)}; "
                f"stale_in_registry={sorted(registry_files - inventory_files)}"
            ),
        )
        for entry in _script_output_surface_entries():
            if entry["output_options"]:
                self.assertIn(entry["classification"], OUTPUT_WRITER_CLASSIFICATIONS)

    def test_permissive_output_resolver_is_only_used_by_user_export_writers(self) -> None:
        registry_files = {
            entry["path"]
            for entry in _script_output_surface_entries()
            if entry["references_resolve_output_path"]
        }

        self.assertEqual(_files_referencing("resolve_output_path"), registry_files)
        for entry in _script_output_surface_entries():
            if entry["references_resolve_output_path"]:
                self.assertIn(entry["classification"], {"user_export", "mixed"})

    def test_repo_artifact_output_options_do_not_use_permissive_resolver(self) -> None:
        for entry in _script_output_surface_entries():
            if entry["classification"] != "repo_artifact" or not entry["output_options"]:
                continue
            with self.subTest(rel_path=entry["path"]):
                self.assertFalse(entry["references_resolve_output_path"])
                self.assertNotIn("resolve_output_path", _referenced_names(entry["path"]))

    def test_repo_output_resolver_users_are_classified(self) -> None:
        registry_files = {
            entry["path"]
            for entry in _script_output_surface_entries()
            if entry["references_resolve_repo_output_path"]
        }

        self.assertEqual(_files_referencing("resolve_repo_output_path"), registry_files)
        for entry in _script_output_surface_entries():
            if entry["references_resolve_repo_output_path"]:
                self.assertIn(entry["classification"], {"repo_artifact", "mixed"})

    def test_mixed_output_writer_uses_both_resolvers_explicitly(self) -> None:
        for entry in _script_output_surface_entries():
            if entry["classification"] != "mixed":
                continue
            with self.subTest(rel_path=entry["path"]):
                names = _referenced_names(entry["path"])
                self.assertIn("resolve_output_path", names)
                self.assertIn("resolve_repo_output_path", names)

    def test_wiki_eval_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                wiki_eval_main,
                "--vault",
                str(vault),
                "--out",
                "reports/eval/report.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "eval" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")

    def test_wiki_lint_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                wiki_lint_main,
                "--vault",
                str(vault),
                "--out",
                "reports/lint/report.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "lint" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")

    def test_wiki_lint_cli_normalizes_windows_separator_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                wiki_lint_main,
                "--vault",
                str(vault),
                "--out",
                "reports\\lint\\windows-path-report.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "lint" / "windows-path-report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")

    def test_wiki_eval_coverage_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                wiki_eval_coverage_main,
                "--vault",
                str(vault),
                "--out",
                "reports/eval-coverage/report.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "eval-coverage" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")

    def test_wiki_stage2_eval_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                wiki_stage2_eval_main,
                "--vault",
                str(vault),
                "--out",
                "reports/stage2/report.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "stage2" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")

    def test_planning_gate_validate_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            seed_planning_artifacts(vault, "run-test-output")

            self.run_main(
                planning_gate_validate_main,
                "--vault",
                str(vault),
                "--artifact-dir",
                "artifacts",
                "--out",
                "reports/planning/validation.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "planning" / "validation.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")

    def test_planning_gate_validate_cli_uses_policy_default_starter_bundle_when_artifact_dir_is_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            policy, _ = load_policy(vault)
            default_artifact_dir = starter_bundle_path(vault, policy, DEFAULT_STARTER_BUNDLE)
            seed_planning_artifacts(
                vault,
                "run-test-default-output",
                artifact_dir=default_artifact_dir,
            )

            self.run_main(
                planning_gate_validate_main,
                "--vault",
                str(vault),
                "--out",
                "reports/planning/default-validation.json",
                cwd=launcher,
            )

            report_path = vault / "reports" / "planning" / "default-validation.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "pass")
            self.assertEqual(
                report["artifact_dir"],
                stable_report_path(vault, default_artifact_dir),
            )

    def test_raw_registry_export_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                raw_registry_export_main,
                "--vault",
                str(vault),
                "--out",
                "generated/registry/export.json",
                cwd=launcher,
            )

            export_path = vault / "generated" / "registry" / "export.json"
            self.assertTrue(export_path.exists())
            export = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(export["entry_count"], 1)
            self.assertIn("content_sha256", export["entries"][0])
            self.assertRegex(export["entries"][0]["content_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                validate_with_schema(export, load_schema(vault / RAW_REGISTRY_EXPORT_SCHEMA_PATH)),
                [],
            )

    def test_raw_registry_preflight_cli_writes_relative_outs_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                raw_registry_preflight_main,
                "--vault",
                str(vault),
                "--out",
                "generated/preflight/report.json",
                "--reproducibility-out",
                "generated/preflight/reproducibility.json",
                cwd=launcher,
            )

            report_path = vault / "generated" / "preflight" / "report.json"
            reproducibility_path = vault / "generated" / "preflight" / "reproducibility.json"
            self.assertTrue(report_path.exists())
            self.assertTrue(reproducibility_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            reproducibility = json.loads(reproducibility_path.read_text(encoding="utf-8"))
            self.assertEqual(report["artifact_kind"], "raw_registry_preflight_report")
            self.assertEqual(
                reproducibility["artifact_kind"],
                "raw_registry_preflight_reproducibility",
            )
            self.assertEqual(reproducibility["stored_report"]["path"], "generated/preflight/report.json")

    def test_wiki_manifest_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                wiki_manifest_main,
                "--vault",
                str(vault),
                "--out",
                "generated/manifest/report.json",
                cwd=launcher,
            )

            manifest_path = vault / "generated" / "manifest" / "report.json"
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("files", manifest)
            self.assertEqual(
                validate_with_schema(manifest, load_schema(vault / WIKI_MANIFEST_SCHEMA_PATH)),
                [],
            )

    def test_promotion_gate_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                promotion_gate_main,
                "--vault",
                str(vault),
                "--artifact-class",
                "wiki_source",
                "--run-id",
                "run-test-output",
                "--primary-target",
                "wiki/source--fake.md",
                "--log-summary",
                "Writer output path regression test",
                "--out",
                "generated/promotion/report.json",
                cwd=launcher,
            )

            report_path = vault / "generated" / "promotion" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["artifact_class"], "wiki_source")
            self.assertEqual(report["run_id"], "run-test-output")

    def test_mechanism_assess_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)

            self.run_main(
                mechanism_assess_main,
                "--vault",
                str(vault),
                "--primary-target",
                "wiki/source--fake.md",
                "--test-file",
                "wiki/source--fake.md",
                "--out",
                "generated/mechanism/report.json",
                cwd=launcher,
            )

            report_path = vault / "generated" / "mechanism" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["primary_targets"], ["wiki/source--fake.md"])

    def test_select_subagent_rung_cli_writes_relative_out_under_vault(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "vault"
            launcher = Path(temp_dir) / "launcher"
            vault.mkdir()
            launcher.mkdir()
            seed_minimal_vault(vault)
            seed_subagent_profiles(vault, ["explorer"])

            self.run_main(
                select_subagent_rung_main,
                "--vault",
                str(vault),
                "--role",
                "explorer",
                "--out",
                "generated/subagent/report.json",
                cwd=launcher,
            )

            report_path = vault / "generated" / "subagent" / "report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["routing_decision"]["selected_rung"], 1)


if __name__ == "__main__":
    unittest.main()
