"""Backward-compatible import surface for external report action matrix tests."""

import pytest

from tests.test_external_report_action_matrix_lifecycle import (
    ExternalReportActionMatrixLifecycleTests as ExternalReportActionMatrixTests,
)
from tests.test_external_report_action_matrix_status import (
    ExternalReportActionMatrixStatusTests,
)

pytestmark = pytest.mark.slow

__all__ = ["ExternalReportActionMatrixStatusTests", "ExternalReportActionMatrixTests"]
