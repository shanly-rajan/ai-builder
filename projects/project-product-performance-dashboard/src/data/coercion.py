"""Shared conversion of tabular inputs to canonical Pandas dtypes."""

from __future__ import annotations

import pandas as pd
from pandas.api import types as pandas_types

from src.data.contracts import TABLE_SPECS, ColumnSpec


class DataCoercionError(ValueError):
    """Raised when source values cannot be represented by a table schema."""


def coerce_table_frame(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of a table converted to its canonical column types.

    Args:
        table_name: Name present in :data:`src.data.contracts.TABLE_SPECS`.
        frame: Source DataFrame to convert.

    Returns:
        DataFrame with canonical column order and dtypes.

    Raises:
        DataCoercionError: If columns are missing or a value cannot be converted.
    """
    if table_name not in TABLE_SPECS:
        raise DataCoercionError(f"Unknown canonical table: {table_name}")

    spec = TABLE_SPECS[table_name]
    missing = [column for column in spec.columns if column not in frame.columns]
    extra = [column for column in frame.columns if column not in spec.columns]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing columns {missing}")
        if extra:
            details.append(f"unexpected columns {extra}")
        raise DataCoercionError(f"{table_name}: " + "; ".join(details))

    result = frame.loc[:, list(spec.columns)].copy()
    for column, column_spec in spec.columns.items():
        try:
            result[column] = _coerce_series(result[column], column_spec)
        except (TypeError, ValueError) as error:
            raise DataCoercionError(
                f"{table_name}.{column} could not be converted to {column_spec.kind}: {error}"
            ) from error
    return result


def _coerce_series(series: pd.Series, spec: ColumnSpec) -> pd.Series:
    """Convert one series according to a logical column specification."""
    if spec.kind == "string":
        return series.astype("string")
    if spec.kind == "date":
        return _coerce_dates(series)
    if spec.kind == "boolean":
        return _coerce_booleans(series, nullable=spec.nullable)
    if spec.kind == "float":
        return pd.to_numeric(series, errors="raise").astype("float64")
    if spec.kind == "integer":
        numeric = pd.to_numeric(series, errors="raise")
        non_null = numeric.dropna()
        if not ((non_null % 1) == 0).all():
            raise ValueError("contains non-integral numeric values")
        return numeric.astype("Int64" if spec.nullable else "int64")
    raise ValueError(f"unsupported logical kind {spec.kind!r}")


def _coerce_dates(series: pd.Series) -> pd.Series:
    """Parse date-like values while preserving legitimate missing values."""
    if pandas_types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series).dt.normalize()

    missing_input = series.isna() | series.astype("string").str.strip().eq("")
    converted = pd.to_datetime(series.mask(missing_input), errors="coerce")
    invalid = ~missing_input & converted.isna()
    if invalid.any():
        values = series.loc[invalid].astype(str).unique().tolist()[:3]
        raise ValueError(f"contains invalid dates {values}")
    return converted.dt.normalize()


def _coerce_booleans(series: pd.Series, *, nullable: bool) -> pd.Series:
    """Parse strict boolean values without relying on Python truthiness."""
    if pandas_types.is_bool_dtype(series):
        return series.astype("boolean" if nullable else "bool")

    true_values = {"true", "1", "yes", "y"}
    false_values = {"false", "0", "no", "n"}

    def parse(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        normalized = str(value).strip().lower()
        if normalized in true_values:
            return True
        if normalized in false_values:
            return False
        raise ValueError(f"invalid boolean value {value!r}")

    parsed = series.map(parse)
    if not nullable and parsed.isna().any():
        raise ValueError("contains missing boolean values")
    return parsed.astype("boolean" if nullable else "bool")
