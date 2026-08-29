# ScholarPath Milestone M10 Prompt

Implement ScholarPath Milestone M10: persistent Candidate preference memory
using Mem0.

Create:

- CandidatePreferenceMemoryPort
- Mem0CandidatePreferenceAdapter
- FakeCandidatePreferenceMemory
- PreferenceLearningAgent
- CandidateMemoryRecord schema

Load relevant Candidate memories in load_candidate_preferences.

Store only durable Candidate preferences such as:

- preferred research themes
- preferred regions
- preferred study modes
- applied versus theoretical preference
- methodological preferences
- excluded research areas
- rejected Supervisor reasons
- previously useful search concepts

Do not use Mem0 as the source of truth for:

- Supervisor affiliation
- Supervisor publications
- Supervisor availability
- evidence URLs
- Research Fit Scores
- current graph position

Memory writes must occur only after an explicit Candidate action such as
approval, rejection, or direct preference submission.
Viewing a Supervisor must not create a memory.

Scope all memory operations by stable Candidate user ID.
Do not store unnecessary personal data.

Update the Research Planning Agent so relevant retrieved preferences are included
in the next SearchPlan.

Mem0 failure must be non-fatal. The graph should continue with current
CandidateProfile data and record that long-term memory was unavailable.

Add tests for:

1. Candidate memory loaded at graph start.
2. Rejection reason stored after explicit rejection.
3. Approval preference stored after explicit approval.
4. Viewing results causing no memory write.
5. Candidate A unable to retrieve Candidate B's memories.
6. Supervisor factual evidence never written to Mem0.
7. Memory failure not stopping the graph.
8. Retrieved preferences influencing FakePlanningModel input.
9. Duplicate preference handling.
10. No live Mem0 calls in default tests.
11. Optional live Mem0 test behind explicit opt-in.
