"""Deterministic a-priori power and sample-size calculations.

The module is stateless and never touches project data: it turns planning
inputs (effect size, alpha, target power, allocation) into closed-form or
statsmodels-solved values.  Two-group designs assume equal allocation.
"""

from __future__ import annotations

import math
import platform
from typing import Literal, Optional

from pydantic import BaseModel, Field
import scipy
from scipy import stats
import statsmodels
from statsmodels.stats.power import (
    FTestAnovaPower,
    NormalIndPower,
    TTestIndPower,
    TTestPower,
)
from statsmodels.stats.proportion import proportion_effectsize


PowerAnalysis = Literal[
    "two_sample_t",
    "paired_t",
    "one_way_anova",
    "two_proportions",
    "correlation",
]

EFFECT_SIZE_NAMES: dict[str, str] = {
    "two_sample_t": "cohen_d",
    "paired_t": "cohen_dz",
    "one_way_anova": "cohen_f",
    "two_proportions": "cohen_h",
    "correlation": "pearson_r",
}
SAMPLE_SIZE_UNITS: dict[str, str] = {
    "two_sample_t": "per_group",
    "paired_t": "pairs",
    "one_way_anova": "total",
    "two_proportions": "per_group",
    "correlation": "pairs",
}


class PowerValidationError(ValueError):
    """A stable, value-free validation failure for power inputs."""


class PowerRequest(BaseModel):
    analysis: PowerAnalysis
    solve_for: Literal["power", "sample_size"]
    alpha: float = 0.05
    power: Optional[float] = None
    effect_size: Optional[float] = None
    proportion_one: Optional[float] = None
    proportion_two: Optional[float] = None
    sample_size: Optional[int] = None
    groups: int = Field(default=3, description="Group count for one-way ANOVA.")


class PowerResult(BaseModel):
    analysis: PowerAnalysis
    solve_for: Literal["power", "sample_size"]
    inputs: dict[str, float | int]
    sample_size_unit: str
    power: Optional[float] = None
    sample_size: Optional[float] = None
    per_group_rounded: Optional[int] = None
    total_rounded: Optional[int] = None
    achieved_power: Optional[float] = None
    method: str
    library_versions: dict[str, str]


def _validate_common(request: PowerRequest) -> None:
    if not 0.0 < request.alpha < 1.0:
        raise PowerValidationError("invalid_alpha")
    if request.solve_for == "sample_size":
        if request.power is None:
            raise PowerValidationError("missing_power_target")
        if not 0.0 < request.power < 1.0:
            raise PowerValidationError("invalid_power")
    else:
        if request.sample_size is None:
            raise PowerValidationError("missing_sample_size")
    if request.power is not None and not 0.0 < request.power < 1.0:
        raise PowerValidationError("invalid_power")


def _standardized_effect(request: PowerRequest) -> float:
    if request.analysis == "two_proportions":
        if request.proportion_one is None or request.proportion_two is None:
            raise PowerValidationError("missing_proportions")
        for proportion in (request.proportion_one, request.proportion_two):
            if not 0.0 < proportion < 1.0:
                raise PowerValidationError("invalid_proportions")
        if request.proportion_one == request.proportion_two:
            raise PowerValidationError("invalid_proportions")
        effect = float(
            proportion_effectsize(request.proportion_one, request.proportion_two)
        )
        if not math.isfinite(effect) or effect == 0.0:
            raise PowerValidationError("invalid_proportions")
        return effect
    if request.effect_size is None:
        raise PowerValidationError("missing_effect_size")
    effect = float(request.effect_size)
    if not math.isfinite(effect) or effect == 0.0:
        raise PowerValidationError("invalid_effect_size")
    if request.analysis == "correlation" and not abs(effect) < 1.0:
        raise PowerValidationError("invalid_effect_size")
    if request.analysis != "correlation" and effect < 0.0:
        raise PowerValidationError("invalid_effect_size")
    return effect


def _minimum_sample_size(analysis: str) -> int:
    return 4 if analysis == "correlation" else 2


def _correlation_power(effect: float, n: float, alpha: float) -> float:
    critical = float(stats.norm.ppf(1 - alpha / 2))
    return float(
        stats.norm.cdf(math.sqrt(n - 3) * abs(math.atanh(effect)) - critical)
    )


def _solver_power(
    analysis: str, effect: float, n: float, alpha: float, groups: int
) -> float:
    if analysis == "two_sample_t":
        return float(
            TTestIndPower().power(
                effect_size=effect, nobs1=n, alpha=alpha, ratio=1.0,
                alternative="two-sided",
            )
        )
    if analysis == "paired_t":
        return float(
            TTestPower().power(
                effect_size=effect, nobs=n, alpha=alpha, alternative="two-sided"
            )
        )
    if analysis == "one_way_anova":
        return float(
            FTestAnovaPower().power(
                effect_size=effect, nobs=n, alpha=alpha, k_groups=groups
            )
        )
    if analysis == "two_proportions":
        return float(
            NormalIndPower().power(
                effect_size=effect, nobs1=n, alpha=alpha, ratio=1.0,
                alternative="two-sided",
            )
        )
    return _correlation_power(effect, n, alpha)


def _solve_sample_size(
    analysis: str, effect: float, power: float, alpha: float, groups: int
) -> float:
    if analysis == "two_sample_t":
        return float(
            TTestIndPower().solve_power(
                effect_size=effect, alpha=alpha, power=power, ratio=1.0,
                alternative="two-sided",
            )
        )
    if analysis == "paired_t":
        return float(
            TTestPower().solve_power(
                effect_size=effect, alpha=alpha, power=power,
                alternative="two-sided",
            )
        )
    if analysis == "one_way_anova":
        return float(
            FTestAnovaPower().solve_power(
                effect_size=effect, alpha=alpha, power=power, k_groups=groups
            )
        )
    if analysis == "two_proportions":
        return float(
            NormalIndPower().solve_power(
                effect_size=effect, alpha=alpha, power=power, ratio=1.0,
                alternative="two-sided",
            )
        )
    critical = float(stats.norm.ppf(1 - alpha / 2))
    beta_quantile = float(stats.norm.ppf(power))
    return ((critical + beta_quantile) / abs(math.atanh(effect))) ** 2 + 3


def _rounded_allocation(analysis: str, raw: float, groups: int) -> tuple[int, int]:
    """Return (per-group or per-unit, total) integer allocations for one raw solution."""
    if analysis == "one_way_anova":
        per_group = math.ceil(raw / groups - 1e-12)
        return per_group, per_group * groups
    per_unit = math.ceil(raw - 1e-12)
    total = per_unit * (2 if analysis in {"two_sample_t", "two_proportions"} else 1)
    return per_unit, total


def _library_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "scipy": scipy.__version__,
        "statsmodels": statsmodels.__version__,
    }


def compute_power(request: PowerRequest) -> PowerResult:
    """Compute power or sample size deterministically from validated inputs."""
    _validate_common(request)
    effect = _standardized_effect(request)
    groups = int(request.groups)
    if request.analysis == "one_way_anova" and groups < 2:
        raise PowerValidationError("invalid_group_count")

    inputs: dict[str, float | int] = {
        "alpha": request.alpha,
        "standardized_effect_size": effect,
    }
    if request.analysis == "two_proportions":
        inputs["proportion_one"] = float(request.proportion_one)
        inputs["proportion_two"] = float(request.proportion_two)
    if request.analysis == "one_way_anova":
        inputs["groups"] = groups
    method = (
        "closed_form_fisher_z"
        if request.analysis == "correlation"
        else "statsmodels_power_solver"
    )
    effect_name = EFFECT_SIZE_NAMES[request.analysis]
    unit = SAMPLE_SIZE_UNITS[request.analysis]

    if request.solve_for == "power":
        n = int(request.sample_size)
        minimum = _minimum_sample_size(request.analysis)
        if request.analysis == "one_way_anova":
            minimum = max(minimum, groups * 2)
        if n < minimum:
            raise PowerValidationError("invalid_sample_size")
        inputs["sample_size"] = n
        achieved = _solver_power(request.analysis, effect, float(n), request.alpha, groups)
        if not math.isfinite(achieved) or not 0.0 <= achieved <= 1.0:
            raise PowerValidationError("power_solution_failed")
        return PowerResult(
            analysis=request.analysis,
            solve_for="power",
            inputs=inputs,
            sample_size_unit=unit,
            power=achieved,
            method=f"{method}:{effect_name}",
            library_versions=_library_versions(),
        )

    inputs["target_power"] = float(request.power)
    raw = _solve_sample_size(
        request.analysis, effect, float(request.power), request.alpha, groups
    )
    if not math.isfinite(raw) or raw <= 0.0:
        raise PowerValidationError("sample_size_solution_failed")
    per_group, total = _rounded_allocation(request.analysis, raw, groups)
    rounded_n = float(total if request.analysis == "one_way_anova" else per_group)
    achieved = _solver_power(request.analysis, effect, rounded_n, request.alpha, groups)
    if not math.isfinite(achieved) or not 0.0 <= achieved <= 1.0:
        raise PowerValidationError("sample_size_solution_failed")
    return PowerResult(
        analysis=request.analysis,
        solve_for="sample_size",
        inputs=inputs,
        sample_size_unit=unit,
        sample_size=raw,
        per_group_rounded=per_group,
        total_rounded=total,
        achieved_power=achieved,
        method=f"{method}:{effect_name}",
        library_versions=_library_versions(),
    )


__all__ = [
    "PowerRequest",
    "PowerResult",
    "PowerValidationError",
    "compute_power",
]
