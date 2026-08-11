#!/usr/bin/env python3
"""Generate the committed fictional CSV fixture for the dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.generator import (  # noqa: E402
    DEFAULT_SEED,
    generate_and_write_sample_data,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed output directory and deterministic seed.
    """
    parser = argparse.ArgumentParser(
        description="Generate deterministic fictional dashboard sample data."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "sample",
        help="Destination directory (default: data/sample).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Deterministic random seed (default: {DEFAULT_SEED}).",
    )
    return parser.parse_args()


def main() -> int:
    """Generate the fixture and print a concise summary.

    Returns:
        Process exit status.
    """
    args = parse_args()
    bundle = generate_and_write_sample_data(args.output_dir, seed=args.seed)
    print(
        "Generated fictional dashboard data: "
        f"{len(bundle.projects)} projects, "
        f"{len(bundle.products)} products, "
        f"{len(bundle.product_monthly_metrics)} monthly rows "
        f"in {args.output_dir.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
