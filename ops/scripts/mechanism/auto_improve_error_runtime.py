from __future__ import annotations


class AutoImproveError(Exception):
    exit_code = 8


class AutoImproveUsageError(AutoImproveError):
    exit_code = 2


class AutoImproveLearningReviewRequiredError(AutoImproveError):
    exit_code = 4
