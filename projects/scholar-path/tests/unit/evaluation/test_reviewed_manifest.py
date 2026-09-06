"""Local freeze records actual approval scope without rewriting or repairing the draft."""

import hashlib
import json
from collections import Counter
from datetime import date

import pytest
from pydantic import ValidationError

from scholarpath.evaluation import reviewed_manifest
from scholarpath.evaluation.draft_models import EvaluationDraft
from scholarpath.evaluation.draft_scenarios import build_evaluation_draft
from scholarpath.evaluation.reviewed_manifest import (
    REVIEW_DATE,
    REVIEWED_DATASET_NAME,
    REVIEWED_VERSION,
    SOURCE_DRAFT_DIGEST,
    ExpectedBehaviorReviewDecision,
    ReviewedEvaluationManifest,
    build_reviewed_manifest,
)
from scholarpath.evaluation.scenarios import EVALUATION_DATASET_NAME, EVALUATION_SCENARIOS


def test_local_manifest_is_separate_and_preserves_the_original_draft_and_eleven_cases() -> None:
    draft = build_evaluation_draft()
    manifest = build_reviewed_manifest()

    assert manifest.source_draft == draft == build_evaluation_draft()
    assert (
        manifest.source_draft.content_digest == manifest.source_draft_digest == SOURCE_DRAFT_DIGEST
    )
    assert manifest.dataset_name == REVIEWED_DATASET_NAME
    assert manifest.dataset_name not in {draft.dataset_name, EVALUATION_DATASET_NAME}
    assert manifest.reviewed_version == REVIEWED_VERSION
    assert manifest.status == "frozen_local"
    assert manifest.approval_scope == "expected_behaviors"
    assert draft.status == "pending_human_review"
    assert all(case.human_review_status == "pending" for case in manifest.source_draft.cases)
    assert tuple(case.scenario for case in manifest.source_draft.cases[:11]) == EVALUATION_SCENARIOS
    original = json.dumps(
        [case.model_dump(mode="json") for case in EVALUATION_SCENARIOS], sort_keys=True
    )
    assert hashlib.sha256(original.encode()).hexdigest() == (
        "d86374ba9cc97f75d1fac5c430278824204cd5c9658fe7a29d23bef042da1fb3"
    )


def test_manifest_records_five_individual_decisions_and_one_actual_batch_response() -> None:
    manifest = build_reviewed_manifest()
    assert manifest.reviewer_role == "project_owner"
    assert manifest.reviewed_on == REVIEW_DATE == date(2026, 9, 6)
    assert tuple(decision.decision_id for decision in manifest.decisions) == (
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
    )
    assert tuple(decision.scenario_ids[0] for decision in manifest.decisions[:5]) == (
        "draft-evidence-heading-bound-research",
        "draft-evidence-confirmed-not-accepting",
        "draft-evidence-missing-identity",
        "draft-evidence-availability-without-statement",
        "draft-graph-reject-then-approve",
    )
    assert Counter(decision.review_method for decision in manifest.decisions) == {
        "individual": 5,
        "batch": 1,
    }
    assert tuple(len(decision.scenario_ids) for decision in manifest.decisions) == (
        1,
        1,
        1,
        1,
        1,
        25,
    )
    assert tuple(decision.exact_user_response for decision in manifest.decisions) == (
        "yes ScholarPath should accept the claim and It should retain the source URL and exact "
        "supporting text.",
        "yes approved",
        "yes approved",
        "approve",
        "approve case 5 and lets also approve the remaineder of the batches and move to next step",
        "approve case 5 and lets also approve the remaineder of the batches and move to next step",
    )
    for decision in manifest.decisions:
        assert decision.approval_scope == "expected_behaviors"
        assert decision.reviewer_role == "project_owner"
        assert decision.reviewed_on == REVIEW_DATE
        assert decision.ledger_reference == "docs/week4-label-review.md"
    ids = [scenario_id for decision in manifest.decisions for scenario_id in decision.scenario_ids]
    assert len(ids) == len(set(ids)) == 30
    assert set(ids) == {case.scenario.scenario_id for case in manifest.source_draft.cases}


def test_reviewed_manifest_and_every_decision_round_trip() -> None:
    manifest = build_reviewed_manifest()
    assert ReviewedEvaluationManifest.model_validate_json(manifest.model_dump_json()) == manifest
    for decision in manifest.decisions:
        assert (
            ExpectedBehaviorReviewDecision.model_validate_json(decision.model_dump_json())
            == decision
        )


def test_digest_is_reproducible_and_includes_all_provenance() -> None:
    manifest = build_reviewed_manifest()
    expected_digest = hashlib.sha256(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    assert manifest.content_digest == expected_digest == build_reviewed_manifest().content_digest
    assert manifest.content_digest != manifest.source_draft_digest
    # model_copy intentionally bypasses validation here to prove the fingerprint
    # includes provenance, not to create another approved manifest.
    changed_decision = manifest.decisions[0].model_copy(update={"exact_user_response": "changed"})
    changed = manifest.model_copy(update={"decisions": (changed_decision, *manifest.decisions[1:])})
    assert changed.content_digest != manifest.content_digest
    with pytest.raises(ValidationError, match="exact recorded user response"):
        ReviewedEvaluationManifest.model_validate(changed.model_dump())


def test_preconstructed_decision_cannot_bypass_provenance_validation() -> None:
    manifest = build_reviewed_manifest()
    forged = manifest.decisions[0].model_copy(update={"exact_user_response": "invented approval"})
    with pytest.raises(ValidationError, match="exact recorded user response"):
        ReviewedEvaluationManifest(
            source_draft=manifest.source_draft,
            decisions=(forged, *manifest.decisions[1:]),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset_name", "old-dataset"),
        ("reviewed_version", "next-version"),
        ("status", "uploaded"),
        ("approval_scope", "all_technical_fields"),
        ("reviewer_role", "independent_reviewer"),
        ("reviewed_on", "2026-09-07"),
        ("source_draft_digest", "0" * 64),
    ],
)
def test_manifest_rejects_unrecorded_scope_or_identity(field: str, value: str) -> None:
    raw = build_reviewed_manifest().model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        ReviewedEvaluationManifest.model_validate(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_decision",
        "duplicate_decision",
        "reordered_decisions",
        "missing_case",
        "unknown_case",
        "duplicate_case",
        "cross_decision_duplicate",
        "batch_order",
        "batch_as_individual",
        "changed_individual_case",
        "individual_as_batch",
        "expanded_scope",
        "invented_response",
        "invented_date",
        "invented_reviewer",
        "invented_source",
    ],
)
def test_manifest_rejects_incomplete_or_fabricated_review_provenance(mutation: str) -> None:
    raw = build_reviewed_manifest().model_dump(mode="json")
    decisions = raw["decisions"]
    if mutation == "missing_decision":
        decisions.pop()
    elif mutation == "duplicate_decision":
        decisions[1] = decisions[0]
    elif mutation == "reordered_decisions":
        decisions[0], decisions[1] = decisions[1], decisions[0]
    elif mutation == "missing_case":
        decisions[-1]["scenario_ids"].pop()
    elif mutation == "unknown_case":
        decisions[-1]["scenario_ids"][0] = "unknown-case"
    elif mutation == "duplicate_case":
        decisions[-1]["scenario_ids"][0] = decisions[-1]["scenario_ids"][1]
    elif mutation == "cross_decision_duplicate":
        decisions[-1]["scenario_ids"][0] = decisions[0]["scenario_ids"][0]
    elif mutation == "batch_order":
        decisions[-1]["scenario_ids"].reverse()
    elif mutation == "batch_as_individual":
        decisions[-1]["review_method"] = "individual"
    elif mutation == "changed_individual_case":
        decisions[0]["scenario_ids"] = [decisions[-1]["scenario_ids"][0]]
    elif mutation == "individual_as_batch":
        decisions[0]["review_method"] = "batch"
    elif mutation == "expanded_scope":
        decisions[0]["approval_scope"] = "all_technical_fields"
    elif mutation == "invented_response":
        decisions[0]["exact_user_response"] = "all tests now pass"
    elif mutation == "invented_date":
        decisions[0]["reviewed_on"] = "2026-09-07"
    elif mutation == "invented_reviewer":
        decisions[0]["reviewer_role"] = "independent_reviewer"
    else:
        decisions[0]["ledger_reference"] = "invented-review.md"
    with pytest.raises(ValidationError):
        ReviewedEvaluationManifest.model_validate(raw)


@pytest.mark.parametrize(
    "mutation", ["label", "expectation", "input", "source", "dataset", "version", "review"]
)
def test_changed_source_draft_cannot_reuse_this_frozen_manifest(mutation: str) -> None:
    raw = build_reviewed_manifest().model_dump(mode="json")
    draft = raw["source_draft"]
    if mutation == "label":
        draft["cases"][0]["label_rationale"] += " Changed expected behavior."
    elif mutation == "expectation":
        draft["cases"][2]["scenario"]["expected"]["expected_availability_status"] = (
            "confirmed_accepting"
        )
    elif mutation == "input":
        draft["cases"][-1]["scenario"]["config"]["graph_case"] = "approval_pause"
    elif mutation == "source":
        draft["cases"][0]["source_reference"] = "different-source.md"
    elif mutation == "dataset":
        draft["dataset_name"] = "different-draft"
    elif mutation == "version":
        draft["draft_version"] = "new-draft-version"
    else:
        draft["cases"][0]["human_review_status"] = "approved"
    with pytest.raises(ValidationError):
        ReviewedEvaluationManifest.model_validate(raw)


def test_builder_fails_closed_if_mutable_source_catalog_drifts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = build_evaluation_draft().model_dump(mode="json")
    raw["cases"][0]["label_rationale"] += " Source has drifted."
    changed_draft = EvaluationDraft.model_validate(raw)
    monkeypatch.setattr(reviewed_manifest, "build_evaluation_draft", lambda: changed_draft)
    with pytest.raises(ValidationError, match="fixed version and content digest"):
        build_reviewed_manifest()


def test_builder_does_not_execute_targets_or_call_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scholarpath.evaluation import runner

    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("Building a reviewed manifest cannot execute targets or providers")

    for name in ("dispatch_evaluation_target", "Client", "sync_evaluation_dataset"):
        monkeypatch.setattr(runner, name, unexpected_call)
    for flag in (
        "LANGSMITH_TRACING",
        "SCHOLARPATH_RUN_LIVE_TESTS",
        "SCHOLARPATH_RUN_LANGSMITH_EVALS",
    ):
        monkeypatch.setenv(flag, "true")
    assert len(build_reviewed_manifest().source_draft.cases) == 30
