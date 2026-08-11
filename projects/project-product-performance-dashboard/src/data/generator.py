"""Deterministic generator for the dashboard's fictional sample dataset."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.data.coercion import coerce_table_frame
from src.data.contracts import TABLE_SPECS
from src.data.validation import validate_dashboard_data
from src.models.dataset import DashboardDataBundle, DatasetMetadata
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
)

DEFAULT_SEED = 20260811
REPORTING_DATE = pd.Timestamp("2025-12-31")
WINDOW_START = pd.Timestamp("2024-01-01")
WINDOW_END = pd.Timestamp("2025-12-01")
FICTIONAL_CURRENCY = "USD"


@dataclass(frozen=True)
class ProjectBlueprint:
    """Designed project scenario used only while creating sample data."""

    name: str
    team: str
    category: str
    status: ProjectStatus
    planned_start: str
    planned_completion: str
    schedule_profile: str
    cost_profile: str
    quality_profile: str


@dataclass(frozen=True)
class ProductBlueprint:
    """Designed product scenario used only while creating sample data."""

    name: str
    category: str
    lifecycle_status: ProductLifecycleStatus
    launch_date: str
    financial_profile: str


PROJECT_BLUEPRINTS: tuple[ProjectBlueprint, ...] = (
    ProjectBlueprint(
        "Unified Customer Profile",
        "Atlas",
        "Customer Experience",
        ProjectStatus.COMPLETE,
        "2023-08-07",
        "2023-12-15",
        "early",
        "under",
        "clean",
    ),
    ProjectBlueprint(
        "Ledger Reconciliation Automation",
        "Beacon",
        "Payments",
        ProjectStatus.COMPLETE,
        "2023-09-11",
        "2024-01-26",
        "on_time",
        "on",
        "clean",
    ),
    ProjectBlueprint(
        "Real-time Fraud Signals",
        "Echo",
        "Risk & Compliance",
        ProjectStatus.COMPLETE,
        "2023-10-02",
        "2024-02-16",
        "late",
        "over",
        "clean",
    ),
    ProjectBlueprint(
        "Analytics Workspace Foundation",
        "Cirrus",
        "Data & Analytics",
        ProjectStatus.COMPLETE,
        "2023-11-06",
        "2024-03-22",
        "early",
        "under",
        "clean",
    ),
    ProjectBlueprint(
        "Partner API Gateway",
        "Delta",
        "Platform",
        ProjectStatus.COMPLETE,
        "2024-01-08",
        "2024-05-17",
        "late",
        "over",
        "clean",
    ),
    ProjectBlueprint(
        "Adaptive Checkout Rules",
        "Beacon",
        "Payments",
        ProjectStatus.COMPLETE,
        "2024-02-05",
        "2024-06-28",
        "on_time",
        "on",
        "exception",
    ),
    ProjectBlueprint(
        "Merchant Risk Console",
        "Echo",
        "Risk & Compliance",
        ProjectStatus.COMPLETE,
        "2024-03-04",
        "2024-07-19",
        "late",
        "over",
        "clean",
    ),
    ProjectBlueprint(
        "Usage Event Pipeline",
        "Cirrus",
        "Data & Analytics",
        ProjectStatus.COMPLETE,
        "2024-04-08",
        "2024-08-23",
        "early",
        "under",
        "clean",
    ),
    ProjectBlueprint(
        "Self-service Account Controls",
        "Atlas",
        "Customer Experience",
        ProjectStatus.COMPLETE,
        "2024-05-06",
        "2024-09-27",
        "on_time",
        "under",
        "clean",
    ),
    ProjectBlueprint(
        "Regional Payment Routing",
        "Beacon",
        "Payments",
        ProjectStatus.COMPLETE,
        "2024-06-03",
        "2024-10-25",
        "late",
        "over",
        "clean",
    ),
    ProjectBlueprint(
        "Product Insights Models",
        "Cirrus",
        "Data & Analytics",
        ProjectStatus.COMPLETE,
        "2024-07-08",
        "2024-11-29",
        "early",
        "on",
        "clean",
    ),
    ProjectBlueprint(
        "Identity Assurance Upgrade",
        "Echo",
        "Risk & Compliance",
        ProjectStatus.COMPLETE,
        "2024-08-05",
        "2024-12-20",
        "late",
        "over",
        "clean",
    ),
    ProjectBlueprint(
        "Assisted Support Pilot",
        "Atlas",
        "Customer Experience",
        ProjectStatus.COMPLETE,
        "2024-09-09",
        "2025-01-31",
        "on_time",
        "under",
        "clean",
    ),
    ProjectBlueprint(
        "Settlement Visibility",
        "Beacon",
        "Payments",
        ProjectStatus.COMPLETE,
        "2024-10-07",
        "2025-02-28",
        "late",
        "over",
        "clean",
    ),
    ProjectBlueprint(
        "Cloud Cost Observability",
        "Delta",
        "Platform",
        ProjectStatus.COMPLETE,
        "2024-11-04",
        "2025-03-28",
        "early",
        "under",
        "ready",
    ),
    ProjectBlueprint(
        "Feature Entitlement Service",
        "Delta",
        "Platform",
        ProjectStatus.COMPLETE,
        "2024-12-02",
        "2025-05-02",
        "late",
        "on",
        "clean",
    ),
    ProjectBlueprint(
        "Dispute Workflow Refresh",
        "Atlas",
        "Customer Experience",
        ProjectStatus.IN_PROGRESS,
        "2025-02-03",
        "2025-09-26",
        "active_overdue",
        "to_date",
        "blocked",
    ),
    ProjectBlueprint(
        "Continuous Control Testing",
        "Echo",
        "Risk & Compliance",
        ProjectStatus.TESTING,
        "2025-03-03",
        "2025-10-31",
        "active_overdue",
        "to_date",
        "blocked",
    ),
    ProjectBlueprint(
        "Embedded Reporting SDK",
        "Cirrus",
        "Data & Analytics",
        ProjectStatus.IN_PROGRESS,
        "2025-06-02",
        "2026-02-27",
        "active_on_track",
        "to_date",
        "in_progress",
    ),
    ProjectBlueprint(
        "Next-gen Vault Discovery",
        "Delta",
        "Platform",
        ProjectStatus.PLANNING,
        "2025-12-15",
        "2026-05-29",
        "future",
        "not_started",
        "planning",
    ),
    ProjectBlueprint(
        "Legacy Notification Migration",
        "Atlas",
        "Internal Operations",
        ProjectStatus.CANCELLED,
        "2025-01-13",
        "2025-07-25",
        "cancelled",
        "cancelled",
        "cancelled",
    ),
    ProjectBlueprint(
        "Merchant Segmentation Engine",
        "Cirrus",
        "Data & Analytics",
        ProjectStatus.IN_PROGRESS,
        "2025-04-07",
        "2025-11-28",
        "active_overdue",
        "to_date",
        "in_progress",
    ),
    ProjectBlueprint(
        "Tokenized Checkout Rollout",
        "Beacon",
        "Payments",
        ProjectStatus.TESTING,
        "2025-07-07",
        "2026-01-30",
        "active_on_track",
        "to_date",
        "testing",
    ),
    ProjectBlueprint(
        "Policy Decision Audit Trail",
        "Echo",
        "Risk & Compliance",
        ProjectStatus.COMPLETE,
        "2025-01-06",
        "2025-08-29",
        "late",
        "over",
        "exception",
    ),
)

PRODUCT_BLUEPRINTS: tuple[ProductBlueprint, ...] = (
    ProductBlueprint(
        "LedgerFlow",
        "Financial Operations",
        ProductLifecycleStatus.ACTIVE,
        "2024-01-15",
        "break_even",
    ),
    ProductBlueprint(
        "PayPilot", "Payments", ProductLifecycleStatus.ACTIVE, "2024-02-12", "break_even"
    ),
    ProductBlueprint(
        "InsightHub", "Analytics", ProductLifecycleStatus.ACTIVE, "2024-04-08", "break_even"
    ),
    ProductBlueprint(
        "ConnectAPI",
        "Developer Platform",
        ProductLifecycleStatus.ACTIVE,
        "2024-06-17",
        "approaching",
    ),
    ProductBlueprint(
        "RiskLens", "Risk", ProductLifecycleStatus.ACTIVE, "2024-08-12", "underperforming"
    ),
    ProductBlueprint(
        "MerchantPulse",
        "Merchant Experience",
        ProductLifecycleStatus.ACTIVE,
        "2025-01-13",
        "break_even",
    ),
    ProductBlueprint(
        "CloudConsole",
        "Platform Operations",
        ProductLifecycleStatus.ACTIVE,
        "2025-03-03",
        "approaching",
    ),
    ProductBlueprint(
        "CheckoutEdge", "Payments", ProductLifecycleStatus.ACTIVE, "2025-06-09", "declining"
    ),
    ProductBlueprint(
        "AssistAI", "Customer Support", ProductLifecycleStatus.PILOT, "2025-11-05", "new"
    ),
    ProductBlueprint("VaultNext", "Security", ProductLifecycleStatus.PILOT, "2025-12-10", "new"),
)

ROLE_RATES: dict[str, float] = {
    "Backend Engineer": 900.0,
    "Frontend Engineer": 850.0,
    "QA Engineer": 700.0,
    "DevOps Engineer": 950.0,
    "Data Engineer": 975.0,
    "Product Designer": 750.0,
    "Security Engineer": 1100.0,
    "Technical Lead": 1150.0,
    "Engineering Lead": 1300.0,
    "Solution Architect": 1400.0,
}


def generate_sample_data(seed: int = DEFAULT_SEED) -> DashboardDataBundle:
    """Generate a deterministic, internally reconciled fictional dataset.

    Args:
        seed: Random seed controlling bounded variation inside designed scenarios.

    Returns:
        Validated canonical dashboard data bundle.
    """
    rng = random.Random(seed)
    metadata = DatasetMetadata(
        reporting_date=REPORTING_DATE,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        currency=FICTIONAL_CURRENCY,
        seed=seed,
        fictional_data=True,
    )

    projects, project_scenarios = _generate_projects(rng)
    resources = _generate_resource_allocations(projects, project_scenarios, rng)
    cost_items = _generate_project_cost_items(projects, project_scenarios, rng)
    requirements, test_cases, defects, releases = _generate_quality_data(
        projects, project_scenarios, rng
    )
    products, product_scenarios = _generate_products()
    mappings = _generate_project_product_mappings()
    investments = _generate_product_investments(products, rng)
    monthly_metrics = _generate_product_monthly_metrics(
        products=products,
        product_scenarios=product_scenarios,
        resources=resources,
        cost_items=cost_items,
        mappings=mappings,
        investments=investments,
        rng=rng,
    )

    bundle = DashboardDataBundle(
        metadata=metadata,
        projects=projects,
        resource_allocations=resources,
        project_cost_items=cost_items,
        project_test_requirements=requirements,
        test_cases=test_cases,
        defects=defects,
        release_assessments=releases,
        products=products,
        project_product_mappings=mappings,
        product_investment_items=investments,
        product_monthly_metrics=monthly_metrics,
    )
    validate_dashboard_data(bundle)
    return bundle


def write_sample_data(bundle: DashboardDataBundle, output_directory: str | Path) -> None:
    """Write a bundle as the canonical CSV fixture.

    Existing canonical CSV files in the target directory are replaced.

    Args:
        bundle: Validated canonical data to serialize.
        output_directory: Destination directory for the CSV files.
    """
    validate_dashboard_data(bundle)
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)

    metadata_rows = [
        ("reporting_date", bundle.metadata.reporting_date.strftime("%Y-%m-%d")),
        ("window_start", bundle.metadata.window_start.strftime("%Y-%m-%d")),
        ("window_end", bundle.metadata.window_end.strftime("%Y-%m-%d")),
        ("currency", bundle.metadata.currency),
        ("seed", str(bundle.metadata.seed)),
        ("fictional_data", str(bundle.metadata.fictional_data).lower()),
    ]
    pd.DataFrame(metadata_rows, columns=["key", "value"]).to_csv(
        destination / "dataset_metadata.csv", index=False
    )
    for table_name, frame in bundle.iter_tables():
        frame.to_csv(
            destination / f"{table_name}.csv",
            index=False,
            date_format="%Y-%m-%d",
            float_format="%.2f",
        )


def generate_and_write_sample_data(
    output_directory: str | Path, seed: int = DEFAULT_SEED
) -> DashboardDataBundle:
    """Generate, validate, and persist the fictional sample fixture.

    Args:
        output_directory: Destination directory for canonical CSV files.
        seed: Deterministic generator seed.

    Returns:
        The generated in-memory data bundle.
    """
    bundle = generate_sample_data(seed)
    write_sample_data(bundle, output_directory)
    return bundle


def _frame(table_name: str, records: list[dict[str, object]]) -> pd.DataFrame:
    """Build a canonical typed frame from generated records."""
    columns = list(TABLE_SPECS[table_name].columns)
    return coerce_table_frame(table_name, pd.DataFrame.from_records(records, columns=columns))


def _generate_projects(
    rng: random.Random,
) -> tuple[pd.DataFrame, dict[str, ProjectBlueprint]]:
    """Generate project identity, ownership, status, and date records."""
    project_owners = (
        "Avery Vale",
        "Morgan Reed",
        "Samira North",
        "Theo Lake",
        "Noah Ember",
        "Imani Frost",
    )
    engineering_leads = ("Riley Forge", "Casey Brook", "Amina Quill", "Luca Pine", "Nia Summit")
    product_owners = ("Eden Moss", "Kai River", "Maya Flint", "Jonah Field", "Zara Coast")
    records: list[dict[str, object]] = []
    scenarios: dict[str, ProjectBlueprint] = {}

    for index, blueprint in enumerate(PROJECT_BLUEPRINTS, start=1):
        project_id = f"PRJ-{index:03d}"
        planned_start = pd.Timestamp(blueprint.planned_start)
        planned_completion = pd.Timestamp(blueprint.planned_completion)
        actual_start: pd.Timestamp | pd.NaTType = pd.NaT
        actual_completion: pd.Timestamp | pd.NaTType = pd.NaT

        if blueprint.status not in {ProjectStatus.PLANNING}:
            actual_start = planned_start + pd.Timedelta(rng.randint(-2, 5), unit="D")
        if blueprint.status is ProjectStatus.COMPLETE:
            if blueprint.schedule_profile == "early":
                actual_completion = planned_completion - pd.Timedelta(7 + index % 6, unit="D")
            elif blueprint.schedule_profile == "on_time":
                actual_completion = planned_completion
            else:
                actual_completion = planned_completion + pd.Timedelta(8 + index % 13, unit="D")

        records.append(
            {
                "project_id": project_id,
                "project_name": blueprint.name,
                "project_owner": project_owners[(index - 1) % len(project_owners)],
                "engineering_lead": engineering_leads[(index - 1) % len(engineering_leads)],
                "product_owner": product_owners[(index - 1) % len(product_owners)],
                "engineering_team": blueprint.team,
                "category": blueprint.category,
                "status": blueprint.status.value,
                "planned_start_date": planned_start,
                "planned_completion_date": planned_completion,
                "actual_start_date": actual_start,
                "actual_completion_date": actual_completion,
            }
        )
        scenarios[project_id] = blueprint
    return _frame("projects", records), scenarios


def _roles_for_category(category: str) -> tuple[str, ...]:
    """Return a plausible cross-functional role mix for a category."""
    common = [
        "Backend Engineer",
        "QA Engineer",
        "DevOps Engineer",
        "Technical Lead",
        "Engineering Lead",
        "Solution Architect",
    ]
    if category in {"Customer Experience", "Payments", "Internal Operations"}:
        common.extend(["Frontend Engineer", "Product Designer"])
    if category in {"Data & Analytics", "Platform"}:
        common.append("Data Engineer")
    if category in {"Risk & Compliance", "Payments", "Platform"}:
        common.append("Security Engineer")
    return tuple(common)


def _actual_effort_factor(blueprint: ProjectBlueprint, rng: random.Random) -> float:
    """Return a bounded effort factor matching a project's cost archetype."""
    ranges = {
        "under": (0.78, 0.92),
        "on": (0.97, 1.04),
        "over": (1.14, 1.32),
        "to_date": (0.62, 0.94),
        "not_started": (0.0, 0.0),
        "cancelled": (0.30, 0.48),
    }
    low, high = ranges[blueprint.cost_profile]
    return rng.uniform(low, high)


def _generate_resource_allocations(
    projects: pd.DataFrame,
    scenarios: dict[str, ProjectBlueprint],
    rng: random.Random,
) -> pd.DataFrame:
    """Generate role-level estimated and actual effort allocations."""
    records: list[dict[str, object]] = []
    allocation_number = 1
    for project in projects.itertuples(index=False):
        blueprint = scenarios[project.project_id]
        project_factor = _actual_effort_factor(blueprint, rng)
        for role in _roles_for_category(project.category):
            role_scale = {
                "Backend Engineer": 1.30,
                "Frontend Engineer": 1.00,
                "QA Engineer": 0.78,
                "DevOps Engineer": 0.48,
                "Data Engineer": 1.05,
                "Product Designer": 0.42,
                "Security Engineer": 0.38,
                "Technical Lead": 0.36,
                "Engineering Lead": 0.30,
                "Solution Architect": 0.26,
            }[role]
            estimated_days = round(rng.uniform(34.0, 78.0) * role_scale, 1)
            if project_factor == 0:
                actual_days = 0.0
            else:
                actual_days = round(estimated_days * project_factor * rng.uniform(0.96, 1.04), 1)
            records.append(
                {
                    "allocation_id": f"RAL-{allocation_number:04d}",
                    "project_id": project.project_id,
                    "role": role,
                    "estimated_person_days": estimated_days,
                    "actual_person_days": actual_days,
                    "fictional_daily_rate": ROLE_RATES[role],
                    "currency": FICTIONAL_CURRENCY,
                }
            )
            allocation_number += 1
    return _frame("resource_allocations", records)


def _generate_project_cost_items(
    projects: pd.DataFrame,
    scenarios: dict[str, ProjectBlueprint],
    rng: random.Random,
) -> pd.DataFrame:
    """Generate infrastructure and external engineering project costs."""
    records: list[dict[str, object]] = []
    cost_item_number = 1
    for project in projects.itertuples(index=False):
        blueprint = scenarios[project.project_id]
        factor = _actual_effort_factor(blueprint, rng)
        items = (
            (
                ProjectCostCategory.ENGINEERING_INFRASTRUCTURE.value,
                "CI/CD, tooling, and non-production environments",
                rng.uniform(14_000, 42_000),
            ),
            (
                ProjectCostCategory.EXTERNAL_ENGINEERING.value,
                "External integration and specialist services",
                rng.uniform(6_000, 32_000),
            ),
        )
        for category, description, estimated in items:
            actual = 0.0 if factor == 0 else estimated * factor * rng.uniform(0.94, 1.06)
            records.append(
                {
                    "cost_item_id": f"PCI-{cost_item_number:04d}",
                    "project_id": project.project_id,
                    "cost_category": category,
                    "description": description,
                    "estimated_cost": round(estimated, 2),
                    "actual_cost": round(actual, 2),
                    "currency": FICTIONAL_CURRENCY,
                }
            )
            cost_item_number += 1
    return _frame("project_cost_items", records)


def _test_applicability(category: str, project_status: str) -> dict[TestCategory, bool]:
    """Return category-specific applicability for each standard test type."""
    return {
        TestCategory.UNIT: True,
        TestCategory.INTEGRATION: True,
        TestCategory.SYSTEM: True,
        TestCategory.REGRESSION: True,
        TestCategory.PERFORMANCE: category != "Internal Operations",
        TestCategory.SECURITY: category != "Internal Operations",
        TestCategory.UAT: category not in {"Platform", "Internal Operations"},
        TestCategory.PRODUCTION_VALIDATION: project_status == ProjectStatus.COMPLETE.value,
    }


def _test_statuses(quality_profile: str, category: TestCategory, case_count: int) -> list[str]:
    """Create transparent test outcomes for a designed quality profile."""
    statuses = [TestStatus.PASSED.value] * case_count
    if quality_profile == "exception" and category is TestCategory.SECURITY:
        statuses[0] = TestStatus.FAILED.value
    elif quality_profile == "blocked":
        if category is TestCategory.INTEGRATION:
            statuses[0] = TestStatus.BLOCKED.value
        if category in {TestCategory.SYSTEM, TestCategory.UAT}:
            statuses[-1] = TestStatus.NOT_RUN.value
    elif quality_profile == "testing":
        statuses[-1] = TestStatus.NOT_RUN.value
        if category is TestCategory.SECURITY:
            statuses[0] = TestStatus.BLOCKED.value
    elif quality_profile == "in_progress":
        if category is TestCategory.UNIT:
            statuses[-1] = TestStatus.NOT_RUN.value
        else:
            statuses = [TestStatus.NOT_RUN.value] * case_count
            if category is TestCategory.INTEGRATION:
                statuses[0] = TestStatus.PASSED.value
    elif quality_profile in {"planning", "cancelled"}:
        statuses = [TestStatus.NOT_RUN.value] * case_count
    return statuses


def _generate_quality_data(
    projects: pd.DataFrame,
    scenarios: dict[str, ProjectBlueprint],
    rng: random.Random,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate requirements, cases, defects, and release assessments."""
    requirement_records: list[dict[str, object]] = []
    case_records: list[dict[str, object]] = []
    defect_records: list[dict[str, object]] = []
    release_records: list[dict[str, object]] = []
    requirement_number = 1
    case_number = 1
    defect_number = 1

    for project in projects.itertuples(index=False):
        blueprint = scenarios[project.project_id]
        applicability = _test_applicability(project.category, project.status)
        for category in TestCategory:
            applicable = applicability[category]
            requirement_records.append(
                {
                    "requirement_id": f"REQ-{requirement_number:04d}",
                    "project_id": project.project_id,
                    "test_category": category.value,
                    "applicable": applicable,
                    "required": applicable,
                }
            )
            requirement_number += 1
            if not applicable:
                continue
            case_count = 4
            statuses = _test_statuses(blueprint.quality_profile, category, case_count)
            for case_index, status in enumerate(statuses, start=1):
                case_records.append(
                    {
                        "test_case_id": f"TST-{case_number:05d}",
                        "project_id": project.project_id,
                        "test_category": category.value,
                        "test_name": f"{category.value} scenario {case_index}",
                        "status": status,
                    }
                )
                case_number += 1

        if blueprint.quality_profile == "exception":
            defect_records.append(
                {
                    "defect_id": f"DEF-{defect_number:04d}",
                    "project_id": project.project_id,
                    "defect_name": "Unresolved authorization boundary condition",
                    "severity": DefectSeverity.HIGH.value,
                    "status": DefectStatus.OPEN.value,
                    "release_blocker": True,
                }
            )
            defect_number += 1
        elif blueprint.quality_profile == "blocked":
            defect_records.append(
                {
                    "defect_id": f"DEF-{defect_number:04d}",
                    "project_id": project.project_id,
                    "defect_name": "Critical integration environment instability",
                    "severity": DefectSeverity.CRITICAL.value,
                    "status": DefectStatus.IN_PROGRESS.value,
                    "release_blocker": True,
                }
            )
            defect_number += 1
        elif blueprint.quality_profile in {"testing", "in_progress"}:
            defect_records.append(
                {
                    "defect_id": f"DEF-{defect_number:04d}",
                    "project_id": project.project_id,
                    "defect_name": "Usability wording requires refinement",
                    "severity": DefectSeverity.MEDIUM.value,
                    "status": DefectStatus.OPEN.value,
                    "release_blocker": False,
                }
            )
            defect_number += 1
        elif blueprint.quality_profile in {"clean", "ready"} and rng.random() < 0.6:
            defect_records.append(
                {
                    "defect_id": f"DEF-{defect_number:04d}",
                    "project_id": project.project_id,
                    "defect_name": "Resolved pre-release validation issue",
                    "severity": rng.choice([DefectSeverity.LOW.value, DefectSeverity.MEDIUM.value]),
                    "status": DefectStatus.RESOLVED.value,
                    "release_blocker": False,
                }
            )
            defect_number += 1

        uat_applicable = applicability[TestCategory.UAT]
        if not uat_applicable:
            uat_status = UATStatus.NOT_APPLICABLE.value
        elif blueprint.quality_profile in {"clean", "ready", "exception"}:
            uat_status = UATStatus.PASSED.value
        elif blueprint.quality_profile == "blocked":
            uat_status = UATStatus.FAILED.value
        elif blueprint.quality_profile == "testing":
            uat_status = UATStatus.IN_PROGRESS.value
        else:
            uat_status = UATStatus.NOT_STARTED.value

        actual_release_date: pd.Timestamp | pd.NaTType = pd.NaT
        if blueprint.quality_profile in {"clean", "exception"} and pd.notna(
            project.actual_completion_date
        ):
            actual_release_date = project.actual_completion_date + pd.Timedelta(
                rng.randint(3, 10), unit="D"
            )
        release_records.append(
            {
                "release_assessment_id": f"REL-{int(project.project_id[-3:]):03d}",
                "project_id": project.project_id,
                "uat_applicable": uat_applicable,
                "uat_status": uat_status,
                "actual_release_date": actual_release_date,
                "release_exception_approved": blueprint.quality_profile == "exception",
            }
        )

    return (
        _frame("project_test_requirements", requirement_records),
        _frame("test_cases", case_records),
        _frame("defects", defect_records),
        _frame("release_assessments", release_records),
    )


def _generate_products() -> tuple[pd.DataFrame, dict[str, ProductBlueprint]]:
    """Generate product identity, ownership, and launch records."""
    owners = ("Eden Moss", "Kai River", "Maya Flint", "Jonah Field", "Zara Coast")
    records: list[dict[str, object]] = []
    scenarios: dict[str, ProductBlueprint] = {}
    for index, blueprint in enumerate(PRODUCT_BLUEPRINTS, start=1):
        product_id = f"PRD-{index:03d}"
        records.append(
            {
                "product_id": product_id,
                "product_name": blueprint.name,
                "product_owner": owners[(index - 1) % len(owners)],
                "category": blueprint.category,
                "lifecycle_status": blueprint.lifecycle_status.value,
                "launch_date": pd.Timestamp(blueprint.launch_date),
            }
        )
        scenarios[product_id] = blueprint
    return _frame("products", records), scenarios


def _generate_project_product_mappings() -> pd.DataFrame:
    """Generate intentional many-to-many and partially allocated mappings."""
    allocations: dict[str, tuple[tuple[str, float], ...]] = {
        "PRJ-001": (("PRD-001", 60.0), ("PRD-002", 30.0)),
        "PRJ-002": (("PRD-001", 100.0),),
        "PRJ-003": (("PRD-002", 100.0),),
        "PRJ-004": (("PRD-003", 70.0), ("PRD-004", 30.0)),
        "PRJ-005": (("PRD-003", 100.0),),
        "PRJ-006": (("PRD-004", 85.0),),
        "PRJ-007": (("PRD-005", 100.0),),
        "PRJ-008": (("PRD-001", 40.0), ("PRD-006", 60.0)),
        "PRJ-009": (("PRD-006", 100.0),),
        "PRJ-010": (("PRD-007", 70.0), ("PRD-008", 30.0)),
        "PRJ-011": (("PRD-007", 100.0),),
        "PRJ-012": (("PRD-008", 100.0),),
        "PRJ-013": (("PRD-009", 50.0), ("PRD-010", 50.0)),
        "PRJ-014": (("PRD-005", 50.0), ("PRD-009", 50.0)),
        "PRJ-015": (("PRD-003", 40.0), ("PRD-006", 40.0)),
        "PRJ-016": (("PRD-004", 50.0), ("PRD-007", 50.0)),
        "PRJ-017": (("PRD-008", 60.0), ("PRD-010", 30.0)),
        "PRJ-018": (("PRD-005", 100.0),),
        "PRJ-019": (("PRD-009", 100.0),),
        "PRJ-020": (("PRD-010", 80.0),),
        "PRJ-021": (("PRD-002", 70.0),),
        "PRJ-022": (("PRD-006", 50.0), ("PRD-008", 50.0)),
        "PRJ-023": (("PRD-007", 40.0), ("PRD-009", 60.0)),
        "PRJ-024": (("PRD-004", 45.0), ("PRD-005", 45.0)),
    }
    records: list[dict[str, object]] = []
    mapping_number = 1
    for project_id, product_allocations in allocations.items():
        for product_id, percentage in product_allocations:
            records.append(
                {
                    "mapping_id": f"MAP-{mapping_number:04d}",
                    "project_id": project_id,
                    "product_id": product_id,
                    "allocation_percentage": percentage,
                }
            )
            mapping_number += 1
    return _frame("project_product_mappings", records)


def _generate_product_investments(products: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    """Generate fictional launch and third-party setup investments."""
    records: list[dict[str, object]] = []
    item_number = 1
    for product in products.itertuples(index=False):
        items = (
            (
                ProductInvestmentType.ADDITIONAL_LAUNCH_COST.value,
                "Launch enablement, training, and communications",
                rng.uniform(28_000, 72_000),
                45,
            ),
            (
                ProductInvestmentType.THIRD_PARTY_SETUP_COST.value,
                "Fictional vendor setup and certification",
                rng.uniform(18_000, 58_000),
                20,
            ),
        )
        for investment_type, description, amount, days_before_launch in items:
            records.append(
                {
                    "investment_item_id": f"INV-{item_number:04d}",
                    "product_id": product.product_id,
                    "investment_type": investment_type,
                    "description": description,
                    "amount": round(amount, 2),
                    "incurred_date": product.launch_date
                    - pd.Timedelta(days_before_launch, unit="D"),
                    "currency": FICTIONAL_CURRENCY,
                }
            )
            item_number += 1
    return _frame("product_investment_items", records)


def _initial_investment_by_product(
    resources: pd.DataFrame,
    cost_items: pd.DataFrame,
    mappings: pd.DataFrame,
    investments: pd.DataFrame,
) -> pd.Series:
    """Calculate the investment basis used to tune fictional financial arcs."""
    resource_costs = (
        resources.assign(
            actual_resource_cost=(
                resources["actual_person_days"] * resources["fictional_daily_rate"]
            )
        )
        .groupby("project_id")["actual_resource_cost"]
        .sum()
    )
    non_resource_costs = cost_items.groupby("project_id")["actual_cost"].sum()
    project_costs = resource_costs.add(non_resource_costs, fill_value=0.0)

    allocated = (
        mappings.assign(
            allocated_cost=mappings["project_id"].map(project_costs)
            * mappings["allocation_percentage"]
            / 100.0
        )
        .groupby("product_id")["allocated_cost"]
        .sum()
    )
    additional = investments.groupby("product_id")["amount"].sum()
    return allocated.add(additional, fill_value=0.0)


def _profit_weights(financial_profile: str, month_count: int) -> list[float]:
    """Return designed monthly weights for a product's profit trajectory."""
    if month_count == 1:
        return [1.0]
    if financial_profile == "declining":
        return [0.9 - (1.25 * index / (month_count - 1)) for index in range(month_count)]
    if financial_profile == "underperforming":
        return [0.7 + (0.3 * index / (month_count - 1)) for index in range(month_count)]
    if financial_profile == "new":
        return [0.8 + (0.4 * index / (month_count - 1)) for index in range(month_count)]
    return [0.45 + (1.35 * index / (month_count - 1)) for index in range(month_count)]


def _monthly_profits(
    financial_profile: str, initial_investment: float, month_count: int
) -> list[float]:
    """Scale a financial archetype to its product investment basis."""
    target_ratios = {
        "break_even": 1.28,
        "approaching": 0.72,
        "underperforming": 0.10,
        "declining": 0.04,
        "new": 0.06,
    }
    target = initial_investment * target_ratios[financial_profile]
    weights = _profit_weights(financial_profile, month_count)
    weight_total = sum(weights)
    return [target * weight / weight_total for weight in weights]


def _generate_product_monthly_metrics(
    *,
    products: pd.DataFrame,
    product_scenarios: dict[str, ProductBlueprint],
    resources: pd.DataFrame,
    cost_items: pd.DataFrame,
    mappings: pd.DataFrame,
    investments: pd.DataFrame,
    rng: random.Random,
) -> pd.DataFrame:
    """Generate monthly adoption, transaction, revenue, and cost histories."""
    initial_investments = _initial_investment_by_product(
        resources, cost_items, mappings, investments
    )
    records: list[dict[str, object]] = []
    metric_number = 1

    for product_index, product in enumerate(products.itertuples(index=False), start=1):
        blueprint = product_scenarios[product.product_id]
        launch_month = max(product.launch_date.to_period("M").to_timestamp(), WINDOW_START)
        months = list(pd.date_range(launch_month, WINDOW_END, freq="MS"))
        initial_investment = float(initial_investments.get(product.product_id, 0.0))
        monthly_profits = _monthly_profits(
            blueprint.financial_profile, initial_investment, len(months)
        )
        starting_eligible = 4_500 + product_index * 1_650
        adoption_ceiling = {
            "break_even": 0.46,
            "approaching": 0.34,
            "underperforming": 0.16,
            "declining": 0.13,
            "new": 0.055,
        }[blueprint.financial_profile]

        for month_index, (month, profit) in enumerate(
            zip(months, monthly_profits, strict=True), start=1
        ):
            progress = month_index / len(months)
            eligible_customers = int(round(starting_eligible * (1.0 + 0.018 * (month_index - 1))))
            adoption_rate = 0.018 + (adoption_ceiling - 0.018) * progress**0.82
            adoption_rate *= rng.uniform(0.975, 1.025)
            active_customers = min(
                eligible_customers,
                int(round(eligible_customers * adoption_rate)),
            )

            operating_cost = (
                30_000 + product_index * 2_750 + month_index * 620 + active_customers * 3.2
            )
            if blueprint.financial_profile == "declining":
                operating_cost *= 1.12
            revenue = max(0.0, operating_cost + profit)
            transaction_count = int(
                round(active_customers * (5.0 + product_index * 0.9) * rng.uniform(0.97, 1.03))
            )
            transaction_value = revenue * (38.0 + product_index * 3.5) * rng.uniform(0.98, 1.02)
            records.append(
                {
                    "metric_id": f"MET-{metric_number:04d}",
                    "product_id": product.product_id,
                    "month": month,
                    "active_customers": active_customers,
                    "eligible_customers": eligible_customers,
                    "transaction_count": transaction_count,
                    "transaction_value": round(transaction_value, 2),
                    "revenue": round(revenue, 2),
                    "operating_cost": round(operating_cost, 2),
                    "currency": FICTIONAL_CURRENCY,
                }
            )
            metric_number += 1
    return _frame("product_monthly_metrics", records)
