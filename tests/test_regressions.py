from clinical_intel.extract import extract, validate


def test_normalize_roman_phase_and_reject_invalid_fields():
    assert extract("Study ID: SYN-1\nPhase: III").phase == "3"
    record = extract("Study ID: SYN-2\nPhase: 12\nParticipants: -4")
    assert record.phase == "12" and record.participants == -4
    assert len(validate(record)) == 2
