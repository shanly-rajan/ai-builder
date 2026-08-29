"""Privacy-safe LangSmith trace tags for ScholarPath evaluation targets."""

from __future__ import annotations

from typing import Annotated, Final, Self

from langsmith.run_helpers import get_current_run_tree
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .models import CandidateReviewOutcome, EvaluationTargetKind

EVALUATION_APPLICATION: Final = "scholarpath"
type EvaluationTraceScalar = str | int | float | bool

NonEmptyTraceString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

SAFE_EVALUATION_TRACE_METADATA_KEYS: Final = (
    "application",
    "environment",
    "graph_version",
    "prompt_version",
    "model_provider",
    "fallback_search_used",
    "candidate_review_outcome",
    "evaluation_target",
    "evaluation_scenario_id",
)


class EvaluationTraceContext(BaseModel):
    """Allowlisted trace dimensions with no Candidate or source content."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    scenario_id: NonEmptyTraceString
    target: EvaluationTargetKind
    environment: NonEmptyTraceString
    graph_version: NonEmptyTraceString
    prompt_versions: tuple[NonEmptyTraceString, ...] = Field(min_length=1)
    model_providers: tuple[NonEmptyTraceString, ...] = Field(min_length=1)
    fallback_search_used: bool | None = None
    candidate_review_outcome: CandidateReviewOutcome = CandidateReviewOutcome.NOT_APPLICABLE

    @field_validator("prompt_versions", "model_providers")
    @classmethod
    def trace_dimensions_must_be_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Avoid duplicate inherited tags while retaining stable ordering."""
        normalized = [value.casefold() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Evaluation trace dimensions must be unique")
        return values

    def tags(self) -> list[str]:
        """Return the complete required evaluation tag set."""
        fallback_value = (
            str(self.fallback_search_used).lower()
            if self.fallback_search_used is not None
            else "not_applicable"
        )
        return [
            f"application:{EVALUATION_APPLICATION}",
            f"environment:{self.environment}",
            f"graph-version:{self.graph_version}",
            *(f"prompt-version:{value}" for value in self.prompt_versions),
            *(f"model-provider:{value}" for value in self.model_providers),
            f"fallback-used:{fallback_value}",
            f"candidate-review-outcome:{self.candidate_review_outcome.value}",
            f"evaluation-target:{self.target.value}",
        ]

    def metadata(self) -> dict[str, EvaluationTraceScalar]:
        """Return only scalar allowlisted metadata safe for LangSmith filters."""
        prompt_version = self.prompt_versions[0] if len(self.prompt_versions) == 1 else "multiple"
        model_provider = self.model_providers[0] if len(self.model_providers) == 1 else "multiple"
        raw: dict[str, object] = {
            "application": EVALUATION_APPLICATION,
            "environment": self.environment,
            "graph_version": self.graph_version,
            "prompt_version": prompt_version,
            "model_provider": model_provider,
            "candidate_review_outcome": self.candidate_review_outcome.value,
            "evaluation_target": self.target.value,
            "evaluation_scenario_id": self.scenario_id,
        }
        if self.fallback_search_used is not None:
            raw["fallback_search_used"] = self.fallback_search_used
        return sanitize_evaluation_trace_metadata(raw)

    def with_outcome(
        self,
        *,
        fallback_search_used: bool | None,
        candidate_review_outcome: CandidateReviewOutcome,
    ) -> Self:
        """Return a revalidated context after dynamic graph outcomes are known."""
        return self.__class__.model_validate(
            {
                **self.model_dump(mode="python"),
                "fallback_search_used": fallback_search_used,
                "candidate_review_outcome": candidate_review_outcome,
            }
        )


def sanitize_evaluation_trace_metadata(
    metadata: dict[str, object],
) -> dict[str, EvaluationTraceScalar]:
    """Drop unknown keys and non-scalar values before trace mutation."""
    sanitized: dict[str, EvaluationTraceScalar] = {}
    for key in SAFE_EVALUATION_TRACE_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
    return sanitized


def tag_current_evaluation_run(
    context: EvaluationTraceContext,
    *,
    include_static: bool = True,
    include_dynamic: bool = True,
) -> bool:
    """Attach selected safe dimensions to the active LangSmith target run."""
    run = get_current_run_tree()
    if run is None:
        return False
    dynamic_tag_prefixes = ("fallback-used:", "candidate-review-outcome:")
    dynamic_metadata_keys = {"fallback_search_used", "candidate_review_outcome"}
    tags = context.tags()
    metadata = context.metadata()
    if not include_static:
        tags = [tag for tag in tags if tag.startswith(dynamic_tag_prefixes)]
        metadata = {key: value for key, value in metadata.items() if key in dynamic_metadata_keys}
    if not include_dynamic:
        tags = [tag for tag in tags if not tag.startswith(dynamic_tag_prefixes)]
        metadata = {
            key: value for key, value in metadata.items() if key not in dynamic_metadata_keys
        }
    run.add_tags(tags)
    run.add_metadata(metadata)
    return True
