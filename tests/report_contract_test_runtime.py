from __future__ import annotations

import copy
from functools import cache
from pathlib import Path
from typing import Any, cast

type ReportPayload = dict[str, Any]
type ReportPayloadMap = dict[str, ReportPayload]
type ReportSchemaMap = dict[str, ReportPayload]

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCHEMA_SAMPLE_SEEDS_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "report_schema_sample_seeds.json"
)


def _coerce_report_payload_map(payload: object, source: object) -> ReportPayloadMap:
    if not isinstance(payload, dict):
        raise TypeError(f"expected report fixture object: {source}")

    reports: ReportPayloadMap = {}
    for name, report in payload.items():
        if not isinstance(name, str) or not isinstance(report, dict):
            raise TypeError(f"expected named report object entries: {source}")
        reports[name] = cast(ReportPayload, report)
    return reports


@cache
def _cached_generated_report_payload_map() -> ReportPayloadMap:
    from tools.regenerate_report_schema_samples import candidate_report_schema_samples

    return _coerce_report_payload_map(
        candidate_report_schema_samples(
            seed_fixture_path=REPORT_SCHEMA_SAMPLE_SEEDS_PATH,
        ),
        "generated report schema sample candidate",
    )


def load_generated_report_payload_map() -> ReportPayloadMap:
    return cast(ReportPayloadMap, copy.deepcopy(_cached_generated_report_payload_map()))
