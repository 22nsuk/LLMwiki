from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tools.verify_installed_wheel import RESOURCE_PROBE, verify_wheel

pytestmark = pytest.mark.public


def test_installed_wheel_rejects_private_build_residue(tmp_path: Path) -> None:
    wheel = tmp_path / "synthetic.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("ops/reports/private_diagnostic.py", "# synthetic private artifact\n")
    with pytest.raises(ValueError, match="policy-excluded local artifacts"):
        verify_wheel(wheel, tmp_path)


def test_installed_wheel_probe_rejects_checkout_imports(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    code = f"import sys; sys.path.insert(0, {str(root)!r})\n" + RESOURCE_PROBE
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode != 0
    assert "ops imported outside installed environment" in result.stderr
