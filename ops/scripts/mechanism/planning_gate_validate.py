#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.mechanism.planning_gate_validate_runtime import (
        ARTIFACT_SCHEMAS,
        OPTIONAL_ARTIFACT_SCHEMAS,
        ArtifactLoadError,
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
        OPTIONAL_ARTIFACT_SCHEMAS,
        ArtifactLoadError,
        PlanningArtifactError,
        load_artifact,
        main,
        validate_artifact,
        validate_optional_artifact,
        validate_run_dir,
    )

__all__ = [
    "ARTIFACT_SCHEMAS",
    "OPTIONAL_ARTIFACT_SCHEMAS",
    "ArtifactLoadError",
    "PlanningArtifactError",
    "load_artifact",
    "main",
    "validate_artifact",
    "validate_optional_artifact",
    "validate_run_dir",
]


if __name__ == "__main__":
    main()
