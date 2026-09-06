# Week 4 step 3aj: approved 40/80 interaction policy

## Proposal approved by the user

> Next is the numerical budget policy. I recommend:
>
> - 40 calls to first Candidate review.
> - 80 calls total for an interaction allowing one search revision and final approval.
>
> The original 76/40 failure remains recorded. A paused run would show
> “within budget so far,” not “completed.”
>
> Shall I implement these 40/80 limits as a separate, versioned policy?

## User response

> yes

## Bounded implementation

- Add a separate versioned, typed policy over the existing offline interaction
  measurements. Do not replace or relabel the historical 40-call whole-case policy.
- First review allows at most 40 fake application-port invocations. The complete
  bounded interaction allows at most 80 total, including feedback/finalization.
- Scope covers one initial research pass, at most one research revision, and up
  to two accepted Candidate actions, with approval last. These are evaluation scope
  limits, not new production routing restrictions.
- Count actual resumed planning, including research restarted after rejection.
  Repeated request-more actions also cannot expand the allowance.
- Require completed state and final explicit Candidate approval for a completed
  interaction pass. Distinguish paused prefixes, exceeded budgets, unfinished
  terminal outcomes, and out-of-scope interactions.
- Preserve frozen scenarios, expected outcomes, source measurements, historical
  artifacts, graph behavior, approval gates, and legacy CLI behavior.
- Add an offline text/JSON report and focused tests; record the actual result,
  approval, rationale, commands, and remaining limitations in the documentation.
- No live provider calls, uploads, caching, model changes, new dependencies, or
  automatic commit/push.

## Concept

Changing a performance target is a policy decision, not an optimization. Keep the
old result and the approved new interpretation side by side. Being within budget
while paused does not establish completion or predict the cost of future work.
