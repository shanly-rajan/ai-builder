"""One allowlisted, entirely synthetic fallback case for trace inspection."""

from langsmith.run_helpers import get_current_run_tree

from .models import EvaluationScenario
from .scenarios import EVALUATION_SCENARIOS, evaluation_dataset_inputs
from .synthetic_tracing import SyntheticEvaluationObservability
from .targets import fake_end_to_end_target

SYNTHETIC_TRACE_DATASET = "scholarpath-week4-synthetic-trace-v1"
SYNTHETIC_TRACE_CASE_ID = "you-timeout-tavily-fallback"


def synthetic_trace_scenario() -> EvaluationScenario:
    """Return a fresh curated case, never arbitrary uploaded Candidate inputs."""
    scenario = next(
        item for item in EVALUATION_SCENARIOS if item.scenario_id == SYNTHETIC_TRACE_CASE_ID
    )
    return scenario.model_copy(deep=True)


def traced_fallback_target(inputs: dict[str, object]) -> dict[str, object]:
    """Trace the approved fake case under the evaluation's existing parent/client."""
    trusted_inputs = evaluation_dataset_inputs(synthetic_trace_scenario())
    if inputs != trusted_inputs:
        raise ValueError("Synthetic tracing accepts only the unchanged curated fallback case.")
    parent = get_current_run_tree()
    if parent is None:
        raise ValueError("Synthetic tracing requires an active evaluation parent.")
    parent.add_tags(["synthetic-evaluation:allowlisted", "model-provider:fake"])
    return fake_end_to_end_target(trusted_inputs, observability=SyntheticEvaluationObservability())
