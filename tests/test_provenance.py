import pytest

from clinical_intel.provenance import extract_with_provenance


def test_extraction_provenance_captures_source_spans() -> None:
    text = (
        "Study ID: ABC-12\n"
        "Phase: II\n"
        "Participants: 120\n"
        "Intervention: Drug A\n"
        "Primary endpoint: Overall survival\n"
    )

    result = extract_with_provenance(text)

    assert result.record.study_id == "ABC-12"
    assert result.record.phase == "2"
    assert result.evidence_coverage == 1.0
    assert result.schema_coverage == 1.0

    phase = next(item for item in result.evidence if item.field == "phase")
    assert phase.raw_value == "II"
    assert phase.normalized_value == "2"
    assert text[phase.start : phase.end] == "II"


def test_provenance_reports_partial_schema_coverage() -> None:
    result = extract_with_provenance("Study ID: X-1\nParticipants: 10")

    assert result.schema_coverage == pytest.approx(0.4)
    assert result.evidence_coverage == 1.0


def test_provenance_rejects_non_text_input() -> None:
    with pytest.raises(TypeError, match="text"):
        extract_with_provenance(123)  # type: ignore[arg-type]
