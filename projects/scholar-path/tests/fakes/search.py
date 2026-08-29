"""Recording fake for the provider-neutral Supervisor search boundary."""

from collections.abc import Mapping

from scholarpath.domain import SearchResult
from scholarpath.graph import build_walking_skeleton_fixtures
from tests.fakes.planning import make_valid_planning_response

type SearchOutcome = tuple[SearchResult, ...] | Exception


def make_fake_search_outcomes() -> dict[str, tuple[SearchResult, ...]]:
    """Map the default fake plan to eight invented academic profile results."""
    queries = tuple(item.query for item in make_valid_planning_response().search_queries)
    raw_results = build_walking_skeleton_fixtures().raw_search_results
    outcomes: dict[str, list[SearchResult]] = {query: [] for query in queries}
    for index, raw in enumerate(raw_results):
        query = queries[min(index // 2, len(queries) - 1)]
        outcomes[query].append(
            SearchResult(
                url=raw.profile_url,
                title=f"{raw.full_name} | {raw.department} | {raw.institution}",
                description=(f"{raw.full_name} is an academic researcher at {raw.institution}."),
                publication_date=None,
                originating_query=query,
            )
        )
    return {query: tuple(results) for query, results in outcomes.items()}


class FakeSupervisorSearch:
    """Return scripted SearchResult batches and record every exact query."""

    def __init__(
        self,
        outcomes: Mapping[str, SearchOutcome] | None = None,
        *,
        scripts: Mapping[str, list[SearchOutcome]] | None = None,
    ) -> None:
        self._outcomes = dict(outcomes or make_fake_search_outcomes())
        self._scripts = {query: list(items) for query, items in (scripts or {}).items()}
        self.calls: list[str] = []

    def search(self, query: str) -> tuple[SearchResult, ...]:
        """Record one query, then return or raise its configured outcome."""
        self.calls.append(query)
        scripted = self._scripts.get(query)
        outcome = scripted.pop(0) if scripted else self._outcomes.get(query, ())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
