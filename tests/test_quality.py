import pytest

from clinical_intel.extract import StudyRecord
from clinical_intel.quality import assess_extraction, record_fingerprint


def test_complete_valid_record_is_production_ready() -> None:
    record = StudyRecord("STUDY-42", "3", 120, "Drug A", "Overall response")
    report = assess_extraction(record)
    assert report.production_ready is True
    assert report.completeness == pytest.approx(1.0)
    assert report.missing_fields == ()
    assert report.record_fingerprint == record_fingerprint(record)


def test_missing_identity_and_low_completeness_fail_quality_gate() -> None:
    record = StudyRecord(None, "2", None, None, "Safety")
    report = assess_extraction(record, min_completeness=0.8)
    assert report.production_ready is False
    assert "study_id missing" in report.validation_errors
    assert set(report.missing_fields) == {"study_id", "participants", "intervention"}
