from __future__ import annotations

import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ops.scripts.policy_runtime import load_policy
from ops.scripts.wiki_eval import evaluate
from ops.scripts.wiki_lint import lint
from ops.scripts.wiki_snapshot_runtime import build_wiki_runtime_snapshot
from tests.minimal_vault_runtime import seed_minimal_vault


def lint_and_evaluate_with_shared_snapshot(
    vault: Path,
    policy_path: str | None = None,
) -> tuple[dict, dict]:
    policy, _ = load_policy(vault, policy_path)
    snapshot = build_wiki_runtime_snapshot(
        vault,
        registry_contract=policy["registry_contract"],
    )
    return (
        lint(vault, policy_path, snapshot=snapshot),
        evaluate(vault, policy_path, snapshot=snapshot),
    )


class SeededMinimalVaultTestCase(unittest.TestCase):
    _seed_temp_dir: tempfile.TemporaryDirectory[str] | None
    _seed_vault: Path | None

    @classmethod
    def seed_vault(cls, vault: Path) -> None:
        seed_minimal_vault(vault)

    @classmethod
    def fresh_vault_strategy(cls) -> str:
        return "copy_seed"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._seed_temp_dir = None
        cls._seed_vault = None
        if cls.fresh_vault_strategy() != "copy_seed":
            return
        cls._seed_temp_dir = tempfile.TemporaryDirectory(prefix=f"{cls.__name__}-seed-")
        cls._seed_vault = Path(cls._seed_temp_dir.name) / "vault"
        cls._seed_vault.mkdir()
        cls.seed_vault(cls._seed_vault)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            if cls._seed_temp_dir is not None:
                cls._seed_temp_dir.cleanup()
        finally:
            super().tearDownClass()

    @contextmanager
    def fresh_vault(self) -> Iterator[Path]:
        temp_dir = tempfile.TemporaryDirectory(prefix=f"{self.__class__.__name__}-case-")
        try:
            vault = Path(temp_dir.name) / "vault"
            strategy = self.fresh_vault_strategy()
            if strategy == "copy_seed":
                if self._seed_vault is None:
                    raise AssertionError("copy_seed strategy requires a prepared seed vault")
                shutil.copytree(self._seed_vault, vault)
            elif strategy == "reseed":
                vault.mkdir()
                self.seed_vault(vault)
            else:
                raise ValueError(f"unsupported fresh vault strategy: {strategy}")
            yield vault
        finally:
            temp_dir.cleanup()
