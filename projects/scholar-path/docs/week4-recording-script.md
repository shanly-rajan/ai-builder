# ScholarPath — five-minute Week 4 recording script

**Shanly Rajan | AI Builder · Ready to record, not yet recorded.**
Read only the quoted paragraphs; the screen cues are not narration. Aim for
roughly five minutes including tab changes. Rehearse once and adjust speaking
pace; timestamps are a plan, not evidence of a completed video.

## Before pressing Record

- Open the [report](week4-submission-report.md), [reviewed dataset/approval](week4-label-review.md),
  [improvement ledger](week4-improvement-ledger.md), and
  [LangSmith comparison guide](week4-reviewed-langsmith-after.md).
- In that guide, pre-open the comparison, heading-case before/after, request-more
  and reject-then-approve links. Select the exact before and after experiment names.
  Confirm that the correct case IDs and feedback are visible before recording.
- Use only existing synthetic experiment pages. Hide unrelated browser tabs,
  workspace details, credentials and notifications. No live application run or
  new experiment upload is needed for this walkthrough.
- If LangSmith cannot be opened, show the saved reports as **offline evidence**;
  do not narrate them as a live UI inspection. Reviewer-access or redacted
  screenshot evidence must still be provided before submission.

## 0:00–0:35 — Problem and approach

Screen: report title and approach.

> Hi, I'm Shanly Rajan. ScholarPath helps postgraduate researchers find Supervisors
> with supporting evidence, while keeping the final shortlist decision with the
> Candidate. For Week 4, I moved from asking “does the demo work?” to “what can I
> measure and trust?” LangChain connects structured model outputs, LangGraph
> orchestrates the workflow, and LangSmith makes execution inspectable. This
> walkthrough evaluates that existing system; it is not another feature build.

## 0:35–1:15 — Dataset and success measures

Screen: dataset identity, approval ledger, report metric table.

> I froze thirty synthetic cases: fifteen happy paths, nine edge cases, four known
> failures and two adversarial cases. I approved five expected behaviors individually
> and the other twenty-five as an explicit batch. These are fictional fixtures,
> not thirty real research journeys. I measure five things: expected outcomes,
> evidence integrity, Candidate approval, target latency and tool effort. The bars
> are full applicable correctness, a five-second fake-target p95, and at most two
> component calls or forty calls for a whole graph case. The before and after runs
> use the same dataset and expectations.

## 1:15–2:15 — Follow one failure to its repair

Screen: heading-bound case before, the abbreviated illustrative excerpt in the
repair guide, then the same case after. Show case ID and `expected_behavior` feedback.

> The baseline passed twenty-nine of thirty cases. Here is the failure that mattered.
> A research statement appeared under the correct Supervisor profile, but a role
> sentence between the heading and research section was mistaken for a different
> person's name. The system rejected a legitimate claim. Other publication evidence
> still allowed overall verification, so checking only the final status would have
> missed the defect.
>
> I changed the bounded context rule, not the expected answer. Recognized role prose
> for the same person now preserves the heading link. Other-person headings,
> ambiguous text and unsupported claims remain blocked. The exact supporting text
> and source URL are retained locally. The after experiment passes thirty of thirty:
> one repaired case, or three-point-three-three percentage points. The saved traces
> let us connect that aggregate improvement to this specific expected behavior.

## 2:15–3:00 — Earlier iterations and their limits

Screen: improvement ledger, four-row table and provenance note.

> Three earlier focused repairs also have recorded results. Formatting-equivalent
> excerpts moved from zero of five passing checks to five of five. Section-label and
> academic-role handling moved from seventeen of thirty to thirty of thirty. Named
> academic specialisation moved from forty-two of fifty-six to fifty-six of
> fifty-six. Their current regression checks still pass.
>
> These are separate cohorts, and those repairs already existed in the frozen
> benchmark. I do not add their scores together or claim four gains on that
> benchmark. Their historical failures are journal records, not newly rerun
> pre-repair implementations. That evidence limitation remains in the report.

## 3:00–3:50 — What did not improve

Screen: request-more trace and interaction measurements/policy summary.

> Correctness improved, but effort did not. Requesting more research used
> thirty-eight calls to reach the first review and seventy-six across two research
> passes. It still fails the original forty-call whole-case bar. I separately
> approved forty calls to first review and eighty for a bounded interaction, but
> that is a policy clarification, not an optimization. Zero calls were saved.
>
> Nine interactions are paused within budget so far, not completed successes.
> The graph p95 also increased slightly in the hosted fake run. These timings and
> counters are not real model latency, tokens or billed cost, and a single run
> cannot establish a stable performance improvement.

## 3:50–4:30 — Human control and trace evidence

Screen: saved reject-then-approve trace; expand its graph child.

> This scripted rejection-and-approval case checks an important user boundary.
> A rejected Supervisor must leave the approval choices, and only explicitly
> approved IDs may reach the saved shortlist. The applicable approval checks remain
> twelve of twelve.
>
> The uploaded experiments contain thirty case roots, metric feedback and twelve
> matching graph-child traces. Application providers are fakes; LangSmith is the
> live observation service. Safe summaries show the route without exposing private
> research or credentials. These scripted actions test the approval mechanism;
> they are not a real Candidate endorsing actual Supervisors.

## 4:30–5:00 — Lessons and next steps

Screen: report limits and submission checklist.

> My biggest lesson: evaluate the specific user outcome, preserve evidence, and
> report what did not improve. The remaining work includes stronger comparable
> improvement evidence, repeatable live affiliation verification, real Candidate
> relevance ratings and measured usage. With more time, I would target those gaps
> and monitor versioned outcome failures, provider errors and latency in LangSmith.
> The report links the dataset, tests, prompts and traces. Thank you for reviewing
> ScholarPath.

## After recording

Add the actual video URL to the report's submission package. Check audio, five-minute
pacing, readable case IDs and feedback, and absence of private data. Confirm reviewer
access or attach appropriately redacted trace screenshots. Only then mark the
recording/access items complete and submit; this script alone does neither.

For a 60-second rehearsal, show the report's before/after table, the linked heading
case, and the unchanged 76/40 result. No fresh upload or paid call is needed.
