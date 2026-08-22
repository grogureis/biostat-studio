"""Bilingual parity coverage for deterministic Word results reports."""

from __future__ import annotations

from pathlib import Path
import re

from docx import Document
from docx.oxml.ns import qn
import pandas as pd

from biostat_service.analyses import run_plan
from biostat_service.contracts import AnalysisPlan, PlanItem, StudyBrief
from biostat_service.projects import LocalProject
from biostat_service.reporting import build_results_docx
from biostat_service.visuals import build_figures


FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "core-study.xlsx"
NUMBER = re.compile(r"(?<![\w.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)")


def _document_text(path: Path) -> str:
    document = Document(path)
    return "\n".join(node.text or "" for node in document.element.iter(qn("w:t")))


def extract_numeric_tokens(path: Path) -> list[str]:
    """Return visible numeric tokens in document order, including cells and captions."""
    return NUMBER.findall(_document_text(path))


def _build_reports(tmp_path: Path) -> tuple[Path, Path]:
    frame = pd.read_excel(FIXTURE_PATH, sheet_name="Analysis")
    descriptive = PlanItem(
        id="descriptive_summary",
        estimand="Confirmed structured descriptive estimand.",
        method="descriptive_summary",
        rationale="Confirmed structured descriptive rationale.",
        required_variables=["age_years", "treatment_group"],
        assumptions=["Confirmed assumptions."],
        outputs=["table:descriptive_summary"],
    )
    item = PlanItem(
        id="primary_outcome",
        estimand="Confirmed structured estimand.",
        method="welch_t_test",
        rationale="Confirmed structured rationale.",
        required_variables=["age_years", "treatment_group"],
        assumptions=["Confirmed assumptions."],
        outputs=["effect_size:required", "confidence_interval:95_percent"],
    )
    plan = AnalysisPlan(
        version=3,
        items=[descriptive, item],
        warnings=["review_assumptions"],
    )
    brief = StudyBrief(
        title="Cardiovascular outcomes",
        question="Is treatment associated with age at the measured endpoint?",
        hypothesis="The exposure groups differ at the measured endpoint.",
        design="cohort",
        outcome_variables=["age_years"],
        exposure_variables=["treatment_group"],
    )
    bundle = run_plan(frame, plan)
    project = LocalProject(tmp_path / "cardio.biostat")
    english_figures = build_figures(frame, plan, bundle, tmp_path / "figures-en", "en")
    turkish_figures = build_figures(frame, plan, bundle, tmp_path / "figures-tr", "tr")
    english = build_results_docx(
        project, brief, plan, bundle, english_figures, "en", tmp_path / "results-en.docx"
    )
    turkish = build_results_docx(
        project, brief, plan, bundle, turkish_figures, "tr", tmp_path / "results-tr.docx"
    )
    return english, turkish


def test_turkish_and_english_reports_share_numerical_tokens(tmp_path: Path) -> None:
    """Translation must never change or reorder a scientific number."""
    report_en, report_tr = _build_reports(tmp_path)

    assert extract_numeric_tokens(report_en) == extract_numeric_tokens(report_tr)
    assert {"11", "1", "-4.167", "-8.714", "0.381", "0.068", "-1.138"} <= set(
        extract_numeric_tokens(report_en)
    )


def test_reports_localize_manuscript_language_without_causal_observational_claims(
    tmp_path: Path,
) -> None:
    """A translated observational report must remain localized and non-causal."""
    report_en, report_tr = _build_reports(tmp_path)
    english = _document_text(report_en)
    turkish = _document_text(report_tr)

    assert english.startswith("Results")
    assert "Table 1" in english
    assert "Figure 1" in english
    assert "Reproducibility" in english
    assert "does not establish causality" in english
    assert turkish.startswith("Bulgular")
    assert "Tablo 1" in turkish
    assert "Şekil 1" in turkish
    assert "Yeniden üretilebilirlik" in turkish
    assert "nedensellik göstermez" in turkish
    assert "eksik = 1" in turkish
    assert "missing = 1" not in turkish
    assert not re.search(r"(?i)\bcaused\b|\bled to\b", english)
    assert not re.search(r"(?i)neden oldu|yol açtı", turkish)
