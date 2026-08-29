"""Preview or explicitly upload the ScholarPath M12 LangSmith dataset."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from langsmith.utils import LangSmithError

from scholarpath.config import (
    ProviderConfigurationError,
    load_evaluation_settings,
    load_langsmith_settings,
)
from scholarpath.evaluation import (
    EVALUATION_SCENARIOS,
    create_langsmith_evaluation_client,
    sync_evaluation_dataset,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or upload ScholarPath's synthetic M12 evaluation dataset."
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help=(
            "Write the dataset to LangSmith. Requires "
            "SCHOLARPATH_RUN_LANGSMITH_EVALS=true and LANGSMITH_API_KEY."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a no-network preview unless upload is explicitly requested."""
    args = _parser().parse_args(argv)
    evaluation_settings = load_evaluation_settings()
    dataset_name = evaluation_settings.evaluation_dataset_name
    if not args.upload:
        print(f"Dataset preview: {dataset_name}")
        print(f"Synthetic scenarios: {len(EVALUATION_SCENARIOS)}")
        for scenario in EVALUATION_SCENARIOS:
            print(f"- {scenario.scenario_id} [{scenario.target.value}]")
        print("No LangSmith write was requested.")
        return 0
    if not evaluation_settings.run_langsmith_evals:
        print(
            "LangSmith dataset upload is disabled. Set "
            "SCHOLARPATH_RUN_LANGSMITH_EVALS=true to opt in.",
            file=sys.stderr,
        )
        return 2
    try:
        client = create_langsmith_evaluation_client(load_langsmith_settings())
        result = sync_evaluation_dataset(client, dataset_name=dataset_name)
    except ProviderConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    except LangSmithError:
        print(
            "The LangSmith dataset request failed. Verify endpoint, API key, workspace, "
            "and permissions.",
            file=sys.stderr,
        )
        return 2
    action = "created" if result.dataset_created else "updated"
    print(
        f"LangSmith dataset {action}: {result.dataset_name} "
        f"({result.example_count} synthetic examples)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
