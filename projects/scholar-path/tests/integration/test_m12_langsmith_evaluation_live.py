"""Opt-in live read-only smoke test for the ScholarPath LangSmith dataset."""

import os

import pytest

from scholarpath.config import load_evaluation_settings, load_langsmith_settings
from scholarpath.evaluation import create_langsmith_evaluation_client


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes"}


@pytest.mark.live
def test_langsmith_evaluation_dataset_exists_and_has_a_synthetic_example() -> None:
    """Read one bounded example; do not run a live model, graph, or search provider."""
    for opt_in in (
        "SCHOLARPATH_RUN_LIVE_TESTS",
        "SCHOLARPATH_RUN_LANGSMITH_EVALS",
    ):
        if not _enabled(opt_in):
            pytest.skip(f"Set {opt_in}=true to opt in to the live LangSmith dataset test")
    if not os.getenv("LANGSMITH_API_KEY", "").strip():
        pytest.skip("LANGSMITH_API_KEY is required for the live LangSmith dataset test")

    evaluation_settings = load_evaluation_settings()
    client = create_langsmith_evaluation_client(load_langsmith_settings())
    dataset_name = evaluation_settings.evaluation_dataset_name
    if not client.has_dataset(dataset_name=dataset_name):
        pytest.fail(
            "The ScholarPath M12 evaluation dataset does not exist. Run "
            "`python scripts/create_eval_dataset.py --upload` first."
        )

    examples = tuple(client.list_examples(dataset_name=dataset_name, limit=1))

    assert len(examples) == 1
    assert examples[0].metadata is not None
    assert examples[0].metadata.get("synthetic_data") is True
