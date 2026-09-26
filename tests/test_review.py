from clinical_intel.extract import StudyRecord
from clinical_intel.review import FieldEvidence, review_gate


def valid_record() -> StudyRecord:
    return StudyRecord(
        study_id="NCT-1",
        phase="3",
        participants=120,
        intervention="Drug A",
        primary_endpoint="Overall survival",
    )


def test_review_gate_accepts_grounded_high_confidence_record():
    evidence = [
        FieldEvidence("study_id", 0.99, "Study ID: NCT-1"),
        FieldEvidence("phase", 0.95, "Phase: III"),
        FieldEvidence("participants", 0.93, "Participants: 120"),
        FieldEvidence("primary_endpoint", 0.91, "Primary endpoint: Overall survival"),
    ]
    decision = review_gate(valid_record(), evidence)
    assert not decision.requires_review


def test_review_gate_routes_low_confidence_to_human():
    evidence = [
        FieldEvidence("study_id", 0.99, "Study ID: NCT-1"),
        FieldEvidence("phase", 0.4, "Phase: III?"),
        FieldEvidence("participants", 0.93, "Participants: 120"),
        FieldEvidence("primary_endpoint", 0.91, "Primary endpoint: Overall survival"),
    ]
    decision = review_gate(valid_record(), evidence)
    assert decision.requires_review
    assert any("low confidence for phase" in reason for reason in decision.reasons)
