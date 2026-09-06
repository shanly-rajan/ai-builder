"""Private capture is opt-in, non-disruptive, and absent from aggregate output."""

import json
from itertools import product
from pathlib import Path

import pytest
from scripts.replay_grounding import main

from scholarpath.agents.evidence_verification import (
    EvidenceGroundingDiagnostics,
    EvidenceVerificationAgent,
    RejectedExcerptObserver,
    StructuredEvidenceClaimDraft,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import EvidenceClaim, GroundingFailureReason, SourceKind
from scholarpath.evaluation.grounding_replay import (
    PrivateReplayError,
    RejectedExcerptCapture,
    read_private_replay,
    replay_snapshot,
    write_private_replay,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeEvidenceVerificationModel, FakeResearchFitModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT, make_candidate_profile
from tests.integration import test_m13_live_canary as canary
from tests.unit.agents.test_official_profile_evidence_context import (
    PAGE_NAME,
    PROFILE_URL,
    _affiliation_draft,
    _identity_draft,
    _supervisor,
)
from tests.unit.agents.test_profile_subject_binding_regressions import _research_draft

PRIVATE = "private-candidate@example.test api_key=secret-sentinel"
AFFILIATION = (
    "Current position: Professor Alice Example is in the "
    "School of Management, University of Bradford."
)
RESEARCH = "Distributed systems are studied using formal models."


def _inputs(
    *, model_supported: bool = True, identity_present: bool = True
) -> tuple[FakeEvidenceVerificationModel, ExtractedContent]:
    drafts: list[StructuredEvidenceClaimDraft] = [_identity_draft()] if identity_present else []
    drafts.extend(
        [
            _affiliation_draft(supporting_excerpt=AFFILIATION).model_copy(
                update={"claim": PRIVATE, "directly_supported": model_supported}
            ),
            _research_draft().model_copy(
                update={
                    "claim": PRIVATE,
                    "supporting_excerpt": RESEARCH,
                    "directly_supported": model_supported,
                }
            ),
        ]
    )
    return (
        FakeEvidenceVerificationModel(
            {PROFILE_URL: StructuredEvidenceExtractionResult(claims=drafts)}
        ),
        ExtractedContent.model_validate(
            {
                "source_url": PROFILE_URL,
                "content": f"# {PAGE_NAME}\n{AFFILIATION}\n{RESEARCH}\n{PRIVATE}",
                "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
            }
        ),
    )


class _BrokenObserver:
    def observe(
        self, *, expected_name: str, claim: EvidenceClaim, failure: GroundingFailureReason
    ) -> None:
        raise RuntimeError(PRIVATE)


@pytest.mark.parametrize("observer_kind", ["disabled", "capture", "broken"])
def test_private_observer_does_not_change_claims_records_or_aggregate_diagnostics(
    observer_kind: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capture = RejectedExcerptCapture()
    observer: RejectedExcerptObserver | None = None
    if observer_kind == "capture":
        observer = capture
    elif observer_kind == "broken":
        observer = _BrokenObserver()
    outputs = []
    for sink in (None, observer):
        model, content = _inputs()
        diagnostics = EvidenceGroundingDiagnostics()
        agent = EvidenceVerificationAgent(model)
        claims = agent.extract_claims(
            _supervisor(),
            content,
            SourceKind.UNIVERSITY_PROFILE,
            diagnostics=diagnostics,
            rejected_excerpt_observer=sink,
        )
        record = agent.build_verification_record(_supervisor(), claims)
        assert record.verified_supervisor is None
        assert model.call_count == 1
        outputs.append((claims, record, diagnostics.summary()))
    assert outputs[0] == outputs[1]
    snapshot = capture.snapshot()
    assert len(snapshot.samples) == (2 if observer_kind == "capture" else 0)
    assert replay_snapshot(snapshot).changed_count == 0
    assert PRIVATE not in snapshot.model_dump_json()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(("model_supported", "identity_present"), [(False, True), (True, False)])
def test_unsupported_or_identity_missing_drafts_are_not_captured(
    model_supported: bool,
    identity_present: bool,
) -> None:
    model, content = _inputs(model_supported=model_supported, identity_present=identity_present)
    capture = RejectedExcerptCapture()
    EvidenceVerificationAgent(model).extract_claims(
        _supervisor(),
        content,
        SourceKind.UNIVERSITY_PROFILE,
        rejected_excerpt_observer=capture,
    )
    assert capture.snapshot().samples == ()
    assert model.call_count == 1


@pytest.mark.parametrize("flags", list(product((False, True), repeat=3)))
def test_private_capture_requires_all_three_environment_opt_ins(
    flags: tuple[bool, bool, bool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = (*canary._LIVE_FLAGS, "SCHOLARPATH_CAPTURE_GROUNDING_REPLAY")
    for name, enabled in zip(names, flags, strict=True):
        monkeypatch.setenv(name, "true" if enabled else "false")
    capture = canary._configured_private_capture()
    assert (capture is not None) is all(flags)
    if capture is not None:
        assert capture.snapshot().origin == "live_canary"


def test_canary_default_capture_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*canary._LIVE_FLAGS, "SCHOLARPATH_CAPTURE_GROUNDING_REPLAY"):
        monkeypatch.delenv(name, raising=False)
    assert canary._configured_private_capture() is None


def test_fake_canary_captures_two_excerpts_without_extra_calls_or_public_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, content = _inputs()
    fit_model = FakeResearchFitModel()
    capture = RejectedExcerptCapture(origin="synthetic_fixture")
    monkeypatch.setattr(
        canary,
        "classify_evidence_source_kind",
        lambda *args, **kwargs: SourceKind.UNIVERSITY_PROFILE,
    )
    with (
        pytest.raises(canary._MissingRequiredEvidenceError),
        canary._summarized_call_budget() as budget,
    ):
        try:
            canary._verify_and_evaluate(
                profile=make_candidate_profile(),
                prospective=_supervisor(),
                extracted_content=content,
                evidence_model=canary._BudgetedEvidenceModel(model, budget),
                research_fit_model=canary._BudgetedResearchFitModel(fit_model, budget),
                budget=budget,
                rejected_excerpt_observer=capture,
            )
        finally:
            canary._save_private_replay(capture, project_root=tmp_path)
    output = capsys.readouterr()
    captured_event, aggregate = [json.loads(line) for line in output.out.splitlines()]
    assert captured_event["status"] == "written"
    assert captured_event["sample_count"] == 2
    assert captured_event["excluded_count"] == 0
    assert aggregate["total_provider_calls"] == model.call_count == 1
    assert aggregate["provider_calls"]["openai_research_fit"] == fit_model.call_count == 0
    assert aggregate["stage_outcomes"]["evidence_verification"]["status"] == "failed"
    path = tmp_path / "artifacts" / "grounding-replays" / captured_event["file_name"]
    snapshot = read_private_replay(path)
    assert replay_snapshot(snapshot).matched_count == 2
    for value in (
        PRIVATE,
        PAGE_NAME,
        PROFILE_URL,
        AFFILIATION,
        RESEARCH,
        _supervisor().supervisor_id,
    ):
        assert value not in output.out + output.err
    assert PRIVATE not in path.read_text()


def test_private_write_failure_does_not_expose_exception_or_change_canary_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise PrivateReplayError(PRIVATE)

    monkeypatch.setattr(canary, "write_private_replay", fail)
    canary._save_private_replay(RejectedExcerptCapture(), project_root=tmp_path)
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == "unavailable"
    assert PRIVATE not in output.out + output.err
    assert not (tmp_path / "artifacts").exists()


def test_cli_replays_without_displaying_private_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model, content = _inputs()
    capture = RejectedExcerptCapture()
    EvidenceVerificationAgent(model).extract_claims(
        _supervisor(),
        content,
        SourceKind.UNIVERSITY_PROFILE,
        rejected_excerpt_observer=capture,
    )
    path = write_private_replay(capture, tmp_path)
    assert path is not None
    assert main([str(path)]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out.splitlines()[0])["matched_count"] == 2
    for value in (PRIVATE, PAGE_NAME, PROFILE_URL, AFFILIATION, RESEARCH):
        assert value not in output.out + output.err


def test_cli_unreadable_file_has_safe_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "private-person@example.test")]) == 2
    output = capsys.readouterr()
    assert "private-person@example.test" not in output.out + output.err
    assert "No content displayed" in output.out


@pytest.mark.parametrize("arguments", [[], ["safe.json", PRIVATE], [f"--{PRIVATE}"]])
def test_cli_invalid_arguments_never_echo_private_input(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(arguments) == 2
    output = capsys.readouterr()
    assert PRIVATE not in output.out + output.err
    assert "No content displayed" in output.out
