"""Recording fake and structured-output factories for evidence verification."""

from collections.abc import Mapping, Sequence

from scholarpath.agents.evidence_verification import (
    EvidenceExtractionInput,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import AvailabilityStatus, EvidenceClaimType, EvidenceConfidence
from scholarpath.graph.fixtures import build_walking_skeleton_fixtures
from tests.fixtures.evidence_pages import (
    ACCEPTING_PROFILE_URL,
    ALTERNATE_OFFICIAL_PROFILE_URL,
    COMPLETE_PROFILE_URL,
    CONFLICTING_AFFILIATION_URL,
    MISSING_AFFILIATION_URL,
    MISSING_RESEARCH_URL,
    NOT_ACCEPTING_PROFILE_URL,
)

type EvidenceModelOutcome = StructuredEvidenceExtractionResult | Exception

EXPECTED_NAME = "Dr Amara Ndlovu"
EXPECTED_INSTITUTION = "Southern Cape Institute of Technology"
EXPECTED_DEPARTMENT = "Department of Information Systems"


def _identity_claim() -> StructuredEvidenceClaim:
    return StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.IDENTITY,
        claim="The official page identifies Dr Amara Ndlovu.",
        supporting_excerpt="Dr Amara Ndlovu",
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
    )


def _affiliation_claim() -> StructuredEvidenceClaim:
    return StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        claim=(
            "Dr Amara Ndlovu is Associate Professor in the Department of Information "
            "Systems at Southern Cape Institute of Technology."
        ),
        supporting_excerpt=(
            "Dr Amara Ndlovu is Associate Professor in the Department of Information "
            "Systems at Southern Cape Institute of Technology."
        ),
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
        asserted_institution=EXPECTED_INSTITUTION,
        asserted_department=EXPECTED_DEPARTMENT,
    )


def _research_claim(*, alternate: bool = False) -> StructuredEvidenceClaim:
    excerpt = (
        "Dr Amara Ndlovu's current research areas include enterprise architecture and "
        "responsible AI governance, according to the directory."
        if alternate
        else (
            "Dr Amara Ndlovu's stated research interests are enterprise architecture, "
            "responsible AI governance, and resilient digital transformation."
        )
    )
    return StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        claim=(
            "The page states research interests in enterprise architecture, responsible AI "
            "governance, and resilient digital transformation."
        ),
        supporting_excerpt=excerpt,
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
    )


def _publication_claim() -> StructuredEvidenceClaim:
    return StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.PUBLICATION,
        claim=("A 2025 publication examines architecture controls for responsible AI adoption."),
        supporting_excerpt=(
            "Dr Amara Ndlovu's 2025 publication, \"Architecture Controls for Responsible AI "
            'Adoption", examines governance mechanisms in complex organisations.'
        ),
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
    )


def _project_claim(*, alternate: bool = False) -> StructuredEvidenceClaim:
    excerpt = (
        "Dr Amara Ndlovu's institutional project page records the 2025 Responsible "
        "Enterprise Architecture Lab."
        if alternate
        else (
            "Dr Amara Ndlovu leads the Responsible Enterprise Architecture Lab project "
            "for 2025–2027."
        )
    )
    return StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.PROJECT,
        claim="The page records a recent Responsible Enterprise Architecture Lab project.",
        supporting_excerpt=excerpt,
        confidence=EvidenceConfidence.MEDIUM,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
    )


def make_complete_evidence_response(
    *,
    availability_status: AvailabilityStatus | None = None,
    include_project: bool = True,
) -> StructuredEvidenceExtractionResult:
    """Return identity, affiliation, research, publication, project, and optional availability."""
    claims = [
        _identity_claim(),
        _affiliation_claim(),
        _research_claim(),
        _publication_claim(),
    ]
    if include_project:
        claims.append(_project_claim())
    if availability_status is AvailabilityStatus.CONFIRMED_ACCEPTING:
        claims.append(
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.AVAILABILITY,
                claim="The page explicitly states that the Supervisor is currently accepting.",
                supporting_excerpt=(
                    "Dr Amara Ndlovu is currently accepting doctoral Candidates for projects "
                    "beginning in 2027."
                ),
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                availability_status=availability_status,
                asserted_name=EXPECTED_NAME,
            )
        )
    elif availability_status is AvailabilityStatus.CONFIRMED_NOT_ACCEPTING:
        claims.append(
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.AVAILABILITY,
                claim="The page explicitly states that the Supervisor is not accepting.",
                supporting_excerpt=(
                    "Dr Amara Ndlovu is not accepting new doctoral Candidates for the 2027 intake."
                ),
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                availability_status=availability_status,
                asserted_name=EXPECTED_NAME,
            )
        )
    return StructuredEvidenceExtractionResult(claims=claims)


def make_missing_affiliation_response() -> StructuredEvidenceExtractionResult:
    """Return grounded evidence without a current-affiliation claim."""
    research = StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        claim=(
            "The page states research in enterprise architecture, responsible AI governance, "
            "and resilient digital transformation."
        ),
        supporting_excerpt=(
            "Dr Amara Ndlovu researches enterprise architecture, responsible AI governance, "
            "and resilient digital transformation."
        ),
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
    )
    return StructuredEvidenceExtractionResult(
        claims=[_identity_claim(), research, _publication_claim()]
    )


def make_missing_research_response() -> StructuredEvidenceExtractionResult:
    """Return grounded identity and affiliation evidence without research evidence."""
    return StructuredEvidenceExtractionResult(claims=[_identity_claim(), _affiliation_claim()])


def make_conflicting_affiliation_response() -> StructuredEvidenceExtractionResult:
    """Return the second official source's incompatible current-affiliation claim."""
    return StructuredEvidenceExtractionResult(
        claims=[
            _identity_claim(),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim=(
                    "Northbridge University lists Dr Amara Ndlovu as Professor in the School "
                    "of Computing and Strategy."
                ),
                supporting_excerpt=(
                    "Dr Amara Ndlovu is listed by the Northbridge University staff directory "
                    "as Professor in the School of Computing and Strategy."
                ),
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=EXPECTED_NAME,
                asserted_institution="Northbridge University",
                asserted_department="School of Computing and Strategy",
            ),
            _research_claim(alternate=True),
        ]
    )


def make_alternate_official_response() -> StructuredEvidenceExtractionResult:
    """Return sufficient evidence from the alternate institutional profile fixture."""
    affiliation = StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        claim=(
            "The faculty directory identifies Dr Amara Ndlovu as Associate Professor in the "
            "Department of Information Systems at Southern Cape Institute of Technology."
        ),
        supporting_excerpt=(
            "Dr Amara Ndlovu is identified by the Southern Cape Institute of Technology "
            "faculty directory as Associate Professor in the Department of Information "
            "Systems."
        ),
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=EXPECTED_NAME,
        asserted_institution=EXPECTED_INSTITUTION,
        asserted_department=EXPECTED_DEPARTMENT,
    )
    return StructuredEvidenceExtractionResult(
        claims=[
            _identity_claim(),
            affiliation,
            _research_claim(alternate=True),
            _project_claim(alternate=True),
        ]
    )


def make_fixed_evidence_outcomes() -> dict[str, StructuredEvidenceExtractionResult]:
    """Map fixed evidence page URLs to matching structured responses."""
    return {
        COMPLETE_PROFILE_URL: make_complete_evidence_response(),
        MISSING_AFFILIATION_URL: make_missing_affiliation_response(),
        MISSING_RESEARCH_URL: make_missing_research_response(),
        ACCEPTING_PROFILE_URL: make_complete_evidence_response(
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
            include_project=False,
        ),
        NOT_ACCEPTING_PROFILE_URL: make_complete_evidence_response(
            availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
            include_project=False,
        ),
        CONFLICTING_AFFILIATION_URL: make_conflicting_affiliation_response(),
        ALTERNATE_OFFICIAL_PROFILE_URL: make_alternate_official_response(),
    }


def make_graph_evidence_outcomes() -> dict[str, StructuredEvidenceExtractionResult]:
    """Return grounded structured responses for the walking-skeleton cohort."""
    outcomes: dict[str, StructuredEvidenceExtractionResult] = {}
    for raw in build_walking_skeleton_fixtures().raw_search_results:
        affiliation = f"{raw.full_name} is Professor in {raw.department} at {raw.institution}."
        outcomes[str(raw.profile_url)] = StructuredEvidenceExtractionResult(
            claims=[
                StructuredEvidenceClaim(
                    claim_type=EvidenceClaimType.IDENTITY,
                    claim=f"The official profile identifies {raw.full_name}.",
                    supporting_excerpt=raw.full_name,
                    confidence=EvidenceConfidence.HIGH,
                    directly_supported=True,
                    asserted_name=raw.full_name,
                ),
                StructuredEvidenceClaim(
                    claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                    claim=affiliation,
                    supporting_excerpt=affiliation,
                    confidence=EvidenceConfidence.HIGH,
                    directly_supported=True,
                    asserted_name=raw.full_name,
                    asserted_institution=raw.institution,
                    asserted_department=raw.department,
                ),
                StructuredEvidenceClaim(
                    claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                    claim=(
                        "The profile states research interests in enterprise architecture, "
                        "responsible AI governance, and resilient digital transformation."
                    ),
                    supporting_excerpt=(
                        f"{raw.full_name}'s current research interests include enterprise "
                        "architecture, responsible AI governance, and resilient digital "
                        "transformation."
                    ),
                    confidence=EvidenceConfidence.HIGH,
                    directly_supported=True,
                    asserted_name=raw.full_name,
                ),
                StructuredEvidenceClaim(
                    claim_type=EvidenceClaimType.PUBLICATION,
                    claim=(
                        "A 2025 publication examines architecture controls for responsible "
                        "AI adoption."
                    ),
                    supporting_excerpt=(
                        f"{raw.full_name} authored a 2025 publication examining architecture "
                        "controls for responsible AI adoption."
                    ),
                    confidence=EvidenceConfidence.HIGH,
                    directly_supported=True,
                    asserted_name=raw.full_name,
                ),
            ]
        )
    return outcomes


class FakeEvidenceVerificationModel:
    """Return URL-scripted typed evidence responses and record every model input."""

    def __init__(
        self,
        outcomes: Mapping[str, EvidenceModelOutcome] | None = None,
        *,
        scripts: Mapping[str, Sequence[EvidenceModelOutcome]] | None = None,
    ) -> None:
        default_outcomes = {**make_fixed_evidence_outcomes(), **make_graph_evidence_outcomes()}
        self._outcomes = dict(default_outcomes if outcomes is None else outcomes)
        self._scripts = {url: list(items) for url, items in (scripts or {}).items()}
        self.inputs: list[EvidenceExtractionInput] = []

    @property
    def call_count(self) -> int:
        """Return how many structured-model calls were made."""
        return len(self.inputs)

    def extract(
        self, extraction_input: EvidenceExtractionInput
    ) -> StructuredEvidenceExtractionResult:
        """Record input, then return or raise its deterministic URL outcome."""
        self.inputs.append(extraction_input)
        source_url = str(extraction_input.source_url)
        scripted = self._scripts.get(source_url)
        outcome = scripted.pop(0) if scripted else self._outcomes.get(source_url)
        if outcome is None:
            raise AssertionError(f"No fake evidence-model outcome for {source_url}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
