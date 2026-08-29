"""Realistic, reproducible factories containing no live or generated data."""

from datetime import UTC, datetime

from scholarpath.domain import (
    AvailabilityStatus,
    CandidateProfile,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    PlannedSearchQuery,
    ProspectiveSupervisor,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitComponentAssessment,
    SearchPlan,
    SearchSourceType,
    SourceKind,
    VerifiedSupervisor,
    validate_research_fit_evidence,
    verify_supervisor,
)

FIXED_RETRIEVED_AT = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)

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
_RESEARCH_SOURCE_KINDS = (
    SourceKind.DEPARTMENT_PAGE,
    SourceKind.PERSONAL_ACADEMIC_PAGE,
    SourceKind.RESEARCH_REPOSITORY,
    SourceKind.DEPARTMENT_PAGE,
    SourceKind.PERSONAL_ACADEMIC_PAGE,
    SourceKind.RESEARCH_REPOSITORY,
)


def make_candidate_profile(**overrides: object) -> CandidateProfile:
    """Return the one canonical synthetic Candidate fixture."""
    data: dict[str, object] = {
        "candidate_id": "candidate-001",
        "proposed_research_statement": (
            "Investigate how enterprise architecture and responsible AI governance "
            "support resilient digital transformation in complex organisations."
        ),
        "research_topics": (
            "enterprise architecture",
            "responsible AI governance",
            "digital transformation",
            "organisational resilience",
        ),
        "preferred_regions": ("South Africa", "United Kingdom", "Netherlands"),
        "preferred_study_modes": ("hybrid", "part-time"),
        "preferred_research_orientation": "applied",
        "methodological_interests": (
            "design science",
            "comparative case study",
            "mixed methods",
        ),
        "exclusions": ("fully residential programmes",),
    }
    return CandidateProfile.model_validate({**data, **overrides})


def make_search_plan(**overrides: object) -> SearchPlan:
    """Return a deterministic search plan aligned with the Candidate fixture."""
    data: dict[str, object] = {
        "search_queries": (
            PlannedSearchQuery(
                query=_DISCOVERY_QUERIES[0],
                purpose="Find official identity, affiliation, and research profile evidence.",
                target_source_types=(SearchSourceType.OFFICIAL_UNIVERSITY_PROFILE,),
            ),
            PlannedSearchQuery(
                query=_DISCOVERY_QUERIES[1],
                purpose="Find department and research-group alignment evidence.",
                target_source_types=(SearchSourceType.DEPARTMENT_OR_RESEARCH_GROUP,),
            ),
            PlannedSearchQuery(
                query=_DISCOVERY_QUERIES[2],
                purpose="Find recent publication evidence for Research Fit.",
                target_source_types=(SearchSourceType.RECENT_PUBLICATION,),
            ),
            PlannedSearchQuery(
                query=_DISCOVERY_QUERIES[7],
                purpose="Find explicit institutional doctoral supervision information.",
                target_source_types=(SearchSourceType.DOCTORAL_SUPERVISION_INFORMATION,),
            ),
        ),
        "expanded_research_concepts": (
            "enterprise design",
            "AI assurance",
            "sociotechnical transformation",
        ),
        "target_regions": ("South Africa", "United Kingdom", "Netherlands"),
        "rationale": (
            "Combine the Candidate's core topics with adjacent concepts and preferred regions."
        ),
    }
    return SearchPlan.model_validate({**data, **overrides})


def make_prospective_supervisor(index: int, **overrides: object) -> ProspectiveSupervisor:
    """Return one of eight invented Prospective Supervisor fixtures."""
    if not 1 <= index <= len(_SUPERVISOR_NAMES):
        raise ValueError("Prospective Supervisor fixture index must be between 1 and 8")
    offset = index - 1
    identifier = f"supervisor-{index:03d}"
    data: dict[str, object] = {
        "supervisor_id": identifier,
        "full_name": _SUPERVISOR_NAMES[offset],
        "institution": _INSTITUTIONS[offset],
        "department": _DEPARTMENTS[offset],
        "profile_url": f"https://profiles.scholarpath.example/{identifier}",
        "discovery_source": "synthetic academic index",
        "discovery_query": _DISCOVERY_QUERIES[offset],
    }
    return ProspectiveSupervisor.model_validate({**data, **overrides})


def make_prospective_supervisors() -> tuple[ProspectiveSupervisor, ...]:
    """Return the complete eight-record discovery fixture cohort."""
    return tuple(make_prospective_supervisor(index) for index in range(1, 9))


def _claim(
    index: int,
    suffix: str,
    claim_type: EvidenceClaimType,
    claim: str,
    source_kind: SourceKind,
    *,
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
    directly_supported: bool = True,
    availability_status: AvailabilityStatus | None = None,
    asserted_name: str | None = None,
    asserted_institution: str | None = None,
    asserted_department: str | None = None,
    activity_year: int | None = None,
    supporting_excerpt: str | None = None,
) -> EvidenceClaim:
    identifier = f"supervisor-{index:03d}"
    return EvidenceClaim.model_validate(
        {
            "evidence_id": f"evidence-{index:03d}-{suffix}",
            "supervisor_id": identifier,
            "claim_type": claim_type,
            "claim": claim,
            "source_url": f"https://evidence.scholarpath.example/{identifier}/{suffix}",
            "source_kind": source_kind,
            "retrieved_at": FIXED_RETRIEVED_AT,
            "confidence": confidence,
            "directly_supported": directly_supported,
            "availability_status": availability_status,
            "asserted_name": asserted_name,
            "asserted_institution": asserted_institution,
            "asserted_department": asserted_department,
            "activity_year": activity_year,
            "supporting_excerpt": supporting_excerpt,
        }
    )


def make_evidence_claims(index: int) -> tuple[EvidenceClaim, ...]:
    """Return source-linked evidence for one of the six Verified fixtures."""
    if not 1 <= index <= 6:
        raise ValueError("Verified Supervisor fixture index must be between 1 and 6")
    prospective = make_prospective_supervisor(index)
    claims = [
        _claim(
            index,
            "identity",
            EvidenceClaimType.IDENTITY,
            f"The profile names {prospective.full_name}.",
            SourceKind.UNIVERSITY_PROFILE,
            asserted_name=prospective.full_name,
            supporting_excerpt=f"The official profile names {prospective.full_name}.",
        ),
        _claim(
            index,
            "affiliation",
            EvidenceClaimType.CURRENT_AFFILIATION,
            f"The directory lists a current role at {prospective.institution}.",
            SourceKind.INSTITUTIONAL_DIRECTORY,
            asserted_name=prospective.full_name,
            asserted_institution=prospective.institution,
            asserted_department=prospective.department,
            supporting_excerpt=(
                f"{prospective.full_name} is currently listed in {prospective.department} "
                f"at {prospective.institution}."
            ),
        ),
        _claim(
            index,
            "research",
            EvidenceClaimType.RESEARCH_INTEREST,
            _RESEARCH_CLAIMS[index - 1],
            _RESEARCH_SOURCE_KINDS[index - 1],
            confidence=EvidenceConfidence.MEDIUM,
            asserted_name=prospective.full_name,
            supporting_excerpt=(
                f"{prospective.full_name}'s profile states: {_RESEARCH_CLAIMS[index - 1]}"
            ),
        ),
        _claim(
            index,
            "methodology",
            EvidenceClaimType.METHODOLOGY,
            _METHODOLOGY_CLAIMS[index - 1],
            SourceKind.RESEARCH_REPOSITORY,
            confidence=EvidenceConfidence.MEDIUM,
            asserted_name=prospective.full_name,
            supporting_excerpt=(
                f"{prospective.full_name}'s methods statement says: "
                f"{_METHODOLOGY_CLAIMS[index - 1]}"
            ),
        ),
        _claim(
            index,
            "publication",
            EvidenceClaimType.PUBLICATION,
            _PUBLICATION_CLAIMS[index - 1],
            SourceKind.PUBLICATION,
            asserted_name=prospective.full_name,
            activity_year=2025,
            supporting_excerpt=(
                f"{prospective.full_name}'s 2025 publication record states: "
                f"{_PUBLICATION_CLAIMS[index - 1]}"
            ),
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
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                asserted_name=prospective.full_name,
                supporting_excerpt=(
                    f"{prospective.full_name} is currently accepting new doctoral Candidates."
                ),
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
                availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
                asserted_name=prospective.full_name,
                supporting_excerpt=(
                    f"{prospective.full_name} is not accepting new doctoral Candidates."
                ),
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
                    availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                    asserted_name=prospective.full_name,
                    supporting_excerpt=(
                        f"{prospective.full_name} is currently accepting new doctoral Candidates."
                    ),
                ),
                _claim(
                    index,
                    "availability-b",
                    EvidenceClaimType.AVAILABILITY,
                    "A department notice states that new doctoral enquiries are paused.",
                    SourceKind.DEPARTMENT_PAGE,
                    confidence=EvidenceConfidence.MEDIUM,
                    availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
                    asserted_name=prospective.full_name,
                    supporting_excerpt=(
                        f"{prospective.full_name} is not accepting new doctoral Candidates."
                    ),
                ),
            )
        )
    elif index == 6:
        claims.append(
            _claim(
                index,
                "indirect-topic",
                EvidenceClaimType.RESEARCH_INTEREST,
                "An index snippet suggests an adjacent research topic.",
                SourceKind.OTHER,
                confidence=EvidenceConfidence.LOW,
                directly_supported=False,
            )
        )
    return tuple(claims)


_AVAILABILITY = (
    AvailabilityStatus.NOT_STATED,
    AvailabilityStatus.CONFIRMED_ACCEPTING,
    AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
    AvailabilityStatus.CONFLICTING_EVIDENCE,
    AvailabilityStatus.NOT_STATED,
    AvailabilityStatus.NOT_STATED,
)
_VERIFICATION_CONCERNS: tuple[tuple[str, ...], ...] = (
    (),
    (),
    ("The source states that the Supervisor is not currently accepting enquiries.",),
    ("Current sources conflict about doctoral availability.",),
    (),
    (),
)


def make_verified_supervisor(index: int, **overrides: object) -> VerifiedSupervisor:
    """Return one of six evidence-backed Verified Supervisor fixtures."""
    if not 1 <= index <= 6:
        raise ValueError("Verified Supervisor fixture index must be between 1 and 6")
    supervisor = verify_supervisor(
        make_prospective_supervisor(index),
        make_evidence_claims(index),
        availability_status=_AVAILABILITY[index - 1],
        verification_concerns=_VERIFICATION_CONCERNS[index - 1],
    )
    return VerifiedSupervisor.model_validate({**supervisor.model_dump(mode="python"), **overrides})


def make_verified_supervisors() -> tuple[VerifiedSupervisor, ...]:
    """Return the complete six-record verification fixture cohort."""
    return tuple(make_verified_supervisor(index) for index in range(1, 7))


_FIT_SCORES = (
    (87, (38, 19, 15, 15, 0), EvidenceConfidence.HIGH),
    (82, (36, 18, 14, 14, 0), EvidenceConfidence.HIGH),
    (72, (31, 16, 12, 13, 0), EvidenceConfidence.MEDIUM),
    (75, (33, 16, 13, 13, 0), EvidenceConfidence.MEDIUM),
    (68, (30, 14, 12, 12, 0), EvidenceConfidence.MEDIUM),
)
_FIT_CONCERNS: tuple[tuple[str, ...], ...] = (
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
    ("Direct region and study-mode evidence is missing.",),
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
)


def make_research_fit_assessment(index: int, **overrides: object) -> ResearchFitAssessment:
    """Return one of five transparent, evidence-linked Research Fit fixtures."""
    if not 1 <= index <= 5:
        raise ValueError("Research Fit fixture index must be between 1 and 5")
    overall, component_scores, _ = _FIT_SCORES[index - 1]
    supervisor = make_verified_supervisor(index)
    evidence_by_type = {claim.claim_type: claim.evidence_id for claim in supervisor.evidence}
    research_id = evidence_by_type[EvidenceClaimType.RESEARCH_INTEREST]
    methodology_id = evidence_by_type[EvidenceClaimType.METHODOLOGY]
    publication_id = evidence_by_type[EvidenceClaimType.PUBLICATION]
    evidence_by_id = {claim.evidence_id: claim for claim in supervisor.evidence}

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

    data: dict[str, object] = {
        "supervisor_id": supervisor.supervisor_id,
        "overall_score": overall,
        "breakdown": ResearchFitBreakdown(
            topic_alignment=component(
                component_scores[0],
                "Research-interest and publication claims support topic alignment.",
                (research_id, publication_id),
            ),
            methodological_alignment=component(
                component_scores[1],
                "The methodology claim supports methodological alignment.",
                (methodology_id,),
            ),
            research_orientation_alignment=component(
                component_scores[2],
                "Research and methodology claims support orientation alignment.",
                (research_id, methodology_id),
            ),
            recent_research_alignment=component(
                component_scores[3],
                "The publication claim supports recent research alignment.",
                (publication_id,),
            ),
            practical_constraint_alignment=component(
                component_scores[4],
                "No direct region or study-mode evidence was retrieved.",
                (),
                evidence_gap="Direct region and study-mode evidence is missing.",
            ),
        ),
        "rationale": _FIT_RATIONALES[index - 1],
        "supporting_evidence_ids": (research_id, publication_id, methodology_id),
        "confidence": EvidenceConfidence.MEDIUM,
        "concerns": _FIT_CONCERNS[index - 1],
    }
    assessment = ResearchFitAssessment.model_validate({**data, **overrides})
    validate_research_fit_evidence(supervisor, assessment)
    return assessment


def make_research_fit_assessments() -> tuple[ResearchFitAssessment, ...]:
    """Return the complete five-record Research Fit fixture cohort."""
    return tuple(make_research_fit_assessment(index) for index in range(1, 6))
