"""Cross-table validation for canonical dashboard datasets."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd
from pandas.api import types as pandas_types

from src.data.contracts import TABLE_SPECS, ColumnSpec
from src.models.dataset import DashboardDataBundle
from src.models.enums import (
    DefectSeverity,
    DefectStatus,
    ProductInvestmentType,
    ProductLifecycleStatus,
    ProjectCostCategory,
    ProjectStatus,
    TestCategory,
    TestStatus,
    UATStatus,
    enum_values,
)


class DataValidationError(ValueError):
    """Raised when one or more canonical data invariants are violated."""

    def __init__(self, issues: Iterable[str]):
        """Initialize an error containing every discovered issue.

        Args:
            issues: Human-readable validation failures.
        """
        self.issues = tuple(issues)
        message = "Dashboard data validation failed:\n- " + "\n- ".join(self.issues)
        super().__init__(message)


def validate_dashboard_data(bundle: DashboardDataBundle) -> None:
    """Validate schemas, categorical values, and cross-table integrity.

    Args:
        bundle: Canonical dataset to validate.

    Raises:
        DataValidationError: If any structural or business rule fails.
    """
    issues = collect_validation_issues(bundle)
    if issues:
        raise DataValidationError(issues)


def collect_validation_issues(bundle: DashboardDataBundle) -> list[str]:
    """Collect all detectable validation issues without raising immediately.

    Args:
        bundle: Canonical dataset to inspect.

    Returns:
        Ordered list of human-readable validation failures.
    """
    issues: list[str] = []
    _validate_metadata(bundle, issues)
    valid_schema_tables = _validate_table_schemas(bundle, issues)

    required_for_relations = set(TABLE_SPECS)
    if valid_schema_tables != required_for_relations:
        return issues

    _validate_categorical_values(bundle, issues)
    _validate_project_dates(bundle, issues)
    _validate_nonnegative_values(bundle, issues)
    _validate_foreign_keys(bundle, issues)
    _validate_table_relationships(bundle, issues)
    _validate_product_metrics(bundle, issues)
    _validate_currencies(bundle, issues)
    return issues


def _validate_metadata(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate dataset-wide reproducibility settings."""
    metadata = bundle.metadata
    if pd.isna(metadata.reporting_date):
        issues.append("metadata.reporting_date is required")
    if pd.isna(metadata.window_start) or pd.isna(metadata.window_end):
        issues.append("metadata product-metric window dates are required")
        return
    if metadata.window_start > metadata.window_end:
        issues.append("metadata.window_start must not be after window_end")
    if metadata.window_start.day != 1 or metadata.window_end.day != 1:
        issues.append("metadata window_start and window_end must be month-start dates")
    if metadata.window_end.to_period("M") > metadata.reporting_date.to_period("M"):
        issues.append("metadata.window_end must not be after reporting_date")
    if len(metadata.currency) != 3 or not metadata.currency.isupper():
        issues.append("metadata.currency must be a three-letter uppercase code")
    if not isinstance(metadata.seed, int) or isinstance(metadata.seed, bool):
        issues.append("metadata.seed must be an integer")
    if not isinstance(metadata.fictional_data, bool):
        issues.append("metadata.fictional_data must be boolean")


def _validate_table_schemas(bundle: DashboardDataBundle, issues: list[str]) -> set[str]:
    """Validate exact columns, types, required fields, and primary keys."""
    valid_tables: set[str] = set()
    tables = bundle.tables()
    for table_name, spec in TABLE_SPECS.items():
        frame = tables.get(table_name)
        if frame is None:
            issues.append(f"missing canonical table {table_name}")
            continue

        expected = list(spec.columns)
        actual = list(frame.columns)
        missing = [column for column in expected if column not in actual]
        extra = [column for column in actual if column not in expected]
        if missing:
            issues.append(f"{table_name} is missing columns {missing}")
        if extra:
            issues.append(f"{table_name} has unexpected columns {extra}")
        if missing or extra:
            continue

        table_types_valid = True
        if actual != expected:
            issues.append(f"{table_name} columns are not in canonical order")

        for column, column_spec in spec.columns.items():
            series = frame[column]
            table_types_valid &= _validate_column_type(
                table_name, column, series, column_spec, issues
            )
            if not column_spec.nullable and series.isna().any():
                issues.append(f"{table_name}.{column} contains missing values")
                table_types_valid = False
            if column_spec.kind == "string":
                blank = series.dropna().astype("string").str.strip().eq("")
                if blank.any():
                    issues.append(f"{table_name}.{column} contains blank values")
                    table_types_valid = False

        if frame.duplicated(list(spec.primary_key)).any():
            issues.append(f"{table_name} contains duplicate primary keys {spec.primary_key}")
        if table_types_valid:
            valid_tables.add(table_name)
    return valid_tables


def _validate_column_type(
    table_name: str,
    column: str,
    series: pd.Series,
    spec: ColumnSpec,
    issues: list[str],
) -> bool:
    """Validate a series against its logical canonical type."""
    valid = True
    if spec.kind == "string":
        valid = pandas_types.is_string_dtype(series.dtype)
    elif spec.kind == "date":
        valid = pandas_types.is_datetime64_any_dtype(series.dtype)
    elif spec.kind == "boolean":
        valid = pandas_types.is_bool_dtype(series.dtype)
    elif spec.kind == "float":
        valid = pandas_types.is_float_dtype(series.dtype)
    elif spec.kind == "integer":
        valid = pandas_types.is_integer_dtype(series.dtype)
    if not valid:
        issues.append(
            f"{table_name}.{column} must use logical type {spec.kind}; found dtype {series.dtype}"
        )
    return valid


def _validate_categorical_values(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate values constrained to canonical enumerations."""
    constraints = (
        ("projects", "status", enum_values(ProjectStatus)),
        ("project_cost_items", "cost_category", enum_values(ProjectCostCategory)),
        (
            "project_test_requirements",
            "test_category",
            enum_values(TestCategory),
        ),
        ("test_cases", "test_category", enum_values(TestCategory)),
        ("test_cases", "status", enum_values(TestStatus)),
        ("defects", "severity", enum_values(DefectSeverity)),
        ("defects", "status", enum_values(DefectStatus)),
        ("release_assessments", "uat_status", enum_values(UATStatus)),
        ("products", "lifecycle_status", enum_values(ProductLifecycleStatus)),
        (
            "product_investment_items",
            "investment_type",
            enum_values(ProductInvestmentType),
        ),
    )
    tables = bundle.tables()
    for table_name, column, allowed in constraints:
        values = set(tables[table_name][column].dropna().astype(str))
        invalid = sorted(values - set(allowed))
        if invalid:
            issues.append(f"{table_name}.{column} contains unsupported values {invalid}")


def _validate_project_dates(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate project chronology and completion semantics."""
    projects = bundle.projects
    invalid_planned = projects["planned_completion_date"] < projects["planned_start_date"]
    if invalid_planned.any():
        issues.append("projects contains planned completion dates before planned starts")

    has_actual_start = projects["actual_start_date"].notna()
    has_actual_completion = projects["actual_completion_date"].notna()
    invalid_actual = has_actual_completion & (
        ~has_actual_start | (projects["actual_completion_date"] < projects["actual_start_date"])
    )
    if invalid_actual.any():
        issues.append("projects contains invalid actual date ranges")

    complete = projects["status"].eq(ProjectStatus.COMPLETE.value)
    if (complete & (~has_actual_start | ~has_actual_completion)).any():
        issues.append("complete projects require actual start and completion dates")
    if (~complete & has_actual_completion).any():
        issues.append("only complete projects may have an actual completion date")

    for column in ("actual_start_date", "actual_completion_date"):
        if (projects[column].dropna() > bundle.metadata.reporting_date).any():
            issues.append(f"projects.{column} must not be after reporting_date")


def _validate_nonnegative_values(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate quantitative fields that cannot be negative."""
    constraints = {
        "resource_allocations": (
            "estimated_person_days",
            "actual_person_days",
            "fictional_daily_rate",
        ),
        "project_cost_items": ("estimated_cost", "actual_cost"),
        "product_investment_items": ("amount",),
        "product_monthly_metrics": (
            "active_customers",
            "eligible_customers",
            "transaction_count",
            "transaction_value",
            "revenue",
            "operating_cost",
        ),
    }
    tables = bundle.tables()
    for table_name, columns in constraints.items():
        for column in columns:
            if (tables[table_name][column] < 0).any():
                issues.append(f"{table_name}.{column} contains negative values")

    if (bundle.resource_allocations["fictional_daily_rate"] <= 0).any():
        issues.append("resource_allocations.fictional_daily_rate must be positive")


def _validate_foreign_keys(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate references between the canonical entity tables."""
    project_ids = set(bundle.projects["project_id"])
    product_ids = set(bundle.products["product_id"])
    project_tables = (
        "resource_allocations",
        "project_cost_items",
        "project_test_requirements",
        "test_cases",
        "defects",
        "release_assessments",
        "project_product_mappings",
    )
    for table_name in project_tables:
        frame = bundle.tables()[table_name]
        unknown = sorted(set(frame["project_id"]) - project_ids)
        if unknown:
            issues.append(f"{table_name}.project_id references unknown projects {unknown}")

    product_tables = (
        "project_product_mappings",
        "product_investment_items",
        "product_monthly_metrics",
    )
    for table_name in product_tables:
        frame = bundle.tables()[table_name]
        unknown = sorted(set(frame["product_id"]) - product_ids)
        if unknown:
            issues.append(f"{table_name}.product_id references unknown products {unknown}")


def _validate_table_relationships(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate relationship cardinality and cross-table consistency."""
    requirements = bundle.project_test_requirements
    if requirements.duplicated(["project_id", "test_category"]).any():
        issues.append("project_test_requirements has duplicate project/category pairs")
    if ((~requirements["applicable"]) & requirements["required"]).any():
        issues.append("non-applicable test requirements cannot be required")

    applicable = requirements.loc[
        requirements["applicable"], ["project_id", "test_category"]
    ].drop_duplicates()
    case_links = bundle.test_cases[["project_id", "test_category"]].drop_duplicates()
    invalid_cases = case_links.merge(
        applicable,
        on=["project_id", "test_category"],
        how="left",
        indicator=True,
    )
    if invalid_cases["_merge"].eq("left_only").any():
        issues.append("test_cases contains cases for non-applicable test categories")

    assessments = bundle.release_assessments
    if assessments.duplicated(["project_id"]).any():
        issues.append("release_assessments must contain one row per project")
    if set(assessments["project_id"]) != set(bundle.projects["project_id"]):
        issues.append("release_assessments must cover every project exactly once")

    uat_requirements = requirements.loc[
        requirements["test_category"].eq(TestCategory.UAT.value),
        ["project_id", "applicable"],
    ].rename(columns={"applicable": "requirement_uat_applicable"})
    uat_check = assessments.merge(uat_requirements, on="project_id", how="left")
    mismatch = uat_check["requirement_uat_applicable"].isna() | (
        uat_check["uat_applicable"] != uat_check["requirement_uat_applicable"]
    )
    if mismatch.any():
        issues.append("release_assessments.uat_applicable must match UAT requirements")
    invalid_na = (~assessments["uat_applicable"]) & ~assessments["uat_status"].eq(
        UATStatus.NOT_APPLICABLE.value
    )
    invalid_required = assessments["uat_applicable"] & assessments["uat_status"].eq(
        UATStatus.NOT_APPLICABLE.value
    )
    if (invalid_na | invalid_required).any():
        issues.append("release assessment UAT status is inconsistent with applicability")

    released = assessments["actual_release_date"].notna()
    projects_for_release = bundle.projects.set_index("project_id")
    for row in assessments.loc[released].itertuples(index=False):
        project = projects_for_release.loc[row.project_id]
        if project["status"] != ProjectStatus.COMPLETE.value:
            issues.append(f"released project {row.project_id} is not delivery-complete")
        completion = project["actual_completion_date"]
        if pd.notna(completion) and row.actual_release_date < completion:
            issues.append(f"project {row.project_id} was released before delivery completion")
        if row.actual_release_date > bundle.metadata.reporting_date:
            issues.append(f"project {row.project_id} has a release after reporting_date")

    mappings = bundle.project_product_mappings
    if mappings.duplicated(["project_id", "product_id"]).any():
        issues.append("project_product_mappings has duplicate project/product pairs")
    if ((mappings["allocation_percentage"] <= 0) | (mappings["allocation_percentage"] > 100)).any():
        issues.append("mapping allocation percentages must be greater than 0 and at most 100")
    totals = mappings.groupby("project_id")["allocation_percentage"].sum()
    if (totals > 100.000001).any():
        projects = sorted(totals[totals > 100.000001].index.tolist())
        issues.append(f"mapping allocations exceed 100% for projects {projects}")

    metrics = bundle.product_monthly_metrics
    if metrics.duplicated(["product_id", "month"]).any():
        issues.append("product_monthly_metrics has duplicate product/month rows")


def _validate_product_metrics(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Validate monthly product coverage, chronology, and customer counts."""
    products = bundle.products
    metrics = bundle.product_monthly_metrics
    if (products["launch_date"] > bundle.metadata.reporting_date).any():
        issues.append("products.launch_date must not be after reporting_date")
    if (bundle.product_investment_items["incurred_date"] > bundle.metadata.reporting_date).any():
        issues.append("product investment dates must not be after reporting_date")

    if (metrics["active_customers"] > metrics["eligible_customers"]).any():
        issues.append("active customers cannot exceed eligible customers")
    if (metrics["month"].dt.day != 1).any():
        issues.append("product_monthly_metrics.month must contain month-start dates")
    outside_window = (metrics["month"] < bundle.metadata.window_start) | (
        metrics["month"] > bundle.metadata.window_end
    )
    if outside_window.any():
        issues.append("product monthly metrics fall outside the configured window")

    product_launch = products.set_index("product_id")["launch_date"].dt.to_period("M")
    metric_launch = metrics["product_id"].map(product_launch)
    if (metrics["month"].dt.to_period("M") < metric_launch).any():
        issues.append("product monthly metrics contain pre-launch months")
    if set(metrics["product_id"]) != set(products["product_id"]):
        issues.append("product_monthly_metrics must cover every product")


def _validate_currencies(bundle: DashboardDataBundle, issues: list[str]) -> None:
    """Ensure all monetary tables use the configured fictional currency."""
    for table_name in (
        "resource_allocations",
        "project_cost_items",
        "product_investment_items",
        "product_monthly_metrics",
    ):
        values = set(bundle.tables()[table_name]["currency"].astype(str))
        if values != {bundle.metadata.currency}:
            issues.append(f"{table_name}.currency must contain only {bundle.metadata.currency}")
