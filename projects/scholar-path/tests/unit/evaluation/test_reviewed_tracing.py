"""The reviewed cohort exposes only bounded synthetic identities, counts, and enums."""

import json
from collections.abc import Callable
from copy import deepcopy
from typing import cast
from uuid import UUID

import pytest
from langsmith import Client
from langsmith.utils import LangSmithRetry
from pydantic import HttpUrl, SecretStr, ValidationError
from requests import Response

from scholarpath.config import LangSmithSettings, ProviderConfigurationError
from scholarpath.evaluation import reviewed_tracing, runner
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.reviewed_tracing import (
    MAX_REVIEWED_TRACE_ITEMS,
    create_reviewed_trace_client,
    make_reviewed_anonymizer,
)
from scholarpath.evaluation.scenarios import evaluation_dataset_inputs
from scholarpath.evaluation.synthetic_tracing import WITHHELD_ERROR, safe_synthetic_payload
from scholarpath.observability import JsonValue, summarize_state, summarize_update

PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"


@pytest.fixture
def anonymize() -> Callable[[object], dict[str, JsonValue]]:
    return make_reviewed_anonymizer(build_reviewed_manifest())


def _evidence() -> dict[str, object]:
    return {
        "target": "evidence_verification",
        "scenario_id": "draft-evidence-heading-bound-research",
        "verification_records": [
            {
                "supervisor_id": PRIVATE,
                "verification_status": "verified",
                "availability_status": "not_stated",
                "verification_concerns": [PRIVATE],
                "missing_required_evidence": ["research_interest_or_publication", PRIVATE],
                "evidence": [
                    {"evidence_id": PRIVATE, "claim_type": "identity", "directly_supported": True},
                    {
                        "source_url": PRIVATE,
                        "claim_type": "research_interest",
                        "directly_supported": False,
                    },
                ],
            }
        ],
        "measurements": {"port_invocations": 2, "secret": PRIVATE},
    }


def _graph() -> dict[str, object]:
    return {
        "target": "graph_fake",
        "scenario_id": "draft-graph-reject-then-approve",
        "prospective_supervisor_ids": [PRIVATE],
        "proposed_supervisor_ids": [PRIVATE],
        "shortlisted_supervisor_ids": [PRIVATE],
        "rejected_supervisor_ids": [PRIVATE],
        "candidate_preferences": {"research_topics": [PRIVATE]},
        "verification_records": _evidence()["verification_records"],
        "independent_reviews": [{"review_status": "accepted", "critique": PRIVATE}],
        "execution_log": ["load_candidate_preferences", PRIVATE, "save_shortlisted_supervisors"],
        "review_status": "completed",
        "fallback_search_used": True,
        "interrupted": False,
        "measurements": {"port_invocations": 40},
    }


@pytest.mark.parametrize(
    "case", build_reviewed_manifest().source_draft.cases, ids=lambda case: case.scenario.scenario_id
)
def test_every_reviewed_scenario_identity_is_visible_without_its_input_content(
    case: object,
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    # Case typing follows the parametrized manifest without importing any live adapter.
    from scholarpath.evaluation.draft_models import DraftEvaluationCase

    assert isinstance(case, DraftEvaluationCase)
    source = evaluation_dataset_inputs(case.scenario)
    source["private"] = PRIVATE
    result = anonymize(source)
    assert result == {
        "evaluation_scenario_id": case.scenario.scenario_id,
        "evaluation_target": case.scenario.target.value,
        "synthetic_data": True,
    }
    assert PRIVATE not in json.dumps(result)


def test_metadata_extends_only_exact_reviewed_values(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    manifest = build_reviewed_manifest()
    source: dict[str, object] = {
        "application": "scholarpath",
        "environment": "test",
        "model_provider": "fake",
        "evaluation_scenario_id": "draft-evidence-heading-bound-research",
        "evaluation_target": "evidence_verification",
        "reviewed_version": manifest.reviewed_version,
        "content_digest": manifest.content_digest,
        "source_draft_digest": manifest.source_draft_digest,
        "dataset_name": manifest.dataset_name,
        "approval_scope": "expected_behaviors",
        "execution_mode": "fake_only",
        "scenario_version": "week4-30case-draft-v1",
        "candidate_id": PRIVATE,
        "api_key": PRIVATE,
        "unknown": PRIVATE,
    }
    expected = {
        key: value
        for key, value in source.items()
        if key not in {"candidate_id", "api_key", "unknown"}
    }
    assert anonymize({"metadata": source}) == {"metadata": expected}
    for key in expected:
        corrupted = {**source, key: PRIVATE}
        sanitized = anonymize({"metadata": corrupted})
        assert PRIVATE not in json.dumps(sanitized)


@pytest.mark.parametrize("version", ["week4-scenarios-v1", "week4-30case-draft-v1"])
def test_only_recorded_scenario_versions_are_retained(
    version: str, anonymize: Callable[[object], dict[str, JsonValue]]
) -> None:
    assert anonymize({"scenario_version": version}) == {"scenario_version": version}
    assert anonymize({"scenario_version": PRIVATE}) == {}


def test_evidence_output_exposes_the_grounding_gap_without_text_or_ids(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    result = anonymize(_evidence())
    assert result["counts"] == {"verification_records": 1}
    assert result["port_invocations"] == 2
    summary = result["verification"]
    assert isinstance(summary, dict)
    assert summary["retained_claim_type_counts"] == {"identity": 1, "research_interest": 1}
    assert summary["directly_supported_claim_type_counts"] == {"identity": 1}
    assert summary["verification_status_counts"] == {"verified": 1}
    assert summary["availability_status_counts"] == {"not_stated": 1}
    assert summary["missing_required_evidence_counts"] == {"research_interest_or_publication": 1}
    assert PRIVATE not in json.dumps(result)


def test_planning_and_fit_outputs_have_meaningful_bounded_summaries(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    planning = anonymize(
        {
            "target": "search_planning",
            "scenario_id": "planning-source-coverage",
            "search_plan": {
                "search_queries": [PRIVATE] * 4,
                "expanded_research_concepts": [PRIVATE] * 2,
                "target_regions": [PRIVATE],
            },
            "measurements": {"port_invocations": 1},
        }
    )
    assert planning["counts"] == {
        "search_queries": 4,
        "expanded_research_concepts": 2,
        "target_regions": 1,
    }
    fit = anonymize(
        {
            "target": "research_fit",
            "scenario_id": "strong-research-alignment",
            "candidate_preferences": PRIVATE,
            "assessments": [
                {
                    "assessment": {
                        "overall_score": 87,
                        "confidence": "high",
                        "rationale": PRIVATE,
                        "supervisor_id": PRIVATE,
                    },
                    "evidence": [PRIVATE],
                }
            ],
        }
    )
    assert fit["counts"] == {"assessments": 1}
    assert fit["research_fit"] == {
        "scores": [87],
        "confidence_counts": {"high": 1},
        "projection_truncated": False,
    }
    assert PRIVATE not in json.dumps([planning, fit])


def test_graph_output_reuses_closed_route_projection(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    result = anonymize(_graph())
    assert result["target"] == "graph_fake"
    assert result["execution_log"] == ["load_candidate_preferences", "save_shortlisted_supervisors"]
    assert result["fallback_search_used"] is True
    assert result["review_status"] == "completed"
    assert result["independent_review_status_counts"] == {"accepted": 1}
    assert result["port_invocations"] == 40
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("wrapper", ["input", "inputs", "output", "outputs"])
def test_sdk_wrappers_preserve_only_safe_projection(
    wrapper: str, anonymize: Callable[[object], dict[str, JsonValue]]
) -> None:
    assert anonymize({wrapper: _evidence(), "name": PRIVATE, "tags": [PRIVATE]}) == {
        wrapper: anonymize(_evidence())
    }


def test_raw_graph_state_and_update_reuse_existing_summaries(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    state = {
        "candidate_profile": {"proposed_research_statement": PRIVATE},
        "prospective_supervisors": [PRIVATE],
        "review_status": "proposed",
    }
    update = {"verified_supervisors": [PRIVATE], "shortlist_briefing": PRIVATE}
    assert anonymize({"state": state}) == {"state": summarize_state(state)}
    assert anonymize({"update": update}) == {"update": summarize_update(update)}
    assert PRIVATE not in json.dumps(anonymize(state))


@pytest.mark.parametrize(
    "error", [PRIVATE, RuntimeError(PRIVATE), {"Authorization": PRIVATE}, None]
)
def test_error_envelopes_always_withhold_original_content(
    error: object, anonymize: Callable[[object], dict[str, JsonValue]]
) -> None:
    assert anonymize({"error": error, "inputs": _evidence()}) == {"error": WITHHELD_ERROR}
    assert anonymize({"outputs": {"error": error}}) == {"outputs": {"error": WITHHELD_ERROR}}


@pytest.mark.parametrize(
    "payload",
    [
        None,
        PRIVATE,
        [PRIVATE],
        {PRIVATE: PRIVATE},
        {"scenario": {"scenario_id": PRIVATE}},
        {"target": "graph_live", "scenario_id": "draft-graph-reject-then-approve"},
    ],
)
def test_unknown_or_live_shapes_fail_closed(
    payload: object, anonymize: Callable[[object], dict[str, JsonValue]]
) -> None:
    assert anonymize(payload) == {}


def test_bounds_are_visible_and_do_not_modify_the_original_business_output(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    source = _graph()
    source["execution_log"] = ["load_candidate_preferences"] * (MAX_REVIEWED_TRACE_ITEMS + 5)
    records = _evidence()["verification_records"]
    assert isinstance(records, list)
    source["verification_records"] = records * (MAX_REVIEWED_TRACE_ITEMS + 5)
    source["measurements"] = {"port_invocations": 10**100}
    original = deepcopy(source)
    result = anonymize(source)
    assert result["execution_log_truncated"] is True
    assert isinstance(result["execution_log"], list)
    assert len(result["execution_log"]) == MAX_REVIEWED_TRACE_ITEMS
    summary = result["verification"]
    assert isinstance(summary, dict)
    assert summary["projection_truncated"] is True
    assert summary["summarized_records"] == MAX_REVIEWED_TRACE_ITEMS
    assert "port_invocations" not in result
    assert source == original
    result["execution_log"].append("changed")
    assert source == original
    nested: object = _evidence()
    for _ in range(30):
        nested = {"inputs": nested}
    assert anonymize(nested) == {}


def test_invalid_enum_and_numeric_values_never_become_trace_content(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    source = _graph()
    source.update(
        {
            "review_status": PRIVATE,
            "fallback_search_used": PRIVATE,
            "interrupted": 1,
            "independent_reviews": [{"review_status": PRIVATE}],
            "raw_search_result_count": -1,
        }
    )
    assert PRIVATE not in json.dumps(anonymize(source))
    assert anonymize({"metadata": {"attempt_number": 10**100, "raw_result_count": True}}) == {
        "metadata": {"attempt_number": None}
    }


def test_original_eleven_case_sanitizer_is_unchanged() -> None:
    new_case = {"scenario": {"scenario_id": "draft-evidence-heading-bound-research"}}
    assert safe_synthetic_payload(new_case) == {}
    assert make_reviewed_anonymizer(build_reviewed_manifest())(new_case)


def test_manifest_tampering_fails_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_reviewed_manifest().model_copy(update={"source_draft_digest": "0" * 64})
    monkeypatch.setattr(
        reviewed_tracing, "Client", lambda **_: pytest.fail("Must not construct a client")
    )
    with pytest.raises(ValidationError):
        make_reviewed_anonymizer(manifest)


def _settings() -> LangSmithSettings:
    return LangSmithSettings(
        tracing=False,
        api_key=SecretStr("fake-secret"),
        endpoint=HttpUrl("https://eu.api.smith.langchain.com"),
        workspace_id="fake-workspace",
        request_timeout_seconds=7.5,
        maximum_retry_count=1,
        _env_file=None,  # type: ignore[call-arg]
    )


def test_client_uses_single_anonymizer_and_bounded_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def factory(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(reviewed_tracing, "_ReviewedTraceClient", factory)
    settings = _settings()
    assert create_reviewed_trace_client(settings, build_reviewed_manifest()) is sentinel
    assert callable(captured["anonymizer"])
    assert captured["hide_inputs"] is captured["hide_outputs"] is captured["hide_metadata"] is False
    assert captured["omit_traced_runtime_info"] is True
    assert captured["api_url"] == str(settings.endpoint)
    assert captured["workspace_id"] == "fake-workspace"
    assert captured["timeout_ms"] == 7500
    retry = captured["retry_config"]
    assert isinstance(retry, LangSmithRetry)
    assert retry.total == 1 and retry.redirect == 0


def test_client_requires_key_before_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reviewed_tracing,
        "_ReviewedTraceClient",
        lambda **_: pytest.fail("Missing credentials must stop construction"),
    )
    settings = _settings().model_copy(update={"api_key": None})
    with pytest.raises(ProviderConfigurationError):
        create_reviewed_trace_client(settings, build_reviewed_manifest())


def test_installed_sdk_filters_inputs_outputs_metadata_and_errors_without_network() -> None:
    anonymizer = make_reviewed_anonymizer(build_reviewed_manifest())
    client = Client(
        api_key="fake-secret",
        api_url="https://api.smith.langchain.com",
        auto_batch_tracing=False,
        anonymizer=anonymizer,
        hide_inputs=False,
        hide_outputs=False,
        hide_metadata=False,
        omit_traced_runtime_info=True,
    )
    payloads: tuple[tuple[str, dict[str, object]], ...] = (
        ("_hide_run_inputs", {"inputs": _evidence()}),
        ("_hide_run_outputs", _graph()),
        (
            "_hide_run_metadata",
            {
                "application": "scholarpath",
                "dataset_name": build_reviewed_manifest().dataset_name,
                "secret": PRIVATE,
            },
        ),
    )
    try:
        for method, payload in payloads:
            filtered = cast(
                Callable[[dict[str, object]], dict[str, object]], getattr(client, method)
            )(payload)
            assert filtered
            assert PRIVATE not in json.dumps(filtered)
        assert cast(Callable[[str], str], client._hide_run_error)(PRIVATE) == WITHHELD_ERROR
    finally:
        client.close()


def test_all_thirty_real_fake_outputs_remain_meaningful_and_unchanged(
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    for case in build_reviewed_manifest().source_draft.cases:
        output = runner.dispatch_evaluation_target(evaluation_dataset_inputs(case.scenario))
        original = deepcopy(output)
        filtered = anonymize(output)
        assert filtered["evaluation_scenario_id"] == case.scenario.scenario_id
        assert filtered["target"] == case.scenario.target.value
        assert filtered["counts"]
        assert output == original
        serialized = json.dumps(filtered)
        for forbidden in (
            "source_url",
            "supervisor_id",
            "supporting_excerpt",
            "rationale",
            "research_topics",
            ".example",
            "candidate_id",
        ):
            assert forbidden not in serialized


def test_sdk_project_create_and_update_never_send_git_or_personal_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_reviewed_manifest()
    requests: list[tuple[str, object]] = []
    project_id = UUID("b9912302-1134-4533-88d0-eb5c345df70a")

    def transport(self: Client, method: str, path: str, **kwargs: object) -> Response:
        body = kwargs["data"]
        assert isinstance(body, (str, bytes))
        decoded = json.loads(body)
        requests.append((method, decoded))
        response = Response()
        response.status_code = 200
        response._content = json.dumps(
            {
                "id": str(project_id),
                "tenant_id": "b0546522-cf59-4f72-b5fb-0669fceebdaa",
                "reference_dataset_id": None,
                "start_time": "2026-09-06T15:00:00+00:00",
                "name": "reviewed-test",
                "extra": decoded["extra"],
            }
        ).encode()
        return response

    monkeypatch.setattr(Client, "request_with_retries", transport)
    client = reviewed_tracing._ReviewedTraceClient(
        api_key="fake-secret",
        api_url="https://eu.api.smith.langchain.com",
        auto_batch_tracing=False,
        anonymizer=make_reviewed_anonymizer(manifest),
        hide_inputs=False,
        hide_outputs=False,
        hide_metadata=False,
        omit_traced_runtime_info=True,
    )
    metadata = {
        "dataset_name": manifest.dataset_name,
        "reviewed_version": manifest.reviewed_version,
        "content_digest": manifest.content_digest,
        "source_draft_digest": manifest.source_draft_digest,
        "approval_scope": "expected_behaviors",
        "execution_mode": "fake_only",
        "dataset_version": "2026-09-06T15:34:28.123456+00:00",
        "dataset_splits": ["base", "evidence-verification", PRIVATE],
        "num_repetitions": 1,
        "__ls_runner": "py_sdk_evaluate",
        "git": {"author": PRIVATE, "remote_url": PRIVATE},
        "environment": {"SECRET": PRIVATE},
        "author_email": PRIVATE,
    }
    extra = {
        "metadata": {"git": PRIVATE, "project_secret": PRIVATE},
        "git": PRIVATE,
        "runtime": PRIVATE,
    }
    try:
        client.create_project(
            "reviewed-test",
            metadata=metadata,
            project_extra=extra,
            num_examples=30,
            num_repetitions=1,
        )
        client.update_project(project_id, metadata=metadata, project_extra=extra)
        client.update_project(project_id, project_extra={"metadata": metadata, "private": PRIVATE})
    finally:
        client.close()
    assert [method for method, _ in requests] == ["POST", "PATCH", "PATCH"]
    assert PRIVATE not in json.dumps(requests)
    for _, body in requests:
        assert isinstance(body, dict)
        assert set(body["extra"]) == {"metadata"}
        safe = body["extra"]["metadata"]
        assert safe["dataset_name"] == manifest.dataset_name
        assert safe["content_digest"] == manifest.content_digest
        assert safe["dataset_version"] == "2026-09-06T15:34:28.123456+00:00"
        assert safe["dataset_splits"] == ["base", "evidence-verification"]
        assert safe["num_repetitions"] == 1
        assert safe["__ls_runner"] == "py_sdk_evaluate"
        assert "git" not in safe and "environment" not in safe and "author_email" not in safe


@pytest.mark.parametrize(
    "value",
    [
        PRIVATE,
        "2026-99-06T15:00:00Z",
        "2026-09-06",
        "2026-09-06T15:00:00",
        "2026-09-06T15:00:00Z secret",
        None,
    ],
)
@pytest.mark.parametrize("key", ["dataset_version", "example_version", "snapshot_as_of"])
def test_sdk_dataset_version_rejects_non_timestamp_payloads(
    value: object,
    anonymize: Callable[[object], dict[str, JsonValue]],
    key: str,
) -> None:
    assert anonymize({key: value}) == {}


@pytest.mark.parametrize("key", ["dataset_version", "example_version", "snapshot_as_of"])
def test_sdk_versions_preserve_valid_timezone_aware_timestamps(
    key: str,
    anonymize: Callable[[object], dict[str, JsonValue]],
) -> None:
    version = "2026-09-06T15:34:28.123456+00:00"
    assert anonymize({key: version}) == {key: version}


def test_sdk_dataset_creation_respects_explicit_empty_runtime_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_reviewed_manifest()
    sent: list[dict[str, object]] = []
    tenant_id = UUID("b0546522-cf59-4f72-b5fb-0669fceebdaa")

    def transport(self: Client, method: str, path: str, **kwargs: object) -> Response:
        assert method == "POST" and path == "/datasets"
        body = kwargs["data"]
        assert isinstance(body, (str, bytes))
        decoded = json.loads(body)
        sent.append(decoded)
        response = Response()
        response.status_code = 200
        response._content = json.dumps(
            {
                "id": "5fdb0c81-baa1-483d-9867-a891bb3a9471",
                "name": decoded["name"],
                "created_at": "2026-09-06T15:00:00+00:00",
                "metadata": decoded["extra"]["metadata"],
            }
        ).encode()
        return response

    monkeypatch.setattr(Client, "request_with_retries", transport)
    monkeypatch.setattr(Client, "_get_optional_tenant_id", lambda _: tenant_id)
    monkeypatch.setattr(
        "langsmith.client.ls_env.get_runtime_environment",
        lambda: {"environment": PRIVATE, "sdk_version": PRIVATE},
    )
    client = create_reviewed_trace_client(_settings(), manifest)
    try:
        client.create_dataset(
            manifest.dataset_name,
            metadata={"content_digest": manifest.content_digest, "runtime": {}},
        )
    finally:
        client.close()
    assert len(sent) == 1
    extra = sent[0]["extra"]
    assert isinstance(extra, dict)
    assert extra["metadata"] == {"content_digest": manifest.content_digest, "runtime": {}}
    assert PRIVATE not in json.dumps(sent)
