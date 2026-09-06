"""Closed, bounded trace projections for the exact reviewed synthetic cohort."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from re import fullmatch
from typing import Any, Final
from uuid import UUID

from langsmith import Client
from langsmith.schemas import TracerSession

from ..config import LangSmithSettings
from ..domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewStatus,
    VerificationStatus,
)
from ..observability import JsonValue, langsmith_retry_config, langsmith_timeout_ms
from .draft_scenarios import DRAFT_SCENARIO_VERSION
from .reviewed_manifest import ReviewedEvaluationManifest
from .scenarios import EVALUATION_SCENARIO_VERSION
from .synthetic_tracing import WITHHELD_ERROR, safe_synthetic_payload

MAX_REVIEWED_TRACE_ITEMS: Final = 128
_MAX_DEPTH: Final = 4
_MAX_COUNT: Final = 1_000_000
_MAX_STRING: Final = 128
_WRAPPERS: Final = ("state", "update", "input", "inputs", "output", "outputs", "metadata")
_MISSING_GATES: Final = frozenset(
    {"identity", "current_affiliation", "research_interest_or_publication"}
)


def _count(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= _MAX_COUNT else None


def _items(value: object) -> tuple[object, ...]:
    if isinstance(value, (tuple, list)):
        return tuple(value[:MAX_REVIEWED_TRACE_ITEMS])
    return ()


def _collection_size(value: object) -> int | None:
    return _count(len(value)) if isinstance(value, (tuple, list)) else None


def _bounded_safe_value(value: JsonValue) -> JsonValue:
    """Bound an already allowlisted projection; never copy raw strings or raw keys."""
    if isinstance(value, dict):
        return {key: _bounded_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_bounded_safe_value(item) for item in value[:MAX_REVIEWED_TRACE_ITEMS]]
    if type(value) is int:
        return _count(value)
    if isinstance(value, str) and len(value) > _MAX_STRING:
        return None
    return value


def _histogram(values: tuple[object, ...], allowed: frozenset[str]) -> dict[str, JsonValue]:
    counts: dict[str, JsonValue] = {}
    for label in sorted(allowed):
        count = sum(isinstance(value, str) and value == label for value in values)
        if count:
            counts[label] = count
    return counts


def _verification_summary(value: object) -> dict[str, JsonValue]:
    records = tuple(item for item in _items(value) if isinstance(item, Mapping))
    evidence = tuple(
        claim
        for record in records
        for claim in _items(record.get("evidence"))
        if isinstance(claim, Mapping)
    )
    missing = tuple(
        gate for record in records for gate in _items(record.get("missing_required_evidence"))
    )
    return {
        "summarized_records": len(records),
        "verification_status_counts": _histogram(
            tuple(record.get("verification_status") for record in records),
            frozenset(item.value for item in VerificationStatus),
        ),
        "availability_status_counts": _histogram(
            tuple(record.get("availability_status") for record in records),
            frozenset(item.value for item in AvailabilityStatus),
        ),
        "retained_claim_type_counts": _histogram(
            tuple(claim.get("claim_type") for claim in evidence),
            frozenset(item.value for item in EvidenceClaimType),
        ),
        "directly_supported_claim_type_counts": _histogram(
            tuple(
                claim.get("claim_type")
                for claim in evidence
                if claim.get("directly_supported") is True
            ),
            frozenset(item.value for item in EvidenceClaimType),
        ),
        "missing_required_evidence_counts": _histogram(missing, _MISSING_GATES),
        "projection_truncated": (
            isinstance(value, (tuple, list)) and len(value) > MAX_REVIEWED_TRACE_ITEMS
        )
        or any(
            isinstance(record.get("evidence"), (tuple, list))
            and len(record["evidence"]) > MAX_REVIEWED_TRACE_ITEMS
            for record in records
        ),
    }


def _assessment_summary(value: object) -> dict[str, JsonValue]:
    assessments = tuple(
        item.get("assessment") for item in _items(value) if isinstance(item, Mapping)
    )
    scores: list[JsonValue] = []
    confidences: list[object] = []
    for assessment in assessments:
        if not isinstance(assessment, Mapping):
            continue
        score = assessment.get("overall_score")
        if type(score) is int and 0 <= score <= 100:
            scores.append(score)
        confidences.append(assessment.get("confidence"))
    return {
        "scores": scores,
        "confidence_counts": _histogram(
            tuple(confidences), frozenset(item.value for item in EvidenceConfidence)
        ),
        "projection_truncated": (
            isinstance(value, (tuple, list)) and len(value) > MAX_REVIEWED_TRACE_ITEMS
        ),
    }


def _target_projection(
    payload: Mapping[str, object], scenario_id: str, target: str
) -> dict[str, JsonValue]:
    counts: dict[str, JsonValue] = {}
    safe: dict[str, JsonValue] = {
        "target": target,
        "evaluation_scenario_id": scenario_id,
        "counts": counts,
    }
    if target == "graph_fake":
        graph_input = dict(payload)
        raw_log = payload.get("execution_log")
        graph_input["execution_log"] = _items(raw_log)
        graph = safe_synthetic_payload(graph_input)
        safe.update(graph)
        graph_counts = safe.get("counts")
        counts = graph_counts if isinstance(graph_counts, dict) else {}
        safe["counts"] = counts
        safe["execution_log_truncated"] = (
            isinstance(raw_log, (tuple, list)) and len(raw_log) > MAX_REVIEWED_TRACE_ITEMS
        )
        for field in ("raw_search_result_count", "plausible_profile_count"):
            if (count := _count(payload.get(field))) is not None:
                counts[field] = count
        safe["independent_review_status_counts"] = _histogram(
            tuple(
                item.get("review_status")
                for item in _items(payload.get("independent_reviews"))
                if isinstance(item, Mapping)
            ),
            frozenset(item.value for item in IndependentReviewStatus),
        )
    if target == "search_planning":
        plan = payload.get("search_plan")
        if isinstance(plan, Mapping):
            for field in ("search_queries", "expanded_research_concepts", "target_regions"):
                if (count := _collection_size(plan.get(field))) is not None:
                    counts[field] = count
    for field in ("verification_records", "assessments"):
        if (count := _collection_size(payload.get(field))) is not None:
            counts[field] = count
            safe["verification" if field == "verification_records" else "research_fit"] = (
                _verification_summary(payload[field])
                if field == "verification_records"
                else _assessment_summary(payload[field])
            )
    measurements = payload.get("measurements")
    if (
        isinstance(measurements, Mapping)
        and (count := _count(measurements.get("port_invocations"))) is not None
    ):
        safe["port_invocations"] = count
    return {key: _bounded_safe_value(value) for key, value in safe.items()}


def make_reviewed_anonymizer(
    manifest: ReviewedEvaluationManifest,
) -> Callable[[object], dict[str, JsonValue]]:
    """Close over validated public identities, never mutable incoming metadata or secrets."""
    manifest = ReviewedEvaluationManifest.model_validate(manifest.model_dump())
    scenarios = {
        case.scenario.scenario_id: case.scenario.target.value
        for case in manifest.source_draft.cases
    }
    metadata_values = {
        "evaluation_scenario_id": frozenset(scenarios),
        "evaluation_target": frozenset({*scenarios.values(), "mixed"}),
        "scenario_version": frozenset({EVALUATION_SCENARIO_VERSION, DRAFT_SCENARIO_VERSION}),
        "reviewed_version": frozenset({manifest.reviewed_version}),
        "content_digest": frozenset({manifest.content_digest}),
        "source_draft_digest": frozenset({manifest.source_draft_digest}),
        "dataset_name": frozenset({manifest.dataset_name}),
        "approval_scope": frozenset({manifest.approval_scope}),
        "execution_mode": frozenset({"fake_only"}),
        "__ls_runner": frozenset({"py_sdk_evaluate"}),
    }
    allowed_splits = frozenset(
        {"base", *(split for case in manifest.source_draft.cases for split in case.scenario.splits)}
    )

    def metadata(payload: Mapping[str, object]) -> dict[str, JsonValue]:
        existing = safe_synthetic_payload({"metadata": payload}).get("metadata")
        safe = dict(existing) if isinstance(existing, dict) else {}
        for key, allowed in metadata_values.items():
            value = payload.get(key)
            if isinstance(value, str) and value in allowed:
                safe[key] = str(value)
            else:
                safe.pop(key, None)
        for key in ("dataset_version", "example_version", "snapshot_as_of"):
            version = payload.get(key)
            if (
                isinstance(version, str)
                and len(version) <= 40
                and fullmatch(
                    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
                    version,
                )
            ):
                try:
                    datetime.fromisoformat(version)
                except ValueError:
                    pass
                else:
                    safe[key] = version
        splits = payload.get("dataset_splits")
        if isinstance(splits, (list, tuple)):
            safe["dataset_splits"] = [
                str(split)
                for split in _items(splits)
                if isinstance(split, str) and split in allowed_splits
            ]
        if type(payload.get("num_repetitions")) is int and payload["num_repetitions"] == 1:
            safe["num_repetitions"] = 1
        return {key: _bounded_safe_value(value) for key, value in safe.items()}

    def project(payload: object, depth: int) -> dict[str, JsonValue]:
        if not isinstance(payload, Mapping) or depth > _MAX_DEPTH:
            return {}
        if "error" in payload:
            return {"error": WITHHELD_ERROR}
        scenario = payload.get("scenario")
        if isinstance(scenario, Mapping):
            scenario_id = scenario.get("scenario_id")
            if isinstance(scenario_id, str) and scenario_id in scenarios:
                return {
                    "evaluation_scenario_id": scenario_id,
                    "evaluation_target": scenarios[scenario_id],
                    "synthetic_data": True,
                }
            return {}
        if "target" in payload:
            scenario_id = payload.get("scenario_id")
            if (
                isinstance(scenario_id, str)
                and scenario_id in scenarios
                and payload.get("target") == scenarios[scenario_id]
            ):
                return _target_projection(payload, scenario_id, scenarios[scenario_id])
            return {}
        wrappers: dict[str, JsonValue] = {}
        for key in _WRAPPERS:
            nested = payload.get(key)
            if isinstance(nested, Mapping):
                safe_nested = metadata(nested) if key == "metadata" else project(nested, depth + 1)
                if safe_nested:
                    wrappers[key] = safe_nested
        if wrappers:
            return wrappers
        # Raw graph state/node updates already have a deterministic allowlist.
        existing = safe_synthetic_payload(payload)
        if "fields" in existing:
            return {key: _bounded_safe_value(value) for key, value in existing.items()}
        return metadata(payload)

    def anonymizer(payload: object) -> dict[str, JsonValue]:
        return project(payload, 0)

    return anonymizer


class _ReviewedTraceClient(Client):
    """Keep automatic SDK git/environment metadata out of experiment CRUD as well."""

    def __init__(
        self,
        *,
        anonymizer: Callable[[object], dict[str, JsonValue]],
        **kwargs: Any,
    ) -> None:
        self._reviewed_anonymizer = anonymizer
        super().__init__(anonymizer=anonymizer, **kwargs)

    def _safe_project_options(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        extra = kwargs.get("project_extra")
        nested_metadata = extra.get("metadata") if isinstance(extra, Mapping) else None
        raw_metadata = dict(nested_metadata) if isinstance(nested_metadata, Mapping) else {}
        direct_metadata = kwargs.get("metadata")
        if isinstance(direct_metadata, Mapping):
            raw_metadata.update(direct_metadata)
        projected = self._reviewed_anonymizer({"metadata": raw_metadata}).get("metadata", {})
        return {**kwargs, "metadata": projected, "project_extra": None}

    def create_project(self, project_name: str, **kwargs: Any) -> TracerSession:
        return super().create_project(project_name, **self._safe_project_options(kwargs))

    def update_project(self, project_id: UUID | str, **kwargs: Any) -> TracerSession:
        return super().update_project(project_id, **self._safe_project_options(kwargs))


def create_reviewed_trace_client(
    settings: LangSmithSettings,
    manifest: ReviewedEvaluationManifest,
) -> Client:
    """Construct one finite-timeout client with a single closed payload anonymizer."""
    anonymizer = make_reviewed_anonymizer(manifest)
    return _ReviewedTraceClient(
        api_url=str(settings.endpoint),
        api_key=settings.require_evaluation_api_key().get_secret_value(),
        workspace_id=settings.workspace_id,
        timeout_ms=langsmith_timeout_ms(settings),
        retry_config=langsmith_retry_config(settings),
        anonymizer=anonymizer,
        hide_inputs=False,
        hide_outputs=False,
        hide_metadata=False,
        omit_traced_runtime_info=True,
    )
