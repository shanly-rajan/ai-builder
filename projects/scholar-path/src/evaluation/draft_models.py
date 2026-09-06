"""Review provenance for an offline-only dataset draft, not frozen ground truth."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from .models import (
    EvaluationModel,
    EvaluationScenario,
    EvaluationTargetKind,
    NonEmptyEvaluationString,
)


class DraftScenarioType(StrEnum):
    """Rubric categories, not the observed pass/fail result of a check."""

    HAPPY = "happy"
    EDGE = "edge"
    KNOWN_FAILURE = "known_failure"
    ADVERSARIAL = "adversarial"


class DraftEvaluationCase(EvaluationModel):
    """One executable scenario with an explicitly unreviewed proposed label."""

    scenario: EvaluationScenario
    scenario_type: DraftScenarioType
    origin: Literal["retained_v1", "new_synthetic_fixture"]
    source_reference: NonEmptyEvaluationString
    source_version: NonEmptyEvaluationString
    label_rationale: NonEmptyEvaluationString
    label_author: Literal["engineering_draft"] = "engineering_draft"
    human_review_status: Literal["pending"] = "pending"
    reviewer: None = None
    reviewed_at: None = None
    starting_outcome_previously_acknowledged: bool = Field(default=False, strict=True)
    starting_outcome_reference: NonEmptyEvaluationString | None = None

    @model_validator(mode="after")
    def provenance_is_explicit(self) -> Self:
        if self.scenario.target is EvaluationTargetKind.GRAPH_LIVE:
            raise ValueError("The review draft supports offline targets only")
        if self.starting_outcome_previously_acknowledged != (
            self.starting_outcome_reference is not None
        ):
            raise ValueError("An acknowledged starting outcome requires its provenance reference")
        if self.origin != "retained_v1" and self.starting_outcome_previously_acknowledged:
            raise ValueError("New labels have no prior starting-outcome acknowledgment")
        return self


def executable_case_fingerprint(scenario: EvaluationScenario) -> str:
    """Ignore titles/IDs/labels when detecting duplicate executable recipes."""
    recipe = scenario.model_dump(
        mode="json", include={"target", "candidate_preferences", "inputs", "config"}
    )
    return hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()


class EvaluationDraft(EvaluationModel):
    """Separately versioned, review-ready 30-case manifest with no approval shortcut."""

    dataset_name: NonEmptyEvaluationString
    draft_version: NonEmptyEvaluationString
    status: Literal["pending_human_review"] = "pending_human_review"
    cases: tuple[DraftEvaluationCase, ...] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_cohort(self) -> Self:
        identifiers = [case.scenario.scenario_id for case in self.cases]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Draft scenario IDs must be unique")
        fingerprints = [executable_case_fingerprint(case.scenario) for case in self.cases]
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("Draft scenarios must have distinct executable recipes")
        if Counter(case.scenario_type for case in self.cases) != {
            DraftScenarioType.HAPPY: 15,
            DraftScenarioType.EDGE: 9,
            DraftScenarioType.KNOWN_FAILURE: 4,
            DraftScenarioType.ADVERSARIAL: 2,
        }:
            raise ValueError("Draft mix must be 15 happy, 9 edge, 4 known-failure, 2 adversarial")
        if sum(case.origin == "retained_v1" for case in self.cases) != 11:
            raise ValueError("The draft must retain eleven original scenarios")
        return self

    @property
    def content_digest(self) -> str:
        """Identify this draft's content; this is not a human-review or freeze certificate."""
        serialized = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()
