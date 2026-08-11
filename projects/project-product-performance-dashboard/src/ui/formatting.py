"""Presentation-only formatting helpers."""

from __future__ import annotations

from datetime import date, datetime
from numbers import Number
from typing import Any

import pandas as pd

NA = "N/A"


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, (bool, type(pd.NA))) else False


def compact_number(value: Any, *, decimals: int = 1) -> str:
    if is_missing(value):
        return NA
    number = float(value)
    absolute = abs(number)
    for divisor, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if absolute >= divisor:
            return f"{number / divisor:.{decimals}f}{suffix}"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.{decimals}f}"


def currency(value: Any, code: str = "USD", *, compact: bool = True) -> str:
    if is_missing(value):
        return NA
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "ZAR": "R"}
    prefix = symbols.get(str(code).upper(), f"{str(code).upper()} ")
    number = float(value)
    sign = "-" if number < 0 else ""
    if compact:
        return f"{sign}{prefix}{compact_number(abs(number))}"
    return f"{sign}{prefix}{abs(number):,.0f}"


def percent(value: Any, *, decimals: int = 1, signed: bool = False) -> str:
    if is_missing(value) or not isinstance(value, Number):
        return NA
    sign = "+" if signed and float(value) > 0 else ""
    return f"{sign}{float(value):.{decimals}f}%"


def integer(value: Any) -> str:
    if is_missing(value):
        return NA
    return f"{int(round(float(value))):,}"


def days(value: Any, *, signed: bool = False) -> str:
    if is_missing(value):
        return NA
    number = int(round(float(value)))
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:,} d"


def month_count(value: Any) -> str:
    if is_missing(value):
        return NA
    number = int(round(float(value)))
    return f"{number} mo" if number == 1 else f"{number} mos"


def date_label(value: Any, *, include_day: bool = True) -> str:
    if is_missing(value):
        return NA
    parsed = pd.Timestamp(value)
    return parsed.strftime("%d %b %Y" if include_day else "%b %Y")


def as_date(value: date | datetime | pd.Timestamp | str) -> date:
    return pd.Timestamp(value).date()


def humanize(value: Any) -> str:
    if is_missing(value):
        return NA
    return str(value).replace("_", " ").strip().title()


def pick(record: Any, *keys: str, default: Any = None) -> Any:
    """Return the first present value from a Series, mapping, or object."""

    for key in keys:
        if isinstance(record, pd.Series) and key in record.index:
            return record[key]
        if isinstance(record, dict) and key in record:
            return record[key]
        if hasattr(record, key):
            return getattr(record, key)
    return default
