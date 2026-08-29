# Milestone M5 prompt: resilient Supervisor discovery with Tavily fallback

Implement ScholarPath Milestone M5: resilient Supervisor discovery with Tavily
fallback.

Add the current official `langchain-tavily` package. Do not use deprecated
community Tavily imports.

Create:

- `TavilySearchAdapter` implementing `SupervisorSearchPort`
- `SearchProviderError`
- `SearchAttempt` record
- `DiscoveryPolicy`
- Pure routing function `route_after_supervisor_discovery`

The `DiscoveryPolicy` must define:

- minimum unique Prospective Supervisors
- maximum retry count for You.com
- maximum Tavily fallback count
- timeout behaviour
- duplicate-result threshold
- stopping condition

Route to Tavily when:

- You.com times out after one retry.
- You.com returns a retryable provider error.
- Too few unique Prospective Supervisors are found.
- Results are mostly duplicates.
- Results contain too few plausible Supervisor profiles.

Persist in graph state:

- provider used
- query
- attempt number
- result count
- error category
- `fallback_search_used`

Allow partial success. If six useful Prospective Supervisors were found before
one later query failed, retain those six.

Add tests for:

1. Successful You.com route without Tavily.
2. You.com timeout followed by one retry.
3. Retry failure followed by Tavily.
4. Empty You.com results followed by Tavily.
5. Duplicate-heavy results followed by Tavily.
6. Non-retryable authentication error stopping immediately.
7. Partial results surviving a later provider failure.
8. Both providers failing and the graph ending with a clear recoverable status.
9. Retry limits preventing infinite loops.
10. Existing graph-state and terminology tests.

Add a deterministic failure-injection setting for demonstrations, but keep it
off by default.

Do not implement evidence extraction yet.
