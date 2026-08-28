# Milestone M1 Prompt: Domain Models and Data Contracts

Implement ScholarPath Milestone M1: domain models and data contracts.

Do not add LangGraph or external API integrations yet.

Create typed Pydantic models and enums for:

1. CandidateProfile

   - candidate_id
   - proposed_research_statement
   - research_topics
   - preferred_regions
   - preferred_study_modes
   - preferred_research_orientation
   - methodological_interests
   - exclusions

2. SearchPlan

   - search_queries
   - expanded_research_concepts
   - target_regions
   - rationale

3. ProspectiveSupervisor

   - supervisor_id
   - full_name
   - institution
   - department
   - profile_url
   - discovery_source
   - discovery_query
   - status

4. EvidenceClaim

   - evidence_id
   - supervisor_id
   - claim_type
   - claim
   - source_url
   - source_kind
   - retrieved_at
   - confidence
   - directly_supported

5. VerifiedSupervisor

   - Supervisor identity and profile data
   - evidence collection
   - verification status
   - availability status
   - verification concerns

6. ResearchFitBreakdown

   - topic_alignment
   - methodological_alignment
   - research_orientation_alignment
   - recent_research_alignment
   - practical_constraint_alignment

7. ResearchFitAssessment

   - supervisor_id
   - overall_score from 0 to 100
   - breakdown
   - rationale
   - supporting_evidence_ids
   - confidence
   - concerns

8. CandidateReviewDecision

   - action: approve, reject, or request_more
   - supervisor_ids
   - reason
   - revised_preferences

9. SupervisorShortlist

   - candidate_id
   - shortlisted_supervisors
   - generated_at
   - briefing

Add explicit enums for Supervisor lifecycle status, evidence confidence,
availability status, source kind, and Candidate review action.

Add pure domain functions for valid Supervisor lifecycle transitions.
A Prospective Supervisor must not become a Verified Supervisor unless identity,
current affiliation, and research alignment evidence are present.
Availability may remain not_stated and must not block verification.

Add tests for:

- Valid construction and serialization of every model.
- Invalid URLs and empty required fields.
- Scores below 0 or above 100.
- Invalid lifecycle transitions.
- Verification with missing identity evidence.
- Verification with missing affiliation evidence.
- Availability remaining not_stated.
- Model JSON round trips.
- Canonical terminology.

Create realistic fixture factories for one Candidate, eight Prospective
Supervisors, six Verified Supervisors, and five Research Fit assessments.

Do not use an LLM for fixtures or validation.
