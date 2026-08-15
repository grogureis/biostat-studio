"""Behavioral coverage for deterministic, publication-ready figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
import pytest

from biostat_service.analyses import run_plan
from biostat_service.contracts import AnalysisPlan, PlanItem
from biostat_service.visuals import build_figures


FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "core-study.xlsx"


def _item(identifier: str, method: str, variables: list[str]) -> PlanItem:
    return PlanItem(
        id=identifier,
        estimand="Confirmed structured estimand.",
        method=method,
        rationale="Confirmed structured rationale.",
        required_variables=variables,
        assumptions=["Confirmed assumptions."],
        outputs=["effect_size:required", "confidence_interval:95_percent"],
    )


@pytest.fixture
def core_frame() -> pd.DataFrame:
    return pd.read_excel(FIXTURE_PATH, sheet_name="Analysis")


@pytest.fixture
def approved_plan() -> AnalysisPlan:
    return AnalysisPlan(
        version=1,
        items=[
            _item("descriptive_summary", "descriptive_summary", ["age_years", "treatment_group"]),
            _item("primary_outcome", "welch_t_test", ["age_years", "treatment_group"]),
        ],
    )


@pytest.fixture
def bundle(core_frame: pd.DataFrame, approved_plan: AnalysisPlan):
    return run_plan(core_frame, approved_plan)


def test_group_figure_has_png_svg_caption_alt_text_and_300_dpi(
    tmp_path: Path,
    core_frame: pd.DataFrame,
    approved_plan: AnalysisPlan,
    bundle,
) -> None:
    """Dropping an accessible publication artifact would leave reports incomplete."""
    figures = build_figures(core_frame, approved_plan, bundle, tmp_path, "en")

    primary = figures[0]
    assert primary.png_path.exists()
    assert primary.svg_path is not None and primary.svg_path.exists()
    assert primary.dpi == 300
    assert primary.caption.startswith("Figure 1.")
    assert "group" in primary.alt_text.lower()
    assert primary.width_inches == pytest.approx(6.5)
    assert primary.height_inches == pytest.approx(4.2)
    with Image.open(primary.png_path) as image:
        assert image.format == "PNG"
        assert round(image.info["dpi"][0]) == 300
        assert image.width >= 1800
        assert image.height >= 1100
    assert primary.svg_path.stat().st_size > 0


def test_group_figure_uses_confirmed_level_order_complete_cases_and_no_open_figures(
    tmp_path: Path,
    core_frame: pd.DataFrame,
    approved_plan: AnalysisPlan,
) -> None:
    """Reversing confirmed order or plotting excluded rows would misrepresent the result."""
    frame = core_frame.copy()
    frame["treatment_group"] = pd.Categorical(
        frame["treatment_group"],
        categories=["Treatment", "Control"],
        ordered=True,
    )
    result_bundle = run_plan(frame, approved_plan)

    artifact = build_figures(frame, approved_plan, result_bundle, tmp_path, "en")[0]

    svg = artifact.svg_path.read_text(encoding="utf-8")
    assert svg.index("Treatment") < svg.index("Control")
    assert "n = 11" in artifact.caption
    assert "n = 11" in artifact.alt_text
    assert plt.get_fignums() == []


def test_turkish_figure_localizes_caption_and_axis_text_without_changing_artifact_data(
    tmp_path: Path,
    core_frame: pd.DataFrame,
    approved_plan: AnalysisPlan,
    bundle,
) -> None:
    """Translation must affect explanatory text without changing plotted science."""
    artifact = build_figures(core_frame, approved_plan, bundle, tmp_path, "tr")[0]

    assert artifact.caption.startswith("Şekil 1.")
    assert "Grup karşılaştırma" in artifact.alt_text
    assert "Maruziyet grubu" in artifact.svg_path.read_text(encoding="utf-8")


def test_figure_output_rejects_a_symlinked_directory_before_writing(
    tmp_path: Path,
    core_frame: pd.DataFrame,
    approved_plan: AnalysisPlan,
    bundle,
) -> None:
    """Following an artifact-directory symlink could write results outside the project."""
    outside = tmp_path / "outside"
    outside.mkdir()
    linked_output = tmp_path / "figures"
    linked_output.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="unsafe_figure_output_dir"):
        build_figures(core_frame, approved_plan, bundle, linked_output, "en")

    assert not list(outside.iterdir())


def test_figure_rejects_a_frame_that_does_not_match_bundle_provenance(
    tmp_path: Path,
    core_frame: pd.DataFrame,
    approved_plan: AnalysisPlan,
    bundle,
) -> None:
    """Plotting a same-sized but changed frame would silently contradict the result."""
    changed = core_frame.copy()
    changed.loc[0, "age_years"] = changed.loc[0, "age_years"] + 1

    with pytest.raises(ValueError, match="figure_data_fingerprint_mismatch"):
        build_figures(changed, approved_plan, bundle, tmp_path, "en")


def test_paired_group_figure_uses_the_executor_complete_pairs(tmp_path: Path) -> None:
    """Plotting a row with an incomplete partner would contradict paired analysis."""
    frame = pd.DataFrame(
        {
            "pair_id": ["p1", "p1", "p2", "p2", "p3", "p3"],
            "condition": pd.Categorical(
                ["after", "before"] * 3,
                categories=["after", "before"],
                ordered=True,
            ),
            "score": [8.0, 5.0, 7.0, 6.0, float("nan"), 4.0],
        }
    )
    plan = AnalysisPlan(
        items=[_item("primary_outcome", "paired_t_test", ["score", "condition", "pair_id"])]
    )
    result_bundle = run_plan(frame, plan)

    artifact = build_figures(frame, plan, result_bundle, tmp_path, "en")[0]

    assert "n = 2" in artifact.caption
    assert "after" in artifact.alt_text
    assert "before" in artifact.alt_text
    assert "p1" not in artifact.alt_text
    assert "p2" not in artifact.svg_path.read_text(encoding="utf-8")
