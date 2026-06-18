from __future__ import annotations

import datetime as dt

from ops.scripts.core.runtime_context import RuntimeContext

DEFAULT_FROZEN_AT = dt.datetime(2026, 4, 15, 0, 0, tzinfo=dt.UTC)
RELEASE_FROZEN_AT = dt.datetime(2026, 5, 23, 12, 0, tzinfo=dt.UTC)
ARTIFACT_FRESHNESS_FROZEN_AT = dt.datetime(2026, 5, 5, 8, 30, tzinfo=dt.UTC)


def frozen_context(
  at: dt.datetime = DEFAULT_FROZEN_AT,
  *,
  display_timezone: dt.tzinfo = dt.UTC,
) -> RuntimeContext:
    return RuntimeContext(display_timezone=display_timezone, clock=lambda: at)


def release_context() -> RuntimeContext:
    return frozen_context(RELEASE_FROZEN_AT)


def artifact_freshness_context() -> RuntimeContext:
    return frozen_context(ARTIFACT_FRESHNESS_FROZEN_AT)
