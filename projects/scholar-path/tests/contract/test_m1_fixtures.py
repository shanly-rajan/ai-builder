"""Contract tests for the deterministic M1 fixture topology."""

from collections.abc import Callable
from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceConfidence,
    SourceKind,
    SupervisorLifecycleStatus,
)
from tests.fixtures import (
    FIXED_RETRIEVED_AT,
    make_candidate_profile,
    make_evidence_claims,
    make_prospective_supervisor,
    make_prospective_supervisors,
    make_research_fit_assessment,
    make_research_fit_assessments,
    make_verified_supervisor,
    make_verified_supervisors,
)


def test_fixture_topology_has_exact_m1_cardinalities() -> None:
    candidate = make_candidate_profile()
    prospective = make_prospective_supervisors()
    verified = make_verified_supervisors()
    assessments = make_research_fit_assessments()

    assert candidate.candidate_id == "candidate-001"
    assert len(prospective) == 8
    assert len(verified) == 6
    assert len(assessments) == 5
    assert len({item.supervisor_id for item in prospective}) == 8
    assert len({item.supervisor_id for item in verified}) == 6
    assert len({item.supervisor_id for item in assessments}) == 5


def test_fixture_relationships_preserve_referential_integrity() -> None:
    prospective_ids = {item.supervisor_id for item in make_prospective_supervisors()}
    verified = make_verified_supervisors()
    verified_ids = {item.supervisor_id for item in verified}
    assessments = make_research_fit_assessments()

    assert verified_ids < prospective_ids
    assert {item.supervisor_id for item in assessments} < verified_ids
    for supervisor in verified:
        assert supervisor.status is SupervisorLifecycleStatus.VERIFIED
        assert all(claim.supervisor_id == supervisor.supervisor_id for claim in supervisor.evidence)
        assert len({claim.evidence_id for claim in supervisor.evidence}) == len(supervisor.evidence)
    for assessment in assessments:
        supervisor = next(
            item for item in verified if item.supervisor_id == assessment.supervisor_id
        )
        supervisor_evidence_ids = {claim.evidence_id for claim in supervisor.evidence}
        assert set(assessment.supporting_evidence_ids) <= supervisor_evidence_ids


def test_fixture_sources_are_reserved_and_timestamps_are_fixed() -> None:
    prospective = make_prospective_supervisors()
    verified = make_verified_supervisors()

    urls = [str(item.profile_url) for item in prospective]
    for supervisor in verified:
        for claim in supervisor.evidence:
            urls.append(str(claim.source_url))
            assert claim.retrieved_at == FIXED_RETRIEVED_AT
            assert claim.retrieved_at.tzinfo is not None
    assert all((urlparse(url).hostname or "").endswith("scholarpath.example") for url in urls)


def test_fixture_availability_covers_explicit_and_unknown_states() -> None:
    statuses = {item.availability_status for item in make_verified_supervisors()}

    assert statuses == set(AvailabilityStatus)
    assert make_verified_supervisor(1).availability_status is AvailabilityStatus.NOT_STATED


def test_fixture_evidence_varies_provenance_and_confidence() -> None:
    claims = tuple(
        claim for supervisor in make_verified_supervisors() for claim in supervisor.evidence
    )

    assert {claim.source_kind for claim in claims} >= {
        SourceKind.UNIVERSITY_PROFILE,
        SourceKind.INSTITUTIONAL_DIRECTORY,
        SourceKind.DEPARTMENT_PAGE,
        SourceKind.PUBLICATION,
        SourceKind.RESEARCH_REPOSITORY,
        SourceKind.PERSONAL_ACADEMIC_PAGE,
    }
    assert {claim.confidence for claim in claims} == set(EvidenceConfidence)
    assert any(not claim.directly_supported for claim in claims)


def test_fixture_fit_examples_are_distinct_without_defining_a_scoring_formula() -> None:
    assessments = make_research_fit_assessments()

    assert [assessment.overall_score for assessment in assessments] == [87, 82, 72, 75, 68]
    assert len({assessment.rationale for assessment in assessments}) == 5


def test_fixture_overrides_are_revalidated() -> None:
    with pytest.raises(ValidationError, match="profile_url"):
        make_prospective_supervisor(1, profile_url="not-a-url")
    with pytest.raises(ValidationError, match="reference this Supervisor"):
        make_verified_supervisor(1, supervisor_id="supervisor-999")
    with pytest.raises(ValidationError, match="overall_score"):
        make_research_fit_assessment(1, overall_score=101)


@pytest.mark.parametrize(
    ("factory", "bad_index"),
    [
        (make_prospective_supervisor, 0),
        (make_prospective_supervisor, 9),
        (make_evidence_claims, 0),
        (make_evidence_claims, 7),
        (make_verified_supervisor, 0),
        (make_verified_supervisor, 7),
        (make_research_fit_assessment, 0),
        (make_research_fit_assessment, 6),
    ],
)
def test_fixture_factories_reject_out_of_range_indices(
    factory: Callable[[int], object], bad_index: int
) -> None:
    with pytest.raises(ValueError, match="between"):
        factory(bad_index)
