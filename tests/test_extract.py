from clinical_intel.extract import extract, validate

SYNTHETIC = """Study ID: DEMO-101
Phase: 2
Participants: 120
Intervention: Example compound
Primary Endpoint: Change in synthetic score at week 12
"""


def test_extract_synthetic_document() -> None:
    record = extract(SYNTHETIC)
    assert record.study_id == "DEMO-101"
    assert record.participants == 120
    assert validate(record) == []
