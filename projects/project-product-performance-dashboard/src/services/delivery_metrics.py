"""Schedule and duration calculations for project delivery performance."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

import numpy as np
import pandas as pd

from ._utils import datetime_series, normalize_token, require_columns, safe_percentage

DateLike = str | date | datetime | pd.Timestamp


def inclusive_duration_days(start: DateLike | None, end: DateLike | None) -> float:
    """Calculate an inclusive calendar-day duration.

    Args:
        start: First calendar date in the interval.
        end: Last calendar date in the interval.

    Returns:
        The number of calendar days, including both endpoints. Missing dates return
        ``NaN``.

    Raises:
        ValueError: If either date is invalid or the end precedes the start.
    """

    if start is None or end is None or pd.isna(start) or pd.isna(end):
        return float("nan")
    try:
        start_ts = pd.Timestamp(start).normalize()
        end_ts = pd.Timestamp(end).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("start and end must be valid dates") from exc
    if end_ts < start_ts:
        raise ValueError("end date cannot precede start date")
    return float((end_ts - start_ts).days + 1)


def schedule_variance_days(
    planned_completion: DateLike | None,
    actual_completion: DateLike | None,
) -> float:
    """Return actual minus planned completion in calendar days.

    Negative values are early, zero is on time, and positive values are late.
    Incomplete work returns ``NaN`` rather than a fabricated completion variance.

    Args:
        planned_completion: Committed completion date.
        actual_completion: Observed completion date, if complete.

    Returns:
        Signed schedule variance in calendar days, or ``NaN`` when unavailable.
    """

    if (
        planned_completion is None
        or actual_completion is None
        or pd.isna(planned_completion)
        or pd.isna(actual_completion)
    ):
        return float("nan")
    try:
        planned_ts = pd.Timestamp(planned_completion).normalize()
        actual_ts = pd.Timestamp(actual_completion).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("completion values must be valid dates") from exc
    return float((actual_ts - planned_ts).days)


def active_days_overdue(
    planned_completion: DateLike | None,
    *,
    as_of: DateLike,
    actual_completion: DateLike | None = None,
) -> float:
    """Calculate overdue days for incomplete work as of a deterministic date.

    Args:
        planned_completion: Committed completion date.
        as_of: Reporting date; callers must pass this explicitly.
        actual_completion: Actual completion, when the project is already complete.

    Returns:
        Positive overdue days or zero for incomplete work not yet overdue. Completed
        work and missing planned dates return ``NaN``.
    """

    if actual_completion is not None and not pd.isna(actual_completion):
        return float("nan")
    if planned_completion is None or pd.isna(planned_completion):
        return float("nan")
    try:
        planned_ts = pd.Timestamp(planned_completion).normalize()
        as_of_ts = pd.Timestamp(as_of).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("planned_completion and as_of must be valid dates") from exc
    return float(max((as_of_ts - planned_ts).days, 0))


def calculate_delivery_metrics(
    projects: pd.DataFrame,
    *,
    as_of: DateLike,
) -> pd.DataFrame:
    """Add project-level duration, schedule variance, and delivery outcome fields.

    Args:
        projects: Project records using the canonical project date columns.
        as_of: Fixed reporting date used only for incomplete-project overdue logic.

    Returns:
        A copy of ``projects`` with ``planned_duration_days``,
        ``actual_duration_days``, ``schedule_variance_days``,
        ``schedule_variance_pct``, ``days_overdue``, and ``delivery_outcome``.

    Raises:
        ValueError: If required columns are absent or a completion precedes its start.
    """

    required = [
        "status",
        "planned_start_date",
        "planned_completion_date",
        "actual_start_date",
        "actual_completion_date",
    ]
    require_columns(projects, required, name="projects")
    result = projects.copy()

    planned_start = datetime_series(result, "planned_start_date", name="projects")
    planned_completion = datetime_series(result, "planned_completion_date", name="projects")
    actual_start = datetime_series(result, "actual_start_date", name="projects")
    actual_completion = datetime_series(result, "actual_completion_date", name="projects")
    try:
        as_of_ts = pd.Timestamp(as_of).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("as_of must be a valid date") from exc

    invalid_planned = (
        planned_start.notna() & planned_completion.notna() & planned_completion.lt(planned_start)
    )
    invalid_actual = (
        actual_start.notna() & actual_completion.notna() & actual_completion.lt(actual_start)
    )
    completion_without_start = actual_completion.notna() & actual_start.isna()
    if invalid_planned.any():
        raise ValueError(
            "planned completion precedes planned start at rows "
            f"{result.index[invalid_planned].tolist()}"
        )
    if invalid_actual.any():
        raise ValueError(
            "actual completion precedes actual start at rows "
            f"{result.index[invalid_actual].tolist()}"
        )
    if completion_without_start.any():
        raise ValueError(
            "actual completion requires an actual start at rows "
            f"{result.index[completion_without_start].tolist()}"
        )

    result["planned_duration_days"] = (
        (planned_completion - planned_start).dt.days.add(1).astype(float)
    )
    result.loc[planned_start.isna() | planned_completion.isna(), "planned_duration_days"] = np.nan

    result["actual_duration_days"] = (actual_completion - actual_start).dt.days.add(1).astype(float)
    result.loc[actual_start.isna() | actual_completion.isna(), "actual_duration_days"] = np.nan

    result["schedule_variance_days"] = (actual_completion - planned_completion).dt.days.astype(
        float
    )
    result.loc[actual_completion.isna() | planned_completion.isna(), "schedule_variance_days"] = (
        np.nan
    )
    result["schedule_variance_pct"] = safe_percentage(
        result["schedule_variance_days"], result["planned_duration_days"]
    )

    incomplete = actual_completion.isna()
    result["days_overdue"] = np.nan
    result.loc[incomplete & planned_completion.notna(), "days_overdue"] = (
        (as_of_ts - planned_completion[incomplete & planned_completion.notna()])
        .dt.days.clip(lower=0)
        .astype(float)
    )

    cancelled = result["status"].map(normalize_token).isin({"cancelled", "canceled"})
    outcome = pd.Series("in_progress", index=result.index, dtype="object")
    outcome.loc[cancelled] = "cancelled"
    complete = actual_completion.notna() & ~cancelled
    outcome.loc[complete & result["schedule_variance_days"].lt(0)] = "early"
    outcome.loc[complete & result["schedule_variance_days"].eq(0)] = "on_time"
    outcome.loc[complete & result["schedule_variance_days"].gt(0)] = "late"
    overdue = incomplete & result["days_overdue"].gt(0) & ~cancelled
    outcome.loc[overdue] = "active_overdue"
    result["delivery_outcome"] = outcome

    return result


def summarize_delivery(
    delivery_metrics: pd.DataFrame,
) -> Mapping[str, int | float]:
    """Summarize delivery outcomes without counting cancelled projects as delivered.

    Args:
        delivery_metrics: Output from :func:`calculate_delivery_metrics`.

    Returns:
        Counts, on-time percentage, and mean/median completed schedule variance.
        On-time includes projects completed early or exactly on the planned date.
    """

    require_columns(
        delivery_metrics,
        ["delivery_outcome", "schedule_variance_days"],
        name="delivery_metrics",
    )
    outcomes = delivery_metrics["delivery_outcome"]
    completed = outcomes.isin(["early", "on_time", "late"])
    on_time = outcomes.isin(["early", "on_time"])
    completed_count = int(completed.sum())
    variances = pd.to_numeric(
        delivery_metrics.loc[completed, "schedule_variance_days"], errors="coerce"
    )
    return {
        "total_projects": int(len(delivery_metrics)),
        "completed_projects": completed_count,
        "on_time_projects": int(on_time.sum()),
        "late_projects": int(outcomes.eq("late").sum()),
        "active_overdue_projects": int(outcomes.eq("active_overdue").sum()),
        "cancelled_projects": int(outcomes.eq("cancelled").sum()),
        "on_time_delivery_pct": float(safe_percentage(int(on_time.sum()), completed_count)),
        "average_schedule_variance_days": float(variances.mean()),
        "median_schedule_variance_days": float(variances.median()),
    }
