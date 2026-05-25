from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ops.scripts.runtime_context import RuntimeContext
from ops.scripts.runtime_event_logging_runtime import (
    AppendRuntimeEventRequest,
    RuntimeEventRequest,
    append_runtime_event,
    build_runtime_event,
)
from ops.scripts.schema_runtime import (
    load_schema_with_vault_override,
    validate_with_schema,
)


def fixed_context() -> RuntimeContext:
    return RuntimeContext(
        display_timezone=dt.UTC,
        clock=lambda: dt.datetime(2026, 4, 23, tzinfo=dt.UTC),
        session_id="session-a",
    )


class RuntimeEventLoggingRuntimeTests(unittest.TestCase):
    def test_build_runtime_event_validates_with_linking_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            event = build_runtime_event(
                context=fixed_context(),
                component="auto_improve_readiness",
                phase="queue_blocked",
                decision="warn",
                decision_reason="all_proposals_blocked",
                artifact_path="ops/reports/auto-improve-readiness.json",
                duration_ms=12,
                policy_version=4,
                proposal_id="proposal-blocked",
                candidate_id="candidate-blocked",
                blocker="recent_log_overlap",
                blocker_kind="hard",
            )
            schema = load_schema_with_vault_override(vault, "ops/schemas/runtime-event.schema.json")

            self.assertEqual(validate_with_schema(event, schema), [])

    def test_append_runtime_event_writes_schema_valid_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            rel_path = append_runtime_event(
                vault,
                context=fixed_context(),
                component="auto_improve_readiness",
                phase="queue_blocked",
                decision="warn",
                decision_reason="recent_log_overlap",
                artifact_path="ops/reports/auto-improve-readiness.json",
                duration_ms=7,
                policy_version=4,
                proposal_id="proposal-blocked",
                candidate_id="candidate-blocked",
                blocker="recent_log_overlap",
                blocker_kind="hard",
            )

            event = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(event["proposal_id"], "proposal-blocked")
            self.assertEqual(event["blocker"], "recent_log_overlap")

    def test_request_objects_drive_build_and_append(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir)
            request = RuntimeEventRequest(
                context=fixed_context(),
                component="Auto Improve Session",
                phase="complete",
                decision="done",
                duration_ms=-4,
                policy_version=4,
                session_id="session-explicit",
            )

            event = build_runtime_event(request)
            self.assertEqual(event["duration_ms"], 0)
            self.assertEqual(event["session_id"], "session-explicit")

            rel_path = append_runtime_event(
                vault,
                AppendRuntimeEventRequest(event=request, log_rel_path="custom/runtime.jsonl"),
            )

            self.assertEqual(rel_path, "custom/runtime.jsonl")
            written = json.loads((vault / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(written["component"], "Auto Improve Session")


if __name__ == "__main__":
    unittest.main()
