"""Pure domain services for the project and product performance dashboard."""

from .delivery_metrics import (
    active_days_overdue,
    calculate_delivery_metrics,
    inclusive_duration_days,
    schedule_variance_days,
    summarize_delivery,
)
from .engineering_costs import (
    allocate_engineering_costs,
    calculate_project_allocation_coverage,
    calculate_project_costs,
    calculate_resource_costs,
    cost_variance,
    summarize_product_allocations,
    validate_project_product_allocations,
)
from .financial_metrics import (
    calculate_financial_metrics,
    calculate_initial_investments,
    summarize_financials,
)
from .portfolio_metrics import (
    build_executive_summary,
    summarize_quality_portfolio,
    weighted_rate_from_counts,
)
from .product_metrics import (
    calculate_product_metrics,
    classify_product_performance,
    latest_product_metrics,
)
from .quality_metrics import (
    assess_release_readiness,
    calculate_defect_metrics,
    calculate_quality_metrics,
    calculate_quality_rates,
)

__all__ = [
    "active_days_overdue",
    "allocate_engineering_costs",
    "assess_release_readiness",
    "build_executive_summary",
    "calculate_delivery_metrics",
    "calculate_defect_metrics",
    "calculate_financial_metrics",
    "calculate_initial_investments",
    "calculate_product_metrics",
    "calculate_project_allocation_coverage",
    "calculate_project_costs",
    "calculate_quality_metrics",
    "calculate_quality_rates",
    "calculate_resource_costs",
    "classify_product_performance",
    "cost_variance",
    "inclusive_duration_days",
    "latest_product_metrics",
    "schedule_variance_days",
    "summarize_delivery",
    "summarize_financials",
    "summarize_product_allocations",
    "summarize_quality_portfolio",
    "validate_project_product_allocations",
    "weighted_rate_from_counts",
]
