"""Deterministic, accessible publication figures for completed analyses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal

import matplotlib

# The service never opens an interactive window.  This must precede pyplot.
matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from biostat_service.analyses import (
    AnalysisBundle,
    _complete_case,
    _data_fingerprint,
    _levels,
    _sort_key,
)
from biostat_service.contracts import AnalysisPlan, AnalysisResult, PlanItem


DPI = 300
JOURNAL_COLUMN_WIDTH_INCHES = 6.5
JOURNAL_COLUMN_HEIGHT_INCHES = 4.2
WARM_WHITE = "#fffdf8"
DEEP_GREEN = "#145a4a"
TERRACOTTA = "#c96f4a"
SLATE = "#2f3b3d"
MIST_GREEN = "#cfe3da"
GROUP_METHODS = frozenset({"welch_t_test", "paired_t_test", "welch_anova"})
_SAFE_STEM = re.compile(r"[^a-z0-9_-]+")
SVG_CREATOR = "BioStat Studio"
SVG_HASH_SALT = "biostat-studio-figure-v1"


@dataclass(frozen=True)
class FigureArtifact:
    """A locally written figure plus the metadata required for accessible reports."""

    id: str
    png_path: Path
    svg_path: Path | None
    caption: str
    alt_text: str
    dpi: int
    width_inches: float
    height_inches: float


_TEXT = {
    "en": {
        "figure": "Figure",
        "group_axis": "Exposure group",
        "observed_value": "observed value",
        "caption": (
            "Distribution of {outcome} by {exposure}; points show individual "
            "complete-case observations (n = {n})."
        ),
        "alt": (
            "Group comparison figure showing individual complete-case observations "
            "and distributions of {outcome} across {groups} (n = {n})."
        ),
        "paired_caption": (
            "Distribution of {outcome} by {exposure}; points show individual "
            "complete-pair observations (n = {pairs} pairs ({observations} observations))."
        ),
        "paired_alt": (
            "Paired group comparison figure showing individual complete-pair observations "
            "and distributions of {outcome} across {groups} "
            "(n = {pairs} pairs ({observations} observations))."
        ),
    },
    "tr": {
        "figure": "Şekil",
        "group_axis": "Maruziyet grubu",
        "observed_value": "gözlenen değer",
        "caption": (
            "{outcome} değişkeninin {exposure} gruplarına göre dağılımı; noktalar "
            "tam olgu bireysel gözlemlerini gösterir (n = {n})."
        ),
        "alt": (
            "Grup karşılaştırma grafiği, {outcome} değişkeninin {groups} gruplarındaki "
            "tam olgu bireysel gözlemlerini ve dağılımlarını gösterir (n = {n})."
        ),
        "paired_caption": (
            "{outcome} değişkeninin {exposure} gruplarına göre dağılımı; noktalar "
            "tam çift bireysel gözlemlerini gösterir "
            "(n = {pairs} çift ({observations} gözlem))."
        ),
        "paired_alt": (
            "Eşleştirilmiş grup karşılaştırma grafiği, {outcome} değişkeninin {groups} "
            "gruplarındaki tam çift bireysel gözlemlerini ve dağılımlarını gösterir "
            "(n = {pairs} çift ({observations} gözlem))."
        ),
    },
}


def _display_label(name: str) -> str:
    """Produce a readable variable label without changing source lookup keys."""
    return re.sub(r"\s+", " ", name.replace("_", " ").replace("-", " ")).strip()


def _safe_stem(identifier: str, figure_number: int) -> str:
    stem = _SAFE_STEM.sub("-", identifier.lower()).strip("-_")
    return f"figure-{figure_number}-{stem or 'analysis'}"


def _reject_symlinked_path(path: Path) -> None:
    """Reject every existing symlink component without resolving through it."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError("unsafe_figure_output_dir")


def _prepare_output_dir(output_dir: Path) -> Path:
    """Create a local output root while preventing symlink-based directory escape."""
    raw = Path(output_dir)
    _reject_symlinked_path(raw)
    if raw.exists() and not raw.is_dir():
        raise ValueError("unsafe_figure_output_dir")
    raw.mkdir(parents=True, exist_ok=True)
    _reject_symlinked_path(raw)
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError("unsafe_figure_output_dir")
    return raw.resolve()


def _safe_destination(root: Path, destination: Path) -> Path:
    """Return a destination contained by the validated root and not a symlink."""
    if destination.is_symlink():
        raise ValueError("unsafe_figure_output_dir")
    try:
        destination.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise ValueError("unsafe_figure_output_dir") from exc
    return destination


def save_figure(fig: Figure, stem: Path, *, output_root: Path) -> tuple[Path, Path]:
    """Write PNG and SVG artifacts, closing the figure even if a write fails."""
    png = _safe_destination(output_root, stem.with_suffix(".png"))
    svg = _safe_destination(output_root, stem.with_suffix(".svg"))
    try:
        with matplotlib.rc_context({"svg.hashsalt": SVG_HASH_SALT}):
            fig.savefig(png, dpi=DPI, bbox_inches="tight", facecolor=WARM_WHITE)
            fig.savefig(
                svg,
                bbox_inches="tight",
                facecolor=WARM_WHITE,
                metadata={"Date": None, "Creator": SVG_CREATOR},
            )
    finally:
        plt.close(fig)
    return png, svg


def _group_data(
    frame: pd.DataFrame, item: PlanItem, result: AnalysisResult
) -> tuple[str, str, pd.DataFrame, list[object], str | None]:
    """Reuse executor complete-case and confirmed-level semantics for one group figure."""
    if item.method == "paired_t_test":
        if len(item.required_variables) != 3:
            raise ValueError("invalid_group_figure_variables")
        outcome, exposure, pair_id = item.required_variables
        complete, counts, _exclusions = _complete_case(
            frame, [outcome, exposure, pair_id], numeric=[outcome]
        )
        pair_sizes = complete.groupby(pair_id, observed=True, sort=False).size()
        pair_conditions = complete.groupby(pair_id, observed=True, sort=False)[exposure].nunique()
        complete_pair_ids = pair_sizes.index[(pair_sizes == 2) & (pair_conditions == 2)]
        complete = complete.loc[complete[pair_id].isin(complete_pair_ids)].copy()
        used = int(len(complete))
        if (
            used != result.diagnostics.get("counts", {}).get("used")
            or result.n != used // 2
            or counts["input"] - used != result.diagnostics.get("counts", {}).get("missing")
        ):
            raise ValueError("figure_result_complete_case_mismatch")
        levels, _strategy = _levels(frame[exposure], expected=2)
        return outcome, exposure, complete, levels, pair_id
    if len(item.required_variables) < 2:
        raise ValueError("invalid_group_figure_variables")
    outcome, exposure = item.required_variables[:2]
    complete, _counts, _exclusions = _complete_case(
        frame, [outcome, exposure], numeric=[outcome]
    )
    if len(complete) != result.n:
        raise ValueError("figure_result_complete_case_mismatch")
    levels, _strategy = _levels(complete[exposure])
    if len(levels) < 2:
        raise ValueError("invalid_group_figure_levels")
    return outcome, exposure, complete, levels, None


def _draw_group_distribution(
    outcome: str,
    exposure: str,
    complete: pd.DataFrame,
    levels: list[object],
    language: Literal["en", "tr"],
    pair_id: str | None = None,
) -> Figure:
    """Draw a violin, box, and deterministic individual-point group comparison."""
    labels = _TEXT[language]
    groups = [
        complete.loc[complete[exposure] == level, outcome].to_numpy(dtype=float)
        for level in levels
    ]
    colors = [DEEP_GREEN, TERRACOTTA]
    fig: Figure | None = None
    with matplotlib.rc_context(
        {
            "axes.edgecolor": SLATE,
            "axes.labelcolor": SLATE,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "svg.fonttype": "none",
            "xtick.color": SLATE,
            "ytick.color": SLATE,
        }
    ):
        try:
            fig, axis = plt.subplots(
                figsize=(JOURNAL_COLUMN_WIDTH_INCHES, JOURNAL_COLUMN_HEIGHT_INCHES),
                constrained_layout=True,
                facecolor=WARM_WHITE,
            )
            axis.set_facecolor(WARM_WHITE)
            positions = np.arange(1, len(groups) + 1, dtype=float)
            violin = axis.violinplot(
                groups,
                positions=positions,
                widths=0.72,
                showmeans=False,
                showmedians=False,
                showextrema=False,
            )
            for index, body in enumerate(violin["bodies"]):
                body.set_facecolor(colors[index % len(colors)])
                body.set_edgecolor(colors[index % len(colors)])
                body.set_alpha(0.25)

            box = axis.boxplot(
                groups,
                positions=positions,
                widths=0.25,
                patch_artist=True,
                showfliers=False,
                medianprops={"color": WARM_WHITE, "linewidth": 1.5},
                whiskerprops={"color": SLATE, "linewidth": 0.9},
                capprops={"color": SLATE, "linewidth": 0.9},
            )
            for index, patch in enumerate(box["boxes"]):
                patch.set_facecolor(colors[index % len(colors)])
                patch.set_edgecolor(colors[index % len(colors)])
                patch.set_alpha(0.9)

            for index, values in enumerate(groups):
                offsets = np.linspace(-0.15, 0.15, num=len(values), endpoint=True)
                axis.scatter(
                    positions[index] + offsets,
                    values,
                    color=colors[index % len(colors)],
                    edgecolors=WARM_WHITE,
                    linewidths=0.55,
                    s=32,
                    alpha=0.95,
                    zorder=3,
                )

            if pair_id is not None:
                for pair in sorted(complete[pair_id].unique().tolist(), key=_sort_key):
                    paired_values = [
                        complete.loc[
                            (complete[pair_id] == pair) & (complete[exposure] == level), outcome
                        ].iloc[0]
                        for level in levels
                    ]
                    axis.plot(
                        positions,
                        paired_values,
                        color=SLATE,
                        linewidth=0.8,
                        alpha=0.5,
                        zorder=2,
                    )

            axis.set_xticks(positions, [str(level) for level in levels])
            axis.set_xlabel(labels["group_axis"])
            axis.set_ylabel(f"{_display_label(outcome)} ({labels['observed_value']})")
            axis.grid(axis="y", color=MIST_GREEN, linewidth=0.7, alpha=0.85)
            axis.set_axisbelow(True)
        except Exception:
            if fig is not None:
                plt.close(fig)
            raise
    return fig


def build_figures(
    frame: pd.DataFrame,
    plan: AnalysisPlan,
    bundle: AnalysisBundle,
    output_dir: Path,
    language: Literal["en", "tr"],
) -> list[FigureArtifact]:
    """Generate deterministic group-comparison figures from approved results only."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame_must_be_dataframe")
    if language not in _TEXT:
        raise ValueError("unsupported_figure_language")
    group_items = [item for item in plan.items if item.method in GROUP_METHODS]
    if group_items and bundle.provenance.plan_version != plan.version:
        raise ValueError("figure_result_plan_mismatch")
    if group_items and _data_fingerprint(frame) != bundle.provenance.data_fingerprint:
        raise ValueError("figure_data_fingerprint_mismatch")
    root = _prepare_output_dir(Path(output_dir))
    artifacts: list[FigureArtifact] = []
    for item in group_items:
        result = bundle.results.get(item.id)
        if result is None or result.method != item.method:
            raise ValueError("figure_result_plan_mismatch")
        if (
            result.provenance.plan_version != plan.version
            or result.provenance.data_fingerprint != bundle.provenance.data_fingerprint
        ):
            raise ValueError("figure_result_provenance_mismatch")
        outcome, exposure, complete, levels, pair_id = _group_data(frame, item, result)
        figure_number = len(artifacts) + 1
        labels = _TEXT[language]
        outcome_label = _display_label(outcome)
        exposure_label = _display_label(exposure)
        group_labels = ", ".join(str(level) for level in levels)
        caption_template = labels["paired_caption"] if pair_id is not None else labels["caption"]
        alt_template = labels["paired_alt"] if pair_id is not None else labels["alt"]
        caption = f"{labels['figure']} {figure_number}. " + caption_template.format(
            outcome=outcome_label,
            exposure=exposure_label,
            pairs=result.n,
            observations=len(complete),
            n=result.n,
        )
        alt_text = alt_template.format(
            outcome=outcome_label,
            groups=group_labels,
            pairs=result.n,
            observations=len(complete),
            n=result.n,
        )
        figure = _draw_group_distribution(
            outcome, exposure, complete, levels, language, pair_id=pair_id
        )
        png, svg = save_figure(
            figure,
            root / _safe_stem(item.id, figure_number),
            output_root=root,
        )
        artifacts.append(
            FigureArtifact(
                id=item.id,
                png_path=png,
                svg_path=svg,
                caption=caption,
                alt_text=alt_text,
                dpi=DPI,
                width_inches=JOURNAL_COLUMN_WIDTH_INCHES,
                height_inches=JOURNAL_COLUMN_HEIGHT_INCHES,
            )
        )
    return artifacts
