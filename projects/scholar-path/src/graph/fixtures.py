"""Deterministic, synthetic data used only by the M2 walking skeleton."""

from dataclasses import dataclass
from datetime import UTC, datetime

from ..agents import deterministic_supervisor_id
from ..domain import (
    AvailabilityStatus,
    CandidatePreferenceRevision,
    CandidateProfile,
    CandidateReviewAction,
    CandidateReviewDecision,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitComponentAssessment,
    SourceKind,
    SupervisorDiscoveryProvenance,
    VerifiedSupervisor,
    validate_research_fit_evidence,
    verify_supervisor,
)
from .state import RawSupervisorSearchResult

FIXTURE_RETRIEVED_AT = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)

_SUPERVISOR_NAMES = (
    "Dr Amara Ndlovu",
    "Professor Elias Hart",
    "Dr Noor van Dijk",
    "Professor Sofia Mensah",
    "Dr Theo Laurent",
    "Professor Lina Okafor",
    "Dr Ravi Solberg",
    "Professor Maya Chen",
)
_INSTITUTIONS = (
    "Southern Cape Institute of Technology",
    "Northbridge University",
    "Delta Lowlands University",
    "Meridian School of Management",
    "Westhaven Technical University",
    "Ubuntu Institute for Digital Society",
    "Fjordland University",
    "Pacific Arc University",
)
_DEPARTMENTS = (
    "Department of Information Systems",
    "School of Computing and Strategy",
    "Department of Digital Governance",
    "School of Organisational Studies",
    "Department of Enterprise Systems",
    "Centre for Responsible Technology",
    "Department of Management Science",
    "School of Digital Innovation",
)
_DISCOVERY_QUERIES = (
    "enterprise architecture responsible AI South Africa",
    "digital transformation organisational resilience United Kingdom",
    "AI governance design science Netherlands",
    "enterprise strategy mixed methods South Africa",
    "sociotechnical systems digital transformation Europe",
    "responsible AI governance organisational change Africa",
    "enterprise architecture comparative case study Europe",
    "digital innovation resilience doctoral supervision",
)
_RESEARCH_CLAIMS = (
    "The profile lists enterprise architecture and responsible AI governance.",
    "The profile lists digital transformation and organisational resilience.",
    "The profile lists algorithmic governance and public-sector AI assurance.",
    "The profile lists enterprise strategy and organisational adaptation.",
    "The profile lists sociotechnical systems and digital operating models.",
    "The profile lists responsible technology and organisational change.",
)
_METHODOLOGY_CLAIMS = (
    "The methods statement describes design science and comparative case studies.",
    "The methods statement describes longitudinal organisational case studies.",
    "The methods statement describes policy analysis and design science.",
    "The methods statement describes mixed-method organisational research.",
    "The methods statement describes sociotechnical field studies.",
    "The methods statement describes participatory action research.",
)
_PUBLICATION_CLAIMS = (
    "A recent publication examines architecture controls for responsible AI adoption.",
    "A recent publication examines resilience during enterprise transformation.",
    "A recent publication examines assurance practices for public-sector AI.",
    "A recent publication examines strategic adaptation in complex organisations.",
    "A recent publication examines sociotechnical digital operating models.",
    "A recent publication examines responsible technology during organisational change.",
)
_FIT_DATA = (
    (87, (38, 19, 15, 15, 0), EvidenceConfidence.HIGH),
    (82, (36, 18, 14, 14, 0), EvidenceConfidence.HIGH),
    (72, (31, 16, 12, 13, 0), EvidenceConfidence.MEDIUM),
    (75, (33, 16, 13, 13, 0), EvidenceConfidence.MEDIUM),
    (68, (30, 14, 12, 12, 0), EvidenceConfidence.MEDIUM),
    (64, (28, 13, 11, 12, 0), EvidenceConfidence.MEDIUM),
)
_FIT_RATIONALES = (
    (
        "Enterprise architecture, responsible AI, and design-science evidence closely "
        "match the applied research direction."
    ),
    (
        "Digital transformation, resilience, and longitudinal case-study evidence "
        "provide strong thematic and methodological fit."
    ),
    (
        "AI assurance and design-science evidence align, while direct practical-constraint "
        "evidence is missing."
    ),
    (
        "Enterprise strategy and mixed-method evidence align, while direct "
        "practical-constraint evidence is missing."
    ),
    (
        "Sociotechnical systems evidence is relevant, though the direct alignment is "
        "more moderate and practical-constraint evidence is missing."
    ),
    (
        "Responsible technology and participatory research evidence provide a useful "
        "alternate fit, while practical-constraint evidence is missing."
    ),
)
_FIT_CONCERNS: tuple[tuple[str, ...], ...] = (
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
)


@dataclass(frozen=True, slots=True)
class WalkingSkeletonFixtures:
    """Complete immutable fixture bundle injected into deterministic graph nodes."""

    candidate_profile: CandidateProfile
    raw_search_results: tuple[RawSupervisorSearchResult, ...]
    verified_supervisors: tuple[VerifiedSupervisor, ...]
    research_fit_assessments: tuple[ResearchFitAssessment, ...]
    generated_at: datetime


def _profile_url(index: int) -> str:
    return f"https://profiles.scholarpath.example/profile-{index:03d}"


def _supervisor_identifier(index: int) -> str:
    offset = index - 1
    return deterministic_supervisor_id(
        _SUPERVISOR_NAMES[offset],
        _INSTITUTIONS[offset],
        _profile_url(index),
    )


def _candidate_profile() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="candidate-001",
        proposed_research_statement=(
            "Investigate how enterprise architecture and responsible AI governance "
            "support resilient digital transformation in complex organisations."
        ),
        research_topics=(
            "enterprise architecture",
            "responsible AI governance",
            "digital transformation",
            "organisational resilience",
        ),
        preferred_regions=("South Africa", "United Kingdom", "Netherlands"),
        preferred_study_modes=("hybrid", "part-time"),
        preferred_research_orientation="applied",
        methodological_interests=("design science", "comparative case study", "mixed methods"),
        exclusions=("fully residential programmes",),
    )


def _raw_search_result(index: int) -> RawSupervisorSearchResult:
    offset = index - 1
    identifier = _supervisor_identifier(index)
    profile_url = _profile_url(index)
    return RawSupervisorSearchResult.model_validate(
        {
            "supervisor_id": identifier,
            "full_name": _SUPERVISOR_NAMES[offset],
            "institution": _INSTITUTIONS[offset],
            "department": _DEPARTMENTS[offset],
            "profile_url": profile_url,
            "discovery_source": "synthetic academic index",
            "discovery_query": _DISCOVERY_QUERIES[offset],
            "discovery_provenance": (
                SupervisorDiscoveryProvenance.model_validate(
                    {
                        "source_url": profile_url,
                        "originating_query": _DISCOVERY_QUERIES[offset],
                    }
                ),
            ),
        }
    )


def _claim(
    index: int,
    suffix: str,
    claim_type: EvidenceClaimType,
    claim: str,
    source_kind: SourceKind,
    *,
    supporting_excerpt: str,
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
    availability_status: AvailabilityStatus | None = None,
    asserted_institution: str | None = None,
    asserted_department: str | None = None,
    activity_year: int | None = None,
) -> EvidenceClaim:
    identifier = _supervisor_identifier(index)
    return EvidenceClaim.model_validate(
        {
            "evidence_id": f"evidence-{index:03d}-{suffix}",
            "supervisor_id": identifier,
            "claim_type": claim_type,
            "claim": claim,
            "source_url": f"https://evidence.scholarpath.example/{identifier}/{suffix}",
            "source_kind": source_kind,
            "retrieved_at": FIXTURE_RETRIEVED_AT,
            "confidence": confidence,
            "directly_supported": True,
            "availability_status": availability_status,
            "asserted_name": _SUPERVISOR_NAMES[index - 1],
            "asserted_institution": asserted_institution,
            "asserted_department": asserted_department,
            "activity_year": activity_year,
            "supporting_excerpt": supporting_excerpt,
        }
    )


def _evidence_claims(index: int) -> tuple[EvidenceClaim, ...]:
    raw = _raw_search_result(index)
    claims = [
        _claim(
            index,
            "identity",
            EvidenceClaimType.IDENTITY,
            f"The profile names {raw.full_name}.",
            SourceKind.UNIVERSITY_PROFILE,
            supporting_excerpt=f"The official profile names {raw.full_name}.",
        ),
        _claim(
            index,
            "affiliation",
            EvidenceClaimType.CURRENT_AFFILIATION,
            f"The directory lists a current role at {raw.institution}.",
            SourceKind.INSTITUTIONAL_DIRECTORY,
            supporting_excerpt=(
                f"{raw.full_name} is currently listed in {raw.department} at {raw.institution}."
            ),
            asserted_institution=raw.institution,
            asserted_department=raw.department,
        ),
        _claim(
            index,
            "research",
            EvidenceClaimType.RESEARCH_INTEREST,
            _RESEARCH_CLAIMS[index - 1],
            SourceKind.DEPARTMENT_PAGE,
            supporting_excerpt=(
                f"{raw.full_name}'s department profile states: {_RESEARCH_CLAIMS[index - 1]}"
            ),
            confidence=EvidenceConfidence.MEDIUM,
        ),
        _claim(
            index,
            "methodology",
            EvidenceClaimType.METHODOLOGY,
            _METHODOLOGY_CLAIMS[index - 1],
            SourceKind.RESEARCH_REPOSITORY,
            supporting_excerpt=(
                f"{raw.full_name}'s methods statement says: {_METHODOLOGY_CLAIMS[index - 1]}"
            ),
            confidence=EvidenceConfidence.MEDIUM,
        ),
        _claim(
            index,
            "publication",
            EvidenceClaimType.PUBLICATION,
            _PUBLICATION_CLAIMS[index - 1],
            SourceKind.PUBLICATION,
            supporting_excerpt=(
                f"{raw.full_name}'s 2025 publication record states: "
                f"{_PUBLICATION_CLAIMS[index - 1]}"
            ),
            activity_year=2025,
        ),
    ]
    if index == 2:
        claims.append(
            _claim(
                index,
                "availability",
                EvidenceClaimType.AVAILABILITY,
                "The institutional profile explicitly states current doctoral availability.",
                SourceKind.UNIVERSITY_PROFILE,
                supporting_excerpt=(
                    f"{raw.full_name} is currently accepting new doctoral Candidates."
                ),
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
            )
        )
    elif index == 3:
        claims.append(
            _claim(
                index,
                "availability",
                EvidenceClaimType.AVAILABILITY,
                "The department page explicitly states no current doctoral availability.",
                SourceKind.DEPARTMENT_PAGE,
                supporting_excerpt=(f"{raw.full_name} is not accepting new doctoral Candidates."),
                availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
            )
        )
    elif index == 4:
        claims.extend(
            (
                _claim(
                    index,
                    "availability-a",
                    EvidenceClaimType.AVAILABILITY,
                    "The institutional profile states current doctoral availability.",
                    SourceKind.UNIVERSITY_PROFILE,
                    supporting_excerpt=(
                        f"{raw.full_name} is currently accepting new doctoral Candidates."
                    ),
                    availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                ),
                _claim(
                    index,
                    "availability-b",
                    EvidenceClaimType.AVAILABILITY,
                    "A department notice states that new doctoral enquiries are paused.",
                    SourceKind.DEPARTMENT_PAGE,
                    supporting_excerpt=(
                        f"{raw.full_name} is not accepting new doctoral Candidates."
                    ),
                    confidence=EvidenceConfidence.MEDIUM,
                    availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
                ),
            )
        )
    return tuple(claims)


def _verified_supervisor(index: int) -> VerifiedSupervisor:
    concerns: tuple[str, ...] = ()
    if index == 3:
        concerns = ("The source states that the Supervisor is not accepting enquiries.",)
    elif index == 4:
        concerns = ("Current sources conflict about doctoral availability.",)
    return verify_supervisor(
        _raw_search_result(index).to_prospective_supervisor(),
        _evidence_claims(index),
        verification_concerns=concerns,
    )


def _research_fit_assessment(index: int, supervisor: VerifiedSupervisor) -> ResearchFitAssessment:
    overall, scores, _ = _FIT_DATA[index - 1]
    evidence_by_type = {claim.claim_type: claim.evidence_id for claim in supervisor.evidence}
    evidence_by_id = {claim.evidence_id: claim for claim in supervisor.evidence}
    research_id = evidence_by_type[EvidenceClaimType.RESEARCH_INTEREST]
    methodology_id = evidence_by_type[EvidenceClaimType.METHODOLOGY]
    publication_id = evidence_by_type[EvidenceClaimType.PUBLICATION]

    def component(
        score: int,
        rationale: str,
        evidence_ids: tuple[str, ...],
        *,
        evidence_gap: str | None = None,
    ) -> ResearchFitComponentAssessment:
        confidence_rank = {
            EvidenceConfidence.LOW: 1,
            EvidenceConfidence.MEDIUM: 2,
            EvidenceConfidence.HIGH: 3,
        }
        return ResearchFitComponentAssessment(
            score=score,
            rationale=rationale,
            supporting_evidence_ids=evidence_ids,
            confidence=(
                EvidenceConfidence.LOW
                if not evidence_ids
                else min(
                    (evidence_by_id[evidence_id].confidence for evidence_id in evidence_ids),
                    key=confidence_rank.__getitem__,
                )
            ),
            evidence_gap=evidence_gap,
        )

    breakdown = ResearchFitBreakdown(
        topic_alignment=component(
            scores[0],
            "The research-interest and publication claims support topic alignment.",
            (research_id, publication_id),
        ),
        methodological_alignment=component(
            scores[1],
            "The methodology claim supports methodological alignment.",
            (methodology_id,),
        ),
        research_orientation_alignment=component(
            scores[2],
            "The research and methodology claims support orientation alignment.",
            (research_id, methodology_id),
        ),
        recent_research_alignment=component(
            scores[3],
            "The recent publication claim supports current research alignment.",
            (publication_id,),
        ),
        practical_constraint_alignment=component(
            scores[4],
            "No direct region or study-mode evidence was retrieved.",
            (),
            evidence_gap="Direct region and study-mode evidence is missing.",
        ),
    )
    assessment = ResearchFitAssessment(
        supervisor_id=supervisor.supervisor_id,
        overall_score=overall,
        breakdown=breakdown,
        rationale=_FIT_RATIONALES[index - 1],
        supporting_evidence_ids=(research_id, publication_id, methodology_id),
        confidence=EvidenceConfidence.MEDIUM,
        concerns=_FIT_CONCERNS[index - 1],
    )
    validate_research_fit_evidence(supervisor, assessment)
    return assessment


def build_walking_skeleton_fixtures() -> WalkingSkeletonFixtures:
    """Build a fresh, fully validated fixture bundle without external calls."""
    verified = tuple(_verified_supervisor(index) for index in range(1, 7))
    assessments = tuple(
        _research_fit_assessment(index, verified[index - 1]) for index in range(1, 7)
    )
    return WalkingSkeletonFixtures(
        candidate_profile=_candidate_profile(),
        raw_search_results=tuple(_raw_search_result(index) for index in range(1, 9)),
        verified_supervisors=verified,
        research_fit_assessments=assessments,
        generated_at=FIXTURE_RETRIEVED_AT,
    )


def default_review_decision() -> CandidateReviewDecision:
    """Return the configured approval used by the default fixture-backed review path."""
    return CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=tuple(_supervisor_identifier(index) for index in (1, 2, 4, 3, 5)),
        reason="The Candidate approved all five fixture-backed recommendations.",
    )


def preferences_from_profile(profile: CandidateProfile) -> CandidatePreferenceRevision:
    """Project the Candidate profile into the graph's append-only preference history."""
    return CandidatePreferenceRevision(
        research_topics=profile.research_topics,
        preferred_regions=profile.preferred_regions,
        preferred_study_modes=profile.preferred_study_modes,
        preferred_research_orientation=profile.preferred_research_orientation,
        methodological_interests=profile.methodological_interests,
        exclusions=profile.exclusions,
    )
