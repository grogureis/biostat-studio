"""Reference and validation coverage for the deterministic power module."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from biostat_service.app import create_app
from biostat_service.power import PowerRequest, PowerValidationError, compute_power


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BIOSTAT_SESSION_TOKEN", "test-token")
    with TestClient(create_app()) as test_client:
        yield test_client


def request(**overrides) -> PowerRequest:
    values = {
        "analysis": "two_sample_t",
        "solve_for": "sample_size",
        "alpha": 0.05,
        "power": 0.80,
        "effect_size": 0.5,
    }
    values.update(overrides)
    return PowerRequest(**values)


def test_two_sample_t_sample_size_matches_reference() -> None:
    """The standard d=0.5, 80%-power benchmark must reproduce n=64 per group."""
    result = compute_power(request())

    assert result.analysis == "two_sample_t"
    assert result.solve_for == "sample_size"
    assert result.sample_size == pytest.approx(63.765611775409695)
    assert result.per_group_rounded == 64
    assert result.total_rounded == 128
    assert result.achieved_power == pytest.approx(0.8014595500498423)
    assert result.power is None
    assert set(result.library_versions) == {"python", "scipy", "statsmodels"}


def test_two_sample_t_power_matches_reference() -> None:
    result = compute_power(
        request(solve_for="power", power=None, sample_size=64)
    )

    assert result.power == pytest.approx(0.8014595500498423)
    assert result.sample_size is None
    assert result.per_group_rounded is None


def test_paired_t_sample_size_matches_reference() -> None:
    result = compute_power(request(analysis="paired_t"))

    assert result.sample_size == pytest.approx(33.36713142751997)
    assert result.per_group_rounded == 34
    assert result.total_rounded == 34
    assert result.achieved_power == pytest.approx(0.8077774970796587)


def test_one_way_anova_sample_size_matches_reference() -> None:
    result = compute_power(
        request(analysis="one_way_anova", effect_size=0.25, groups=3)
    )

    assert result.sample_size == pytest.approx(157.18939443740618)
    assert result.per_group_rounded == 53
    assert result.total_rounded == 159
    assert result.achieved_power == pytest.approx(0.8048884422767989)


def test_two_proportions_sample_size_matches_reference() -> None:
    result = compute_power(
        request(
            analysis="two_proportions",
            effect_size=None,
            proportion_one=0.6,
            proportion_two=0.4,
        )
    )

    assert result.inputs["standardized_effect_size"] == pytest.approx(
        0.40271584158066154
    )
    assert result.sample_size == pytest.approx(96.79193707310118)
    assert result.per_group_rounded == 97
    assert result.total_rounded == 194
    assert result.achieved_power == pytest.approx(0.800841470805849)


def test_correlation_sample_size_matches_reference() -> None:
    result = compute_power(request(analysis="correlation"))

    assert result.sample_size == pytest.approx(29.012300401053597)
    assert result.per_group_rounded == 30
    assert result.total_rounded == 30
    assert result.achieved_power == pytest.approx(0.8144231694861087)


def test_correlation_power_matches_reference() -> None:
    result = compute_power(
        request(analysis="correlation", solve_for="power", power=None, sample_size=29)
    )

    assert result.power == pytest.approx(0.799814482146544)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"alpha": 0.0}, "invalid_alpha"),
        ({"alpha": 1.0}, "invalid_alpha"),
        ({"power": 1.0}, "invalid_power"),
        ({"effect_size": 0.0}, "invalid_effect_size"),
        ({"effect_size": None}, "missing_effect_size"),
        ({"analysis": "correlation", "effect_size": 1.0}, "invalid_effect_size"),
        (
            {"solve_for": "power", "power": None, "sample_size": None},
            "missing_sample_size",
        ),
        ({"solve_for": "power", "power": None, "sample_size": 1}, "invalid_sample_size"),
        ({"solve_for": "sample_size", "power": None}, "missing_power_target"),
        ({"analysis": "one_way_anova", "groups": 1}, "invalid_group_count"),
        (
            {
                "analysis": "two_proportions",
                "effect_size": None,
                "proportion_one": 0.5,
                "proportion_two": 0.5,
            },
            "invalid_proportions",
        ),
        (
            {"analysis": "two_proportions", "effect_size": None},
            "missing_proportions",
        ),
    ],
)
def test_invalid_requests_fail_closed(overrides: dict, expected: str) -> None:
    with pytest.raises(PowerValidationError, match=expected):
        compute_power(request(**overrides))


def test_non_converged_solver_fails_closed_instead_of_reporting_a_start_value() -> None:
    """statsmodels returns its brentq start value on non-convergence; reporting it
    as a required sample size would silently misplan a study."""
    with pytest.raises(PowerValidationError, match="sample_size_solution_failed"):
        compute_power(request(effect_size=9.0))


def test_two_proportions_method_names_the_arcsine_convention() -> None:
    """The output must say which two-proportion convention was applied; the
    arcsine and pooled-z constructions diverge for rare outcomes."""
    result = compute_power(
        request(
            analysis="two_proportions",
            effect_size=None,
            proportion_one=0.05,
            proportion_two=0.20,
        )
    )

    assert result.method == "statsmodels_normal_solver_arcsine_transform:cohen_h"
    assert result.sample_size == pytest.approx(69.198, abs=0.01)


def test_power_endpoint_is_stateless_and_session_authenticated(client) -> None:
    """The calculator must not require a project and must reject missing tokens."""
    payload = {
        "analysis": "two_sample_t",
        "solve_for": "sample_size",
        "alpha": 0.05,
        "power": 0.80,
        "effect_size": 0.5,
    }
    unauthorized = client.post("/v1/power", json=payload)
    assert unauthorized.status_code == 401

    response = client.post(
        "/v1/power", headers={"Authorization": "Bearer test-token"}, json=payload
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"] == "two_sample_t"
    assert body["per_group_rounded"] == 64
    assert body["achieved_power"] == pytest.approx(0.8014595500498423)

    invalid = client.post(
        "/v1/power",
        headers={"Authorization": "Bearer test-token"},
        json={**payload, "alpha": 0.0},
    )
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "invalid_alpha"}
