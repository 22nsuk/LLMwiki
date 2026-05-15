from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ops.scripts.sanitize_run_artifacts import sanitize_run_artifacts, sanitize_run_text


class SanitizeRunArtifactsTests(unittest.TestCase):
    def test_sanitize_run_text_rewrites_repo_and_temp_workspace_paths(self) -> None:
        repo_root = Path("/mnt/c/Users/Administrator/Desktop/작업/LLM Wiki vNext")
        text = """
repo=/mnt/c/Users/Administrator/Desktop/작업/LLM Wiki vNext
python="/mnt/c/Users/Administrator/Desktop/작업/LLM Wiki vNext/.venv/bin/python"
page=/mnt/c/Users/ADMINI~1/AppData/Local/Temp/run-123-workspace-abcd/vault/wiki/page.md
workspace=/mnt/c/Users/ADMINI~1/AppData/Local/Temp/run-123-workspace-abcd/vault
"""
        sanitized = sanitize_run_text(text, repo_root=repo_root)

        self.assertIn("repo=.", sanitized)
        self.assertIn('python=".venv/bin/python"', sanitized)
        self.assertIn("page=wiki/page.md", sanitized)
        self.assertIn("workspace=.", sanitized)
        self.assertNotIn("/mnt/c/Users/Administrator/Desktop/작업/LLM Wiki vNext", sanitized)
        self.assertNotIn("/AppData/Local/Temp/", sanitized)

    def test_sanitize_run_artifacts_updates_text_artifacts_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir) / "vault"
            run_dir = repo_root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            text_path = run_dir / "baseline-eval.json"
            text_path.write_text(
                '{"vault": "'
                + repo_root.as_posix()
                + '",'
                ' "page": "/mnt/c/Users/ADMINI~1/AppData/Local/Temp/run-1-workspace-a/vault/wiki/page.md"}',
                encoding="utf-8",
            )
            binary_path = run_dir / "image.bin"
            binary_path.write_bytes(b"\x00\x01")

            changed = sanitize_run_artifacts(repo_root=repo_root)

            self.assertEqual(changed, ["runs/run-1/baseline-eval.json"])
            self.assertEqual(binary_path.read_bytes(), b"\x00\x01")
            sanitized = text_path.read_text(encoding="utf-8")
            self.assertIn('"vault": "."', sanitized)
            self.assertIn('"page": "wiki/page.md"', sanitized)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
