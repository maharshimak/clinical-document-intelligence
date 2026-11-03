"""Evidence invariants, schema validation and append-only review history."""

import copy

import pytest

from clinical_intel.document import DocumentVersionError, SourceDocument
from clinical_intel.evidence import (
    DocumentExtraction,
    EvidenceError,
    EvidenceSpan,
    ExtractedField,
    extract_document,
    from_model_result,
    value_supported_by,
)
from clinical_intel.export import export_review
from clinical_intel.extract import FIELDS, StudyRecord
from clinical_intel.model_extract import ModelExtractionResult, ModelFieldEvidence
from clinical_intel.review_log import ReviewHistoryError, ReviewLog
from clinical_intel.schema import FIELD_SPECS, validate_field

SHARP_S = chr(0xDF)
TEXT = (
    "Study ID: SYN-77\n"
    "Phase: III\n"
    "Participants: 120\n"
    "Intervention: Example compound\n"
    "Primary Endpoint: Synthetic score at week 12\n"
    "Notes: corrected enrolment was 210 participants\n"
)


@pytest.fixture()
def document() -> SourceDocument:
    return SourceDocument.from_text(TEXT)


@pytest.fixture()
def log(document: SourceDocument) -> ReviewLog:
    return ReviewLog.from_extraction(extract_document(document))


# -- field invariants ---------------------------------------------------------------------


def test_schema_covers_every_field() -> None:
    assert set(FIELD_SPECS) == set(FIELDS)


def test_machine_field_without_evidence_is_rejected() -> None:
    with pytest.raises(EvidenceError, match="requires evidence"):
        ExtractedField("study_id", "X", "rule_based", None)
    with pytest.raises(EvidenceError, match="requires evidence"):
        ExtractedField("study_id", "X", "model", None)


def test_human_field_may_omit_evidence_but_null_cannot_carry_it() -> None:
    assert ExtractedField("study_id", "X", "human", None, None, "human_asserted").evidence is None
    with pytest.raises(EvidenceError, match="null field"):
        ExtractedField("study_id", None, "rule_based", EvidenceSpan(0, 1, "S"))


@pytest.mark.parametrize(
    ("origin", "confidence", "confidence_origin"),
    [
        ("rule_based", 0.9, "not_estimated"),
        ("rule_based", None, "model_self_reported"),
        ("human", None, "not_estimated"),
        ("model", 0.9, "not_estimated"),
        ("model", 1.5, "model_self_reported"),
        ("model", True, "model_self_reported"),
    ],
)
def test_confidence_must_state_a_consistent_origin(origin, confidence, confidence_origin) -> None:
    with pytest.raises(ValueError):
        ExtractedField(
            "study_id", "S", origin, EvidenceSpan(0, 1, "S"), confidence, confidence_origin
        )


def test_model_confidence_is_labelled_self_reported() -> None:
    item = ExtractedField(
        "study_id", "S", "model", EvidenceSpan(0, 1, "S"), 0.7, "model_self_reported"
    )
    assert item.to_dict()["confidence_origin"] == "model_self_reported"


def test_rule_based_extraction_never_invents_confidence(document: SourceDocument) -> None:
    for item in extract_document(document).fields:
        assert item.confidence is None
        assert item.confidence_origin == "not_estimated"


@pytest.mark.parametrize("span", [(-1, 2), (3, 3), (5, 2), (0, 10_000), (True, 2)])
def test_span_bounds_are_enforced(document: SourceDocument, span) -> None:
    with pytest.raises(EvidenceError):
        EvidenceSpan.from_source(document.text, *span)


def test_span_verification_detects_wrong_text(document: SourceDocument) -> None:
    with pytest.raises(EvidenceError, match="does not match"):
        EvidenceSpan(0, 5, "Phase").verify(document.text)


def test_model_result_with_shifted_offsets_is_rejected() -> None:
    # Offsets computed on case-folded text are shifted by the sharp-s -> "ss" expansion.
    source = f"Stra{SHARP_S}e. Protocol ABC-1."
    rows = [ModelFieldEvidence(name, None, None, None, None) for name in FIELDS[1:]]
    shifted = source.casefold().find("abc-1")
    assert shifted != source.index("ABC-1")
    bad = ModelFieldEvidence("study_id", "ABC-1", "ABC-1", shifted, shifted + 5)
    record = StudyRecord("ABC-1", None, None, None, None)
    document = SourceDocument.from_text(source)
    with pytest.raises(EvidenceError):
        from_model_result(document, ModelExtractionResult(record, (bad, *rows), (), 1))
    start = source.index("ABC-1")
    good = ModelFieldEvidence("study_id", "ABC-1", "ABC-1", start, start + 5)
    extraction = from_model_result(document, ModelExtractionResult(record, (good, *rows), (), 1))
    assert extraction.field("study_id").evidence.text == "ABC-1"
    assert extraction.field("study_id").origin == "model"


# -- schema validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", "5"),
        ("phase", 3),
        ("participants", 0),
        ("participants", True),
        ("participants", "120"),
        ("study_id", "bad id with spaces"),
        ("study_id", " X"),
        ("intervention", ""),
        ("intervention", "drug" + chr(0)),
        ("sponsor", "x" * 201),
        ("unknown_field", "x"),
    ],
)
def test_schema_rejects_invalid_values(field, value) -> None:
    assert validate_field(field, value)


@pytest.mark.parametrize(
    ("field", "value"),
    [("phase", "2"), ("participants", 1), ("study_id", "NCT-01/2.3"), ("condition", None)],
)
def test_schema_accepts_valid_values(field, value) -> None:
    assert validate_field(field, value) == []


# -- extraction issues ----------------------------------------------------------------------


def test_conflicting_labels_and_unparseable_values_are_reported_not_raised() -> None:
    text = "Study ID: A-1\nParticipants: about 40\nStudy ID: B-2\n"
    extraction = extract_document(SourceDocument.from_text(text))
    assert extraction.field("study_id").value == "A-1"
    assert extraction.field("participants").value is None
    codes = {(issue.field, issue.code) for issue in extraction.issues}
    assert codes == {("study_id", "CONFLICTING_VALUES"), ("participants", "UNPARSEABLE_VALUE")}
    conflict = next(i for i in extraction.issues if i.code == "CONFLICTING_VALUES")
    assert text[conflict.span[0] : conflict.span[1]] == "B-2"
    assert extraction.requires_review


def test_extraction_must_list_every_field_in_order() -> None:
    with pytest.raises(ValueError, match="every schema field"):
        DocumentExtraction("0" * 64, "x", ())


# -- review history -------------------------------------------------------------------------


def test_correction_does_not_inherit_prediction_citation(document, log) -> None:
    predicted = log.current_fields()["participants"]
    assert predicted.evidence is not None and predicted.value == 120
    corrected = log.correct(document, "participants", 210, reviewer="rev-1", reason="typo")
    item = corrected.current_fields()["participants"]
    assert item.value == 210
    assert item.origin == "human"
    assert item.evidence is None
    assert item.confidence_origin == "human_asserted"


def test_correction_cannot_reuse_the_wrong_citation(document, log) -> None:
    old = log.current_fields()["participants"].evidence
    with pytest.raises(EvidenceError, match="does not support"):
        log.correct(
            document, "participants", 210, reviewer="rev-1", reason="typo",
            evidence=(old.start, old.end),
        )


def test_correction_with_supporting_citation_is_verified(document, log) -> None:
    start = TEXT.index("210 participants")
    corrected = log.correct(
        document, "participants", 210, reviewer="rev-1", reason="see notes",
        evidence=(start, start + 16),
    )
    item = corrected.current_fields()["participants"]
    assert item.evidence.text == "210 participants"
    assert TEXT[item.evidence.start : item.evidence.end] == item.evidence.text


def test_corrections_are_validated_against_the_schema(document, log) -> None:
    with pytest.raises(ValueError, match="phase"):
        log.correct(document, "phase", "7", reviewer="rev-1", reason="x")
    with pytest.raises(ValueError, match="reviewer"):
        log.correct(document, "phase", "2", reviewer=" ", reason="x")


def test_history_is_append_only_and_original_prediction_is_kept(document, log) -> None:
    corrected = log.correct(document, "phase", "2", reviewer="rev-1", reason="x")
    confirmed = corrected.confirm("study_id", reviewer="rev-2")
    assert confirmed.events[: len(log.events)] == log.events
    assert confirmed.events[: len(corrected.events)] == corrected.events
    assert len(log.events) == len(FIELDS)  # the original log object is unchanged
    phase_events = [e for e in confirmed.events if e.field == "phase"]
    assert [(e.kind, e.value) for e in phase_events] == [("extraction", "3"), ("correction", "2")]
    status = confirmed.review_status()
    assert status["phase"] == "corrected"
    assert status["study_id"] == "confirmed"
    assert status["sponsor"] == "unreviewed"


def test_correction_bound_to_another_document_version_is_rejected(log) -> None:
    other = SourceDocument.from_text(TEXT.replace("120", "121"))
    with pytest.raises(DocumentVersionError):
        log.correct(other, "phase", "2", reviewer="rev-1", reason="x")


def test_serialized_history_round_trips(document, log) -> None:
    updated = log.correct(
        document, "phase", "2", reviewer="rev-1", reason="x", recorded_at="2026-11-03T10:00:00Z"
    )
    assert ReviewLog.from_events(document, updated.to_events()) == updated


@pytest.mark.parametrize(
    "tamper",
    [
        lambda events: events[-1].__setitem__("value", "4"),
        lambda events: events.pop(3),
        lambda events: events[2].__setitem__("evidence", {"start": 0, "end": 3, "text": "Stu"}),
        lambda events: events[-1].__setitem__("origin", "rule_based"),
        lambda events: events.__setitem__(slice(0, 2), [events[1], events[0]]),
        lambda events: events[0].__setitem__("extra", 1),
    ],
)
def test_tampered_history_is_rejected(document, log, tamper) -> None:
    events = copy.deepcopy(
        log.correct(document, "phase", "2", reviewer="rev-1", reason="x").to_events()
    )
    tamper(events)
    with pytest.raises(ReviewHistoryError):
        ReviewLog.from_events(document, events)


def test_forged_citation_is_rejected_before_hash_check(document, log) -> None:
    # A span must reproduce the document text regardless of the hash chain.
    events = copy.deepcopy(log.to_events())
    events[0]["evidence"] = {"start": 10, "end": 16, "text": "FORGED"}
    with pytest.raises(ReviewHistoryError, match="invalid"):
        ReviewLog.from_events(document, events)


def test_history_for_another_document_is_rejected(log) -> None:
    other = SourceDocument.from_text(TEXT + " ")
    with pytest.raises(DocumentVersionError):
        ReviewLog.from_events(other, log.to_events())


def test_value_support_uses_whole_tokens() -> None:
    assert value_supported_by("phase", "1", "Phase I")
    assert not value_supported_by("phase", "1", "Phase III")
    assert not value_supported_by("phase", "1", "Phase 1.5")
    assert value_supported_by("participants", 1250, "1,250 enrolled")
    assert not value_supported_by("participants", 12, "120 enrolled")
    assert value_supported_by("intervention", "Drug A", "given drug a daily")
    assert not value_supported_by("intervention", "Drug A", "Drug AB")


# -- export ---------------------------------------------------------------------------------


def test_export_reports_review_state_and_history(document, log) -> None:
    corrected = log.correct(document, "phase", "2", reviewer="r", reason="x")
    exported = export_review(document, corrected)
    assert exported["document"]["sha256"] == document.sha256
    assert exported["document"]["offset_unit"] == "unicode_code_point"
    fields = {row["field"]: row for row in exported["fields"]}
    assert fields["phase"]["review_status"] == "corrected"
    assert fields["phase"]["evidence"] is None
    assert fields["study_id"]["evidence"]["text"] == "SYN-77"
    assert exported["history_head"] == exported["history"][-1]["event_hash"]
    assert exported["requires_review"] is False


def test_export_keeps_unreviewed_conflicts_in_review() -> None:
    document = SourceDocument.from_text(
        "Study ID: A-1\nStudy ID: B-2\nPhase: 2\nParticipants: 9\nPrimary Endpoint: S\n"
    )
    extraction = extract_document(document)
    log = ReviewLog.from_extraction(extraction)
    assert export_review(document, log, issues=extraction.issues)["requires_review"] is True
    confirmed = log.confirm("study_id", reviewer="rev-1")
    assert export_review(document, confirmed, issues=extraction.issues)["requires_review"] is False
