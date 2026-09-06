"""Locally frozen expected behaviors with explicit, scope-limited human provenance."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from .draft_models import EvaluationDraft
from .draft_scenarios import build_evaluation_draft
from .models import EvaluationModel, NonEmptyEvaluationString

REVIEWED_DATASET_NAME: Final = "scholarpath-week4-30case-reviewed-v1"
REVIEWED_VERSION: Final = "week4-30case-reviewed-v1"
SOURCE_DRAFT_DIGEST: Final = "f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e"
REVIEW_DATE: Final = date(2026, 9, 6)
_LEDGER_REFERENCE: Final = "docs/week4-label-review.md"
_BATCH_APPROVAL_RESPONSE: Final = (
    "approve case 5 and lets also approve the remaineder of the batches and move to next step"
)
_INDIVIDUAL_SCENARIO_IDS: Final = (
    "draft-evidence-heading-bound-research",
    "draft-evidence-confirmed-not-accepting",
    "draft-evidence-missing-identity",
    "draft-evidence-availability-without-statement",
    "draft-graph-reject-then-approve",
)
_EXACT_RESPONSES: Final = (
    "yes ScholarPath should accept the claim and It should retain the source URL and exact "
    "supporting text.",
    "yes approved",
    "yes approved",
    "approve",
    _BATCH_APPROVAL_RESPONSE,
    _BATCH_APPROVAL_RESPONSE,
)


class ExpectedBehaviorReviewDecision(EvaluationModel):
    """A conversational decision, not a claim of exhaustive technical-field review."""

    decision_id: Literal["001", "002", "003", "004", "005", "006"]
    review_method: Literal["individual", "batch"]
    scenario_ids: tuple[NonEmptyEvaluationString, ...] = Field(min_length=1, max_length=30)
    exact_user_response: NonEmptyEvaluationString
    ledger_reference: Literal["docs/week4-label-review.md"] = _LEDGER_REFERENCE
    approval_scope: Literal["expected_behaviors"] = "expected_behaviors"
    reviewer_role: Literal["project_owner"] = "project_owner"
    reviewed_on: date = REVIEW_DATE

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if self.reviewed_on != REVIEW_DATE:
            raise ValueError("Review date must match the recorded user decision")
        if len(set(self.scenario_ids)) != len(self.scenario_ids):
            raise ValueError("A review decision cannot repeat a scenario ID")
        index = int(self.decision_id) - 1
        if self.exact_user_response != _EXACT_RESPONSES[index]:
            raise ValueError("Review provenance must preserve the exact recorded user response")
        if index < len(_INDIVIDUAL_SCENARIO_IDS):
            if self.review_method != "individual" or self.scenario_ids != (
                _INDIVIDUAL_SCENARIO_IDS[index],
            ):
                raise ValueError("Individual approval must match its one reviewed scenario")
        elif self.review_method != "batch" or len(self.scenario_ids) != 25:
            raise ValueError("Decision 006 is one explicit batch approval for 25 remaining cases")
        return self


class ReviewedEvaluationManifest(EvaluationModel):
    """Frozen local behavior expectations; no upload, passing result, or release implied."""

    dataset_name: Literal["scholarpath-week4-30case-reviewed-v1"] = REVIEWED_DATASET_NAME
    reviewed_version: Literal["week4-30case-reviewed-v1"] = REVIEWED_VERSION
    status: Literal["frozen_local"] = "frozen_local"
    approval_scope: Literal["expected_behaviors"] = "expected_behaviors"
    source_draft_digest: str = Field(default=SOURCE_DRAFT_DIGEST, pattern=r"^[a-f0-9]{64}$")
    source_draft: EvaluationDraft
    reviewer_role: Literal["project_owner"] = "project_owner"
    reviewed_on: date = REVIEW_DATE
    decisions: tuple[ExpectedBehaviorReviewDecision, ...] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_frozen_review(self) -> Self:
        if self.reviewed_on != REVIEW_DATE:
            raise ValueError("Manifest date must match its recorded review decisions")
        # Pydantic normally trusts nested model instances. Revalidate provenance
        # so an unchecked model_copy cannot manufacture a reviewed decision.
        for decision in self.decisions:
            ExpectedBehaviorReviewDecision.model_validate(decision.model_dump())
        if (
            self.source_draft.dataset_name != "scholarpath-week4-30case-draft-v1"
            or self.source_draft.draft_version != "week4-30case-draft-v1"
            or self.source_draft_digest != SOURCE_DRAFT_DIGEST
            or self.source_draft.content_digest != SOURCE_DRAFT_DIGEST
        ):
            raise ValueError(
                "Reviewed source draft must match the fixed version and content digest"
            )
        if tuple(decision.decision_id for decision in self.decisions) != (
            "001",
            "002",
            "003",
            "004",
            "005",
            "006",
        ):
            raise ValueError("Review decisions must appear exactly once in ledger order")
        reviewed_ids = tuple(
            scenario_id for decision in self.decisions for scenario_id in decision.scenario_ids
        )
        scenario_ids = tuple(case.scenario.scenario_id for case in self.source_draft.cases)
        if len(set(reviewed_ids)) != len(reviewed_ids) or set(reviewed_ids) != set(scenario_ids):
            raise ValueError("Review decisions must cover every source scenario exactly once")
        remaining_ids = tuple(
            scenario_id
            for scenario_id in scenario_ids
            if scenario_id not in _INDIVIDUAL_SCENARIO_IDS
        )
        if self.decisions[-1].scenario_ids != remaining_ids:
            raise ValueError("Batch approval must preserve the remaining source-scenario order")
        return self

    @property
    def content_digest(self) -> str:
        """Hash executable labels and all recorded review provenance, without observations."""
        serialized = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()


def build_reviewed_manifest() -> ReviewedEvaluationManifest:
    """Reconcile recorded approvals with the exact draft; fail closed on any source drift."""
    draft = build_evaluation_draft()
    decision_ids: tuple[Literal["001", "002", "003", "004", "005"], ...] = (
        "001",
        "002",
        "003",
        "004",
        "005",
    )
    decisions = tuple(
        ExpectedBehaviorReviewDecision(
            decision_id=decision_id,
            review_method="individual",
            scenario_ids=(scenario_id,),
            exact_user_response=_EXACT_RESPONSES[index],
        )
        for index, (decision_id, scenario_id) in enumerate(
            zip(decision_ids, _INDIVIDUAL_SCENARIO_IDS, strict=True)
        )
    )
    remaining_ids = tuple(
        case.scenario.scenario_id
        for case in draft.cases
        if case.scenario.scenario_id not in _INDIVIDUAL_SCENARIO_IDS
    )
    return ReviewedEvaluationManifest(
        source_draft=draft,
        decisions=(
            *decisions,
            ExpectedBehaviorReviewDecision(
                decision_id="006",
                review_method="batch",
                scenario_ids=remaining_ids,
                exact_user_response=_BATCH_APPROVAL_RESPONSE,
            ),
        ),
    )
