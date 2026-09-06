"""Count-only traces for explicitly allowlisted fake-provider evaluation runs."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Final

from langsmith import Client, tracing_context
from langsmith.run_helpers import get_current_run_tree

from ..agents.prompts import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    RESEARCH_PLANNING_PROMPT_VERSION,
)
from ..config import Environment, LangSmithSettings
from ..domain import ResearchFitRubric
from ..graph import ReviewStatus
from ..observability import (
    GRAPH_LOG_NODE_NAMES,
    GRAPH_VERSION,
    SCHOLARPATH_STATE_FIELDS,
    JsonValue,
    LangSmithObservability,
    langsmith_retry_config,
    langsmith_timeout_ms,
    summarize_state,
    summarize_update,
)
from ..tools import SearchErrorCategory
from .models import CandidateReviewOutcome, EvaluationTargetKind
from .scenarios import EVALUATION_SCENARIO_VERSION, EVALUATION_SCENARIOS

SYNTHETIC_EVALUATION_TRACE_TAG: Final = "synthetic-evaluation:allowlisted"
WITHHELD_ERROR: Final = "Error details withheld for synthetic evaluation."
_SCENARIOS: Final = {item.scenario_id: item.target.value for item in EVALUATION_SCENARIOS}
_REVIEW_STATUSES: Final = frozenset(item.value for item in ReviewStatus)
_PROJECTION_COUNT_FIELDS: Final = {
    "prospective_supervisor_ids": "prospective_supervisors",
    "verification_records": "verification_records",
    "assessments": "assessments",
    "independent_reviews": "independent_reviews",
    "proposed_supervisor_ids": "proposed_supervisors",
    "shortlisted_supervisor_ids": "shortlisted_supervisors",
    "rejected_supervisor_ids": "rejected_supervisors",
    "search_attempts": "search_attempts",
}
_METADATA_VALUES: Final = {
    "application": frozenset({"scholarpath"}),
    "environment": frozenset({Environment.TEST.value}),
    "graph_version": frozenset({GRAPH_VERSION}),
    "scenario_version": frozenset({EVALUATION_SCENARIO_VERSION}),
    "evaluation_scenario_id": frozenset(_SCENARIOS),
    "evaluation_target": frozenset(
        item.value for item in EvaluationTargetKind if item is not EvaluationTargetKind.GRAPH_LIVE
    ),
    "model_provider": frozenset({"fake"}),
    "provider": frozenset({"fake", "fixture", "you.com", "tavily", "openai", "nebius", "mem0"}),
    "prompt_version": frozenset(
        {
            "multiple",
            RESEARCH_PLANNING_PROMPT_VERSION,
            EVIDENCE_VERIFICATION_PROMPT_VERSION,
            RESEARCH_FIT_PROMPT_VERSION,
            INDEPENDENT_REVIEW_PROMPT_VERSION,
        }
    ),
    "rubric_version": frozenset({ResearchFitRubric().version}),
    "candidate_review_outcome": frozenset(item.value for item in CandidateReviewOutcome),
    "discovery_route": frozenset({"primary", "fallback"}),
    "error_category": frozenset({"none", *(item.value for item in SearchErrorCategory)}),
    "langgraph_node": GRAPH_LOG_NODE_NAMES,
    "component": frozenset(
        {
            "research_planning_agent",
            "supervisor_discovery_agent",
            "evidence_verification_agent",
            "research_fit_evaluation_agent",
            "independent_review_agent",
        }
    ),
}
_METADATA_COUNT_FIELDS: Final = frozenset(
    {
        "attempt_number",
        "raw_result_count",
        "plausible_supervisor_count",
        "langgraph_step",
        "rejected_person_not_established_count",
        "rejected_academic_context_not_established_count",
        "rejected_identity_conflict_count",
        "rejected_institution_not_established_count",
        "rejected_incomplete_institution_count",
    }
)


def _safe_metadata(payload: Mapping[str, object]) -> dict[str, JsonValue]:
    """Even known metadata keys must contain closed values, never arbitrary text."""
    safe: dict[str, JsonValue] = {}
    for key, allowed in _METADATA_VALUES.items():
        value = payload.get(key)
        if isinstance(value, str) and value in allowed:
            safe[key] = str(value)
    for key in _METADATA_COUNT_FIELDS:
        value = payload.get(key)
        if type(value) is int and value >= 0:
            safe[key] = value
    for key in ("synthetic_data", "fallback_search_used"):
        value = payload.get(key)
        if type(value) is bool:
            safe[key] = value
    return safe


def _safe_graph_projection(payload: Mapping[str, object]) -> dict[str, JsonValue]:
    counts: dict[str, JsonValue] = {}
    for field, label in _PROJECTION_COUNT_FIELDS.items():
        values = payload.get(field)
        if isinstance(values, (list, tuple)):
            counts[label] = len(values)
    safe: dict[str, JsonValue] = {"target": "graph_fake", "counts": counts}
    raw_log = payload.get("execution_log")
    if isinstance(raw_log, (list, tuple)):
        safe["execution_log"] = [
            str(node) for node in raw_log if isinstance(node, str) and node in GRAPH_LOG_NODE_NAMES
        ]
    for key in ("fallback_search_used", "interrupted"):
        value = payload.get(key)
        if type(value) is bool:
            safe[key] = value
    review_status = payload.get("review_status")
    if isinstance(review_status, str) and review_status in _REVIEW_STATUSES:
        safe["review_status"] = str(review_status)
    return safe


def _safe_payload(payload: object, depth: int) -> dict[str, JsonValue]:
    if not isinstance(payload, Mapping) or depth > 4:
        return {}
    if "error" in payload:
        return {"error": WITHHELD_ERROR}
    scenario = payload.get("scenario")
    if isinstance(scenario, Mapping):
        scenario_id = scenario.get("scenario_id")
        if isinstance(scenario_id, str) and scenario_id in _SCENARIOS:
            return {
                "evaluation_scenario_id": scenario_id,
                "evaluation_target": _SCENARIOS[scenario_id],
                "synthetic_data": True,
            }
        return {}
    if payload.get("target") == "graph_fake" and "prospective_supervisor_ids" in payload:
        return _safe_graph_projection(payload)
    wrappers: dict[str, JsonValue] = {}
    for key in ("state", "update", "input", "inputs", "output", "outputs", "metadata"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            if key == "metadata":
                safe_nested = _safe_metadata(nested)
            elif key in {"state", "update"} and SCHOLARPATH_STATE_FIELDS.intersection(nested):
                safe_nested = (
                    summarize_state(nested) if key == "state" else summarize_update(nested)
                )
            else:
                safe_nested = _safe_payload(nested, depth + 1)
            if safe_nested:
                wrappers[key] = safe_nested
    if wrappers:
        return wrappers
    if any(key in payload for key in ("application", "evaluation_scenario_id", "langgraph_node")):
        return _safe_metadata(payload)
    if SCHOLARPATH_STATE_FIELDS.intersection(payload):
        return (
            summarize_state(payload)
            if "candidate_profile" in payload
            else summarize_update(payload)
        )
    return _safe_metadata(payload)


def safe_synthetic_payload(payload: object) -> dict[str, JsonValue]:
    """Project SDK inputs, outputs, metadata, and wrapped errors into fresh safe mappings."""
    return _safe_payload(payload, 0)


def create_synthetic_trace_client(settings: LangSmithSettings) -> Client:
    """Construct a bounded evaluation client whose single anonymizer covers every payload."""
    return Client(
        api_url=str(settings.endpoint),
        api_key=settings.require_evaluation_api_key().get_secret_value(),
        workspace_id=settings.workspace_id,
        timeout_ms=langsmith_timeout_ms(settings),
        retry_config=langsmith_retry_config(settings),
        anonymizer=safe_synthetic_payload,
        hide_inputs=False,
        hide_outputs=False,
        hide_metadata=False,
        omit_traced_runtime_info=True,
    )


class SyntheticEvaluationObservability(LangSmithObservability):
    """Inherit the explicitly approved synthetic parent client and project only."""

    def __init__(self) -> None:
        super().__init__(
            # BaseSettings supports this runtime option outside its generated signature.
            LangSmithSettings(tracing=True, api_key=None, _env_file=None),  # type: ignore[call-arg]
            Environment.TEST,
        )

    @contextmanager
    def activate(self) -> Iterator[None]:
        parent = get_current_run_tree()
        if parent is None or SYNTHETIC_EVALUATION_TRACE_TAG not in (parent.tags or []):
            raise RuntimeError("An allowlisted synthetic evaluation parent trace is required.")
        with tracing_context(
            enabled=True,
            parent=parent,
            client=parent.client,
            project_name=parent.session_name,
            tags=self.tags,
            metadata=self.graph_metadata,
        ):
            yield
