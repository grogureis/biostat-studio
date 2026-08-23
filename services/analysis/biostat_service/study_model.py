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


# Group-comparison methods that produce the shared distribution figure, and the
# subset whose data are linked pairs.  visuals.py and reporting.py both consume
# these so figure generation and report expectations cannot drift apart.
GROUP_FIGURE_METHOD_IDS = frozenset(
    {
        "welch_t_test",
        "paired_t_test",
        "welch_anova",
        "mann_whitney_u",
        "wilcoxon_signed_rank",
        "kruskal_wallis",
    }
)
PAIRED_METHOD_IDS = frozenset({"paired_t_test", "wilcoxon_signed_rank"})


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
