from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from ops.scripts.core.runtime_context import RuntimeContext

LOCKED_CI_INSTALL_SNIPPET = (
    "- run: python -c \"from pathlib import Path; Path('tmp').mkdir(exist_ok=True)\"\n"
    "- run: make uv-lock-check\n"
    "- run: uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt\n"
    "- run: python -m pip install -r tmp/locked-requirements.ci.txt\n"
)
LOCKED_COMPOSITE_ACTION_SNIPPET = """
name: Setup Python and uv
runs:
  using: composite
  steps:
    - name: Install dependencies from lock
      shell: bash
      run: |
        python -c "from pathlib import Path; Path('tmp').mkdir(exist_ok=True)"
        make uv-lock-check
        uv export --frozen --extra dev --format requirements-txt --no-hashes -o tmp/locked-requirements.ci.txt
        python -m pip install --upgrade pip
        python -m pip install -r tmp/locked-requirements.ci.txt
""".strip()
SOURCE_ZIP_SHA256 = "a" * 64


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 15, 12, 0, tzinfo=dt.UTC),
    )


def seed_dependency_inputs(vault: Path) -> None:
    (vault / "pyproject.toml").write_text(
        """
[project]
name = "sample"
version = "0.1.0"
dependencies = [
  "PyYAML>=6.0,<7",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (vault / "requirements.txt").write_text("PyYAML>=6.0,<7\n", encoding="utf-8")
    (vault / "requirements-dev.txt").write_text(
        "-r requirements.txt\npytest>=8.3,<9\n", encoding="utf-8"
    )
    (vault / "uv.lock").write_text(
        """
version = 1

[[package]]
name = "pyyaml"
version = "6.0.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [
  { name = "typing-extensions", marker = "python_version >= '3.12'" },
]
sdist = { url = "https://files.pythonhosted.org/packages/pyyaml.tar.gz", hash = "sha256:abc", upload-time = "2026-01-01T00:00:00Z" }
wheels = [
  { url = "https://files.pythonhosted.org/packages/pyyaml.whl", hash = "sha256:def" },
]

[[package]]
name = "typing-extensions"
version = "4.15.0"
source = { registry = "https://pypi.org/simple" }
sdist = { url = "https://files.pythonhosted.org/packages/typing_extensions.tar.gz", hash = "sha256:ghi", upload-time = "2026-01-01T00:00:00Z" }
wheels = [
  { url = "https://files.pythonhosted.org/packages/typing_extensions.whl", hash = "sha256:jkl" },
]
""".strip()
        + "\n",
        encoding="utf-8",
    )


def seed_source_package_evidence(vault: Path, *, status: str = "pass") -> None:
    report_path = vault / "ops" / "reports" / "source-package-clean-extract.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "status": status,
                "source_zip": {
                    "path": "build/source-package-check/LLMwiki-source.zip",
                    "exists": True,
                    "sha256": SOURCE_ZIP_SHA256,
                },
                "source_package_reproducibility_status": status,
                "test_source_package_status": status,
                "zip_smoke_report": {
                    "status": status,
                    "archive_budget_pass": status == "pass",
                    "manifest_comparison_pass": status == "pass",
                },
            }
        ),
        encoding="utf-8",
    )
