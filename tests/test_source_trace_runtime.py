from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.core.policy_runtime import load_policy
from ops.scripts.core.source_trace_profile_runtime import (
    MISSING_EXPORT_EXCLUDED_BOUND,
    MISSING_EXPORT_EXCLUDED_UNBOUND,
    MISSING_GENERATED_REBUILDABLE,
    MISSING_INVALID_PATH,
    MISSING_PRIVATE_SURFACE_EXPECTED,
    MISSING_UNCLASSIFIED,
    PRESENT,
    PUBLIC_CODE_MIRROR_PROFILE,
    RELEASE_ARCHIVE_PROFILE,
    STRICT_PROFILE,
    classify_source_trace_targets,
)
from ops.scripts.core.source_trace_runtime import (
    extract_source_trace_refs,
    missing_source_trace_targets,
)
from ops.scripts.registry.raw_registry_runtime import (
    load_registry_source_trace_resolution_state,
)
from tests.minimal_vault_runtime import seed_open_question_smoke_vault


class SourceTraceRuntimeTests(unittest.TestCase):
    def test_extract_and_resolve_missing_source_trace_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "existing.txt").write_text("ok", encoding="utf-8")
            source_trace = """
- `existing.txt`
- `missing.txt`
- `https://example.com/reference`
"""
            self.assertEqual(
                extract_source_trace_refs(source_trace),
                ["existing.txt", "missing.txt", "https://example.com/reference"],
            )
            self.assertEqual(
                missing_source_trace_targets(root, source_trace),
                [{"ref": "missing.txt", "resolved_path": "missing.txt"}],
            )

    def test_extract_source_trace_refs_normalizes_slashes_and_unicode(self) -> None:
        source_trace = """
- `raw\\Cafe\u0301.pdf`
- `./raw/../raw/Caf\u00e9.pdf`
"""
        self.assertEqual(extract_source_trace_refs(source_trace), ["raw/Café.pdf"])

    def test_missing_source_trace_targets_accepts_alias_resolution_map(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "vault"
            root.mkdir()
            seed_open_question_smoke_vault(root, "raw\\fake.pdf")
            (root / "raw" / "fake.pdf").rename(root / "raw" / "fake-alias.pdf")

            shard = root / "system" / "system-raw-registry" / "wiki.md"
            shard_text = shard.read_text(encoding="utf-8")
            shard_text = shard_text.replace(
                "- display_path: `raw/fake.pdf`\n",
                "- display_path: `raw/fake.pdf`\n- path aliases:\n  - `raw/fake-alias.pdf`\n",
            )
            shard.write_text(shard_text, encoding="utf-8")

            source_page = root / "wiki" / "source--fake.md"
            source_text = source_page.read_text(encoding="utf-8")
            source_text = source_text.replace('raw_path: "raw/fake.pdf"', 'raw_path: "raw/fake-alias.pdf"')
            source_page.write_text(source_text, encoding="utf-8")

            policy, _ = load_policy(root)
            resolution_state = load_registry_source_trace_resolution_state(root, policy["registry_contract"])

            self.assertEqual(
                missing_source_trace_targets(
                    root,
                    "- `raw/fake.pdf`\n",
                    resolution_state["resolution_map"],
                ),
                [],
            )

    def test_flat_ops_script_source_trace_resolves_to_subpackage_relocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "ops" / "scripts" / "eval" / "wiki_lint.py"
            script.parent.mkdir(parents=True)
            script.write_text("def main():\n    return 0\n", encoding="utf-8")

            self.assertEqual(
                missing_source_trace_targets(root, "- `ops/scripts/wiki_lint.py`\n"),
                [],
            )

    def test_source_trace_profile_classifies_missing_targets_by_distribution_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("ok\n", encoding="utf-8")
            source_trace = """
- `README.md`
- `missing.md`
- `runs/run-1/promotion/evidence.json`
- `ops/reports/generated.json`
- `tmp/local.json`
- `raw/private.pdf`
"""

            strict_by_ref = {
                item["ref"]: item
                for item in classify_source_trace_targets(
                    root,
                    source_trace,
                    profile=STRICT_PROFILE,
                )
            }
            release_by_ref = {
                item["ref"]: item
                for item in classify_source_trace_targets(
                    root,
                    source_trace,
                    profile=RELEASE_ARCHIVE_PROFILE,
                )
            }
            public_by_ref = {
                item["ref"]: item
                for item in classify_source_trace_targets(
                    root,
                    source_trace,
                    profile=PUBLIC_CODE_MIRROR_PROFILE,
                )
            }

            self.assertEqual(strict_by_ref["README.md"]["classification"], PRESENT)
            self.assertEqual(strict_by_ref["missing.md"]["classification"], MISSING_UNCLASSIFIED)
            self.assertTrue(strict_by_ref["missing.md"]["blocks_profile"])
            self.assertEqual(
                release_by_ref["runs/run-1/promotion/evidence.json"]["classification"],
                MISSING_EXPORT_EXCLUDED_BOUND,
            )
            self.assertTrue(
                release_by_ref["runs/run-1/promotion/evidence.json"]["profile_allows_missing"]
            )
            self.assertEqual(
                release_by_ref["ops/reports/generated.json"]["classification"],
                MISSING_GENERATED_REBUILDABLE,
            )
            self.assertTrue(
                release_by_ref["ops/reports/generated.json"]["profile_allows_missing"]
            )
            self.assertEqual(
                release_by_ref["tmp/local.json"]["classification"],
                MISSING_EXPORT_EXCLUDED_UNBOUND,
            )
            self.assertTrue(release_by_ref["tmp/local.json"]["blocks_profile"])
            self.assertEqual(
                public_by_ref["raw/private.pdf"]["classification"],
                MISSING_PRIVATE_SURFACE_EXPECTED,
            )
            self.assertIn("full-vault", public_by_ref["raw/private.pdf"]["linkage_requirement"])

    def test_source_trace_profile_classifies_invalid_path_shapes_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            absolute_missing_export_excluded = root / "runs" / "run-1" / "evidence.json"
            source_trace = f"""
- `{absolute_missing_export_excluded.as_posix()}`
- `tmp/../runs/run-1/evidence.json`
"""

            by_ref = {
                item["ref"]: item
                for item in classify_source_trace_targets(
                    root,
                    source_trace,
                    profile=RELEASE_ARCHIVE_PROFILE,
                )
            }

            regression_cases = {
                "absolute": (absolute_missing_export_excluded.as_posix(),),
                "traversal": ("tmp/../runs/run-1/evidence.json", "runs/run-1/evidence.json"),
            }

            for label, candidate_refs in regression_cases.items():
                with self.subTest(label=label):
                    target = next((by_ref[ref] for ref in candidate_refs if ref in by_ref), None)
                    self.assertIsNotNone(target, f"expected one of {candidate_refs!r} in classified source trace targets")
                    assert target is not None
                    self.assertEqual(target["classification"], MISSING_INVALID_PATH)
                    self.assertTrue(target["blocks_profile"])
                    self.assertFalse(target["profile_allows_missing"])
                    self.assertNotIn(
                        target["classification"],
                        {MISSING_EXPORT_EXCLUDED_BOUND, MISSING_EXPORT_EXCLUDED_UNBOUND},
                    )


if __name__ == "__main__":
    unittest.main()
