"""Internal helpers shared by the dashboard's pure metric services."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd


def require_columns(frame: pd.DataFrame, columns: Iterable[str], *, name: str) -> None:
    """Raise a useful error when a service input is missing required columns."""

    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def safe_divide(
    numerator: float | int | pd.Series,
    denominator: float | int | pd.Series,
) -> float | pd.Series:
    """Divide while representing missing or zero denominators as ``NaN``."""

    if isinstance(numerator, pd.Series) or isinstance(denominator, pd.Series):
        index = (
            numerator.index if isinstance(numerator, pd.Series) else denominator.index  # type: ignore[union-attr]
        )
        left = (
            pd.to_numeric(numerator, errors="coerce")
            if isinstance(numerator, pd.Series)
            else pd.Series(float(numerator), index=index)
        )
        right = (
            pd.to_numeric(denominator, errors="coerce")
            if isinstance(denominator, pd.Series)
            else pd.Series(float(denominator), index=index)
        )
        result = left.div(right)
        return result.mask(right.eq(0) | right.isna() | left.isna())

    if pd.isna(numerator) or pd.isna(denominator) or float(denominator) == 0:
        return float("nan")
    return float(numerator) / float(denominator)


def safe_percentage(
    numerator: float | int | pd.Series,
    denominator: float | int | pd.Series,
) -> float | pd.Series:
    """Return a percentage with ``NaN`` for a missing or zero denominator."""

    result = safe_divide(numerator, denominator)
    return result * 100.0


def normalize_token(value: Any) -> str:
    """Normalize a human-readable enum-like value for resilient comparison."""

    if pd.isna(value):
        return ""
    return "_".join(str(value).strip().lower().replace("-", " ").split())


def bool_value(value: Any) -> bool:
    """Coerce common serialized boolean representations to ``bool``."""

    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    token = normalize_token(value)
    if token in {"true", "yes", "y", "1"}:
        return True
    if token in {"false", "no", "n", "0", ""}:
        return False
    raise ValueError(f"Cannot interpret {value!r} as a boolean")


def numeric_series(frame: pd.DataFrame, column: str, *, name: str) -> pd.Series:
    """Convert a required column to numeric values without silently losing data."""

    require_columns(frame, [column], name=name)
    converted = pd.to_numeric(frame[column], errors="coerce")
    bad = frame[column].notna() & converted.isna()
    if bad.any():
        indexes = frame.index[bad].tolist()
        raise ValueError(f"{name}.{column} contains non-numeric values at rows {indexes}")
    return converted.astype(float)


def datetime_series(frame: pd.DataFrame, column: str, *, name: str) -> pd.Series:
    """Convert a required column to normalized timestamps and reject bad values."""

    require_columns(frame, [column], name=name)
    converted = pd.to_datetime(frame[column], errors="coerce")
    bad = frame[column].notna() & converted.isna()
    if bad.any():
        indexes = frame.index[bad].tolist()
        raise ValueError(f"{name}.{column} contains invalid dates at rows {indexes}")
    return converted.dt.normalize()
