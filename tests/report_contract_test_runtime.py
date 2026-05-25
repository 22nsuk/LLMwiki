from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

type ReportPayload = dict[str, Any]
type ReportPayloadMap = dict[str, ReportPayload]
type ReportSchemaMap = dict[str, ReportPayload]


def load_report_payload_map(path: Path) -> ReportPayloadMap:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected report fixture object: {path}")

    reports: ReportPayloadMap = {}
    for name, report in payload.items():
        if not isinstance(name, str) or not isinstance(report, dict):
            raise TypeError(f"expected named report object entries: {path}")
        reports[name] = cast(ReportPayload, report)
    return reports
