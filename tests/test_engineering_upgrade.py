import pytest

from clinical_intel.extract import extract
from clinical_intel.provenance import extract_with_provenance


@pytest.mark.parametrize("value", ["12.5", "12 people", "1e3"])
def test_participants_are_not_silently_truncated(value):
    with pytest.raises(ValueError):
        extract("Study ID: X\nParticipants: " + value)


def test_empty_fields_do_not_capture_next_line():
    result = extract_with_provenance("Study ID: X\nIntervention: \nPrimary Endpoint: Survival")
    assert result.record.intervention is None
    assert result.record.primary_endpoint == "Survival"
    assert all(e.field != "intervention" for e in result.evidence)
