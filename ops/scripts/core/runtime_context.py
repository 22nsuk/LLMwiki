from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from dataclasses import dataclass, replace

from .policy_runtime import display_timezone_from_policy

Clock = Callable[[], dt.datetime]


def _default_clock() -> dt.datetime:
    injected = os.environ.get("LLMWIKI_RUNTIME_UTC_NOW", "").strip()
    if injected:
        try:
            parsed = dt.datetime.fromisoformat(injected.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.UTC)
            return parsed.astimezone(dt.UTC)
    return dt.datetime.now(dt.UTC)


@dataclass(frozen=True)
class RuntimeContext:
    display_timezone: dt.timezone
    clock: Clock = _default_clock
    session_id: str = ""
    iteration: int = 0
    executor_id: str = ""

    @classmethod
    def from_policy(
        cls,
        policy: dict,
        *,
        clock: Clock | None = None,
        session_id: str = "",
        iteration: int = 0,
        executor_id: str = "",
    ) -> RuntimeContext:
        return cls(
            display_timezone=display_timezone_from_policy(policy),
            clock=clock or _default_clock,
            session_id=session_id,
            iteration=iteration,
            executor_id=executor_id,
        )

    def with_iteration(self, iteration: int) -> RuntimeContext:
        return replace(self, iteration=iteration)

    def with_executor(self, executor_id: str) -> RuntimeContext:
        return replace(self, executor_id=executor_id)

    def utcnow(self) -> dt.datetime:
        current = self.clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=dt.UTC)
        return current.astimezone(dt.UTC)

    def isoformat_z(self) -> str:
        return self.utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def today(self) -> dt.date:
        return self.utcnow().astimezone(self.display_timezone).date()

    def local_heading_timestamp(self) -> str:
        current = self.utcnow().astimezone(self.display_timezone)
        tz_name = self.display_timezone.tzname(current) or "UTC"
        return f"{current.strftime('%Y-%m-%d %H:%M')} {tz_name}"
