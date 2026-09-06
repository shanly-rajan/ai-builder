"""Synthetic source/response variations for the separate Week 4 draft dataset.

These are inputs to the production verifier, never manufactured verification
results or labels inferred from its output. Only the reserved ``.example`` cohort
is accepted. The historical eleven-case dataset is not changed by this module.
"""

from typing import Final

from ..agents.evidence_verification import (
    StructuredEvidenceClaimDraft,
    StructuredEvidenceExtractionResult,
)
from ..domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    EvidenceConfidence,
    ProspectiveSupervisor,
)
from ..tools import ExtractedContent

DRAFT_EVIDENCE_CASES: Final = (
    "confirmed_accepting",
    "confirmed_not_accepting",
    "markdown_identity",
    "honorific_identity",
    "line_wrapped_affiliation",
    "publication_only",
    "heading_bound_research",
    "missing_identity",
    "missing_affiliation",
    "missing_research",
    "publication_year_not_stated",
    "availability_without_statement",
    "off_page_excerpt",
)


def _claim_index(claims: list[StructuredEvidenceClaimDraft], kind: EvidenceClaimType) -> int:
    positions = [index for index, claim in enumerate(claims) if claim.claim_type is kind]
    if len(positions) != 1:
        raise ValueError("Draft evidence variations require one baseline claim of each used type")
    return positions[0]


def _replace_source_excerpt(content: str, original: str, replacement: str) -> str:
    if content.count(original) != 1:
        raise ValueError("Draft evidence variations require an unambiguous baseline excerpt")
    return content.replace(original, replacement, 1)


def _update_claim(
    claims: list[StructuredEvidenceClaimDraft],
    kind: EvidenceClaimType,
    **updates: object,
) -> StructuredEvidenceClaimDraft:
    index = _claim_index(claims, kind)
    original = claims[index]
    claims[index] = StructuredEvidenceClaimDraft.model_validate(
        {**original.model_dump(mode="python"), **updates}
    )
    return original


def _drop_claims(
    claims: list[StructuredEvidenceClaimDraft],
    content: str,
    kinds: tuple[EvidenceClaimType, ...],
) -> tuple[list[StructuredEvidenceClaimDraft], str]:
    for kind in kinds:
        index = _claim_index(claims, kind)
        removed = claims.pop(index)
        content = _replace_source_excerpt(content, removed.supporting_excerpt, "")
    return claims, content


def apply_draft_evidence_case(
    supervisor: ProspectiveSupervisor,
    page: ExtractedContent,
    response: StructuredEvidenceExtractionResult,
    case: str,
) -> tuple[ExtractedContent, StructuredEvidenceExtractionResult]:
    """Vary one fixed source and scripted response without modifying caller inputs.

    Provenance remains on the original synthetic URL and retrieval time. Missing
    evidence is removed explicitly; adversarial cases retain valid typed drafts
    whose factual support must be rejected by the unchanged production verifier.
    """
    if case not in DRAFT_EVIDENCE_CASES:
        raise ValueError("Unknown draft evidence case")
    if (
        not (page.source_url.host or "").endswith(".example")
        or page.source_url != supervisor.profile_url
    ):
        raise ValueError("Draft evidence variations require the matching synthetic profile URL")
    if any(claim.asserted_name != supervisor.full_name for claim in response.claims):
        raise ValueError("Draft evidence variations require the matching synthetic Supervisor")

    claims = [claim.model_copy(deep=True) for claim in response.claims]
    content = page.content
    name = supervisor.full_name
    if case in {"confirmed_accepting", "confirmed_not_accepting"}:
        negative = case == "confirmed_not_accepting"
        excerpt = f"{name} is {'not ' if negative else ''}accepting doctoral Candidates."
        claims.append(
            StructuredEvidenceClaimDraft(
                claim_type=EvidenceClaimType.AVAILABILITY,
                claim=excerpt,
                supporting_excerpt=excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=name,
                availability_status=(
                    AvailabilityStatus.CONFIRMED_NOT_ACCEPTING
                    if negative
                    else AvailabilityStatus.CONFIRMED_ACCEPTING
                ),
            )
        )
        content += f"\n{excerpt}"
    elif case == "markdown_identity":
        original = _update_claim(claims, EvidenceClaimType.IDENTITY, supporting_excerpt=name)
        content = _replace_source_excerpt(content, original.supporting_excerpt, f"# **{name}**")
    elif case == "honorific_identity":
        # The fixed cohort uses only these two titles. This is a fixture variation,
        # not a new identity-normalization or validation rule.
        title = next((prefix for prefix in ("Dr ", "Professor ") if name.startswith(prefix)), None)
        if title is None:
            raise ValueError("Draft honorific variation requires a known synthetic cohort title")
        alternate_name = f"Dr. {name[len(title) :]}"
        excerpt = f"The official profile names {alternate_name}."
        original = _update_claim(
            claims,
            EvidenceClaimType.IDENTITY,
            claim=f"The official profile identifies {alternate_name}.",
            supporting_excerpt=excerpt,
            asserted_name=alternate_name,
        )
        content = _replace_source_excerpt(content, original.supporting_excerpt, excerpt)
    elif case == "line_wrapped_affiliation":
        original = claims[_claim_index(claims, EvidenceClaimType.CURRENT_AFFILIATION)]
        wrapped = original.supporting_excerpt.replace(" at ", "\n  at\t", 1)
        if wrapped == original.supporting_excerpt:
            raise ValueError("Draft affiliation variation requires the baseline affiliation form")
        content = _replace_source_excerpt(content, original.supporting_excerpt, wrapped)
    elif case == "publication_only":
        claims, content = _drop_claims(
            claims, content, (EvidenceClaimType.RESEARCH_INTEREST, EvidenceClaimType.METHODOLOGY)
        )
    elif case == "heading_bound_research":
        excerpt = "Research interests: enterprise architecture and responsible AI governance."
        original = _update_claim(
            claims,
            EvidenceClaimType.RESEARCH_INTEREST,
            claim=(
                "The profile states enterprise architecture and responsible AI governance research."
            ),
            supporting_excerpt=excerpt,
        )
        content = f"# {name}\n" + _replace_source_excerpt(
            content, original.supporting_excerpt, f"## Research interests\n{excerpt}"
        )
    elif case in {"missing_identity", "missing_affiliation", "missing_research"}:
        removed_types = {
            "missing_identity": (EvidenceClaimType.IDENTITY,),
            "missing_affiliation": (EvidenceClaimType.CURRENT_AFFILIATION,),
            "missing_research": (
                EvidenceClaimType.RESEARCH_INTEREST,
                EvidenceClaimType.PUBLICATION,
            ),
        }
        claims, content = _drop_claims(claims, content, removed_types[case])
    elif case == "publication_year_not_stated":
        excerpt = f"{name}'s publication record examines architecture controls for responsible AI."
        original = _update_claim(
            claims,
            EvidenceClaimType.PUBLICATION,
            claim="A publication examines architecture controls for responsible AI.",
            supporting_excerpt=excerpt,
            activity_year=None,
        )
        content = _replace_source_excerpt(content, original.supporting_excerpt, excerpt)
    elif case == "availability_without_statement":
        research = claims[_claim_index(claims, EvidenceClaimType.RESEARCH_INTEREST)]
        # A structurally valid model assertion is not an explicit availability statement.
        claims.append(
            StructuredEvidenceClaimDraft(
                claim_type=EvidenceClaimType.AVAILABILITY,
                claim=f"{name} is accepting doctoral Candidates.",
                supporting_excerpt=research.supporting_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=name,
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
            )
        )
    elif case == "off_page_excerpt":
        # Both research routes are attacked. The real synthetic page stays unchanged;
        # neither invented quote occurs in it, despite valid names and typed values.
        _update_claim(
            claims,
            EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states quantum-safe supply-chain analysis research.",
            supporting_excerpt=(
                f"{name}'s research interests include quantum-safe supply-chain analysis."
            ),
        )
        _update_claim(
            claims,
            EvidenceClaimType.PUBLICATION,
            claim="A 2024 publication examines verified protocols for distributed data stores.",
            supporting_excerpt=(
                f"{name}'s 2024 publication examines verified protocols "
                "for distributed data stores."
            ),
            activity_year=2024,
        )

    return (
        ExtractedContent.model_validate({**page.model_dump(mode="python"), "content": content}),
        StructuredEvidenceExtractionResult(claims=claims),
    )
