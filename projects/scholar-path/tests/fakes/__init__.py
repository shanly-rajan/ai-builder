"""Provider-neutral fakes used by ScholarPath's offline test suite."""

from tests.fakes.content_extraction import (
    FakeContentExtraction,
    make_fixed_content_outcomes,
    make_graph_content_outcomes,
)
from tests.fakes.evidence import (
    FakeEvidenceVerificationModel,
    make_alternate_official_response,
    make_complete_evidence_response,
    make_conflicting_affiliation_response,
    make_fixed_evidence_outcomes,
    make_graph_evidence_outcomes,
    make_missing_affiliation_response,
    make_missing_research_response,
)
from tests.fakes.independent_review import (
    FakeIndependentReviewModel,
    make_accepted_review,
    make_revised_review,
)
from tests.fakes.memory import FakeCandidatePreferenceMemory, unavailable_candidate_memory
from tests.fakes.planning import FakePlanningModel, make_valid_planning_response
from tests.fakes.research_fit import (
    FakeResearchFitModel,
    make_graph_research_fit_response,
    make_strong_research_fit_response,
    make_superficial_keyword_research_fit_response,
    make_weak_research_fit_response,
)
from tests.fakes.search import FakeSupervisorSearch, make_fake_search_outcomes

__all__ = [
    "FakeContentExtraction",
    "FakeEvidenceVerificationModel",
    "FakeIndependentReviewModel",
    "FakeCandidatePreferenceMemory",
    "FakePlanningModel",
    "FakeResearchFitModel",
    "FakeSupervisorSearch",
    "make_alternate_official_response",
    "make_accepted_review",
    "make_complete_evidence_response",
    "make_conflicting_affiliation_response",
    "make_fake_search_outcomes",
    "make_fixed_content_outcomes",
    "make_fixed_evidence_outcomes",
    "make_graph_content_outcomes",
    "make_graph_evidence_outcomes",
    "make_graph_research_fit_response",
    "make_missing_affiliation_response",
    "make_missing_research_response",
    "make_revised_review",
    "make_strong_research_fit_response",
    "make_superficial_keyword_research_fit_response",
    "make_valid_planning_response",
    "make_weak_research_fit_response",
    "unavailable_candidate_memory",
]
