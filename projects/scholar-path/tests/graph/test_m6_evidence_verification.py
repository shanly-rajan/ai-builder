"""Graph scenarios for grounded M6 Supervisor evidence verification."""

from typing import cast

from scholarpath.agents import StructuredEvidenceClaimDraft, StructuredEvidenceExtractionResult
from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    EvidenceConfidence,
    SearchResult,
    SourceKind,
    VerificationStatus,
)
from scholarpath.graph import (
    CandidateApproveResponse,
    ReviewStatus,
    ScholarPathState,
    alternate_official_source_query,
    build_walking_skeleton_fixtures,
    default_review_decision,
    run_scholarpath_graph,
)
from scholarpath.tools import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionProvider,
    ExtractedContent,
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
)
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_fixed_content_outcomes,
    make_fixed_evidence_outcomes,
    make_graph_content_outcomes,
    make_graph_evidence_outcomes,
)
from tests.fixtures import (
    ALTERNATE_OFFICIAL_PROFILE_URL,
    CONFLICTING_AFFILIATION_URL,
)


def _failure(source_url: str) -> ContentExtractionError:
    return ContentExtractionError(
        "Synthetic page extraction failure.",
        provider=ContentExtractionProvider.TAVILY,
        category=ContentExtractionErrorCategory.EXTRACTION_FAILED,
        retryable=True,
        source_url=source_url,
    )


def _alternate_result(
    *,
    url: str,
    title: str,
    query: str,
    description: str = "Official institutional profile.",
) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": url,
            "title": title,
            "description": description,
            "originating_query": query,
        }
    )


def _run(
    *,
    content_extractor: FakeContentExtraction | None = None,
    evidence_model: FakeEvidenceVerificationModel | None = None,
    alternate_search: FakeSupervisorSearch | None = None,
) -> ScholarPathState:
    approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )
    return cast(
        ScholarPathState,
        run_scholarpath_graph(
            thread_id="legacy-m6-evidence",
            candidate_review_responses=(approval,),
            planning_model=FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=FakeSupervisorSearch(),
            tavily_search=FakeSupervisorSearch(),
            content_extractor=content_extractor or FakeContentExtraction(),
            evidence_model=evidence_model or FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            alternate_evidence_search=alternate_search or FakeSupervisorSearch(),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        ),
    )


def test_complete_official_profiles_produce_provenance_backed_verified_records() -> None:
    final_state = _run()

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["verification_records"]) == 8
    assert len(final_state["verified_supervisors"]) == 8
    assert final_state["retry_counts"]["evidence"] == 0
    assert all(
        record.verification_status is VerificationStatus.VERIFIED
        for record in final_state["verification_records"]
    )
    for supervisor in final_state["verified_supervisors"]:
        evidence_ids = {claim.evidence_id for claim in supervisor.evidence}
        source_urls = {str(claim.source_url) for claim in supervisor.evidence}
        assert len(evidence_ids) == len(supervisor.evidence)
        assert evidence_ids
        assert source_urls == {str(supervisor.profile_url)}
        assert all(claim.supporting_excerpt for claim in supervisor.evidence)
        assert supervisor.availability_status is AvailabilityStatus.NOT_STATED


def test_one_invalid_draft_does_not_discard_valid_page_evidence_in_the_graph() -> None:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    evidence_outcomes = {**make_fixed_evidence_outcomes(), **make_graph_evidence_outcomes()}
    complete = evidence_outcomes[primary_url]
    evidence_outcomes[primary_url] = StructuredEvidenceExtractionResult(
        claims=[
            *complete.claims,
            StructuredEvidenceClaimDraft(
                claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                claim="The model proposed a sentence absent from the source page.",
                supporting_excerpt="This exact sentence is absent from the source page.",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=supervisor.full_name,
            ),
        ]
    )

    final_state = _run(evidence_model=FakeEvidenceVerificationModel(evidence_outcomes))

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["verified_supervisors"]) == 8
    record = next(
        item
        for item in final_state["verification_records"]
        if item.prospective_supervisor.supervisor_id == supervisor.supervisor_id
    )
    assert record.verification_status is VerificationStatus.VERIFIED
    assert len(record.evidence) == len(complete.claims)
    assert all("absent from the source page" not in claim.claim for claim in record.evidence)
    assert all(
        error.code != "evidence_model_output_invalid" for error in final_state["tool_errors"]
    )


def test_failed_profile_uses_one_alternate_official_source_and_retries_once() -> None:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    alternate_url = "https://faculty.southerncape.edu.au/people/amara-ndlovu"
    fixed_content_outcomes = make_fixed_content_outcomes()
    alternate_content = fixed_content_outcomes[ALTERNATE_OFFICIAL_PROFILE_URL]
    content_outcomes: dict[str, ExtractedContent | Exception] = {
        **fixed_content_outcomes,
        **make_graph_content_outcomes(),
    }
    content_outcomes[primary_url] = _failure(primary_url)
    content_outcomes[alternate_url] = ExtractedContent.model_validate(
        {
            "source_url": alternate_url,
            "content": alternate_content.content,
            "retrieved_at": alternate_content.retrieved_at,
            "content_truncated": alternate_content.content_truncated,
        }
    )
    extractor = FakeContentExtraction(content_outcomes)
    evidence_outcomes = {**make_fixed_evidence_outcomes(), **make_graph_evidence_outcomes()}
    evidence_outcomes[alternate_url] = evidence_outcomes[ALTERNATE_OFFICIAL_PROFILE_URL]
    evidence_model = FakeEvidenceVerificationModel(evidence_outcomes)
    query = alternate_official_source_query(supervisor)
    snippet = "SEARCH-SNIPPET-ONLY says accepting; it must never become evidence."
    alternate_search = FakeSupervisorSearch(
        {
            query: (
                _alternate_result(
                    url=alternate_url,
                    title=("Dr Amara Ndlovu | Southern Cape Institute of Technology faculty"),
                    query=query,
                    description=snippet,
                ),
            )
        }
    )

    final_state = _run(
        content_extractor=extractor,
        evidence_model=evidence_model,
        alternate_search=alternate_search,
    )

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert final_state["retry_counts"]["evidence"] == 1
    assert alternate_search.calls == [query]
    assert extractor.calls.count(primary_url) == 1
    assert extractor.calls.count(alternate_url) == 1
    record = next(
        item
        for item in final_state["verification_records"]
        if item.prospective_supervisor.supervisor_id == supervisor.supervisor_id
    )
    assert record.verification_status is VerificationStatus.VERIFIED
    assert {str(claim.source_url) for claim in record.evidence} == {alternate_url}
    assert all(snippet not in claim.claim for claim in record.evidence)
    attempts = [
        attempt
        for attempt in final_state["evidence_extraction_attempts"]
        if attempt.supervisor_id == supervisor.supervisor_id
    ]
    assert [(attempt.attempt_number, attempt.alternate_source) for attempt in attempts] == [
        (1, False),
        (2, True),
    ]


def test_failed_profile_accepts_one_person_page_on_an_abbreviated_academic_host() -> None:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    alternate_url = "https://www.scit.ac.za/people/amara-ndlovu"
    fixed_content_outcomes = make_fixed_content_outcomes()
    alternate_content = fixed_content_outcomes[ALTERNATE_OFFICIAL_PROFILE_URL]
    content_outcomes: dict[str, ExtractedContent | Exception] = {
        **fixed_content_outcomes,
        **make_graph_content_outcomes(),
        primary_url: _failure(primary_url),
        alternate_url: ExtractedContent.model_validate(
            {
                "source_url": alternate_url,
                "content": alternate_content.content,
                "retrieved_at": alternate_content.retrieved_at,
                "content_truncated": alternate_content.content_truncated,
            }
        ),
    }
    evidence_outcomes = {**make_fixed_evidence_outcomes(), **make_graph_evidence_outcomes()}
    evidence_outcomes[alternate_url] = evidence_outcomes[ALTERNATE_OFFICIAL_PROFILE_URL]
    query = alternate_official_source_query(supervisor)
    alternate_search = FakeSupervisorSearch(
        {
            query: (
                _alternate_result(
                    url=alternate_url,
                    title=("Dr Amara Ndlovu | Southern Cape Institute of Technology"),
                    query=query,
                ),
            )
        }
    )

    final_state = _run(
        content_extractor=FakeContentExtraction(content_outcomes),
        evidence_model=FakeEvidenceVerificationModel(evidence_outcomes),
        alternate_search=alternate_search,
    )

    assert alternate_search.calls == [query]
    assert final_state["retry_counts"]["evidence"] == 1
    record = next(
        item
        for item in final_state["verification_records"]
        if item.prospective_supervisor.supervisor_id == supervisor.supervisor_id
    )
    assert record.verification_status is VerificationStatus.VERIFIED
    assert {str(claim.source_url) for claim in record.evidence} == {alternate_url}
    alternate_attempt = next(
        attempt
        for attempt in final_state["evidence_extraction_attempts"]
        if attempt.supervisor_id == supervisor.supervisor_id and attempt.alternate_source
    )
    assert alternate_attempt.source_kind is SourceKind.UNIVERSITY_PROFILE


def test_same_surname_wrong_person_is_not_used_as_an_alternate_source() -> None:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    wrong_person_url = "https://www.southerncape.ac.za/staff/nomsa-ndlovu"
    content_outcomes: dict[str, ExtractedContent | Exception] = {
        **make_graph_content_outcomes(),
        primary_url: _failure(primary_url),
    }
    extractor = FakeContentExtraction(content_outcomes)
    query = alternate_official_source_query(supervisor)
    alternate_search = FakeSupervisorSearch(
        {
            query: (
                _alternate_result(
                    url=wrong_person_url,
                    title="Dr Nomsa Ndlovu | Southern Cape Institute of Technology",
                    query=query,
                ),
            )
        }
    )

    final_state = _run(content_extractor=extractor, alternate_search=alternate_search)

    assert wrong_person_url not in extractor.calls
    record = next(
        item
        for item in final_state["verification_records"]
        if item.prospective_supervisor.supervisor_id == supervisor.supervisor_id
    )
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert any(
        error.code == "alternate_official_source_not_found" for error in final_state["tool_errors"]
    )


def test_returned_primary_url_is_used_for_conservative_source_provenance() -> None:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    returned_url = "https://www.southerncape.edu/academics/amara-ndlovu"
    content_outcomes = make_graph_content_outcomes()
    original_content = content_outcomes[primary_url]
    content_outcomes[primary_url] = ExtractedContent.model_validate(
        {
            "source_url": returned_url,
            "content": original_content.content,
            "retrieved_at": original_content.retrieved_at,
            "content_truncated": original_content.content_truncated,
        }
    )
    evidence_outcomes = make_graph_evidence_outcomes()
    evidence_outcomes[returned_url] = evidence_outcomes[primary_url]

    final_state = _run(
        content_extractor=FakeContentExtraction(content_outcomes),
        evidence_model=FakeEvidenceVerificationModel(evidence_outcomes),
    )

    attempt = next(
        item
        for item in final_state["evidence_extraction_attempts"]
        if item.supervisor_id == supervisor.supervisor_id
    )
    assert str(attempt.source_url) == returned_url
    assert attempt.source_kind is SourceKind.OTHER
    verified = next(
        item
        for item in final_state["verified_supervisors"]
        if item.supervisor_id == supervisor.supervisor_id
    )
    assert {str(claim.source_url) for claim in verified.evidence} == {returned_url}
    assert {claim.source_kind for claim in verified.evidence} == {SourceKind.OTHER}


def test_retry_exhaustion_retains_five_successes_and_partial_records() -> None:
    fixtures = build_walking_skeleton_fixtures()
    prospective = tuple(raw.to_prospective_supervisor() for raw in fixtures.raw_search_results)
    content_outcomes: dict[str, ExtractedContent | Exception] = {**make_graph_content_outcomes()}
    failed = prospective[5:]
    for supervisor in failed:
        content_outcomes[str(supervisor.profile_url)] = _failure(str(supervisor.profile_url))
    extractor = FakeContentExtraction(content_outcomes)
    empty_alternates = FakeSupervisorSearch(
        {alternate_official_source_query(supervisor): () for supervisor in failed}
    )

    final_state = _run(
        content_extractor=extractor,
        alternate_search=empty_alternates,
    )

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["verified_supervisors"]) == 5
    assert final_state["retry_counts"]["evidence"] == 1
    assert len(empty_alternates.calls) == 3
    partial = [
        record
        for record in final_state["verification_records"]
        if record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    ]
    assert len(partial) == 3
    assert all(record.evidence == () for record in partial)
    assert all(record.verified_supervisor is None for record in partial)
    assert all(
        record.missing_required_evidence
        == ("identity", "current_affiliation", "research_interest_or_publication")
        for record in partial
    )
    assert "evaluate_research_fit" in final_state["execution_log"]


def test_non_retryable_alternate_search_error_stops_further_search_calls() -> None:
    fixtures = build_walking_skeleton_fixtures()
    prospective = tuple(raw.to_prospective_supervisor() for raw in fixtures.raw_search_results)
    content_outcomes: dict[str, ExtractedContent | Exception] = {**make_graph_content_outcomes()}
    failed = prospective[5:]
    for supervisor in failed:
        content_outcomes[str(supervisor.profile_url)] = _failure(str(supervisor.profile_url))
    first_query = alternate_official_source_query(failed[0])
    alternate_search = FakeSupervisorSearch(
        {
            first_query: SearchProviderError(
                "Synthetic authentication failure.",
                provider=SearchProvider.TAVILY,
                category=SearchErrorCategory.AUTHENTICATION,
                retryable=False,
            )
        }
    )

    final_state = _run(
        content_extractor=FakeContentExtraction(content_outcomes),
        alternate_search=alternate_search,
    )

    assert alternate_search.calls == [first_query]
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["verified_supervisors"]) == 5
    assert final_state["retry_counts"]["evidence"] == 1
    assert any(error.code == "tavily_search_authentication" for error in final_state["tool_errors"])


def test_below_minimum_after_retry_exhaustion_stops_with_recoverable_status() -> None:
    fixtures = build_walking_skeleton_fixtures()
    prospective = tuple(raw.to_prospective_supervisor() for raw in fixtures.raw_search_results)
    content_outcomes: dict[str, ExtractedContent | Exception] = {**make_graph_content_outcomes()}
    failed = prospective[4:]
    for supervisor in failed:
        content_outcomes[str(supervisor.profile_url)] = _failure(str(supervisor.profile_url))
    empty_alternates = FakeSupervisorSearch(
        {alternate_official_source_query(supervisor): () for supervisor in failed}
    )

    final_state = _run(
        content_extractor=FakeContentExtraction(content_outcomes),
        alternate_search=empty_alternates,
    )

    assert final_state["review_status"] is ReviewStatus.EVIDENCE_INCOMPLETE
    assert len(final_state["verified_supervisors"]) == 4
    assert len(final_state["verification_records"]) == 8
    assert final_state["retry_counts"]["evidence"] == 1
    assert final_state["tool_errors"][-1].code == "supervisor_evidence_incomplete"
    assert final_state["tool_errors"][-1].recoverable is True
    assert final_state["execution_log"][-1] == "supervisor_evidence_sufficient"
    assert "evaluate_research_fit" not in final_state["execution_log"]


def test_conflicting_affiliations_are_retained_cross_referenced_and_surfaced() -> None:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    conflicting_url = "https://directory.southerncape.ac.za/staff/amara-ndlovu"
    evidence_outcomes = {**make_fixed_evidence_outcomes(), **make_graph_evidence_outcomes()}
    primary_response = evidence_outcomes[primary_url]
    primary_claims = [
        claim
        for claim in primary_response.claims
        if claim.claim_type in {EvidenceClaimType.IDENTITY, EvidenceClaimType.CURRENT_AFFILIATION}
    ]
    evidence_outcomes[primary_url] = StructuredEvidenceExtractionResult(claims=primary_claims)
    evidence_outcomes[conflicting_url] = evidence_outcomes[CONFLICTING_AFFILIATION_URL]
    evidence_model = FakeEvidenceVerificationModel(evidence_outcomes)
    fixed_content_outcomes = make_fixed_content_outcomes()
    conflicting_content = fixed_content_outcomes[CONFLICTING_AFFILIATION_URL]
    content_outcomes: dict[str, ExtractedContent | Exception] = {
        **fixed_content_outcomes,
        **make_graph_content_outcomes(),
        conflicting_url: ExtractedContent.model_validate(
            {
                "source_url": conflicting_url,
                "content": conflicting_content.content,
                "retrieved_at": conflicting_content.retrieved_at,
                "content_truncated": conflicting_content.content_truncated,
            }
        ),
    }
    query = alternate_official_source_query(supervisor)
    alternate_search = FakeSupervisorSearch(
        {
            query: (
                _alternate_result(
                    url=conflicting_url,
                    title=(
                        "Dr Amara Ndlovu | Southern Cape Institute of Technology | "
                        "official directory"
                    ),
                    query=query,
                ),
            )
        }
    )

    final_state = _run(
        content_extractor=FakeContentExtraction(content_outcomes),
        evidence_model=evidence_model,
        alternate_search=alternate_search,
    )

    record = next(
        item
        for item in final_state["verification_records"]
        if item.prospective_supervisor.supervisor_id == supervisor.supervisor_id
    )
    assert record.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
    assert any("conflict" in concern.casefold() for concern in record.verification_concerns)
    affiliation_claims = [
        claim
        for claim in record.evidence
        if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
    ]
    assert {claim.asserted_institution for claim in affiliation_claims} == {
        "Southern Cape Institute of Technology",
        "Northbridge University",
    }
    assert all(claim.conflicting_evidence_ids for claim in affiliation_claims)
    assert {str(claim.source_url) for claim in affiliation_claims} == {
        primary_url,
        conflicting_url,
    }


def test_research_fit_assessments_reference_current_verified_evidence() -> None:
    final_state = _run()

    assert len(final_state["research_fit_assessments"]) == len(final_state["verified_supervisors"])
    supervisors = {
        supervisor.supervisor_id: supervisor for supervisor in final_state["verified_supervisors"]
    }
    for assessment in final_state["research_fit_assessments"]:
        evidence_ids = {
            claim.evidence_id for claim in supervisors[assessment.supervisor_id].evidence
        }
        assert set(assessment.supporting_evidence_ids) <= evidence_ids
        assert assessment.overall_score == sum(
            (
                assessment.breakdown.topic_alignment.score,
                assessment.breakdown.methodological_alignment.score,
                assessment.breakdown.research_orientation_alignment.score,
                assessment.breakdown.recent_research_alignment.score,
                assessment.breakdown.practical_constraint_alignment.score,
            )
        )
        assert assessment.confidence in {
            EvidenceConfidence.HIGH,
            EvidenceConfidence.MEDIUM,
        }
