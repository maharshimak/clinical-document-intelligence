import json

import pytest

from clinical_intel.model_extract import OpenAICompatibleClinicalExtractor


def parse_field(source, field, value, evidence):
    return OpenAICompatibleClinicalExtractor("http://localhost", "unused").parse(
        source, json.dumps({"fields": {field: {"value": value, "evidence": evidence}}})
    )


def test_evidence_offsets_reference_original_unicode_source():
    source = "Straße. Protocol ABC-1."
    result = parse_field(source, "study_id", "ABC-1", "ABC-1")
    evidence = next(item for item in result.evidence if item.field == "study_id")
    assert source[evidence.start:evidence.end] == evidence.evidence
    assert evidence.start == source.index("ABC-1")


def test_evidence_must_be_verbatim_including_case():
    with pytest.raises(ValueError, match="not present"):
        parse_field("Protocol ABC-1.", "study_id", "ABC-1", "abc-1")


@pytest.mark.parametrize("value,evidence", [("I", "Phase III"), ("II", "Phase III"),
                                           ("1", "Phase 10"), ("IV", "Phase IVa"),
                                           ("1", "Phase 1.5")])
def test_phase_evidence_cannot_ground_a_prefix(value, evidence):
    with pytest.raises(ValueError, match="phase value is not supported"):
        parse_field(evidence, "phase", value, evidence)


@pytest.mark.parametrize("value,evidence", [("III", "Phase III"), ("3", "Phase 3."),
                                           ("II", "PHASE\tII trial")])
def test_complete_phase_tokens_are_supported(value, evidence):
    result = parse_field(evidence, "phase", value, evidence)
    assert result.record.phase in {"2", "3"}
