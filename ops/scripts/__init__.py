"""Runtime scripts package for lint, eval, export, and promotion tooling."""

from __future__ import annotations

import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec
from importlib.util import spec_from_loader
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any

from ._compatibility_alias_policy import discover_flat_reexport_targets


class _ProxyLoader(Loader):
    """Loader that proxies to the canonical subpackage module."""

    def __init__(self, target_name: str, target_path: Path) -> None:
        self._target_name = target_name
        self._target_path = target_path

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        return None

    def exec_module(self, module: ModuleType) -> None:
        alias_name = module.__name__
        target = __import__(self._target_name, fromlist=["__name__"])
        sys.modules[alias_name] = target
        module.__dict__.update(target.__dict__)
        module.__file__ = target.__file__

    def get_filename(self, fullname: str) -> str:
        return str(self._target_path)

    def get_code(self, fullname: str) -> CodeType:
        source = (
            "from runpy import run_module\n"
            f"run_module({self._target_name!r}, run_name='__main__', alter_sys=True)\n"
        )
        return compile(source, str(self._target_path), "exec")


class _ReexportFinder(MetaPathFinder):
    """Intercepts ``ops.scripts.<name>`` imports and redirects them to the
    appropriate subpackage (e.g. ``ops.scripts.core.<name>``).
    """

    def __init__(self) -> None:
        self._mapping: dict[str, tuple[str, Path]] = {}
        here = Path(__file__).parent
        for name, target in discover_flat_reexport_targets(here).items():
            self._mapping[name] = (target.canonical_module, target.path)

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if not fullname.startswith("ops.scripts."):
            return None
        parts = fullname.split(".")
        if len(parts) != 3:
            return None
        name = parts[2]
        mapped_target = self._mapping.get(name)
        if mapped_target is None:
            return None
        target_name, target_path = mapped_target
        loader = _ProxyLoader(target_name, target_path)
        return spec_from_loader(fullname, loader, origin=str(target_path))


# Install the finder early so that ``import ops.scripts.X`` continues to work
# after the flat layout was reorganized into domain subpackages.
sys.meta_path.insert(0, _ReexportFinder())
