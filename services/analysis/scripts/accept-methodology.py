#!/usr/bin/env python3
"""Run a value-free methodology/Excel acceptance check on local files."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from biostat_service.data_intake import profile_excel
from biostat_service.extractors.contracts import BriefProposal, Proposal, column_summaries
from biostat_service.extractors.engine import EngineStatus, MethodologyEngine
from biostat_service.extractors.local import LocalExtractor
from biostat_service.extractors.rule import RuleExtractor
from biostat_service.methodology_intake import extract_document


DEFAULT_MODEL = "qwen2.5:14b"
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _default_engine() -> MethodologyEngine:
    model = os.environ.get("BIOSTAT_LOCAL_LLM_MODEL", DEFAULT_MODEL)
    if not MODEL_NAME.fullmatch(model):
        model = DEFAULT_MODEL
    return MethodologyEngine(LocalExtractor(model=model), RuleExtractor())


def _status(status: EngineStatus) -> dict[str, str | None]:
    return {
        "requested": status.requested,
        "used": status.used,
        "fallback_reason": status.fallback_reason,
    }


def _value(proposal: Proposal | None) -> str | None:
    return proposal.value if proposal is not None else None


def _values(proposals: tuple[Proposal, ...]) -> list[str]:
    return [proposal.value for proposal in proposals]


def _brief(brief: BriefProposal) -> dict[str, Any]:
    return {
        "title": _value(brief.title),
        "question": _value(brief.question),
        "hypothesis": _value(brief.hypothesis),
        "design": _value(brief.design),
        "outcomes": _values(brief.outcome_concepts),
        "exposures": _values(brief.exposure_concepts),
        "covariates": _values(brief.covariate_concepts),
        "warnings": list(brief.warnings),
    }


def acceptance_summary(
    document_path: Path,
    workbook_path: Path,
    *,
    engine: MethodologyEngine | Any | None = None,
) -> dict[str, Any]:
    """Return only filenames, structure, proposal values, and engine provenance."""
    selected_engine = engine or _default_engine()
    document = extract_document(document_path)
    profile = profile_excel(workbook_path)
    extraction = selected_engine.extract(document)
    variables = selected_engine.variables(document, column_summaries(profile))
    roles: list[dict[str, Any]] = []
    for item in variables.proposals:
        proposal = item.role or item.kind
        roles.append(
            {
                "column": item.column,
                "role": _value(item.role),
                "kind_correction": _value(item.kind),
                "confidence": proposal.confidence if proposal is not None else None,
                "source": proposal.source if proposal is not None else None,
            }
        )
    return {
        "document": {
            "name": document_path.name,
            "format": document.source_format,
            "characters": document.char_count,
        },
        "workbook": {
            "name": workbook_path.name,
            "sheet": profile.selected_sheet,
            "rows": profile.rows,
            "columns": profile.columns,
        },
        "engine": {
            "brief": _status(extraction.status),
            "variables": _status(variables.status),
        },
        "brief": _brief(extraction.brief),
        "roles": roles,
        "analysis_boundary": {
            "method_selection_performed": False,
            "unsupported_in_current_release": [
                "firth_logistic_regression",
                "little_mcar_test",
                "multiple_imputation",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a local, value-free methodology acceptance check."
    )
    parser.add_argument("methodology", type=Path)
    parser.add_argument("workbook", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            acceptance_summary(args.methodology, args.workbook),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
