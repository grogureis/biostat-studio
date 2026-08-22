"""Application-owned study-planning rules shared across service boundaries."""

from __future__ import annotations

from dataclasses import dataclass


PLAN_VERSION = 1
SUPPORTED_STUDY_DESIGNS = frozenset(
    {"cross_sectional", "cohort", "case_control", "trial", "repeated"}
)
VERTICAL_SLICE_METHOD_IDS = frozenset(
    {
        "descriptive_summary",
        "welch_t_test",
        "mann_whitney_u",
        "paired_t_test",
        "wilcoxon_signed_rank",
        "welch_anova",
        "kruskal_wallis",
        "chi_square_or_fisher",
        "pearson_or_spearman",
        "spearman_rank",
        "linear_regression",
        "logistic_regression",
    }
)


class BlockingPlanError(ValueError):
    """A stable planning failure caused by incomplete or unsupported structure."""


@dataclass(frozen=True)
class PlanChoice:
    """A primary method and its pre-planned robustness alternative."""

    method: str
    robust_alternative: str | None = None

    def __post_init__(self) -> None:
        identifiers = (self.method, self.robust_alternative)
        if any(
            identifier is not None and identifier not in VERTICAL_SLICE_METHOD_IDS
            for identifier in identifiers
        ):
            raise ValueError("unknown_vertical_slice_method")
