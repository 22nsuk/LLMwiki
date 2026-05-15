#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path

import sys

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ops.scripts.planning_gate_validate_runtime import (
        ARTIFACT_SCHEMAS,
        ArtifactLoadError,
        OPTIONAL_ARTIFACT_SCHEMAS,
        PlanningArtifactError,
        load_artifact,
        main,
        validate_artifact,
        validate_optional_artifact,
        validate_run_dir,
    )
else:
    from .planning_gate_validate_runtime import (
        ARTIFACT_SCHEMAS,
        ArtifactLoadError,
        OPTIONAL_ARTIFACT_SCHEMAS,
        PlanningArtifactError,
        load_artifact,
        main,
        validate_artifact,
        validate_optional_artifact,
        validate_run_dir,
    )

__all__ = [
    "ARTIFACT_SCHEMAS",
    "ArtifactLoadError",
    "OPTIONAL_ARTIFACT_SCHEMAS",
    "PlanningArtifactError",
    "load_artifact",
    "main",
    "validate_artifact",
    "validate_optional_artifact",
    "validate_run_dir",
]


if __name__ == "__main__":
    main()
