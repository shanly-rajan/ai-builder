"""Private replay retains bounded synthetic excerpts without widening grounding."""

from __future__ import annotations

import json
import stat
import traceback
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import HttpUrl, ValidationError

from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    GroundingFailureReason,
    SourceKind,
)
from scholarpath.evaluation import grounding_replay as replay_module
from scholarpath.evaluation.grounding_replay import (
    GroundingReplaySnapshot,
    PrivateReplayError,
    RejectedExcerptCapture,
    read_private_replay,
    replay_details,
    replay_snapshot,
    write_private_replay,
)
from tests.unit.domain.test_grounding_failure_reasons import _claim

_NAME = "Dr Alex Morgan"
_EXCERPT = "Research interests: Dr Jane Smith studies safety."
_REASON = GroundingFailureReason.CONTEXT_CONFLICTING_PERSON
_SAMPLE_FIELDS = {
    "claim_type",
    "expected_name",
    "asserted_name",
    "supporting_excerpt",
    "source_url",
    "source_kind",
    "observed_reason",
}


def _research_claim(**updates: object) -> EvidenceClaim:
    return _claim(
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        supporting_excerpt=_EXCERPT,
    ).model_copy(update=updates)


def _capture(
    claim: EvidenceClaim | None = None,
    *,
    expected_name: str = _NAME,
    reason: GroundingFailureReason = _REASON,
) -> RejectedExcerptCapture:
    capture = RejectedExcerptCapture(origin="synthetic_fixture")
    capture.observe(
        expected_name=expected_name,
        claim=claim if claim is not None else _research_claim(),
        failure=reason,
    )
    return capture


def _write_capture(project_root: Path) -> Path:
    path = write_private_replay(_capture(), project_root=project_root)
    assert path is not None
    return path


def test_capture_retains_only_two_distinct_eligible_claim_types() -> None:
    capture = _capture()
    first = capture.snapshot()
    capture.observe(
        expected_name=_NAME,
        claim=_research_claim(supporting_excerpt="Another rejected research excerpt."),
        failure=GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
    )
    capture.observe(
        expected_name=_NAME,
        claim=_research_claim(claim_type=EvidenceClaimType.CURRENT_AFFILIATION),
        failure=_REASON,
    )
    capture.observe(
        expected_name=_NAME,
        claim=_research_claim(claim_type=EvidenceClaimType.CURRENT_AFFILIATION),
        failure=_REASON,
    )

    snapshot = capture.snapshot()
    assert len(first.samples) == 1
    assert len(snapshot.samples) == 2
    assert {sample.claim_type for sample in snapshot.samples} == {
        EvidenceClaimType.RESEARCH_INTEREST,
        EvidenceClaimType.CURRENT_AFFILIATION,
    }
    assert snapshot.samples[0] == first.samples[0]
    assert snapshot.excluded_count == 0


@pytest.mark.parametrize(
    "claim_type",
    [
        claim_type
        for claim_type in EvidenceClaimType
        if claim_type
        not in {EvidenceClaimType.CURRENT_AFFILIATION, EvidenceClaimType.RESEARCH_INTEREST}
    ],
)
def test_capture_ignores_other_claim_types(claim_type: EvidenceClaimType) -> None:
    status = (
        AvailabilityStatus.CONFIRMED_ACCEPTING
        if claim_type is EvidenceClaimType.AVAILABILITY
        else None
    )
    snapshot = _capture(
        _research_claim(claim_type=claim_type, availability_status=status)
    ).snapshot()

    assert snapshot.samples == ()
    assert snapshot.excluded_count == 0


@pytest.mark.parametrize(
    "reason",
    [
        reason
        for reason in GroundingFailureReason
        if reason
        not in {
            GroundingFailureReason.CONTEXT_CONFLICTING_PERSON,
            GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
        }
    ],
)
def test_capture_ignores_other_grounding_reasons(reason: GroundingFailureReason) -> None:
    snapshot = _capture(reason=reason).snapshot()

    assert snapshot.samples == ()
    assert snapshot.excluded_count == 0


@pytest.mark.parametrize(
    "reason",
    [
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON,
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
    ],
)
def test_snapshot_preserves_reason_and_has_only_explicit_replay_fields(
    reason: GroundingFailureReason,
) -> None:
    claim = _research_claim(
        claim="Private Candidate preferences and full generated claim prose.",
        evidence_id="private-evidence-id",
        supervisor_id="private-supervisor-id",
        subject_identity_evidence_id="private-linked-identity-id",
        asserted_institution="Private institutional detail",
        asserted_department="Private department detail",
        conflicting_evidence_ids=("private-conflict-id",),
    )
    snapshot = _capture(claim, reason=reason).snapshot()
    payload = snapshot.model_dump(mode="json")
    encoded = json.dumps(payload)

    assert set(payload) == {"schema_version", "origin", "samples", "excluded_count"}
    assert payload["schema_version"] == 1
    assert payload["origin"] == "synthetic_fixture"
    assert set(payload["samples"][0]) == _SAMPLE_FIELDS
    assert snapshot.samples[0].observed_reason is reason
    assert snapshot.samples[0].expected_name == _NAME
    assert snapshot.samples[0].asserted_name == claim.asserted_name
    assert str(snapshot.samples[0].source_url) == str(claim.source_url)
    assert snapshot.samples[0].source_kind is claim.source_kind
    assert "Private" not in encoded
    assert "private-" not in encoded
    assert "Candidate" not in encoded
    for discarded in (
        "claim",
        "evidence_id",
        "supervisor_id",
        "subject_identity_evidence_id",
        "retrieved_at",
        "confidence",
        "asserted_institution",
        "asserted_department",
        "conflicting_evidence_ids",
    ):
        assert discarded not in payload["samples"][0]


def test_capture_preserves_exact_excerpt_whitespace_and_unicode(tmp_path: Path) -> None:
    excerpt = "  Research overview:\n\tResearch interests: Dr Jane Smith’s safety work.\n  "
    capture = _capture(
        _claim(claim_type=EvidenceClaimType.RESEARCH_INTEREST, supporting_excerpt=excerpt)
    )
    path = write_private_replay(capture, project_root=tmp_path)
    assert path is not None

    assert capture.snapshot().samples[0].supporting_excerpt == excerpt
    assert read_private_replay(path).samples[0].supporting_excerpt == excerpt


@pytest.mark.parametrize("field", ["expected_name", "asserted_name", "supporting_excerpt"])
def test_capture_accepts_exact_limits_and_excludes_oversize_without_truncation(
    field: str,
) -> None:
    limit = 1200 if field == "supporting_excerpt" else 200
    accepted_value = "x" * limit
    rejected_value = accepted_value + "x"
    if field == "expected_name":
        accepted = _capture(expected_name=accepted_value).snapshot()
        rejected = _capture(expected_name=rejected_value).snapshot()
    else:
        accepted = _capture(_research_claim(**{field: accepted_value})).snapshot()
        rejected = _capture(_research_claim(**{field: rejected_value})).snapshot()

    assert getattr(accepted.samples[0], field) == accepted_value
    assert accepted.excluded_count == 0
    assert rejected.samples == ()
    assert rejected.excluded_count == 1


@pytest.mark.parametrize("field", ["expected_name", "asserted_name", "supporting_excerpt"])
@pytest.mark.parametrize(
    "sensitive",
    [
        "private-person@example.test",
        "OPENAI_API_KEY=synthetic-value-only",
        "api_key: synthetic-value-only",
        '{"api_key": "synthetic-value-only"}',
        "{'api_key': 'synthetic-value-only'}",
        "`api_key` = `synthetic-value-only`",
        '{"password": "synthetic-value-only"}',
        "{'password': 'synthetic-value-only'}",
        "`password` = `synthetic-value-only`",
        "-----BEGIN PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----",
        "-----BEGIN EC PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----",
        "-----BEGIN ENCRYPTED PRIVATE KEY-----",
        "Bearer synthetic-value-only",
        "sk-abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_sensitive_retained_text_is_excluded_without_printing(
    field: str,
    sensitive: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capture = (
        _capture(expected_name=sensitive)
        if field == "expected_name"
        else _capture(_research_claim(**{field: sensitive}))
    )
    snapshot = capture.snapshot()

    assert snapshot.samples == ()
    assert snapshot.excluded_count == 1
    assert sensitive not in repr(capture) + repr(snapshot) + snapshot.model_dump_json()
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize("field", ["asserted_name", "supporting_excerpt"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_retained_text_is_excluded(field: str, value: object) -> None:
    snapshot = _capture(
        _claim(claim_type=EvidenceClaimType.RESEARCH_INTEREST, **{field: value})
    ).snapshot()

    assert snapshot.samples == ()
    assert snapshot.excluded_count == 1


@pytest.mark.parametrize(
    "source_url",
    [
        "http://example.edu/people/alex-morgan",
        "https://private-user:private-password@example.edu/people/alex-morgan",
        "https://example.edu/people/alex-morgan?token=private-value",
        "https://example.edu/people/alex-morgan#private-fragment",
        "https://example.edu/people/private-person@example.test",
        "https://example.edu/people/sk-abcdefghijklmnopqrstuvwxyz123456",
    ],
)
def test_unsafe_url_is_excluded_without_rewriting(source_url: str) -> None:
    snapshot = _capture(_research_claim(source_url=HttpUrl(source_url))).snapshot()

    assert snapshot.samples == ()
    assert snapshot.excluded_count == 1


@pytest.mark.parametrize("source_kind", list(SourceKind))
def test_capture_accepts_only_official_profile_source_kinds(source_kind: SourceKind) -> None:
    snapshot = _capture(_research_claim(source_kind=source_kind)).snapshot()
    eligible = source_kind in {
        SourceKind.UNIVERSITY_PROFILE,
        SourceKind.INSTITUTIONAL_DIRECTORY,
    }

    assert len(snapshot.samples) == int(eligible)
    assert snapshot.excluded_count == int(not eligible)


def test_multibyte_sample_is_excluded_when_combined_file_would_exceed_byte_cap() -> None:
    name = "𐍈" * 200
    claim = _research_claim(
        asserted_name=name,
        supporting_excerpt="𐍈" * 1200,
        source_url=HttpUrl("https://example.edu/people/" + "x" * 1900),
    )
    capture = _capture(claim, expected_name=name)
    capture.observe(
        expected_name=name,
        claim=claim.model_copy(update={"claim_type": EvidenceClaimType.CURRENT_AFFILIATION}),
        failure=_REASON,
    )

    snapshot = capture.snapshot()
    assert len(snapshot.samples) == 1
    assert snapshot.excluded_count == 1
    assert snapshot.samples[0].supporting_excerpt == "𐍈" * 1200
    assert len(snapshot.model_dump_json(indent=2).encode("utf-8")) <= 16 * 1024


def test_an_excluded_sample_does_not_consume_the_claim_type_slot() -> None:
    capture = _capture(_research_claim(supporting_excerpt="x" * 1201))
    capture.observe(expected_name=_NAME, claim=_research_claim(), failure=_REASON)

    assert len(capture.snapshot().samples) == 1
    assert capture.snapshot().samples[0].supporting_excerpt == _EXCERPT
    assert capture.snapshot().excluded_count == 1


def test_private_capture_and_snapshot_repr_never_expose_retained_values() -> None:
    capture = _capture()
    snapshot = capture.snapshot()
    representation = repr(capture) + repr(snapshot) + repr(snapshot.samples[0])

    for value in (_NAME, _EXCERPT, "https://example.edu/people/alex-morgan"):
        assert value not in representation


def test_snapshot_and_sample_are_immutable() -> None:
    snapshot = _capture().snapshot()

    with pytest.raises(ValidationError):
        snapshot.excluded_count = 9
    with pytest.raises(ValidationError):
        snapshot.samples[0].supporting_excerpt = "Replacement excerpt."


@pytest.mark.parametrize(
    ("claim_type", "excerpt", "observed", "matches"),
    [
        (EvidenceClaimType.RESEARCH_INTEREST, _EXCERPT, _REASON, True),
        (
            EvidenceClaimType.RESEARCH_INTEREST,
            "Research interests of Jane Smith: secure systems.",
            _REASON,
            True,
        ),
        (
            EvidenceClaimType.RESEARCH_INTEREST,
            "Secure systems are a research topic.",
            GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
            True,
        ),
        (
            EvidenceClaimType.CURRENT_AFFILIATION,
            "Dr Jane Smith is a professor.",
            _REASON,
            True,
        ),
        (
            EvidenceClaimType.RESEARCH_INTEREST,
            "Research interests: secure systems.",
            GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
            False,
        ),
        (
            EvidenceClaimType.CURRENT_AFFILIATION,
            "Professor, Department of Computing, Example University.",
            GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
            False,
        ),
        (
            EvidenceClaimType.RESEARCH_INTEREST,
            "Secure systems are a research topic.",
            _REASON,
            False,
        ),
    ],
)
def test_replay_compares_observed_reason_with_current_domain_behavior(
    claim_type: EvidenceClaimType,
    excerpt: str,
    observed: GroundingFailureReason,
    matches: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot = _capture(
        _research_claim(claim_type=claim_type, supporting_excerpt=excerpt), reason=observed
    ).snapshot()
    before = snapshot.model_dump_json()

    first, second = replay_snapshot(snapshot), replay_snapshot(snapshot)

    assert first == second
    assert first.sample_count == 1
    assert first.matched_count == int(matches)
    assert first.changed_count == int(not matches)
    assert first.excluded_count == 0
    assert snapshot.model_dump_json() == before
    assert set(first.model_dump(mode="json")) == {
        "sample_count",
        "matched_count",
        "changed_count",
        "excluded_count",
    }
    assert _NAME not in repr(first) + first.model_dump_json()
    assert excerpt not in repr(first) + first.model_dump_json()
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_replay_preserves_excluded_count_without_fabricating_a_sample() -> None:
    summary = replay_snapshot(_capture(_research_claim(supporting_excerpt="x" * 1201)).snapshot())

    assert summary.sample_count == summary.matched_count == summary.changed_count == 0
    assert summary.excluded_count == 1


@pytest.mark.parametrize(
    ("excerpt", "family", "matched_text", "wrapper_removed", "prefix_recognized"),
    [
        (_EXCERPT, "titled_person", "Dr Jane Smith", False, True),
        (
            "Research interests of Jane Smith: secure systems.",
            "untitled_context_1",
            "Jane Smith",
            False,
            True,
        ),
        ("Research overview: I research secure systems.", None, None, True, True),
        ("Secure systems are a research topic.", None, None, False, False),
    ],
)
def test_private_details_explain_existing_matchers_without_stdout_or_repr_disclosure(
    excerpt: str,
    family: str | None,
    matched_text: str | None,
    wrapper_removed: bool,
    prefix_recognized: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot = _capture(_research_claim(supporting_excerpt=excerpt)).snapshot()
    before = snapshot.model_dump_json()

    first = replay_details(snapshot)

    assert first == replay_details(snapshot)
    assert len(first) == 1
    detail = first[0]
    assert detail.matcher_family == family
    assert detail.matched_text == matched_text
    assert detail.wrapper_removed is wrapper_removed
    assert detail.prefix_recognized is prefix_recognized
    assert len(detail.normalized_prefix) <= 160
    assert excerpt not in repr(detail)
    if matched_text is not None:
        assert matched_text not in repr(detail)
    assert snapshot.model_dump_json() == before
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_private_storage_round_trip_uses_restricted_directory_and_file_modes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = _write_capture(tmp_path)

    assert path.parent == tmp_path / "artifacts" / "grounding-replays"
    assert path.suffix == ".json"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert read_private_replay(path) == _capture().snapshot()
    assert path.stat().st_size <= 16 * 1024
    output = capsys.readouterr()
    assert output.out == output.err == ""


def test_independent_writes_use_different_names_and_preserve_the_first_file(tmp_path: Path) -> None:
    first = _write_capture(tmp_path)
    original = first.read_bytes()
    second = _write_capture(tmp_path)

    assert first != second
    assert first.read_bytes() == original
    assert first.read_bytes() == second.read_bytes()


def test_existing_artifacts_permissions_are_preserved_and_replay_directory_is_private(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    private_directory = artifacts / "grounding-replays"
    private_directory.mkdir(parents=True)
    artifacts.chmod(0o755)
    private_directory.chmod(0o755)

    path = _write_capture(tmp_path)

    assert stat.S_IMODE(artifacts.stat().st_mode) == 0o755
    assert stat.S_IMODE(private_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_writer_revalidates_a_snapshot_created_by_unsafe_model_copy(tmp_path: Path) -> None:
    capture = _capture()
    snapshot = capture.snapshot()
    unsafe_sample = snapshot.samples[0].model_copy(
        update={"supporting_excerpt": "private-person@example.test"}
    )
    capture._snapshot = snapshot.model_copy(update={"samples": (unsafe_sample,)})

    with pytest.raises(PrivateReplayError):
        write_private_replay(capture, project_root=tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_exclusive_creation_never_overwrites_a_colliding_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        replay_module, "uuid4", lambda: UUID("2273a4a9-9e7c-4ffc-9ab3-218f4d0e531c")
    )
    path = _write_capture(tmp_path)
    original = path.read_bytes()

    with pytest.raises(PrivateReplayError):
        _write_capture(tmp_path)

    assert path.read_bytes() == original
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("excluded", [False, True])
def test_empty_capture_does_not_create_files_or_directories(tmp_path: Path, excluded: bool) -> None:
    capture = (
        _capture(_research_claim(supporting_excerpt="x" * 1201))
        if excluded
        else RejectedExcerptCapture(origin="synthetic_fixture")
    )

    assert write_private_replay(capture, project_root=tmp_path) is None
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("symlink_component", ["root", "artifacts", "grounding-replays"])
def test_storage_rejects_a_symlink_in_any_destination_component(
    tmp_path: Path,
    symlink_component: str,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    project = tmp_path / "project"
    if symlink_component == "root":
        project.symlink_to(outside, target_is_directory=True)
    else:
        project.mkdir()
        link = project / "artifacts"
        if symlink_component == "grounding-replays":
            link.mkdir()
            link = link / "grounding-replays"
        link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PrivateReplayError):
        _write_capture(project)

    assert list(outside.iterdir()) == []


def test_storage_rejects_a_file_where_the_private_directory_should_be(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    conflicting = artifacts / "grounding-replays"
    conflicting.write_text("Existing user content", encoding="utf-8")

    with pytest.raises(PrivateReplayError):
        _write_capture(tmp_path)

    assert conflicting.read_text(encoding="utf-8") == "Existing user content"


@pytest.mark.parametrize("symlink_component", ["file", "parent"])
def test_reader_rejects_symlink_file_and_parent(tmp_path: Path, symlink_component: str) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original = _write_capture(project)
    if symlink_component == "file":
        replay_path = tmp_path / "linked.json"
        replay_path.symlink_to(original)
    else:
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(original.parent, target_is_directory=True)
        replay_path = linked_parent / original.name

    with pytest.raises(PrivateReplayError):
        read_private_replay(replay_path)


def test_reader_rejects_files_over_sixteen_kibibytes(tmp_path: Path) -> None:
    path = _write_capture(tmp_path)
    payload = path.read_bytes()
    path.write_bytes(payload + b" " * (16 * 1024 + 1 - len(payload)))

    with pytest.raises(PrivateReplayError):
        read_private_replay(path)


@pytest.mark.parametrize("payload", [b"", b"{broken", b"\xff\xfe", b"[]", b"null"])
def test_reader_rejects_corrupt_or_non_snapshot_payloads(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "corrupt.json"
    path.write_bytes(payload)

    with pytest.raises(PrivateReplayError):
        read_private_replay(path)


@pytest.mark.parametrize("location", ["snapshot", "sample"])
def test_unknown_fields_fail_closed_without_disclosing_their_content(
    tmp_path: Path,
    location: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = "private-person@example.test undisclosed Candidate preferences"
    payload = _capture().snapshot().model_dump(mode="json")
    target = payload if location == "snapshot" else payload["samples"][0]
    target["unexpected_private_payload"] = private
    path = tmp_path / "unknown-fields.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PrivateReplayError) as error:
        read_private_replay(path)

    assert private not in str(error.value) + repr(error.value)
    assert private not in "".join(traceback.format_exception(error.value))
    output = capsys.readouterr()
    assert output.out == output.err == ""


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "too_many", "invalid_reason", "invalid_type", "invalid_source_kind"],
)
def test_read_schema_rejects_out_of_scope_or_unbounded_samples(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = _capture().snapshot().model_dump(mode="json")
    samples = payload["samples"]
    if mutation == "duplicate":
        samples.append(dict(samples[0]))
    elif mutation == "too_many":
        samples.extend([dict(samples[0]), dict(samples[0])])
    elif mutation == "invalid_reason":
        samples[0]["observed_reason"] = "context_identity_not_found"
    elif mutation == "invalid_type":
        samples[0]["claim_type"] = "identity"
    else:
        samples[0]["source_kind"] = "other"
    path = tmp_path / "invalid-schema.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PrivateReplayError):
        read_private_replay(path)


def test_schema_validation_errors_hide_retained_input_values() -> None:
    private = "private-person@example.test"
    payload = _capture().snapshot().model_dump(mode="json")
    payload["samples"][0]["supporting_excerpt"] = private

    with pytest.raises(ValidationError) as error:
        GroundingReplaySnapshot.model_validate(payload)

    assert private not in str(error.value) + repr(error.value)
