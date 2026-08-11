"""Canonical table schemas and the source abstraction for dashboard data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from src.models.dataset import DashboardDataBundle

ColumnKind = Literal["string", "float", "integer", "boolean", "date"]


@dataclass(frozen=True)
class ColumnSpec:
    """Expected representation of one canonical table column.

    Attributes:
        kind: Logical type used during CSV coercion and validation.
        nullable: Whether missing values are permitted.
    """

    kind: ColumnKind
    nullable: bool = False


@dataclass(frozen=True)
class TableSpec:
    """Schema and primary key for a canonical table.

    Attributes:
        columns: Ordered mapping of column names to logical types.
        primary_key: Columns that uniquely identify a row.
    """

    columns: dict[str, ColumnSpec]
    primary_key: tuple[str, ...]


TABLE_SPECS: dict[str, TableSpec] = {
    "projects": TableSpec(
        columns={
            "project_id": ColumnSpec("string"),
            "project_name": ColumnSpec("string"),
            "project_owner": ColumnSpec("string"),
            "engineering_lead": ColumnSpec("string"),
            "product_owner": ColumnSpec("string"),
            "engineering_team": ColumnSpec("string"),
            "category": ColumnSpec("string"),
            "status": ColumnSpec("string"),
            "planned_start_date": ColumnSpec("date"),
            "planned_completion_date": ColumnSpec("date"),
            "actual_start_date": ColumnSpec("date", nullable=True),
            "actual_completion_date": ColumnSpec("date", nullable=True),
        },
        primary_key=("project_id",),
    ),
    "resource_allocations": TableSpec(
        columns={
            "allocation_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "role": ColumnSpec("string"),
            "estimated_person_days": ColumnSpec("float"),
            "actual_person_days": ColumnSpec("float"),
            "fictional_daily_rate": ColumnSpec("float"),
            "currency": ColumnSpec("string"),
        },
        primary_key=("allocation_id",),
    ),
    "project_cost_items": TableSpec(
        columns={
            "cost_item_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "cost_category": ColumnSpec("string"),
            "description": ColumnSpec("string"),
            "estimated_cost": ColumnSpec("float"),
            "actual_cost": ColumnSpec("float"),
            "currency": ColumnSpec("string"),
        },
        primary_key=("cost_item_id",),
    ),
    "project_test_requirements": TableSpec(
        columns={
            "requirement_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "test_category": ColumnSpec("string"),
            "applicable": ColumnSpec("boolean"),
            "required": ColumnSpec("boolean"),
        },
        primary_key=("requirement_id",),
    ),
    "test_cases": TableSpec(
        columns={
            "test_case_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "test_category": ColumnSpec("string"),
            "test_name": ColumnSpec("string"),
            "status": ColumnSpec("string"),
        },
        primary_key=("test_case_id",),
    ),
    "defects": TableSpec(
        columns={
            "defect_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "defect_name": ColumnSpec("string"),
            "severity": ColumnSpec("string"),
            "status": ColumnSpec("string"),
            "release_blocker": ColumnSpec("boolean"),
        },
        primary_key=("defect_id",),
    ),
    "release_assessments": TableSpec(
        columns={
            "release_assessment_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "uat_applicable": ColumnSpec("boolean"),
            "uat_status": ColumnSpec("string"),
            "actual_release_date": ColumnSpec("date", nullable=True),
            "release_exception_approved": ColumnSpec("boolean"),
        },
        primary_key=("release_assessment_id",),
    ),
    "products": TableSpec(
        columns={
            "product_id": ColumnSpec("string"),
            "product_name": ColumnSpec("string"),
            "product_owner": ColumnSpec("string"),
            "category": ColumnSpec("string"),
            "lifecycle_status": ColumnSpec("string"),
            "launch_date": ColumnSpec("date"),
        },
        primary_key=("product_id",),
    ),
    "project_product_mappings": TableSpec(
        columns={
            "mapping_id": ColumnSpec("string"),
            "project_id": ColumnSpec("string"),
            "product_id": ColumnSpec("string"),
            "allocation_percentage": ColumnSpec("float"),
        },
        primary_key=("mapping_id",),
    ),
    "product_investment_items": TableSpec(
        columns={
            "investment_item_id": ColumnSpec("string"),
            "product_id": ColumnSpec("string"),
            "investment_type": ColumnSpec("string"),
            "description": ColumnSpec("string"),
            "amount": ColumnSpec("float"),
            "incurred_date": ColumnSpec("date"),
            "currency": ColumnSpec("string"),
        },
        primary_key=("investment_item_id",),
    ),
    "product_monthly_metrics": TableSpec(
        columns={
            "metric_id": ColumnSpec("string"),
            "product_id": ColumnSpec("string"),
            "month": ColumnSpec("date"),
            "active_customers": ColumnSpec("integer"),
            "eligible_customers": ColumnSpec("integer"),
            "transaction_count": ColumnSpec("integer"),
            "transaction_value": ColumnSpec("float"),
            "revenue": ColumnSpec("float"),
            "operating_cost": ColumnSpec("float"),
            "currency": ColumnSpec("string"),
        },
        primary_key=("metric_id",),
    ),
}

METADATA_COLUMNS = ("key", "value")
METADATA_KEYS = frozenset(
    {
        "reporting_date",
        "window_start",
        "window_end",
        "currency",
        "seed",
        "fictional_data",
    }
)


@runtime_checkable
class DashboardDataSource(Protocol):
    """Interface implemented by canonical dashboard data providers."""

    def load(self) -> DashboardDataBundle:
        """Load and validate a complete dashboard dataset.

        Returns:
            Canonical in-memory data bundle.
        """
        ...
