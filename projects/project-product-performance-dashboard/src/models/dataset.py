"""In-memory representation of the canonical dashboard dataset."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, fields

import pandas as pd


@dataclass(frozen=True)
class DatasetMetadata:
    """Dataset-wide settings used to make calculations reproducible.

    Attributes:
        reporting_date: Fixed as-of date for active-project calculations.
        window_start: First calendar month represented by product metrics.
        window_end: Last calendar month represented by product metrics.
        currency: Fictional presentation currency shared by all cost tables.
        seed: Seed used to generate the sample fixture.
        fictional_data: Whether the dataset is explicitly fictional.
    """

    reporting_date: pd.Timestamp
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    currency: str
    seed: int
    fictional_data: bool


@dataclass
class DashboardDataBundle:
    """Canonical collection of related dashboard tables.

    Each table is a Pandas DataFrame so calculation services can remain
    independent of the source system that produced the data.
    """

    metadata: DatasetMetadata
    projects: pd.DataFrame
    resource_allocations: pd.DataFrame
    project_cost_items: pd.DataFrame
    project_test_requirements: pd.DataFrame
    test_cases: pd.DataFrame
    defects: pd.DataFrame
    release_assessments: pd.DataFrame
    products: pd.DataFrame
    project_product_mappings: pd.DataFrame
    product_investment_items: pd.DataFrame
    product_monthly_metrics: pd.DataFrame

    def iter_tables(self) -> Iterator[tuple[str, pd.DataFrame]]:
        """Yield canonical table names and frames in declaration order.

        Yields:
            Pairs containing a table name and its DataFrame.
        """
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, pd.DataFrame):
                yield field.name, value

    def tables(self) -> dict[str, pd.DataFrame]:
        """Return a name-to-DataFrame mapping for all canonical tables.

        Returns:
            New dictionary referencing the bundle's DataFrames.
        """
        return dict(self.iter_tables())

    def copy(self, *, deep: bool = True) -> DashboardDataBundle:
        """Copy the bundle and all contained DataFrames.

        Args:
            deep: Passed to :meth:`pandas.DataFrame.copy`.

        Returns:
            A new bundle with copied DataFrames and the same immutable metadata.
        """
        return DashboardDataBundle(
            metadata=self.metadata,
            **{name: frame.copy(deep=deep) for name, frame in self.iter_tables()},
        )
