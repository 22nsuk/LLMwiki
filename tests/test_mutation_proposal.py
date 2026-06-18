"""Backward-compatible import surface for mutation proposal tests."""

from tests.test_mutation_proposal_build_report import (
    MutationProposalBuildReportTest as MutationProposalTest,
)
from tests.test_mutation_proposal_promotion import MutationProposalPromotionTest

__all__ = ["MutationProposalPromotionTest", "MutationProposalTest"]
