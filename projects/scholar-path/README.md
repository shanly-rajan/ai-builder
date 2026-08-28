# ScholarPath

**Multi-Agent Doctoral Supervisor Discovery and Research-Fit System**

ScholarPath helps a prospective doctoral Candidate discover, verify, evaluate, and
shortlist research-aligned Supervisors through a Streamlit web application. It is
intended to replace hours of fragmented searching across university profiles and
academic publications with an evidence-backed, human-controlled workflow.

The system plans searches, discovers Prospective Supervisors, verifies supporting
evidence, evaluates Research Fit, and learns from Candidate feedback. It uses six
planned platform integrations while retaining a Candidate approval gate before any
Supervisor is shortlisted or any outreach is drafted.

## Project status

Product context captured. Design and implementation will proceed through small,
explicit milestones.

No implementation stack or dependency choices beyond those named in this product
brief are committed by this milestone.

## Target outcome and success measures

ScholarPath succeeds when one research run:

1. Produces five evidence-backed Supervisor recommendations in under 15 minutes.
2. Receives a relevant rating from the Candidate for at least four of the five
   recommendations.
3. Preserves the supporting evidence and rationale for every Research Fit assessment.
4. Gives the Candidate final control over rejection, further research, shortlisting,
   and any subsequent outreach drafting.
5. Traces, tests, and evaluates the complete workflow through LangSmith.

## Product principles

- **Evidence before recommendation:** discovery alone cannot qualify a Supervisor for
  Research Fit evaluation or Candidate review.
- **Explainable fit:** every score must include its supporting evidence, confidence,
  and a plain-language reason.
- **Human decision authority:** agents may recommend, but only the Candidate may move
  a Verified Supervisor to the shortlist.
- **No premature outreach:** outreach is not drafted before Candidate approval.
- **Source-aware resilience:** primary search and evidence paths have explicit fallback
  behavior.
- **Traceable execution:** agent decisions, tool calls, state transitions, retries,
  and evaluation results must be observable.
- **Feedback-driven refinement:** approvals and rejection reasons inform subsequent
  searches without replacing the Candidate's current instructions.

## Glossary

| Term | Definition |
|---|---|
| **Candidate** | The person pursuing a doctorate and using ScholarPath. |
| **Supervisor** | An academic or researcher who may supervise the Candidate's doctoral research. |
| **Prospective Supervisor** | A discovered Supervisor who has not yet completed verification and Candidate review. |
| **Verified Supervisor** | A Supervisor whose relevant information has been checked against supporting sources. |
| **Shortlisted Supervisor** | A Verified Supervisor approved by the Candidate. |
| **Rejected Supervisor** | A Supervisor excluded by the Candidate. |
| **Research Fit Score** | The assessed alignment between the Candidate's doctoral interests and a Supervisor's verified research profile. |

### Example Research Fit assessment

```text
Research Fit Score: 84/100
Confidence: High

Reason:
The Supervisor's work on enterprise architecture, digital transformation, and
organisational strategy aligns closely with the Candidate's proposed applied
research direction.
```

The score and confidence are decision-support signals, not proof of supervisory
availability or a substitute for the Candidate's judgment.

## Supervisor lifecycle

```mermaid
flowchart TD
    A[Raw Search Result] --> B[Prospective Supervisor]
    B --> C[Verified Supervisor]
    C --> D[Research Fit Evaluation]
    D --> E{Candidate Review}
    E -->|Reject| F[Rejected Supervisor]
    E -->|Approve| G[Shortlisted Supervisor]

    classDef human fill:#fff4cc,stroke:#9a6b00,stroke-width:2px;
    class E human;
```

Only the Candidate Review decision can create a Shortlisted Supervisor.

## Agents

| Agent | Responsibility |
|---|---|
| **Candidate Intake Agent** | Captures and structures the Candidate's proposed research area, preferences, and constraints. |
| **Research Planning Agent** | Expands the Candidate's interests into search concepts and prepares the research strategy. |
| **Supervisor Discovery Agent** | Finds Prospective Supervisors using You.com, with Tavily as a fallback. |
| **Evidence Verification Agent** | Verifies Supervisor identity, affiliation, research interests, publications, and stated supervisor availability. |
| **Research Fit Evaluation Agent** | Calculates and explains the Research Fit between the Candidate and each Verified Supervisor. |
| **Independent Review Agent** | Reviews the evidence and fit assessment using Nebius, identifying unsupported claims or inflated scores. |
| **Shortlist Synthesis Agent** | Produces the ranked set of Verified Supervisors for Candidate review. |
| **Preference Learning Agent** | Records Candidate rejection reasons, approvals, and search preferences through Mem0. |
| **Orchestrator Agent** | Coordinates workflow state, transitions, retries, tool fallback, and human approval using LangGraph. |

## Planned platform integrations

Agents are logical responsibilities; integrations are the external platforms used to
execute, coordinate, remember, or observe those responsibilities.

| Integration | Planned role |
|---|---|
| **You.com** | Primary Supervisor discovery search. |
| **Tavily** | Fallback Supervisor discovery search. |
| **Nebius** | Independent evidence and Research Fit review. |
| **Mem0** | Candidate preference and feedback memory. |
| **LangGraph** | Stateful multi-agent orchestration and human approval flow. |
| **LangSmith** | End-to-end tracing, testing, and evaluation. |

Streamlit is the planned Candidate-facing web interface.

## Central workflow

```mermaid
flowchart TD
    Start([START]) --> Load[load_candidate_preferences]
    Load --> Plan[plan_supervisor_searches]
    Plan --> Discover[discover_prospective_supervisors]
    Discover --> Found{enough_supervisors_found?}

    Found -->|No| Fallback[fallback_supervisor_search]
    Found -->|Yes| Dedupe[deduplicate_supervisors]
    Fallback --> Dedupe

    Dedupe --> Extract[extract_supervisor_evidence]
    Extract --> Sufficient{supervisor_evidence_sufficient?}
    Sufficient -->|No| Alternate[retry_alternate_evidence_source]
    Alternate --> Extract
    Sufficient -->|Yes| Evaluate[evaluate_research_fit]

    Evaluate --> Review[review_fit_assessments]
    Review --> Synthesize[synthesize_supervisor_shortlist]
    Synthesize --> Gate{candidate_review_gate}

    Gate -->|Reject| Feedback[capture_candidate_feedback]
    Feedback --> Refine[refine_search]
    Gate -->|Request more| Refine
    Refine --> Plan

    Gate -->|Approve| Save[save_shortlisted_supervisors]
    Save --> Briefing[generate_shortlist_briefing]
    Briefing --> End([END])

    classDef human fill:#fff4cc,stroke:#9a6b00,stroke-width:2px;
    class Gate human;
```

Retry limits, sufficiency thresholds, scoring dimensions, source-authority rules, and
data-retention policies remain implementation decisions for later milestones.
