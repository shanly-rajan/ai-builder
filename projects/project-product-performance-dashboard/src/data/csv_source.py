"""CSV-backed implementation of the dashboard data-source contract."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.coercion import DataCoercionError, coerce_table_frame
from src.data.contracts import METADATA_COLUMNS, METADATA_KEYS, TABLE_SPECS
from src.data.validation import validate_dashboard_data
from src.models.dataset import DashboardDataBundle, DatasetMetadata


class CsvDataSourceError(ValueError):
    """Raised when a CSV fixture cannot be loaded into the canonical model."""


class CsvDashboardDataSource:
    """Load a complete dashboard dataset from a directory of CSV files."""

    def __init__(self, data_directory: str | Path, *, validate: bool = True) -> None:
        """Initialize the source.

        Args:
            data_directory: Directory containing all canonical CSV files.
            validate: Whether to enforce all business invariants after loading.
        """
        self.data_directory = Path(data_directory)
        self.validate = validate

    def load(self) -> DashboardDataBundle:
        """Load, coerce, and optionally validate the CSV dataset.

        Returns:
            Canonical dashboard data bundle.

        Raises:
            CsvDataSourceError: If files are missing, malformed, or uncoercible.
            DataValidationError: If cross-table validation fails.
        """
        if not self.data_directory.is_dir():
            raise CsvDataSourceError(
                f"Dashboard data directory does not exist: {self.data_directory}"
            )

        metadata = self._load_metadata()
        frames: dict[str, pd.DataFrame] = {}
        for table_name in TABLE_SPECS:
            path = self.data_directory / f"{table_name}.csv"
            if not path.is_file():
                raise CsvDataSourceError(f"Missing canonical data file: {path}")
            try:
                raw = pd.read_csv(path, keep_default_na=True)
                frames[table_name] = coerce_table_frame(table_name, raw)
            except (OSError, pd.errors.ParserError, DataCoercionError, UnicodeError) as error:
                raise CsvDataSourceError(f"Could not load {path}: {error}") from error

        bundle = DashboardDataBundle(metadata=metadata, **frames)
        if self.validate:
            validate_dashboard_data(bundle)
        return bundle

    def _load_metadata(self) -> DatasetMetadata:
        """Load scalar dataset metadata from its key/value CSV."""
        path = self.data_directory / "dataset_metadata.csv"
        if not path.is_file():
            raise CsvDataSourceError(f"Missing canonical data file: {path}")
        try:
            frame = pd.read_csv(path, dtype="string", keep_default_na=False)
        except (OSError, pd.errors.ParserError, UnicodeError) as error:
            raise CsvDataSourceError(f"Could not load {path}: {error}") from error

        if tuple(frame.columns) != METADATA_COLUMNS:
            raise CsvDataSourceError(
                f"{path} must contain exactly the columns {list(METADATA_COLUMNS)}"
            )
        if frame["key"].duplicated().any():
            raise CsvDataSourceError(f"{path} contains duplicate metadata keys")
        values = dict(
            zip(
                frame["key"].astype(str),
                frame["value"].astype(str),
                strict=True,
            )
        )
        missing = sorted(METADATA_KEYS - set(values))
        extra = sorted(set(values) - METADATA_KEYS)
        if missing or extra:
            raise CsvDataSourceError(
                f"{path} metadata keys mismatch; missing={missing}, unexpected={extra}"
            )

        try:
            reporting_date = _parse_metadata_date(values["reporting_date"], "reporting_date")
            window_start = _parse_metadata_date(values["window_start"], "window_start")
            window_end = _parse_metadata_date(values["window_end"], "window_end")
            seed = int(values["seed"])
            fictional_data = _parse_metadata_bool(values["fictional_data"])
        except ValueError as error:
            raise CsvDataSourceError(f"Invalid metadata in {path}: {error}") from error

        return DatasetMetadata(
            reporting_date=reporting_date,
            window_start=window_start,
            window_end=window_end,
            currency=values["currency"],
            seed=seed,
            fictional_data=fictional_data,
        )


def load_dashboard_data(
    data_directory: str | Path, *, validate: bool = True
) -> DashboardDataBundle:
    """Convenience wrapper for loading a canonical CSV dataset.

    Args:
        data_directory: Directory containing canonical CSV files.
        validate: Whether to run cross-table business validation.

    Returns:
        Loaded dashboard data bundle.
    """
    return CsvDashboardDataSource(data_directory, validate=validate).load()


def _parse_metadata_date(value: str, name: str) -> pd.Timestamp:
    """Parse and normalize one required metadata date."""
    try:
        parsed = pd.to_datetime(value, errors="raise")
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} is not a valid date: {value!r}") from error
    return pd.Timestamp(parsed).normalize()


def _parse_metadata_bool(value: str) -> bool:
    """Parse a strict true/false metadata value."""
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"fictional_data must be true or false, found {value!r}")
