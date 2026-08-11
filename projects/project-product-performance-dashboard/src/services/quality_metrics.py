"""Testing, defect, UAT, and transparent release-readiness calculations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd

from ._utils import bool_value, normalize_token, require_columns, safe_percentage

TEST_STATUSES = ("passed", "failed", "blocked", "not_run")
UAT_STATUSES = {
    "not_applicable",
    "not_started",
    "in_progress",
    "passed",
    "failed",
}
OPEN_DEFECT_STATUSES = {"open", "in_progress"}
BLOCKING_SEVERITIES = {"critical", "high"}
DEFECT_SEVERITIES = ("critical", "high", "medium", "low")
RESOLVED_DEFECT_STATUSES = {"resolved", "closed"}
DEFECT_STATUSES = OPEN_DEFECT_STATUSES | RESOLVED_DEFECT_STATUSES


def _normalized_test_cases(test_cases: pd.DataFrame) -> pd.DataFrame:
    """Return test cases with a validated internal normalized status."""

    require_columns(
        test_cases,
        ["project_id", "test_category", "status"],
        name="test_cases",
    )
    result = test_cases.copy()
    result["_normalized_status"] = result["status"].map(normalize_token)
    invalid = ~result["_normalized_status"].isin(TEST_STATUSES)
    if invalid.any():
        values = sorted(result.loc[invalid, "status"].astype(str).unique().tolist())
        raise ValueError(f"Unknown test statuses: {values}")
    return result


def calculate_quality_rates(
    *,
    passed: int,
    failed: int,
    blocked: int,
    not_run: int,
) -> dict[str, int | float]:
    """Calculate execution and pass rates from mutually exclusive test counts.

    Args:
        passed: Count of passed tests.
        failed: Count of failed tests.
        blocked: Count of attempted but blocked tests.
        not_run: Count of tests that have not been attempted.

    Returns:
        Counts plus total, executed, execution percentage, and pass percentage.
        Zero denominators produce ``NaN``.

    Raises:
        ValueError: If any count is negative.
    """

    counts = {
        "passed": passed,
        "failed": failed,
        "blocked": blocked,
        "not_run": not_run,
    }
    if any(value < 0 for value in counts.values()):
        raise ValueError("Test counts cannot be negative")
    total = passed + failed + blocked + not_run
    executed = passed + failed + blocked
    return {
        **counts,
        "total": total,
        "executed": executed,
        "execution_rate_pct": float(safe_percentage(executed, total)),
        "pass_rate_pct": float(safe_percentage(passed, executed)),
    }


def calculate_quality_metrics(
    test_cases: pd.DataFrame,
    *,
    group_columns: Sequence[str] = ("project_id",),
) -> pd.DataFrame:
    """Aggregate granular test cases into auditable quality metrics.

    Blocked tests count as executed but unsuccessful. Portfolio callers should sum
    the returned counts before calculating rates rather than averaging percentages.

    Args:
        test_cases: Canonical granular test-case records.
        group_columns: Columns defining each output group, typically project and
            optionally test category.

    Returns:
        Counts and calculated rates for each group.

    Raises:
        ValueError: If group columns or statuses are invalid.
    """

    if not group_columns:
        raise ValueError("group_columns must contain at least one column")
    normalized = _normalized_test_cases(test_cases)
    require_columns(normalized, group_columns, name="test_cases")
    output_columns = [
        *group_columns,
        *TEST_STATUSES,
        "total",
        "executed",
        "execution_rate_pct",
        "pass_rate_pct",
    ]
    if normalized.empty:
        return pd.DataFrame(columns=output_columns)

    grouped = (
        normalized.groupby([*group_columns, "_normalized_status"], dropna=False)
        .size()
        .unstack("_normalized_status", fill_value=0)
        .reset_index()
    )
    grouped.columns.name = None
    for status in TEST_STATUSES:
        if status not in grouped:
            grouped[status] = 0
        grouped[status] = grouped[status].astype(int)
    grouped["total"] = grouped[list(TEST_STATUSES)].sum(axis=1).astype(int)
    grouped["executed"] = grouped[["passed", "failed", "blocked"]].sum(axis=1).astype(int)
    grouped["execution_rate_pct"] = safe_percentage(grouped["executed"], grouped["total"])
    grouped["pass_rate_pct"] = safe_percentage(grouped["passed"], grouped["executed"])
    return grouped[output_columns]


def calculate_defect_metrics(
    defects: pd.DataFrame,
    *,
    group_columns: Sequence[str] = ("project_id",),
) -> pd.DataFrame:
    """Aggregate granular defects into open/resolved and severity counts.

    ``Open`` and ``In Progress`` defects are open. ``Resolved`` defects are
    resolved, with legacy ``Closed`` records accepted as the same terminal state.
    Severity counts include open defects only.

    Args:
        defects: Granular defect records with workflow status and severity.
        group_columns: Columns defining each output group, normally ``project_id``.

    Returns:
        One row per group with ``open_defects``, ``resolved_defects``, and open
        critical/high/medium/low defect counts.

    Raises:
        ValueError: If group columns, workflow statuses, or severities are invalid.
    """

    if not group_columns:
        raise ValueError("group_columns must contain at least one column")
    require_columns(defects, [*group_columns, "status", "severity"], name="defects")
    output_columns = [
        *group_columns,
        "open_defects",
        "resolved_defects",
        *[f"open_{severity}_defects" for severity in DEFECT_SEVERITIES],
    ]
    if defects.empty:
        return pd.DataFrame(columns=output_columns)

    normalized = defects.copy()
    normalized["_status"] = normalized["status"].map(normalize_token)
    invalid_status = ~normalized["_status"].isin(DEFECT_STATUSES)
    if invalid_status.any():
        values = sorted(normalized.loc[invalid_status, "status"].astype(str).unique().tolist())
        raise ValueError(f"Unknown defect statuses: {values}")

    normalized["_severity"] = normalized["severity"].map(normalize_token)
    invalid_severity = ~normalized["_severity"].isin(DEFECT_SEVERITIES)
    if invalid_severity.any():
        values = sorted(normalized.loc[invalid_severity, "severity"].astype(str).unique().tolist())
        raise ValueError(f"Unknown defect severities: {values}")

    is_open = normalized["_status"].isin(OPEN_DEFECT_STATUSES)
    normalized["open_defects"] = is_open.astype(int)
    normalized["resolved_defects"] = (
        normalized["_status"].isin(RESOLVED_DEFECT_STATUSES).astype(int)
    )
    for severity in DEFECT_SEVERITIES:
        normalized[f"open_{severity}_defects"] = (
            is_open & normalized["_severity"].eq(severity)
        ).astype(int)

    metric_columns = output_columns[len(group_columns) :]
    return (
        normalized.groupby(list(group_columns), as_index=False, dropna=False, sort=False)[
            metric_columns
        ]
        .sum()
        .loc[:, output_columns]
    )


def assess_release_readiness(
    project_test_requirements: pd.DataFrame,
    test_cases: pd.DataFrame,
    defects: pd.DataFrame,
    release_assessments: pd.DataFrame,
    *,
    project_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Assess explicit project release gates without a composite quality score.

    A gate passes only when a test plan exists, every applicable required category
    has evidence with no failed/blocked/not-run tests, applicable UAT has passed,
    and no open critical/high release-blocking defect exists. A release date always
    yields the state ``Released``; unmet gates then produce an exception warning.

    Args:
        project_test_requirements: Applicable/required categories by project.
        test_cases: Granular test results.
        defects: Project defects with severity, workflow state, and blocker flag.
        release_assessments: UAT applicability/status and actual release date.
        project_ids: Optional complete ordered project universe.

    Returns:
        One row per project with gate evidence, readiness state, exception warning,
        and a human-readable reason.

    Raises:
        ValueError: If required columns, statuses, or one-row-per-project assessment
            constraints are invalid.
    """

    require_columns(
        project_test_requirements,
        ["project_id", "test_category", "applicable", "required"],
        name="project_test_requirements",
    )
    normalized_tests = _normalized_test_cases(test_cases)
    require_columns(
        defects,
        ["project_id", "severity", "status", "release_blocker"],
        name="defects",
    )
    require_columns(
        release_assessments,
        [
            "project_id",
            "uat_applicable",
            "uat_status",
            "actual_release_date",
            "release_exception_approved",
        ],
        name="release_assessments",
    )
    if release_assessments["project_id"].duplicated().any():
        duplicated = sorted(
            release_assessments.loc[
                release_assessments["project_id"].duplicated(keep=False), "project_id"
            ].unique()
        )
        raise ValueError(f"Multiple release assessments for projects: {duplicated}")

    requirements = project_test_requirements.copy()
    requirements["_applicable"] = requirements["applicable"].map(bool_value)
    requirements["_required"] = requirements["required"].map(bool_value)
    requirements["_normalized_category"] = requirements["test_category"].map(normalize_token)
    normalized_tests["_normalized_category"] = normalized_tests["test_category"].map(
        normalize_token
    )

    defect_rows = defects.copy()
    defect_rows["_severity"] = defect_rows["severity"].map(normalize_token)
    defect_rows["_status"] = defect_rows["status"].map(normalize_token)
    defect_rows["_release_blocker"] = defect_rows["release_blocker"].map(bool_value)

    assessments = release_assessments.copy()
    assessments["_uat_applicable"] = assessments["uat_applicable"].map(bool_value)
    assessments["_uat_status"] = assessments["uat_status"].map(normalize_token)
    assessments["_release_exception_approved"] = assessments["release_exception_approved"].map(
        bool_value
    )
    invalid_uat = ~assessments["_uat_status"].isin(UAT_STATUSES)
    if invalid_uat.any():
        values = sorted(assessments.loc[invalid_uat, "uat_status"].astype(str).unique().tolist())
        raise ValueError(f"Unknown UAT statuses: {values}")
    assessments["actual_release_date"] = pd.to_datetime(
        assessments["actual_release_date"], errors="coerce"
    )

    if project_ids is None:
        id_parts = [
            requirements["project_id"],
            normalized_tests["project_id"],
            defect_rows["project_id"],
            assessments["project_id"],
        ]
        ids = pd.concat(id_parts, ignore_index=True).dropna().drop_duplicates().tolist()
    else:
        ids = list(dict.fromkeys(project_ids))

    assessment_lookup = assessments.set_index("project_id", drop=False)
    rows: list[dict[str, object]] = []
    for project_id in ids:
        project_requirements = requirements[requirements["project_id"].eq(project_id)]
        test_plan_present = not project_requirements.empty
        required_categories = set(
            project_requirements.loc[
                project_requirements["_applicable"] & project_requirements["_required"],
                "_normalized_category",
            ]
        )
        project_tests = normalized_tests[normalized_tests["project_id"].eq(project_id)]
        required_tests = project_tests[
            project_tests["_normalized_category"].isin(required_categories)
        ]
        evidenced_categories = set(required_tests["_normalized_category"])
        missing_categories = sorted(required_categories.difference(evidenced_categories))
        status_counts = required_tests["_normalized_status"].value_counts()
        failed_count = int(status_counts.get("failed", 0))
        blocked_count = int(status_counts.get("blocked", 0))
        not_run_count = int(status_counts.get("not_run", 0))

        project_defects = defect_rows[defect_rows["project_id"].eq(project_id)]
        blocking_defects = project_defects[
            project_defects["_release_blocker"]
            & project_defects["_severity"].isin(BLOCKING_SEVERITIES)
            & project_defects["_status"].isin(OPEN_DEFECT_STATUSES)
        ]
        blocker_count = int(len(blocking_defects))

        if project_id in assessment_lookup.index:
            assessment = assessment_lookup.loc[project_id]
            uat_applicable = bool(assessment["_uat_applicable"])
            uat_status = str(assessment["_uat_status"])
            release_date = assessment["actual_release_date"]
            exception_approved = bool(assessment["_release_exception_approved"])
        else:
            uat_applicable = False
            uat_status = "not_applicable"
            release_date = pd.NaT
            exception_approved = False

        uat_gate_passed = (not uat_applicable) or uat_status == "passed"
        testing_complete = (
            not missing_categories
            and failed_count == 0
            and blocked_count == 0
            and not_run_count == 0
        )
        gate_passed = (
            test_plan_present and testing_complete and uat_gate_passed and blocker_count == 0
        )
        explicit_blocker = (
            failed_count > 0
            or blocked_count > 0
            or blocker_count > 0
            or (uat_applicable and uat_status == "failed")
        )
        missing_evidence = (
            not test_plan_present
            or bool(missing_categories)
            or (uat_applicable and uat_status in {"", "not_applicable"})
        )
        released = pd.notna(release_date)

        if released:
            readiness = "Released"
        elif gate_passed:
            readiness = "Ready for Release"
        elif explicit_blocker or missing_evidence:
            readiness = "Not Ready"
        else:
            readiness = "Testing"

        reasons: list[str] = []
        if not test_plan_present:
            reasons.append("test plan missing")
        if missing_categories:
            reasons.append(f"missing test evidence: {', '.join(missing_categories)}")
        if failed_count:
            reasons.append(f"{failed_count} required test(s) failed")
        if blocked_count:
            reasons.append(f"{blocked_count} required test(s) blocked")
        if not_run_count:
            reasons.append(f"{not_run_count} required test(s) not run")
        if uat_applicable and not uat_gate_passed:
            reasons.append(f"UAT is {uat_status.replace('_', ' ')}")
        if blocker_count:
            reasons.append(f"{blocker_count} open high-severity release blocker(s)")
        if not reasons:
            reasons.append("all required release gates pass")

        rows.append(
            {
                "project_id": project_id,
                "test_plan_present": test_plan_present,
                "required_category_count": len(required_categories),
                "missing_required_category_count": len(missing_categories),
                "required_failed_count": failed_count,
                "required_blocked_count": blocked_count,
                "required_not_run_count": not_run_count,
                "open_release_blocker_count": blocker_count,
                "uat_applicable": uat_applicable,
                "uat_status": uat_status.replace("_", " ").title(),
                "uat_gate_passed": uat_gate_passed,
                "release_gate_passed": gate_passed,
                "actual_release_date": release_date,
                "release_readiness": readiness,
                "release_exception_warning": bool(released and not gate_passed),
                "release_exception_approved": exception_approved,
                "readiness_reason": "; ".join(reasons),
            }
        )

    return pd.DataFrame(rows)
