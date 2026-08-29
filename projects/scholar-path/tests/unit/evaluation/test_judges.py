"""Unit tests for scoped, injected, privacy-safe qualitative evaluators."""

import json
from typing import Any

import pytest
from pydantic import HttpUrl, ValidationError

from scholarpath.domain import AvailabilityStatus, EvidenceConfidence
from scholarpath.evaluation.judges import (
    JUDGE_PROMPT_VERSION,
    JUDGE_SYSTEM_PROMPT_V1,
    EvaluationJudgeInvocationError,
    JudgeCriterion,
    JudgeInput,
    StructuredJudgeResult,
    evidence_grounded_rationale_judge,
    explanation_usefulness_judge,
    make_judge_evaluators,
    research_fit_relevance_judge,
    shortlist_usefulness_judge,
)
from scholarpath.evaluation.models import (
    CandidatePreferenceProjection,
    EvaluationTargetKind,
    GraphTargetOutput,
    ResearchFitAssessmentProjection,
    ResearchFitTargetOutput,
    SearchPlanningTargetOutput,
    ShortlistRecommendationProjection,
)
from scholarpath.graph import ReviewStatus
from tests.fixtures import (
    make_research_fit_assessment,
    make_search_plan,
    make_verified_supervisor,
)


class RecordingJudge:
    """Typed fake that proves exactly what reaches the judge boundary."""

    def __init__(self, result: StructuredJudgeResult | None = None) -> None:
        self.result = result or StructuredJudgeResult(
            score=4,
            rationale="The bounded artifact directly supports a useful explanation.",
        )
        self.inputs: list[JudgeInput] = []

    def judge(self, judge_input: JudgeInput) -> StructuredJudgeResult:
        self.inputs.append(judge_input)
        return self.result


class FailingJudge:
    """Provider fake used to assert graceful judge unavailability."""

    def judge(self, judge_input: JudgeInput) -> StructuredJudgeResult:
        del judge_input
        raise EvaluationJudgeInvocationError("secret provider detail must be sanitized")


def _preferences() -> CandidatePreferenceProjection:
    return CandidatePreferenceProjection(
        research_topics=("enterprise architecture", "responsible AI governance"),
        preferred_regions=("South Africa",),
        preferred_study_modes=("part-time",),
        preferred_research_orientation="applied",
        methodological_interests=("design science",),
        exclusions=("fully residential programmes",),
    )


def _fit_output() -> dict[str, object]:
    supervisor = make_verified_supervisor(1)
    from scholarpath.evaluation.models import EvidenceReferenceProjection

    evidence = tuple(
        EvidenceReferenceProjection(
            evidence_id=claim.evidence_id,
            supervisor_id=claim.supervisor_id,
            claim_type=claim.claim_type,
            claim_summary=claim.claim,
            source_url=claim.source_url,
            directly_supported=claim.directly_supported,
            confidence=claim.confidence,
            availability_status=claim.availability_status,
        )
        for claim in supervisor.evidence
    )
    return ResearchFitTargetOutput(
        target=EvaluationTargetKind.RESEARCH_FIT,
        scenario_id="judge-fit-fixed-example",
        candidate_preferences=_preferences(),
        assessments=(
            ResearchFitAssessmentProjection(
                assessment=make_research_fit_assessment(1),
                evidence=evidence,
            ),
        ),
    ).model_dump(mode="json")


def _shortlist_output() -> dict[str, object]:
    recommendation = ShortlistRecommendationProjection(
        rank=1,
        supervisor_id="supervisor-001",
        institution="Southern Cape Institute of Technology",
        effective_score=87,
        evidence_confidence=EvidenceConfidence.HIGH,
        availability_status=AvailabilityStatus.NOT_STATED,
        strengths=("Direct evidence supports applied enterprise-architecture alignment.",),
        concerns=("Study-mode evidence is missing.",),
        source_urls=(HttpUrl("https://evidence.scholarpath.example/supervisor-001/research"),),
    )
    return GraphTargetOutput(
        target=EvaluationTargetKind.GRAPH_FAKE,
        scenario_id="judge-shortlist-fixed-example",
        candidate_preferences=_preferences(),
        review_status=ReviewStatus.PROPOSED,
        interrupted=True,
        execution_log=("candidate_review_gate",),
        fallback_search_used=False,
        search_attempts=(),
        raw_search_result_count=1,
        plausible_profile_count=1,
        prospective_supervisor_ids=("supervisor-001",),
        supervisor_provenance=(),
        verification_records=(),
        assessments=(),
        independent_reviews=(),
        proposed_supervisor_ids=("supervisor-001",),
        shortlist_recommendations=(recommendation,),
        shortlisted_supervisor_ids=(),
        rejected_supervisor_ids=(),
        candidate_reviews=(),
        tool_error_codes=(),
    ).model_dump(mode="json")


@pytest.mark.parametrize("score", (-1, 5, 2.5, "4"))
def test_structured_judge_result_rejects_out_of_range_or_non_integer_scores(
    score: Any,
) -> None:
    with pytest.raises(ValidationError):
        StructuredJudgeResult.model_validate({"score": score, "rationale": "Bounded."})


def test_judge_schemas_are_strict_concise_immutable_and_versioned() -> None:
    with pytest.raises(ValidationError, match="extra"):
        StructuredJudgeResult.model_validate(
            {"score": 4, "rationale": "Useful.", "hidden_reasoning": "never"}
        )
    with pytest.raises(ValidationError, match="80 words"):
        StructuredJudgeResult(score=4, rationale="word " * 81)

    result = StructuredJudgeResult(score=3, rationale="Useful and evidence-grounded.")
    with pytest.raises(ValidationError, match="frozen"):
        result.score = 2

    judge_input = JudgeInput(
        criterion=JudgeCriterion.RESEARCH_FIT_RELEVANCE,
        candidate_preferences=_preferences(),
        artifact={"assessment": {"overall_score": 87}},
    )
    assert judge_input.rubric_version == JUDGE_PROMPT_VERSION
    with pytest.raises(ValidationError, match="extra"):
        JudgeInput.model_validate(
            {**judge_input.model_dump(mode="python"), "candidate_email": "hidden@example.test"}
        )


def test_judge_prompt_is_narrowly_scoped_away_from_deterministic_facts() -> None:
    prompt = JUDGE_SYSTEM_PROMPT_V1.casefold()

    for boundary in (
        "do not browse",
        "call tools",
        "infer\nsupervisor availability",
        "estimate admission probability",
        "recalculate scores",
        "validate\nurls",
        "audit graph routing",
    ):
        assert boundary in prompt


@pytest.mark.parametrize(
    ("factory", "criterion"),
    (
        (research_fit_relevance_judge, JudgeCriterion.RESEARCH_FIT_RELEVANCE),
        (explanation_usefulness_judge, JudgeCriterion.EXPLANATION_USEFULNESS),
        (evidence_grounded_rationale_judge, JudgeCriterion.EVIDENCE_GROUNDED_RATIONALE),
    ),
)
def test_fit_judges_use_the_injected_fake_and_normalize_the_four_point_scale(
    factory: Any,
    criterion: JudgeCriterion,
) -> None:
    judge = RecordingJudge()
    evaluator = factory(judge)

    result = evaluator(
        {"candidate_preferences": _preferences().model_dump(mode="json")},
        _fit_output(),
    )

    assert result.key == f"llm_{criterion.value}"
    assert result.score == 1.0
    assert result.value == 4
    assert result.metadata == {
        "criterion": criterion.value,
        "rubric_version": JUDGE_PROMPT_VERSION,
        "scale_maximum": 4,
    }
    assert len(judge.inputs) == 1
    assert judge.inputs[0].criterion is criterion


def test_shortlist_usefulness_judge_receives_only_bounded_recommendations() -> None:
    judge = RecordingJudge(StructuredJudgeResult(score=3, rationale="Useful with one gap."))

    result = shortlist_usefulness_judge(judge)({}, _shortlist_output())

    assert result.score == pytest.approx(0.75)
    assert result.value == 3
    assert set(judge.inputs[0].artifact) == {"recommendations"}
    serialized = json.dumps(judge.inputs[0].model_dump(mode="json")).casefold()
    assert "study-mode evidence is missing" in serialized
    assert "candidate_review" not in serialized
    assert "execution_log" not in serialized


def test_explanation_judge_accepts_a_bounded_search_plan_artifact() -> None:
    judge = RecordingJudge()
    output = SearchPlanningTargetOutput(
        target=EvaluationTargetKind.SEARCH_PLANNING,
        scenario_id="planning-explanation-fixed-example",
        search_plan=make_search_plan(),
    ).model_dump(mode="json")

    result = explanation_usefulness_judge(judge)(
        {"candidate_preferences": _preferences().model_dump(mode="json")},
        output,
    )

    assert result.score == 1.0
    assert set(judge.inputs[0].artifact) == {"search_plan"}


def test_judge_projection_ignores_identity_secrets_and_full_content() -> None:
    judge = RecordingJudge()
    sentinels: dict[str, object] = {
        "candidate_id": "candidate-sensitive-123",
        "candidate_name": "Sensitive Person",
        "candidate_email": "sensitive@example.test",
        "proposed_research_statement": "complete sensitive statement",
        "api_key": "sk-secret-sentinel",
        "full_page_content": "complete extracted source sentinel",
        "thread_id": "thread-sensitive-123",
    }

    result = research_fit_relevance_judge(judge)(sentinels, _fit_output())

    assert result.score == 1.0
    serialized = json.dumps(judge.inputs[0].model_dump(mode="json")).casefold()
    for value in sentinels.values():
        assert isinstance(value, str)
        assert value.casefold() not in serialized
    for key in sentinels:
        assert key not in serialized


def test_injected_fake_does_not_construct_or_call_a_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Default tests must not construct a live judge model")

    monkeypatch.setattr("scholarpath.evaluation.judges.ChatOpenAI", fail_if_constructed)
    judge = RecordingJudge()

    evaluators = make_judge_evaluators(judge)

    assert len(evaluators) == 4
    assert judge.inputs == []


def test_not_applicable_artifact_does_not_call_fake_judge() -> None:
    judge = RecordingJudge()
    output = SearchPlanningTargetOutput(
        target=EvaluationTargetKind.SEARCH_PLANNING,
        scenario_id="planning-not-fit",
        search_plan=make_search_plan(),
    ).model_dump(mode="json")

    result = research_fit_relevance_judge(judge)(
        {"candidate_preferences": _preferences().model_dump(mode="json")}, output
    )

    assert result.score is None
    assert result.value == "not_applicable"
    assert judge.inputs == []


def test_judge_failure_is_sanitized_and_does_not_crash() -> None:
    result = research_fit_relevance_judge(FailingJudge())({}, _fit_output())

    assert result.score is None
    assert result.value == "judge_unavailable"
    assert result.comment == "The qualitative evaluation judge was unavailable."
    assert "secret provider detail" not in str(result)


def test_judge_evaluator_registry_has_exactly_the_four_scoped_criteria() -> None:
    judge = RecordingJudge()
    evaluators = make_judge_evaluators(judge)

    assert tuple(item._criterion for item in evaluators) == tuple(JudgeCriterion)  # noqa: SLF001
