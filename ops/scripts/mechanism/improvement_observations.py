from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - direct script fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from ops.scripts.improvement_observations_runtime import main
else:
    from .improvement_observations_runtime import main


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
