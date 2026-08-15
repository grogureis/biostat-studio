"""Read-only Excel intake and deterministic data profiling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from numbers import Number
from pathlib import Path
import re
from typing import Any

import numpy as np
import pandas as pd


MAX_CATEGORICAL_LEVELS = 20
IDENTIFIER_UNIQUENESS_RATIO = 0.80
FREE_TEXT_AVERAGE_LENGTH = 20
IDENTIFIER_NAME = re.compile(
    r"(?:^|[_\s-])(id|identifier|patient|participant|subject|record|mrn)(?:$|[_\s-])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VariableMetadata:
    """Inferred metadata while retaining the workbook's original label."""

    source_label: Any
    original_name: str
    display_name: str
    kind: str
    non_missing: int
    missing: int
    unique_values: int


@dataclass(frozen=True)
class DataWarning:
    """A machine-readable profile warning that never includes cell values."""

    code: str
    column: str | None
    message: str


@dataclass(frozen=True)
class DataProfile:
    """A source fingerprint and deterministic structural description of one sheet."""

    source_sha256: str
    sheets: tuple[str, ...]
    selected_sheet: str
    rows: int
    columns: int
    missing_cells: int
    variables: dict[str, VariableMetadata]
    warnings: tuple[DataWarning, ...]


def sha256_file(path: Path) -> str:
    """Fingerprint a file without retaining its contents in memory."""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_label(name: object) -> str:
    """Format a label for display only; lookup keys remain the original label."""
    label = str(name).strip()
    if not label:
        return "Unnamed column"
    return re.sub(r"\s+", " ", label.replace("_", " ").replace("-", " ")).capitalize()


def json_safe_label(label: object) -> str:
    """Represent a source header deterministically for API and mapping use."""
    if isinstance(label, np.generic):
        label = label.item()
    if isinstance(label, (pd.Timestamp, datetime, date)):
        return label.isoformat()
    return str(label)


def variable_key(label: object) -> str:
    """Keep string labels backward compatible and type-tag non-string labels."""
    if isinstance(label, str):
        return label
    if isinstance(label, np.generic):
        label = label.item()
    return f"{type(label).__name__}:{json_safe_label(label)}"


def _value_family(value: Any) -> str:
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return "date"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, Number):
        return "number"
    return "text"


def _is_identifier_name(name: str) -> bool:
    return bool(IDENTIFIER_NAME.search(name))


def infer_variable(series: pd.Series) -> VariableMetadata:
    """Infer one stable display type using only column-level properties."""
    source_label = series.name
    name = json_safe_label(source_label)
    values = series.dropna()
    non_missing = int(values.shape[0])
    missing = int(series.isna().sum())
    unique_values = int(values.nunique(dropna=True))

    if non_missing == 0:
        kind = "empty"
    elif pd.api.types.is_datetime64_any_dtype(series):
        kind = "date"
    else:
        numeric = pd.to_numeric(values, errors="coerce")
        numeric_ratio = float(numeric.notna().mean())
        uniqueness_ratio = unique_values / non_missing
        families = {_value_family(value) for value in values}
        all_strings = families == {"text"}
        average_text_length = (
            float(values.astype(str).str.len().mean()) if all_strings else 0.0
        )

        if unique_values <= 2:
            kind = "binary"
        elif _is_identifier_name(name) and uniqueness_ratio >= IDENTIFIER_UNIQUENESS_RATIO:
            kind = "identifier-candidate"
        elif numeric_ratio == 1.0:
            kind = "continuous"
        elif all_strings and average_text_length >= FREE_TEXT_AVERAGE_LENGTH:
            kind = "free-text"
        elif unique_values <= MAX_CATEGORICAL_LEVELS or uniqueness_ratio <= 0.20:
            kind = "categorical"
        else:
            kind = "free-text"

    return VariableMetadata(
        source_label=source_label,
        original_name=name,
        display_name=display_label(name),
        kind=kind,
        non_missing=non_missing,
        missing=missing,
        unique_values=unique_values,
    )


def quality_warnings(
    frame: pd.DataFrame, variables: dict[str, VariableMetadata]
) -> tuple[DataWarning, ...]:
    """Return deterministic quality warnings without exposing any source cell values."""
    warnings: list[DataWarning] = []
    for column in frame.columns:
        name = variable_key(column)
        series = frame[column]
        metadata = variables[name]
        values = series.dropna()

        if values.empty:
            warnings.append(
                DataWarning("empty_column", name, "Column contains no non-missing values.")
            )
        else:
            families = {_value_family(value) for value in values}
            if "number" in families and "text" in families:
                warnings.append(
                    DataWarning("mixed_types", name, "Column contains mixed value types.")
                )

            numeric = pd.to_numeric(values, errors="coerce")
            finite_numeric = numeric.dropna()
            if not finite_numeric.empty and not np.isfinite(finite_numeric.astype(float)).all():
                warnings.append(
                    DataWarning("non_finite_values", name, "Column contains non-finite numeric values.")
                )

        if _is_identifier_name(metadata.original_name):
            if not values.empty and values.duplicated().any():
                warnings.append(
                    DataWarning("duplicated_identifier", name, "Identifier-labelled column contains duplicates.")
                )
            warnings.append(
                DataWarning(
                    "suspicious_identifier_leakage",
                    name,
                    "Identifier-labelled column may require de-identification before analysis.",
                )
            )
    return tuple(warnings)


def profile_excel(path: Path, sheet: str | None = None) -> DataProfile:
    """Profile one workbook sheet without modifying its source bytes."""
    source = Path(path)
    before = sha256_file(source)
    with pd.ExcelFile(source, engine="openpyxl") as book:
        sheets = tuple(book.sheet_names)
        selected = sheet or sheets[0]
        if selected not in sheets:
            raise ValueError("unknown_sheet")
        frame = pd.read_excel(book, sheet_name=selected)

    variables = {
        variable_key(column): infer_variable(frame[column]) for column in frame.columns
    }
    after = sha256_file(source)
    if before != after:
        raise RuntimeError("source_file_changed")

    return DataProfile(
        source_sha256=before,
        sheets=sheets,
        selected_sheet=selected,
        rows=int(frame.shape[0]),
        columns=int(frame.shape[1]),
        missing_cells=int(frame.isna().sum().sum()),
        variables=variables,
        warnings=quality_warnings(frame, variables),
    )
