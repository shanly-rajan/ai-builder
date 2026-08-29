"""Provider-neutral fakes used by ScholarPath's offline test suite."""

from tests.fakes.planning import FakePlanningModel, make_valid_planning_response
from tests.fakes.search import FakeSupervisorSearch, make_fake_search_outcomes

__all__ = [
    "FakePlanningModel",
    "FakeSupervisorSearch",
    "make_fake_search_outcomes",
    "make_valid_planning_response",
]
